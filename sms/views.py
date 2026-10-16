import datetime
import logging
import re
from django.conf import settings
from django.db.models import Q, Max
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from student.models import Student, StudentAttendance, FacultyActivity
from users.models import User as StandardUser
from common.signals import send_targeted_broadcast
from .models import SMSLog
from .serializers import (
    SMSLogSerializer,
    FullDayAbsenteeStudentSerializer,
    SendFullDayAbsentSMSRequestSerializer,
    AfternoonAbsenteeStudentSerializer,
    SendAfternoonAbsentSMSRequestSerializer,
    FeesPendingStudentSerializer,
    SendFeesPendingSMSRequestSerializer,
    MarksStudentSerializer,
    SendMarksSMSRequestSerializer,
)
from .services import (
    get_student_sms_info,
    send_full_day_absent_sms_to_student,
    send_afternoon_absent_sms_to_student,
    send_fees_pending_sms_to_student,
    format_fees_pending_message,
    send_marks_sms_to_student,
    format_marks_message,
    get_dial4sms_balance,
)

logger = logging.getLogger(__name__)


class FullDayAbsenteesListView(APIView):
    """
    Returns the list of full day absentee students for a given date.
    Calculates students marked 'AB' across periods on the specified date.
    Also retrieves the latest SMS log status for that date.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            target_date = datetime.date.today()
            date_str = target_date.strftime('%Y-%m-%d')
        else:
            try:
                target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    "code": 400,
                    "message": "Invalid date format. Expected YYYY-MM-DD."
                }, status=status.HTTP_400_BAD_REQUEST)

        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')
        search_query = request.query_params.get('search', '').strip()

        # 1. Fetch attendance records for the target date
        activities_qs = FacultyActivity.objects.filter(date=target_date).select_related(
            'timetable', 'timetable__period', 'timetable__period__session'
        )
        if department_id:
            activities_qs = activities_qs.filter(timetable__department_id=department_id)
        if batch_id:
            activities_qs = activities_qs.filter(timetable__batch_id=batch_id)
        if section_id:
            activities_qs = activities_qs.filter(timetable__section_id=section_id)

        all_activities = list(activities_qs)

        # Separate FN 1st period activities (Period 1 or earliest FN period)
        fn_first_period_activity_ids = []
        fn_all_activity_ids = []

        for act in all_activities:
            tt = getattr(act, 'timetable', None)
            period = getattr(tt, 'period', None) if tt else None
            session = getattr(period, 'session', None) if period else None
            session_name = (getattr(session, 'session_name', '') or '').upper()
            p_no = getattr(period, 'period_no', 0) if period else 0

            if session_name == 'FN' or (p_no and p_no <= 4):
                fn_all_activity_ids.append(act.id)
                # FN 1st period is period_no 1 (or lowest FN period)
                if p_no == 1:
                    fn_first_period_activity_ids.append(act.id)

        # Fallback if no specific period 1 exists: use all FN activities
        if not fn_first_period_activity_ids:
            fn_first_period_activity_ids = fn_all_activity_ids

        # Query attendances for FN 1st period where status is 'AB'
        fn_absent_attendances = StudentAttendance.objects.filter(
            faculty_activity_id__in=fn_first_period_activity_ids,
            status='AB'
        ).select_related(
            'student',
            'student__department',
            'student__batch',
            'student__section',
            'student__application',
            'student__application__candidate',
            'faculty_activity',
            'faculty_activity__timetable',
            'faculty_activity__timetable__period'
        )

        fn_absent_map = {}
        for att in fn_absent_attendances:
            sid = att.student_id
            p_no = 1
            try:
                p_no = att.faculty_activity.timetable.period.period_no
            except Exception:
                p_no = 1

            if sid not in fn_absent_map:
                fn_absent_map[sid] = {
                    'student': att.student,
                    'period_no': p_no
                }

        absentee_student_ids = list(fn_absent_map.keys())

        # Pre-fetch SMS Logs for this date to display SMS status
        sms_logs = SMSLog.objects.filter(
            sent_date=target_date,
            sms_type='FULL_DAY_ABSENT'
        ).order_by('student_id', '-created_at')

        latest_sms_map = {}
        for log in sms_logs:
            if log.student_id and log.student_id not in latest_sms_map:
                latest_sms_map[log.student_id] = log

        # If no activity records exist on date or for testing, also support returning students matching filters
        results = []
        if absentee_student_ids:
            students_qs = Student.objects.filter(id__in=absentee_student_ids).select_related(
                'department', 'batch', 'section', 'application', 'application__candidate'
            )
            if search_query:
                students_qs = students_qs.filter(
                    Q(student_name__icontains=search_query) |
                    Q(register_number__icontains=search_query) |
                    Q(roll_number__icontains=search_query) |
                    Q(application__candidate__name__icontains=search_query) |
                    Q(application__candidate__phone_number__icontains=search_query)
                )

            for st in students_qs:
                info = get_student_sms_info(st)
                fn_item = fn_absent_map.get(st.id, {})
                sms_log = latest_sms_map.get(st.id)

                sms_status = 'NOT_SENT'
                sms_sent_at = None
                sms_log_id = None
                sms_response = None

                if sms_log:
                    sms_status = sms_log.status
                    sms_sent_at = sms_log.created_at
                    sms_log_id = sms_log.id
                    sms_response = sms_log.gateway_response

                results.append({
                    'student_id': st.id,
                    'student_name': info['student_name'],
                    'register_number': info['register_number'],
                    'roll_number': info['roll_number'],
                    'department_id': info['department_id'],
                    'department_name': info['department_name'],
                    'batch_id': info['batch_id'],
                    'batch_name': info['batch_name'],
                    'section_id': info['section_id'],
                    'section_name': info['section_name'],
                    'student_mobile': info['student_mobile'],
                    'parent_mobile': info['parent_mobile'],
                    'parent_name': info['parent_name'],
                    'fn_period_no': fn_item.get('period_no', 1),
                    'absent_periods_count': 1,
                    'total_periods_count': 1,
                    'sms_status': sms_status,
                    'sms_sent_at': sms_sent_at,
                    'sms_log_id': sms_log_id,
                    'sms_response': sms_response
                })

        # Calculate statistics
        total_absentees = len(results)
        sent_count = sum(1 for r in results if r['sms_status'] == 'SUCCESS')
        failed_count = sum(1 for r in results if r['sms_status'] == 'FAILED')
        pending_count = sum(1 for r in results if r['sms_status'] in ['NOT_SENT', 'PENDING'])

        return Response({
            "code": 200,
            "message": "Full day absentees retrieved successfully",
            "date": date_str,
            "stats": {
                "total_absentees": total_absentees,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "pending_count": pending_count
            },
            "data": results
        }, status=status.HTTP_200_OK)


class SendFullDayAbsentSMSView(APIView):
    """
    Sends Full Day Absent SMS to selected students / parents and logs the gateway responses.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SendFullDayAbsentSMSRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Invalid payload",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        target_date = serializer.validated_data['date']
        student_ids = serializer.validated_data['student_ids']
        recipient_type = serializer.validated_data.get('recipient_type', 'PARENT')

        user = request.user
        tracking_user = user if isinstance(user, StandardUser) else None

        students = Student.objects.filter(id__in=student_ids).select_related(
            'department', 'batch', 'section', 'application', 'application__candidate'
        )

        results = []
        success_count = 0
        failed_count = 0
        task_id = request.data.get('task_id')
        total_count = len(students)

        for idx, student in enumerate(students, start=1):
            # Check if SMS is already sent and locked for this student on this date
            if SMSLog.objects.filter(student=student, sent_date=target_date, sms_type='FULL_DAY_ABSENT', status='SUCCESS').exists():
                results.append({
                    'student_id': student.id,
                    'student_name': student.name,
                    'status': 'ALREADY_SENT',
                    'error': 'SMS is already sent and locked for this date.'
                })
                continue

            try:
                res = send_full_day_absent_sms_to_student(
                    student=student,
                    absent_date=target_date,
                    user=tracking_user,
                    recipient_type=recipient_type
                )
                if res['status'] == 'SUCCESS':
                    success_count += 1
                else:
                    failed_count += 1
                results.append(res)
            except Exception as e:
                logger.error(f"Error sending SMS for student {student.id}: {str(e)}")
                failed_count += 1
                results.append({
                    'student_id': student.id,
                    'student_name': student.name,
                    'status': 'FAILED',
                    'error': str(e)
                })

            if task_id and (idx % 2 == 0 or idx == total_count):
                send_targeted_broadcast(f'task_{task_id}', {
                    'type': 'sms_progress',
                    'task_id': task_id,
                    'progress': round((idx / total_count) * 100) if total_count else 100,
                    'processed': idx,
                    'total': total_count,
                    'success': success_count,
                    'failed': failed_count,
                    'status': f'Sending {idx} of {total_count} absentee alerts...'
                })

        already_sent_count = sum(1 for r in results if r['status'] == 'ALREADY_SENT')
        return Response({
            "code": 200,
            "message": f"Processed SMS for {len(results)} students ({success_count} succeeded, {failed_count} failed, {already_sent_count} locked/already sent).",
            "data": {
                "total": len(results),
                "success_count": success_count,
                "failed_count": failed_count,
                "already_sent_count": already_sent_count,
                "results": results
            }
        }, status=status.HTTP_200_OK)


class AfternoonAbsenteesListView(APIView):
    """
    Returns the list of Afternoon (AN) absentee students for a given date.
    Condition: Student is marked 'AB' in the first period of AN session (e.g. Period 5),
    AND was NOT absent in the morning (FN session).
    If the student was absent in the FN session, they are excluded from the Afternoon list.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            target_date = datetime.date.today()
            date_str = target_date.strftime('%Y-%m-%d')
        else:
            try:
                target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    "code": 400,
                    "message": "Invalid date format. Expected YYYY-MM-DD."
                }, status=status.HTTP_400_BAD_REQUEST)

        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')
        search_query = request.query_params.get('search', '').strip()

        # 1. Fetch activities for the target date
        activities_qs = FacultyActivity.objects.filter(date=target_date).select_related(
            'timetable', 'timetable__period', 'timetable__period__session'
        )
        if department_id:
            activities_qs = activities_qs.filter(timetable__department_id=department_id)
        if batch_id:
            activities_qs = activities_qs.filter(timetable__batch_id=batch_id)
        if section_id:
            activities_qs = activities_qs.filter(timetable__section_id=section_id)

        all_activities = list(activities_qs)

        # Separate FN vs AN activities
        fn_activity_ids = []
        an_first_period_activity_ids = []
        an_all_activity_ids = []

        # Find AN minimum period number for each timetable/class or default 5
        for act in all_activities:
            tt = getattr(act, 'timetable', None)
            period = getattr(tt, 'period', None) if tt else None
            session = getattr(period, 'session', None) if period else None
            session_name = (getattr(session, 'session_name', '') or '').upper()
            p_no = getattr(period, 'period_no', 0) if period else 0

            if session_name == 'FN' or (p_no and p_no <= 4):
                fn_activity_ids.append(act.id)
            elif session_name == 'AN' or (p_no and p_no >= 5):
                an_all_activity_ids.append(act.id)
                # First period of AN is period_no 5 or lowest AN period
                if p_no == 5 or (p_no and p_no >= 5):
                    an_first_period_activity_ids.append(act.id)

        # Fallback: if no specific period is 5, use all AN activities
        if not an_first_period_activity_ids:
            an_first_period_activity_ids = an_all_activity_ids

        # 2. Find students absent in Forenoon (FN)
        # Any student marked 'AB' in FN MUST BE EXCLUDED from the Afternoon SMS list
        fn_absent_student_ids = set()
        if fn_activity_ids:
            fn_absent_student_ids = set(
                StudentAttendance.objects.filter(
                    faculty_activity_id__in=fn_activity_ids,
                    status='AB'
                ).values_list('student_id', flat=True)
            )

        # 3. Find students marked 'AB' in Afternoon (AN 1st period / AN session)
        an_absent_attendances = StudentAttendance.objects.filter(
            faculty_activity_id__in=an_first_period_activity_ids,
            status='AB'
        ).select_related(
            'student',
            'student__department',
            'student__batch',
            'student__section',
            'student__application',
            'student__application__candidate',
            'faculty_activity',
            'faculty_activity__timetable',
            'faculty_activity__timetable__period'
        )

        an_absent_students_map = {}
        for att in an_absent_attendances:
            sid = att.student_id
            # Filter out students who were already absent in the morning (FN)
            if sid in fn_absent_student_ids:
                continue
            
            p_no = 5
            try:
                p_no = att.faculty_activity.timetable.period.period_no
            except Exception:
                p_no = 5

            if sid not in an_absent_students_map:
                an_absent_students_map[sid] = {
                    'student': att.student,
                    'an_period_no': p_no,
                    'fn_status': 'P'  # Attended in FN / Present
                }

        afternoon_student_ids = list(an_absent_students_map.keys())

        # Pre-fetch SMS Logs for this date with sms_type='AFTERNOON_ABSENT'
        sms_logs = SMSLog.objects.filter(
            sent_date=target_date,
            sms_type='AFTERNOON_ABSENT'
        ).order_by('student_id', '-created_at')

        latest_sms_map = {}
        for log in sms_logs:
            if log.student_id and log.student_id not in latest_sms_map:
                latest_sms_map[log.student_id] = log

        results = []
        if afternoon_student_ids:
            students_qs = Student.objects.filter(id__in=afternoon_student_ids).select_related(
                'department', 'batch', 'section', 'application', 'application__candidate'
            )
            if search_query:
                students_qs = students_qs.filter(
                    Q(student_name__icontains=search_query) |
                    Q(register_number__icontains=search_query) |
                    Q(roll_number__icontains=search_query) |
                    Q(application__candidate__name__icontains=search_query) |
                    Q(application__candidate__phone_number__icontains=search_query)
                )

            for st in students_qs:
                info = get_student_sms_info(st)
                item_meta = an_absent_students_map.get(st.id, {})
                sms_log = latest_sms_map.get(st.id)

                sms_status = 'NOT_SENT'
                sms_sent_at = None
                sms_log_id = None
                sms_response = None

                if sms_log:
                    sms_status = sms_log.status
                    sms_sent_at = sms_log.created_at
                    sms_log_id = sms_log.id
                    sms_response = sms_log.gateway_response

                results.append({
                    'student_id': st.id,
                    'student_name': info['student_name'],
                    'register_number': info['register_number'],
                    'roll_number': info['roll_number'],
                    'department_id': info['department_id'],
                    'department_name': info['department_name'],
                    'batch_id': info['batch_id'],
                    'batch_name': info['batch_name'],
                    'section_id': info['section_id'],
                    'section_name': info['section_name'],
                    'student_mobile': info['student_mobile'],
                    'parent_mobile': info['parent_mobile'],
                    'parent_name': info['parent_name'],
                    'an_period_no': item_meta.get('an_period_no', 5),
                    'fn_status': item_meta.get('fn_status', 'P'),
                    'sms_status': sms_status,
                    'sms_sent_at': sms_sent_at,
                    'sms_log_id': sms_log_id,
                    'sms_response': sms_response
                })

        # Calculate statistics
        total_absentees = len(results)
        sent_count = sum(1 for r in results if r['sms_status'] == 'SUCCESS')
        failed_count = sum(1 for r in results if r['sms_status'] == 'FAILED')
        pending_count = sum(1 for r in results if r['sms_status'] in ['NOT_SENT', 'PENDING'])

        return Response({
            "code": 200,
            "message": "Afternoon absentees retrieved successfully",
            "date": date_str,
            "stats": {
                "total_absentees": total_absentees,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "pending_count": pending_count
            },
            "data": results
        }, status=status.HTTP_200_OK)


class SendAfternoonAbsentSMSView(APIView):
    """
    Sends Afternoon Absent SMS to selected students / parents and logs the gateway responses.
    Template: Dear Parent, {#var#} is absent today Afternoon {#var#}. Principal - Thirumalai Engineering Collge
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SendAfternoonAbsentSMSRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Invalid payload",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        target_date = serializer.validated_data['date']
        student_ids = serializer.validated_data['student_ids']
        recipient_type = serializer.validated_data.get('recipient_type', 'PARENT')

        user = request.user
        tracking_user = user if isinstance(user, StandardUser) else None

        students = Student.objects.filter(id__in=student_ids).select_related(
            'department', 'batch', 'section', 'application', 'application__candidate'
        )

        results = []
        success_count = 0
        failed_count = 0

        for student in students:
            # Check if Afternoon SMS is already sent and locked for this student on this date
            if SMSLog.objects.filter(student=student, sent_date=target_date, sms_type='AFTERNOON_ABSENT', status='SUCCESS').exists():
                results.append({
                    'student_id': student.id,
                    'student_name': student.name,
                    'status': 'ALREADY_SENT',
                    'error': 'Afternoon SMS is already sent and locked for this date.'
                })
                continue

            try:
                res = send_afternoon_absent_sms_to_student(
                    student=student,
                    absent_date=target_date,
                    user=tracking_user,
                    recipient_type=recipient_type
                )
                if res['status'] == 'SUCCESS':
                    success_count += 1
                else:
                    failed_count += 1
                results.append(res)
            except Exception as e:
                logger.error(f"Error sending Afternoon SMS for student {student.id}: {str(e)}")
                failed_count += 1
                results.append({
                    'student_id': student.id,
                    'student_name': student.name,
                    'status': 'FAILED',
                    'error': str(e)
                })

        already_sent_count = sum(1 for r in results if r['status'] == 'ALREADY_SENT')
        return Response({
            "code": 200,
            "message": f"Processed Afternoon SMS for {len(results)} students ({success_count} succeeded, {failed_count} failed, {already_sent_count} locked/already sent).",
            "data": {
                "total": len(results),
                "success_count": success_count,
                "failed_count": failed_count,
                "already_sent_count": already_sent_count,
                "results": results
            }
        }, status=status.HTTP_200_OK)


class FeesPendingStudentsListView(APIView):
    """
    Returns the list of students with pending fees for an Academic Year.
    Supports filtering by Academic Year, Department, Batch, Section, and text search.
    Only students with balance_fee > 0 (academic year pending fee) are included.
    Includes parent and student mobile numbers, live SMS status, and formatted message preview.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from student.views.student_views import StudentViewSet
        from collections import OrderedDict

        try:
            res_helper = StudentViewSet()._get_fees_academic_year_data_helper(request)
            meta, summary, records, groups_list, _, department, batch, sec_name, acad_year_str = res_helper[:9]
            student_map = res_helper[9] if len(res_helper) > 9 else {}
        except Exception as e:
            logger.exception("Error calculating academic year fees")
            return Response({
                "code": 500,
                "message": f"Failed to compute academic year fees: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        min_balance = float(request.query_params.get('min_balance', 0) or 0)
        search_query = (request.query_params.get('search') or '').strip().lower()

        pending_records = [r for r in records if float(r.get('balance_fee', 0)) > min_balance]

        if search_query:
            pending_records = [
                r for r in pending_records
                if (search_query in str(r.get('name', '')).lower() or
                    search_query in str(r.get('register_no', '')).lower() or
                    search_query in str(r.get('roll_no', '')).lower() or
                    search_query in str(r.get('department_name', '')).lower() or
                    search_query in str(r.get('batch', '')).lower())
            ]

        student_ids = [r['student_id'] for r in pending_records]
        if not student_map:
            students_qs = Student.objects.filter(id__in=student_ids).select_related(
                'department', 'batch', 'section', 'application', 'application__candidate'
            )
            student_map = {s.id: s for s in students_qs}

        # Query latest SMSLog for FEES_PENDING
        sms_logs = SMSLog.objects.filter(
            student_id__in=student_ids,
            sms_type='FEES_PENDING'
        ).values('id', 'student_id', 'status', 'response_id', 'error_message', 'created_at').order_by('-created_at')

        latest_sms_map = {}
        for log in sms_logs:
            sid = log['student_id']
            if sid and sid not in latest_sms_map:
                latest_sms_map[sid] = log

        enriched_records = []
        tot_pending_amount = 0.0
        sent_count = 0
        failed_count = 0
        not_sent_count = 0

        grouped_dict = OrderedDict()

        for rec in pending_records:
            sid = rec['student_id']
            st_obj = student_map.get(sid)
            info = get_student_sms_info(st_obj) if st_obj else {
                'student_name': rec.get('name', 'Student'),
                'student_mobile': '',
                'parent_mobile': '',
                'parent_name': ''
            }

            bal_amount = float(rec.get('balance_fee', 0))
            tot_pending_amount += bal_amount

            st_name = rec.get('name') or info.get('student_name') or 'Student'
            msg_preview, amt_str = format_fees_pending_message(st_name, bal_amount)

            sms_log = latest_sms_map.get(sid)
            if sms_log:
                sms_status = sms_log.get('status') if isinstance(sms_log, dict) else sms_log.status
                sms_sent_at = sms_log.get('created_at') if isinstance(sms_log, dict) else sms_log.created_at
                sms_log_id = sms_log.get('id') if isinstance(sms_log, dict) else sms_log.id
                sms_resp = {
                    'response_id': sms_log.get('response_id') if isinstance(sms_log, dict) else sms_log.response_id,
                    'error_message': sms_log.get('error_message') if isinstance(sms_log, dict) else sms_log.error_message
                }
                if sms_status == 'SUCCESS':
                    sent_count += 1
                elif sms_status == 'FAILED':
                    failed_count += 1
                else:
                    not_sent_count += 1
            else:
                sms_status = 'NOT_SENT'
                sms_sent_at = None
                sms_log_id = None
                sms_resp = None
                not_sent_count += 1

            enriched = {
                'student_id': sid,
                'student_name': st_name,
                'register_number': rec.get('register_no') or '',
                'roll_number': rec.get('roll_no') or '',
                'department_id': st_obj.department_id if st_obj else None,
                'department_name': rec.get('department_name') or '',
                'department_code': rec.get('department_code') or '',
                'batch_id': st_obj.batch_id if st_obj else None,
                'batch_name': rec.get('batch') or '',
                'section_id': st_obj.section_id if st_obj else None,
                'section_name': rec.get('section') or 'A',
                'year_of_study': rec.get('year_of_study', 1),
                'semesters': rec.get('semesters', []),
                'semesters_label': rec.get('semesters_label', ''),
                'quota': rec.get('quota', 'Regular'),
                'total_fee': rec.get('total_fee', 0.0),
                'paid_fee': rec.get('paid_fee', 0.0),
                'concession_fee': rec.get('concession_fee', 0.0),
                'balance_fee': bal_amount,
                'student_mobile': info.get('student_mobile') or '',
                'parent_mobile': info.get('parent_mobile') or '',
                'parent_name': info.get('parent_name') or '',
                'sms_status': sms_status,
                'sms_sent_at': sms_sent_at,
                'sms_log_id': sms_log_id,
                'sms_response': sms_resp,
                'message_preview': msg_preview,
            }
            enriched_records.append(enriched)

            dept_k = enriched['department_name']
            batch_k = enriched['batch_name']
            sec_k = enriched['section_name']
            g_key = (dept_k, batch_k, sec_k)
            if g_key not in grouped_dict:
                grouped_dict[g_key] = {
                    'department_name': dept_k,
                    'department_code': enriched.get('department_code', ''),
                    'batch': batch_k,
                    'year_of_study': enriched.get('year_of_study', 1),
                    'semesters_label': enriched.get('semesters_label', ''),
                    'section': sec_k,
                    'total_pending_students': 0,
                    'total_pending_amount': 0.0,
                    'students': []
                }
            g_item = grouped_dict[g_key]
            g_item['total_pending_students'] += 1
            g_item['total_pending_amount'] += bal_amount
            g_item['students'].append(enriched)

        return Response({
            "code": 200,
            "message": "Fees pending students retrieved successfully",
            "academic_year": acad_year_str,
            "stats": {
                "total_students_with_pending_fees": len(enriched_records),
                "total_pending_amount": tot_pending_amount,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "not_sent_count": not_sent_count,
            },
            "template": {
                "template_id": getattr(settings, 'DIAL4SMS_FEES_TEMPLATE_ID', '1177179058551929973'),
                "sender_id": getattr(settings, 'DIAL4SMS_SENDER_ID', 'TECKPM'),
                "template_text": "Dear Parent, {#var#} Fees Pending {#var#}. ignore if already paid - PRINCIPAL, - Thirumlai Engineering College"
            },
            "metadata": meta,
            "groups": list(grouped_dict.values()),
            "data": enriched_records
        }, status=status.HTTP_200_OK)


class SendFeesPendingSMSView(APIView):
    """
    Sends Fees Pending SMS to selected students and logs the gateway responses.
    Uses Academic Year pending amount.
    DLT Template: Dear Parent, {#var#} Fees Pending {#var#}. ignore if already paid - PRINCIPAL, - Thirumlai Engineering College
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from student.views.student_views import StudentViewSet

        serializer = SendFeesPendingSMSRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Invalid payload",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        academic_year = validated.get('academic_year')
        recipient_type = validated.get('recipient_type', 'PARENT')
        force = validated.get('force', False)

        target_student_map = {}
        if validated.get('students'):
            for item in validated['students']:
                sid = item['student_id']
                target_student_map[sid] = item.get('amount')

        if validated.get('student_ids'):
            for sid in validated['student_ids']:
                if sid not in target_student_map:
                    target_student_map[sid] = None

        user = request.user
        tracking_user = user if isinstance(user, StandardUser) else None

        missing_amounts = [sid for sid, amt in target_student_map.items() if amt is None or amt <= 0]
        if missing_amounts:
            calc_req = type('Req', (), {'query_params': {'academic_year': academic_year}, 'data': {}, 'GET': {'academic_year': academic_year}})()
            try:
                _, _, records, _, _, _, _, _, _ = StudentViewSet()._get_fees_academic_year_data_helper(calc_req)
                for rec in records:
                    sid = rec['student_id']
                    if sid in target_student_map and (target_student_map[sid] is None or target_student_map[sid] <= 0):
                        target_student_map[sid] = float(rec.get('balance_fee', 0))
            except Exception as e:
                logger.warning(f"Could not recalculate academic year fees: {str(e)}")

        students_qs = Student.objects.filter(id__in=list(target_student_map.keys())).select_related(
            'department', 'batch', 'section', 'application', 'application__candidate'
        )

        results = []
        success_count = 0
        failed_count = 0
        already_sent_count = 0
        task_id = request.data.get('task_id')
        total_students = len(students_qs)

        today = datetime.date.today()

        for idx, student in enumerate(students_qs, start=1):
            bal_amt = target_student_map.get(student.id, 0.0) or 0.0

            if not force and SMSLog.objects.filter(student=student, sent_date=today, sms_type='FEES_PENDING', status='SUCCESS').exists():
                already_sent_count += 1
                results.append({
                    'student_id': student.id,
                    'student_name': student.student_name or student.name or 'Student',
                    'amount': bal_amt,
                    'status': 'ALREADY_SENT',
                    'error': 'Fees SMS has already been sent to this student today.'
                })
                continue

            try:
                res = send_fees_pending_sms_to_student(
                    student=student,
                    balance_amount=bal_amt,
                    user=tracking_user,
                    recipient_type=recipient_type,
                    academic_year_str=str(academic_year) if academic_year else None
                )
                if res['status'] == 'SUCCESS':
                    success_count += 1
                else:
                    failed_count += 1
                results.append(res)
            except Exception as e:
                logger.exception(f"Error sending fees SMS for student {student.id}")
                failed_count += 1
                results.append({
                    'student_id': student.id,
                    'student_name': student.student_name or student.name or 'Student',
                    'amount': bal_amt,
                    'status': 'FAILED',
                    'error': str(e)
                })

            if task_id and (idx % 2 == 0 or idx == total_students):
                send_targeted_broadcast(f'task_{task_id}', {
                    'type': 'sms_progress',
                    'task_id': task_id,
                    'progress': round((idx / total_students) * 100) if total_students else 100,
                    'processed': idx,
                    'total': total_students,
                    'success': success_count,
                    'failed': failed_count,
                    'already_sent': already_sent_count,
                    'status': f'Sent {idx} of {total_students} fees alerts...'
                })

        return Response({
            "code": 200,
            "message": f"Processed Fees SMS for {len(results)} students ({success_count} succeeded, {failed_count} failed, {already_sent_count} skipped/already sent).",
            "data": {
                "total": len(results),
                "success_count": success_count,
                "failed_count": failed_count,
                "already_sent_count": already_sent_count,
                "results": results
            }
        }, status=status.HTTP_200_OK)


class MarksStudentsListView(APIView):
    """
    Returns list of students with entered marks for an exam.
    Filters: exam_id, program_id, department_id, batch_id, section_id, search.
    Computes total marks and class rank for each student based on their class group:
    (batch, department, section).
    Includes subject-wise marks, formatted DLT template preview, and live SMS delivery status.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from student.models import Marks
        from institution.models import Exam, Section, Batch, Semester, Department, Program

        exam_id = request.query_params.get('exam_id')
        program_id = request.query_params.get('program_id')
        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')
        semester_id = request.query_params.get('semester_id')
        search_query = (request.query_params.get('search') or '').strip().lower()

        # Resolve exam
        exam_obj = None
        if exam_id:
            exam_obj = Exam.objects.filter(id=exam_id).first()
        if not exam_obj:
            exam_obj = Exam.objects.filter(is_active=True).order_by('-id').first()
            if exam_obj:
                exam_id = exam_obj.id

        if not exam_obj:
            return Response({
                "code": 200,
                "message": "No active exams found",
                "stats": {"total_students": 0, "sent_count": 0, "failed_count": 0, "not_sent_count": 0},
                "data": []
            }, status=status.HTTP_200_OK)

        exam_name = exam_obj.exam_name

        # 1. Fetch all marks entered for this exam to ensure accurate class ranking across the whole class group
        marks_qs = Marks.objects.filter(exam_id=exam_obj.id).select_related(
            'student',
            'student__department',
            'student__department__program',
            'student__batch',
            'student__section',
            'student__application',
            'student__application__candidate',
            'subject',
            'subject__semester',
        ).order_by('student_id', 'subject__subject_code')

        target_sem_num = None
        if semester_id:
            sem_clean = str(semester_id).strip()
            if sem_clean.isdigit():
                num = int(sem_clean)
                if 1 <= num <= 8:
                    target_sem_num = num
                else:
                    s_obj = Semester.objects.filter(id=num).first()
                    if s_obj and s_obj.semester_number and 1 <= s_obj.semester_number <= 8:
                        target_sem_num = s_obj.semester_number
            else:
                m_match = re.search(r'\d+', sem_clean)
                if m_match and 1 <= int(m_match.group(0)) <= 8:
                    target_sem_num = int(m_match.group(0))

        if target_sem_num:
            marks_qs = marks_qs.filter(
                Q(subject__semester__semester_number=target_sem_num) |
                Q(subject__semester__semester_name__iexact=f"Semester {target_sem_num}") |
                Q(subject__semester__semester_name__iexact=f"Sem {target_sem_num}")
            )

        # Group all marks by student
        all_students_map = {}
        for m in marks_qs:
            st = m.student
            if not st:
                continue
            sid = st.id
            if sid not in all_students_map:
                all_students_map[sid] = {
                    'student': st,
                    'marks': []
                }
            all_students_map[sid]['marks'].append(m)

        # 2. Compute total marks and group by class: (batch_id, department_id, section_id)
        class_groups = {}  # (batch_id, dept_id, sec_id) -> list of (student_id, total_numeric)
        student_totals = {}  # student_id -> { 'total_num': float, 'total_str': str, 'subject_items': list }

        for sid, data in all_students_map.items():
            st = data['student']
            grp_key = (st.batch_id, st.department_id, st.section_id)
            if grp_key not in class_groups:
                class_groups[grp_key] = []

            subj_items = []
            tot_num = 0.0
            for m in data['marks']:
                val_clean = str(m.marks_obtained or '').strip()
                code_str = m.subject.subject_code if m.subject else ''
                name_str = m.subject.subject_name if m.subject else ''
                sem_obj = getattr(m.subject, 'semester', None) if m.subject else None
                subj_items.append({
                    'code': code_str,
                    'name': name_str,
                    'marks': val_clean,
                    'semester_id': sem_obj.id if sem_obj else None,
                    'semester_name': sem_obj.semester_name if sem_obj else '',
                })


                # Numeric score parsing
                if val_clean.upper() not in ['AB', 'UA', 'ABSENT', '-', '', 'N/A']:
                    try:
                        tot_num += float(val_clean)
                    except ValueError:
                        pass

            tot_str = str(int(tot_num)) if tot_num.is_integer() else f"{tot_num:.1f}"
            student_totals[sid] = {
                'total_num': tot_num,
                'total_str': tot_str,
                'subject_items': subj_items
            }
            class_groups[grp_key].append((sid, tot_num))

        # 3. Compute dense rank within each class group
        rank_map = {}  # student_id -> rank
        for grp_key, st_list in class_groups.items():
            sorted_st = sorted(st_list, key=lambda x: x[1], reverse=True)
            cur_rank = 0
            prev_score = None
            for s_id, score in sorted_st:
                if prev_score is None or score != prev_score:
                    cur_rank += 1
                    prev_score = score
                rank_map[s_id] = cur_rank

        # Resolve section name target
        sec_name_target = None
        if section_id:
            sec_clean = str(section_id).strip()
            if sec_clean.isdigit():
                sec_pk = int(sec_clean)
                s_obj = None
                if department_id and str(department_id).isdigit():
                    s_obj = Section.objects.filter(id=sec_pk, department_id=int(department_id)).first()
                if not s_obj:
                    s_obj = Section.objects.filter(id=sec_pk).first()
                if s_obj:
                    sec_name_target = s_obj.sections.strip().upper()
            else:
                sec_name_target = sec_clean.upper()

        # Resolve batch name target
        batch_name_target = None
        if batch_id:
            batch_clean = str(batch_id).strip()
            if batch_clean.isdigit():
                b_pk = int(batch_clean)
                b_obj = None
                if department_id and str(department_id).isdigit():
                    b_obj = Batch.objects.filter(id=b_pk, department_id=int(department_id)).first()
                if not b_obj:
                    b_obj = Batch.objects.filter(id=b_pk).first()
                if b_obj:
                    batch_name_target = b_obj.batch.strip().lower()
            else:
                batch_name_target = batch_clean.lower()

        # 4. Filter students based on user query params
        filtered_student_ids = []
        for sid, data in all_students_map.items():
            st = data['student']
            if program_id:
                prog_id = getattr(st.department, 'program_id', None)
                if str(prog_id) != str(program_id):
                    continue
            if department_id and str(st.department_id) != str(department_id):
                continue
            if batch_id:
                st_bname = (st.batch.batch if st.batch else '').strip().lower()
                if str(st.batch_id) != str(batch_id) and (not batch_name_target or st_bname != batch_name_target):
                    continue
            if section_id:
                st_sname = (st.section.sections if st.section else '').strip().upper()
                if str(st.section_id) != str(section_id) and (not sec_name_target or st_sname != sec_name_target):
                    continue
            if search_query:
                st_name = (st.student_name or st.name or '').lower()
                roll = (st.roll_number or '').lower()
                reg = (st.register_number or '').lower()
                dept_name = (st.department.department_name if st.department else '').lower()
                if search_query not in st_name and search_query not in roll and search_query not in reg and search_query not in dept_name:
                    continue
            filtered_student_ids.append(sid)

        # 5. Query SMSLog for sms_type='MARKS' to get latest delivery status for these students
        sms_logs = SMSLog.objects.filter(
            student_id__in=filtered_student_ids,
            sms_type='MARKS'
        ).values('id', 'student_id', 'status', 'response_id', 'error_message', 'created_at', 'sent_date').order_by('-created_at')

        latest_sms_map = {}
        for log in sms_logs:
            s_id = log['student_id']
            if s_id and s_id not in latest_sms_map:
                latest_sms_map[s_id] = log

        # 6. Build enriched result list
        enriched_students = []
        sent_count = 0
        failed_count = 0
        not_sent_count = 0

        for sid in filtered_student_ids:
            st = all_students_map[sid]['student']
            info = get_student_sms_info(st)
            tot_info = student_totals.get(sid, {'total_num': 0.0, 'total_str': '0', 'subject_items': []})
            s_rank = rank_map.get(sid, 1)

            st_name = info['student_name']
            clean_roll = getattr(st, 'roll_number', '') or info.get('register_number') or ''
            subj_items = tot_info['subject_items']
            total_str = tot_info['total_str']

            msg_preview, part1, part2, _, _ = format_marks_message(
                exam_name=exam_name,
                student_name=st_name,
                roll_no=clean_roll,
                subject_marks_list=subj_items,
                total_marks=total_str,
                rank=s_rank
            )

            sms_log = latest_sms_map.get(sid)
            if sms_log:
                s_status = sms_log.get('status')
                sms_sent_at = sms_log.get('created_at')
                sms_log_id = sms_log.get('id')
                sms_resp = {
                    'response_id': sms_log.get('response_id'),
                    'error_message': sms_log.get('error_message')
                }
                if s_status == 'SUCCESS':
                    sent_count += 1
                elif s_status == 'FAILED':
                    failed_count += 1
                else:
                    not_sent_count += 1
            else:
                s_status = 'NOT_SENT'
                sms_sent_at = None
                sms_log_id = None
                sms_resp = None
                not_sent_count += 1

            enriched = {
                'student_id': sid,
                'student_name': st_name,
                'register_number': info.get('register_number') or '',
                'roll_number': clean_roll,
                'program_id': getattr(st.department, 'program_id', None) if st.department else None,
                'program_name': getattr(st.department.program, 'program_name', '') if st.department and getattr(st.department, 'program', None) else '',
                'department_id': st.department_id,
                'department_name': st.department.department_name if st.department else '',
                'department_code': st.department.department_code if st.department else '',
                'batch_id': st.batch_id,
                'batch_name': st.batch.batch if st.batch else '',
                'section_id': st.section_id,
                'section_name': st.section.sections if st.section else 'A',
                'semester_id': next((sm['semester_id'] for sm in subj_items if sm.get('semester_id')), None),
                'semester_name': next((sm['semester_name'] for sm in subj_items if sm.get('semester_name')), ''),
                'exam_id': exam_obj.id,
                'exam_name': exam_name,
                'subject_marks': subj_items,
                'marks_part_1': part1,
                'marks_part_2': part2,
                'total_marks': total_str,
                'rank': s_rank,
                'student_mobile': info.get('student_mobile') or '',
                'parent_mobile': info.get('parent_mobile') or '',
                'parent_name': info.get('parent_name') or '',
                'sms_status': s_status,
                'sms_sent_at': sms_sent_at,
                'sms_log_id': sms_log_id,
                'sms_response': sms_resp,
                'message_preview': msg_preview,
            }
            enriched_students.append(enriched)

        # Sort enriched students by department, batch, section, and rank
        enriched_students.sort(key=lambda x: (x['department_name'], x['batch_name'], x['section_name'], x['rank']))

        return Response({
            "code": 200,
            "message": "Marks entered students retrieved successfully",
            "exam": {
                "id": exam_obj.id,
                "exam_name": exam_name,
                "exam_type_id": exam_obj.exam_type_id if hasattr(exam_obj, 'exam_type_id') else None,
            },
            "stats": {
                "total_students": len(enriched_students),
                "sent_count": sent_count,
                "failed_count": failed_count,
                "not_sent_count": not_sent_count,
            },
            "template": {
                "template_id": getattr(settings, 'DIAL4SMS_MARKS_TEMPLATE_ID', '1177179058575792171'),
                "sender_id": getattr(settings, 'DIAL4SMS_SENDER_ID', 'TECKPM'),
                "template_text": "Dear Parent, {#var#} Marks Name: {#var#} Roll No: {#var#} Subject-wise Marks: {#var#}{#var#} Total: {#var#} Rank: {#var#} Regards, Principal - Thirumalai Engineering College"
            },
            "data": enriched_students
        }, status=status.HTTP_200_OK)


class SendMarksSMSView(APIView):
    """
    Sends Marks SMS to selected students and logs gateway responses.
    Template: Dear Parent, {#var#} Marks Name: {#var#} Roll No: {#var#} Subject-wise Marks: {#var#}{#var#} Total: {#var#} Rank: {#var#} Regards, Principal - Thirumalai Engineering College
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from student.models import Marks, Student
        from institution.models import Exam, Semester

        serializer = SendMarksSMSRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Invalid payload",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        exam_id = validated['exam_id']
        semester_id = validated.get('semester_id') or request.data.get('semester_id')
        recipient_type = validated.get('recipient_type', 'PARENT')
        force = validated.get('force', False)

        exam_obj = Exam.objects.filter(id=exam_id).first()
        if not exam_obj:
            return Response({
                "code": 404,
                "message": f"Exam with id {exam_id} not found."
            }, status=status.HTTP_404_NOT_FOUND)

        exam_name = exam_obj.exam_name

        # Target student IDs
        target_student_ids = []
        if validated.get('student_ids'):
            target_student_ids = list(validated['student_ids'])
        elif validated.get('students'):
            target_student_ids = [item['student_id'] for item in validated['students']]

        # Query all marks for this exam to ensure accurate ranking within class groups
        marks_qs = Marks.objects.filter(exam_id=exam_id).select_related(
            'student', 'subject', 'subject__semester', 'student__batch', 'student__department', 'student__section'
        ).order_by('student_id', 'subject__subject_code')

        target_sem_num = None
        if semester_id:
            sem_clean = str(semester_id).strip()
            if sem_clean.isdigit():
                num = int(sem_clean)
                if 1 <= num <= 8:
                    target_sem_num = num
                else:
                    s_obj = Semester.objects.filter(id=num).first()
                    if s_obj and s_obj.semester_number and 1 <= s_obj.semester_number <= 8:
                        target_sem_num = s_obj.semester_number
            else:
                m_match = re.search(r'\d+', sem_clean)
                if m_match and 1 <= int(m_match.group(0)) <= 8:
                    target_sem_num = int(m_match.group(0))

        if target_sem_num:
            marks_qs = marks_qs.filter(
                Q(subject__semester__semester_number=target_sem_num) |
                Q(subject__semester__semester_name__iexact=f"Semester {target_sem_num}") |
                Q(subject__semester__semester_name__iexact=f"Sem {target_sem_num}")
            )


        all_students_map = {}
        for m in marks_qs:
            st = m.student
            if not st:
                continue
            sid = st.id
            if sid not in all_students_map:
                all_students_map[sid] = {'student': st, 'marks': []}
            all_students_map[sid]['marks'].append(m)

        # Compute rank within class groups
        class_groups = {}
        student_totals = {}
        for sid, data in all_students_map.items():
            st = data['student']
            grp_key = (st.batch_id, st.department_id, st.section_id)
            if grp_key not in class_groups:
                class_groups[grp_key] = []
            subj_items = []
            tot_num = 0.0
            for m in data['marks']:
                val_clean = str(m.marks_obtained or '').strip()
                code_str = m.subject.subject_code if m.subject else ''
                name_str = m.subject.subject_name if m.subject else ''
                subj_items.append({'code': code_str, 'name': name_str, 'marks': val_clean})
                if val_clean.upper() not in ['AB', 'UA', 'ABSENT', '-', '', 'N/A']:
                    try:
                        tot_num += float(val_clean)
                    except ValueError:
                        pass
            tot_str = str(int(tot_num)) if tot_num.is_integer() else f"{tot_num:.1f}"
            student_totals[sid] = {'total_num': tot_num, 'total_str': tot_str, 'subject_items': subj_items}
            class_groups[grp_key].append((sid, tot_num))

        rank_map = {}
        for grp_key, st_list in class_groups.items():
            sorted_st = sorted(st_list, key=lambda x: x[1], reverse=True)
            cur_rank = 0
            prev_score = None
            for s_id, score in sorted_st:
                if prev_score is None or score != prev_score:
                    cur_rank += 1
                    prev_score = score
                rank_map[s_id] = cur_rank

        # Check existing successful logs to avoid double sending unless force=True
        already_sent_ids = set()
        if not force and target_student_ids:
            already_sent_ids = set(SMSLog.objects.filter(
                student_id__in=target_student_ids,
                sms_type='MARKS',
                status='SUCCESS'
            ).values_list('student_id', flat=True))

        students_qs = Student.objects.filter(id__in=target_student_ids).select_related(
            'department', 'batch', 'section', 'application', 'application__candidate'
        )
        student_map = {s.id: s for s in students_qs}

        results = []
        success_count = 0
        failed_count = 0
        already_sent_count = 0

        total_to_send = len(target_student_ids)

        for idx, sid in enumerate(target_student_ids, start=1):
            if sid in already_sent_ids:
                already_sent_count += 1
                results.append({
                    'student_id': sid,
                    'status': 'SKIPPED',
                    'message': 'Marks SMS already delivered successfully.'
                })
                continue

            st = student_map.get(sid)
            if not st:
                failed_count += 1
                results.append({
                    'student_id': sid,
                    'status': 'FAILED',
                    'error': f'Student #{sid} not found'
                })
                continue

            tot_data = student_totals.get(sid, {'total_num': 0.0, 'total_str': '0', 'subject_items': []})
            s_rank = rank_map.get(sid, 1)

            res = send_marks_sms_to_student(
                student=st,
                exam_name=exam_name,
                subject_marks_list=tot_data['subject_items'],
                total_marks=tot_data['total_str'],
                rank=s_rank,
                recipient_type=recipient_type,
                user=request.user
            )

            if res['status'] == 'SUCCESS':
                success_count += 1
            else:
                failed_count += 1

            results.append(res)

        # Notify via websocket broadcast
        try:
            send_targeted_broadcast('sms_updates', {
                'type': 'sms_sent',
                'sms_type': 'MARKS',
                'exam_id': exam_id,
                'success_count': success_count,
                'failed_count': failed_count,
                'total': total_to_send
            })
        except Exception:
            pass

        return Response({
            "code": 200,
            "message": f"Processed Marks SMS for {len(results)} students ({success_count} succeeded, {failed_count} failed, {already_sent_count} skipped/already sent).",
            "data": {
                "total": len(results),
                "success_count": success_count,
                "failed_count": failed_count,
                "already_sent_count": already_sent_count,
                "results": results
            }
        }, status=status.HTTP_200_OK)


class SMSLogViewSet(ReadOnlyModelViewSet):
    """
    Viewset to retrieve and filter SMS delivery logs.
    """
    queryset = SMSLog.objects.select_related('student', 'created_by').all().order_by('-created_at')
    serializer_class = SMSLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        date = self.request.query_params.get('date')
        student_id = self.request.query_params.get('student_id')
        sms_type = self.request.query_params.get('sms_type')
        status_filter = self.request.query_params.get('status')

        if date:
            qs = qs.filter(sent_date=date)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if sms_type:
            qs = qs.filter(sms_type=sms_type)
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs


class SMSBalanceView(APIView):
    """
    Returns the real-time SMS credit balance from Dial4SMS Gateway API:
    GET http://smsssl.dial4sms.com/api/v2/Balance?ApiKey={ApiKey}&ClientId={ClientId}
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        balance_info = get_dial4sms_balance()
        status_code = status.HTTP_200_OK if balance_info.get('success') else status.HTTP_200_OK
        return Response({
            "code": 200 if balance_info.get('success') else 502,
            "message": "SMS credit balance retrieved successfully" if balance_info.get('success') else (balance_info.get('error') or "Failed to retrieve balance"),
            "data": balance_info
        }, status=status_code)


class SMSDashboardStatsView(APIView):
    """
    Returns aggregated real-time metrics for the SMS Dashboard:
    - Live Dial4SMS credit balance
    - Today's dispatch metrics & absentee counts
    - Overall delivery metrics & success rate
    - Recent activity logs
    - Approved DLT template info
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = datetime.date.today()
        today_str = today.strftime('%Y-%m-%d')

        # 1. Live Dial4SMS credit balance
        balance_info = get_dial4sms_balance()

        # 2. Today's Dispatches from SMSLog
        today_logs_qs = SMSLog.objects.filter(created_at__date=today)
        total_sent_today = today_logs_qs.count()
        success_today = today_logs_qs.filter(status='SUCCESS').count()
        failed_today = today_logs_qs.filter(status='FAILED').count()

        # 3. Overall lifetime SMSLog stats
        total_lifetime = SMSLog.objects.count()
        success_lifetime = SMSLog.objects.filter(status='SUCCESS').count()
        failed_lifetime = SMSLog.objects.filter(status='FAILED').count()
        delivery_rate = round((success_lifetime / total_lifetime * 100), 1) if total_lifetime > 0 else 100.0

        # 4. Forenoon and Afternoon absentee counts for today
        # Forenoon (Period 1 absentees)
        fn_absentee_count = 0
        try:
            fn_activities = FacultyActivity.objects.filter(date=today, timetable__period__period_number=1)
            if fn_activities.exists():
                fn_absentee_count = StudentAttendance.objects.filter(
                    faculty_activity__in=fn_activities,
                    status='AB'
                ).values('student_id').distinct().count()
        except Exception:
            pass

        # Afternoon (AN 1st period absentees, excluding FN absentees)
        an_absentee_count = 0
        try:
            an_activities = FacultyActivity.objects.filter(
                date=today,
                timetable__period__session__name__icontains='afternoon'
            ).order_by('timetable__period__period_number')
            if an_activities.exists():
                first_an_act = an_activities.first()
                # Exclude students absent in FN
                fn_absent_ids = StudentAttendance.objects.filter(
                    faculty_activity__date=today,
                    faculty_activity__timetable__period__period_number=1,
                    status='AB'
                ).values_list('student_id', flat=True)

                an_absentee_count = StudentAttendance.objects.filter(
                    faculty_activity=first_an_act,
                    status='AB'
                ).exclude(student_id__in=fn_absent_ids).values('student_id').distinct().count()
        except Exception:
            pass

        # 5. Recent 8 SMS logs
        recent_logs_qs = SMSLog.objects.select_related('student').order_by('-created_at')[:8]
        recent_logs = []
        for log in recent_logs_qs:
            recent_logs.append({
                'id': log.id,
                'student_name': log.student_name or (log.student.name if log.student else 'Unknown'),
                'register_number': log.register_number,
                'phone_number': log.phone_number,
                'sms_type': log.sms_type,
                'status': log.status,
                'sent_date': log.sent_date.strftime('%Y-%m-%d') if log.sent_date else '',
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            })

        # 6. Approved Templates Config
        templates = [
            {
                'type': 'FULL_DAY_ABSENT',
                'title': 'Forenoon / Full Day Absent',
                'template_id': getattr(settings, 'DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', '1177179058643015435'),
                'sender_id': getattr(settings, 'DIAL4SMS_SENDER_ID', 'TECKPM'),
                'template_text': 'Dear Parent, {#var#} is absent today {#var#}. Principal - Thirumalai Engineering Collge'
            },
            {
                'type': 'AFTERNOON_ABSENT',
                'title': 'Afternoon Absent',
                'template_id': getattr(settings, 'DIAL4SMS_AFTERNOON_ABSENT_TEMPLATE_ID', '1177179058643015435'),
                'sender_id': getattr(settings, 'DIAL4SMS_SENDER_ID', 'TECKPM'),
                'template_text': 'Dear Parent, {#var#} is absent today Afternoon {#var#}. Principal - Thirumalai Engineering Collge'
            },
            {
                'type': 'FEES_PENDING',
                'title': 'Academic Year Fees Pending',
                'template_id': getattr(settings, 'DIAL4SMS_FEES_TEMPLATE_ID', '1177179058551929973'),
                'sender_id': getattr(settings, 'DIAL4SMS_SENDER_ID', 'TECKPM'),
                'template_text': 'Dear Parent, {#var#} Fees Pending {#var#}. ignore if already paid - PRINCIPAL, - Thirumlai Engineering College'
            },
            {
                'type': 'MARKS',
                'title': 'Student Marks & Rank Alert',
                'template_id': getattr(settings, 'DIAL4SMS_MARKS_TEMPLATE_ID', '1177179058575792171'),
                'sender_id': getattr(settings, 'DIAL4SMS_SENDER_ID', 'TECKPM'),
                'template_text': 'Dear Parent, {#var#} Marks Name: {#var#} Roll No: {#var#} Subject-wise Marks: {#var#}{#var#} Total: {#var#} Rank: {#var#} Regards, Principal - Thirumalai Engineering College'
            }
        ]


        return Response({
            "code": 200,
            "message": "SMS dashboard metrics retrieved successfully",
            "data": {
                "balance": balance_info,
                "today": {
                    "date": today_str,
                    "total_sent": total_sent_today,
                    "success_count": success_today,
                    "failed_count": failed_today,
                    "fullday_absentees": fn_absentee_count,
                    "afternoon_absentees": an_absentee_count,
                },
                "overall": {
                    "total_dispatched": total_lifetime,
                    "total_success": success_lifetime,
                    "total_failed": failed_lifetime,
                    "delivery_rate": delivery_rate,
                },
                "recent_logs": recent_logs,
                "templates": templates
            }
        }, status=status.HTTP_200_OK)

