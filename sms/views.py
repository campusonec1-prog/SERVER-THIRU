import datetime
import logging
from django.db.models import Q, Max
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from student.models import Student, StudentAttendance, FacultyActivity
from users.models import User as StandardUser
from .models import SMSLog
from .serializers import (
    SMSLogSerializer,
    FullDayAbsenteeStudentSerializer,
    SendFullDayAbsentSMSRequestSerializer,
    AfternoonAbsenteeStudentSerializer,
    SendAfternoonAbsentSMSRequestSerializer,
)
from .services import (
    get_student_sms_info,
    send_full_day_absent_sms_to_student,
    send_afternoon_absent_sms_to_student,
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

        for student in students:
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
