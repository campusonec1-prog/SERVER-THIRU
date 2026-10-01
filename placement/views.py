from django.db.models import Count, Q
from django.http import Http404
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, NotAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from common.pagination import CustomPageNumberPagination
from common.r2 import upload_file_to_r2
from student.models import Student, GradeSystem
from .models import (
    PlacementCompany,
    PlacementDrive,
    PlacementDriveEligibility,
    StudentPlacementTracking,
    IndustryChoices,
    DriveTypeChoices,
    DriveStatusChoices,
    AttendanceStatusChoices,
    PlacementOutcomeChoices
)
from .serializers import (
    PlacementCompanySerializer,
    PlacementDriveSerializer,
    PlacementDriveEligibilitySerializer,
    StudentPlacementTrackingSerializer
)
from .permissions import PlacementCompanyPermission


def broadcast_placement_event(model_name, event_name, data):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': model_name,
                        'event': event_name,
                        'data': data
                    }
                }
            )
        except Exception:
            pass


class PlacementCompanyViewSet(viewsets.ModelViewSet):
    queryset = PlacementCompany.objects.select_related('created_by', 'updated_by').all().order_by('-created_at')
    serializer_class = PlacementCompanySerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'company_name',
        'contact_person_name',
        'contact_email',
        'contact_phone_number',
        'city',
        'state',
        'industry',
        'description'
    ]

    filterset_fields = [
        'industry',
        'is_active',
        'city',
        'state'
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('PlacementCompany', 'create', {'id': instance.id, 'company_name': instance.company_name})

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('PlacementCompany', 'update', {'id': instance.id, 'company_name': instance.company_name})

    def perform_destroy(self, instance):
        inst_id = instance.id
        inst_name = instance.company_name
        instance.delete()
        broadcast_placement_event('PlacementCompany', 'delete', {'id': inst_id, 'company_name': inst_name})

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement companies retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement company details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement company created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement company updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement company deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        company = self.get_object()
        company.is_active = not company.is_active
        user = request.user if request.user and request.user.is_authenticated else None
        company.updated_by = user
        company.save()
        
        serializer = self.get_serializer(company)
        broadcast_placement_event('PlacementCompany', 'update', {
            'id': company.id,
            'company_name': company.company_name,
            'is_active': company.is_active
        })
        
        return Response({
            "code": 200,
            "message": f"Company marked as {'active' if company.is_active else 'inactive'} successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='industry-choices')
    def industry_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in IndustryChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Industry choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary-stats')
    def summary_stats(self, request):
        total = PlacementCompany.objects.count()
        active = PlacementCompany.objects.filter(is_active=True).count()
        inactive = total - active
        
        industry_counts = (
            PlacementCompany.objects.values('industry')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        
        industry_dict = dict(IndustryChoices.choices)
        top_industries = [
            {
                "industry": item['industry'],
                "label": industry_dict.get(item['industry'], item['industry']),
                "count": item['count']
            }
            for item in industry_counts
        ]

        return Response({
            "code": 200,
            "message": "Placement stats retrieved successfully",
            "data": {
                "total_companies": total,
                "active_companies": active,
                "inactive_companies": inactive,
                "top_industries": top_industries
            }
        }, status=status.HTTP_200_OK)


class PlacementDriveViewSet(viewsets.ModelViewSet):
    queryset = PlacementDrive.objects.select_related('company', 'created_by', 'updated_by').all().order_by('-application_start_date', '-created_at')
    serializer_class = PlacementDriveSerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'job_role',
        'company__company_name',
        'location',
        'ctc',
        'job_description',
    ]

    filterset_fields = [
        'company',
        'drive_type',
        'status',
        'location',
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('PlacementDrive', 'create', {
            'id': instance.id,
            'job_role': instance.job_role,
            'company_name': instance.company.company_name
        })

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('PlacementDrive', 'update', {
            'id': instance.id,
            'job_role': instance.job_role,
            'company_name': instance.company.company_name
        })

    def perform_destroy(self, instance):
        inst_id = instance.id
        role_name = instance.job_role
        instance.delete()
        broadcast_placement_event('PlacementDrive', 'delete', {'id': inst_id, 'job_role': role_name})

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drives retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement drive created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        drive = self.get_object()
        new_status = request.data.get('status')
        if not new_status or new_status not in DriveStatusChoices.values:
            return Response({
                "code": 400,
                "message": f"Invalid status. Choose from: {list(DriveStatusChoices.values)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        drive.status = new_status
        user = request.user if request.user and request.user.is_authenticated else None
        drive.updated_by = user
        drive.save()

        serializer = self.get_serializer(drive)
        broadcast_placement_event('PlacementDrive', 'update', {
            'id': drive.id,
            'job_role': drive.job_role,
            'status': drive.status
        })

        return Response({
            "code": 200,
            "message": f"Placement drive status updated to {drive.get_status_display()}",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='type-choices')
    def type_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in DriveTypeChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Drive type choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='status-choices')
    def status_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in DriveStatusChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Drive status choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary-stats')
    def summary_stats(self, request):
        total = PlacementDrive.objects.count()
        reg_open = PlacementDrive.objects.filter(status=DriveStatusChoices.REGISTRATION_OPEN).count()
        upcoming = PlacementDrive.objects.filter(status=DriveStatusChoices.UPCOMING).count()
        in_progress = PlacementDrive.objects.filter(status=DriveStatusChoices.IN_PROGRESS).count()
        completed = PlacementDrive.objects.filter(status=DriveStatusChoices.COMPLETED).count()

        return Response({
            "code": 200,
            "message": "Placement drive stats retrieved successfully",
            "data": {
                "total_drives": total,
                "registration_open": reg_open,
                "upcoming": upcoming,
                "in_progress": in_progress,
                "completed": completed
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='upload-document')
    def upload_document(self, request):
        file_obj = request.FILES.get('file') or request.FILES.get('document')
        if not file_obj:
            return Response({
                "code": 400,
                "message": "No document file provided for upload."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            file_url = upload_file_to_r2(file_obj, folder_name="placement_drives")
            return Response({
                "code": 200,
                "message": "Placement document uploaded successfully to Cloudflare R2.",
                "data": {
                    "document_name": file_obj.name,
                    "document_url": file_url
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Failed to upload document to Cloudflare R2: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='eligible-students')
    def eligible_students(self, request, pk=None):
        drive = self.get_object()
        eligibility = PlacementDriveEligibility.objects.filter(drive=drive).prefetch_related('departments', 'batches', 'batches__department').first()
        if not eligibility:
            return Response({
                "code": 404,
                "message": f"No eligibility criteria configured for drive: {drive.job_role}",
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)
        
        result_data = evaluate_drive_eligible_students(eligibility, request.query_params)
        return Response({
            "code": 200,
            "message": "Eligible students evaluated and retrieved successfully",
            "data": result_data
        }, status=status.HTTP_200_OK)


def calculate_student_academic_metrics(student, grade_systems):
    """
    Computes university CGPA, total registered credits, total earned credits,
    standing backlogs count, and history of arrears count for a given student.
    """
    def get_gp_and_pass(val):
        if val is None or str(val).strip() == '':
            return 0.0, False, '—'
        str_val = str(val).strip().upper()
        for g in grade_systems:
            if g.grade.strip().upper() == str_val:
                return float(g.points), bool(g.is_pass), g.grade
        try:
            num = float(str_val)
            for g in grade_systems:
                if g.min_mark is not None and g.max_mark is not None:
                    if float(g.min_mark) <= num <= float(g.max_mark):
                        return float(g.points), bool(g.is_pass), g.grade
        except ValueError:
            pass
        return 0.0, False, str_val

    univ_subject_attempts = {}
    history_arrears_count = 0

    for m in student.marks.all():
        exam_type_label = 'CIA'
        is_univ_exam = False
        if m.exam:
            if m.exam.exam_type:
                exam_type_label = getattr(m.exam.exam_type, 'exam_type_name', str(m.exam.exam_type))
            else:
                exam_type_label = m.exam.exam_name or 'Internal'
        
        type_str = str(exam_type_label).lower()
        if 'university' in type_str or 'external' in type_str or 'end sem' in type_str or 'semester exam' in type_str:
            is_univ_exam = True

        if is_univ_exam:
            credits_val = float(m.subject.credits) if (m.subject and m.subject.credits is not None) else 0.0
            gp, is_pass_val, grade_letter = get_gp_and_pass(m.marks_obtained)
            
            if not is_pass_val and m.marks_obtained:
                history_arrears_count += 1

            subj_key = f"{m.subject_id}_{m.subject_category or 'THEORY'}"
            if subj_key not in univ_subject_attempts:
                univ_subject_attempts[subj_key] = []
            
            univ_subject_attempts[subj_key].append({
                'id': m.id,
                'credits': credits_val,
                'grade_point': gp,
                'is_pass': is_pass_val,
                'marks_obtained': m.marks_obtained,
            })

    total_reg_credits = 0.0
    total_earned_credits = 0.0
    total_credit_points = 0.0
    standing_backlogs = 0

    for subj_key, attempts in univ_subject_attempts.items():
        sorted_att = sorted(attempts, key=lambda x: x['id'] or 0)
        latest = sorted_att[-1]
        c = latest['credits']
        gp = latest['grade_point']
        if c > 0:
            total_reg_credits += c
            total_credit_points += (c * gp)
            if latest['is_pass']:
                total_earned_credits += c
            else:
                standing_backlogs += 1
        elif not latest['is_pass']:
            standing_backlogs += 1

    cgpa = round(total_credit_points / total_earned_credits, 2) if total_earned_credits > 0 else 0.00

    return {
        'cgpa': cgpa,
        'total_registered_credits': total_reg_credits,
        'total_earned_credits': total_earned_credits,
        'standing_backlogs': standing_backlogs,
        'history_arrears_count': history_arrears_count
    }


def evaluate_drive_eligible_students(eligibility, query_params):
    """
    Evaluates students across target batches and departments against drive eligibility criteria:
    - Minimum CGPA (calculated dynamically using Anna University earned credit points formula)
    - Maximum Allowed Standing Backlogs (latest university attempt != PASS)
    - Target Departments (empty = all)
    - Target Batches (empty = all)
    - Also pre-fetches and attaches StudentPlacementTracking data (attendance, cleared rounds, final status)
    """
    drive = eligibility.drive
    drive_id = eligibility.drive_id
    min_cgpa = float(eligibility.minimum_cgpa or 0.0)
    max_backlogs = int(eligibility.max_backlogs or 0)

    target_dept_ids = list(eligibility.departments.values_list('id', flat=True))
    target_batch_ids = list(eligibility.batches.values_list('id', flat=True))

    grade_systems = list(GradeSystem.objects.filter(is_active=True).order_by('-points'))

    # Pre-fetch existing placement tracking records for this drive
    trackings_qs = StudentPlacementTracking.objects.filter(drive_id=drive_id)
    trackings_map = {t.student_id: t for t in trackings_qs}
    tracked_student_ids = list(trackings_qs.values_list('student_id', flat=True))

    # Query candidate students from target batches and departments
    students_qs = Student.objects.select_related(
        'department',
        'department__program',
        'batch',
        'section',
        'status',
        'application',
        'application__candidate'
    ).prefetch_related(
        'marks',
        'marks__subject',
        'marks__exam',
        'marks__exam__exam_type'
    )

    target_q = Q()
    if target_dept_ids and target_batch_ids:
        target_q = Q(department_id__in=target_dept_ids, batch_id__in=target_batch_ids)
    elif target_dept_ids:
        target_q = Q(department_id__in=target_dept_ids)
    elif target_batch_ids:
        target_q = Q(batch_id__in=target_batch_ids)

    if tracked_student_ids:
        if target_q:
            students_qs = students_qs.filter(target_q | Q(id__in=tracked_student_ids))
    elif target_q:
        students_qs = students_qs.filter(target_q)

    # Exclude students who have been manually removed from this drive
    excluded_student_ids = list(eligibility.excluded_students.values_list('id', flat=True))
    if excluded_student_ids:
        students_qs = students_qs.exclude(id__in=excluded_student_ids)

    # Optional department or batch filter from UI
    dept_filter = query_params.get('department_id') or query_params.get('department')
    if dept_filter:
        students_qs = students_qs.filter(department_id=dept_filter)

    batch_filter = query_params.get('batch_id') or query_params.get('batch')
    if batch_filter:
        students_qs = students_qs.filter(batch_id=batch_filter)

    status_filter = query_params.get('status', 'all').lower()  # 'all', 'eligible', 'ineligible'
    tracking_filter = query_params.get('tracking_status', 'all').lower()  # 'all', 'present', 'absent', 'selected', 'rejected'
    search_query = query_params.get('search', '').strip().lower()

    evaluated_students = []
    total_eligible = 0
    total_ineligible = 0
    sum_eligible_cgpa = 0.0

    total_present = 0
    total_absent = 0
    total_selected = 0
    total_rejected = 0
    total_in_progress = 0

    for student in students_qs:
        # Resolve personal details
        app = student.application
        candidate = app.candidate if app else None
        
        name_val = candidate.name if candidate else None
        email_val = candidate.email if candidate else None
        phone_val = candidate.phone_number if (candidate and getattr(candidate, 'phone_number', None)) else None
        photo_url = ""

        if app and app.form_data and isinstance(app.form_data, dict):
            fd = app.form_data
            pd = fd.get('personal_details', {})
            if isinstance(pd, dict):
                if not name_val:
                    name_val = pd.get('candidate_name') or pd.get('name')
                if not phone_val:
                    phone_val = pd.get('phone') or pd.get('mobile') or pd.get('phone_number')
            if not name_val:
                name_val = fd.get('candidate_name') or fd.get('name')
            if not phone_val:
                phone_val = fd.get('phone') or fd.get('mobile') or fd.get('phone_number')

            if not photo_url:
                photo_url = fd.get('photo', '')

        # Calculate student's latest CGPA and standing backlogs
        metrics = calculate_student_academic_metrics(student, grade_systems)
        cgpa = metrics['cgpa']
        total_reg_credits = metrics['total_registered_credits']
        total_earned_credits = metrics['total_earned_credits']
        standing_backlogs = metrics['standing_backlogs']
        history_arrears_count = metrics['history_arrears_count']

        is_cgpa_eligible = (cgpa >= min_cgpa)
        is_backlog_eligible = (standing_backlogs <= max_backlogs)
        is_eligible = (is_cgpa_eligible and is_backlog_eligible)

        if is_eligible:
            total_eligible += 1
            sum_eligible_cgpa += cgpa
        else:
            total_ineligible += 1

        ineligibility_reasons = []
        if not is_cgpa_eligible:
            ineligibility_reasons.append(f"CGPA ({cgpa:.2f}) is below required minimum ({min_cgpa:.2f})")
        if not is_backlog_eligible:
            ineligibility_reasons.append(f"Standing backlogs ({standing_backlogs}) exceed max allowed ({max_backlogs})")

        sec_str = ""
        if student.section:
            if isinstance(student.section.sections, list):
                sec_str = ", ".join(student.section.sections)
            else:
                sec_str = str(student.section.sections)

        tracking_obj = trackings_map.get(student.id)
        if tracking_obj:
            att_stat = tracking_obj.attendance_status
            fin_stat = tracking_obj.final_status
            if att_stat == 'ABSENT' and fin_stat in ['IN_PROGRESS', 'NOT_ATTENDED']:
                fin_stat = 'REJECTED'
            cleared_r = tracking_obj.cleared_rounds if isinstance(tracking_obj.cleared_rounds, list) else []
            remarks_val = tracking_obj.remarks or ""
            track_id = tracking_obj.id
        else:
            att_stat = 'PENDING'
            fin_stat = 'IN_PROGRESS'
            cleared_r = []
            remarks_val = ""
            track_id = None

        if att_stat == 'PRESENT':
            total_present += 1
        elif att_stat == 'ABSENT':
            total_absent += 1

        if fin_stat == 'SELECTED':
            total_selected += 1
        elif fin_stat == 'REJECTED':
            total_rejected += 1
        elif fin_stat == 'IN_PROGRESS':
            total_in_progress += 1

        tracking_data = {
            'id': track_id,
            'student_id': student.id,
            'drive_id': drive_id,
            'attendance_status': att_stat,
            'cleared_rounds': cleared_r,
            'final_status': fin_stat,
            'remarks': remarks_val,
        }

        student_data = {
            'student_id': student.id,
            'roll_number': student.roll_number or '—',
            'register_number': student.register_number or '—',
            'student_name': name_val or f"Student #{student.id}",
            'student_email': email_val,
            'student_phone': phone_val or '—',
            'student_photo': photo_url,
            'department_id': student.department_id,
            'department_name': student.department.department_name if student.department else '—',
            'department_code': student.department.department_code if student.department else '—',
            'department_short_name': student.department.short_name if (student.department and hasattr(student.department, 'short_name')) else (student.department.department_name if student.department else '—'),
            'batch_id': student.batch_id,
            'batch_name': student.batch.batch if student.batch else '—',
            'section_name': sec_str or '—',
            'cgpa': cgpa,
            'total_registered_credits': total_reg_credits,
            'total_earned_credits': total_earned_credits,
            'standing_backlogs': standing_backlogs,
            'history_arrears': history_arrears_count,
            'is_eligible': is_eligible,
            'is_cgpa_eligible': is_cgpa_eligible,
            'is_backlog_eligible': is_backlog_eligible,
            'ineligibility_reasons': ineligibility_reasons,
            'tracking': tracking_data,
        }

        # Apply search filter
        if search_query:
            match_str = f"{student_data['student_name']} {student_data['roll_number']} {student_data['register_number']} {student_data['student_email'] or ''} {student_data['department_name']} {student_data['batch_name']}".lower()
            if search_query not in match_str:
                continue

        # Apply eligibility status filter
        if status_filter == 'eligible' and not is_eligible:
            continue
        if status_filter == 'ineligible' and is_eligible:
            continue

        # Apply tracking status filter
        if tracking_filter == 'present' and att_stat != 'PRESENT':
            continue
        if tracking_filter == 'absent' and att_stat != 'ABSENT':
            continue
        if tracking_filter == 'selected' and fin_stat != 'SELECTED':
            continue
        if tracking_filter == 'rejected' and fin_stat != 'REJECTED':
            continue
        if tracking_filter == 'in_progress' and fin_stat != 'IN_PROGRESS':
            continue

        evaluated_students.append(student_data)

    # Sort students: eligible first, then by descending CGPA
    evaluated_students.sort(key=lambda s: (not s['is_eligible'], -s['cgpa'], s['student_name']))

    avg_cgpa = round(sum_eligible_cgpa / total_eligible, 2) if total_eligible > 0 else 0.00
    total_evaluated = total_eligible + total_ineligible
    eligible_percentage = round((total_eligible / total_evaluated * 100), 1) if total_evaluated > 0 else 0.0

    return {
        'criteria': {
            'eligibility_id': eligibility.id,
            'drive_id': eligibility.drive_id,
            'job_role': drive.job_role if drive else 'Recruitment Drive',
            'company_name': drive.company.company_name if (drive and drive.company) else 'Hiring Company',
            'drive_type': drive.drive_type if drive else 'FULL_TIME',
            'drive_type_display': drive.get_drive_type_display() if drive else 'Full Time',
            'minimum_cgpa': min_cgpa,
            'max_backlogs': max_backlogs,
            'no_of_rounds': drive.no_of_rounds if drive else 0,
            'rounds': drive.rounds if (drive and drive.rounds) else [],
            'departments': [
                {'id': d.id, 'department_name': d.department_name, 'department_code': d.department_code, 'short_name': d.short_name}
                for d in eligibility.departments.all()
            ],
            'batches': [
                {'id': b.id, 'batch': b.batch, 'department_name': b.department.department_name if b.department else None}
                for b in eligibility.batches.select_related('department').all()
            ],
        },
        'summary': {
            'total_students_evaluated': total_evaluated,
            'total_eligible': total_eligible,
            'total_ineligible': total_ineligible,
            'eligible_percentage': eligible_percentage,
            'average_eligible_cgpa': avg_cgpa,
            'total_present': total_present,
            'total_absent': total_absent,
            'total_selected': total_selected,
            'total_rejected': total_rejected,
            'total_in_progress': total_in_progress,
        },
        'students': evaluated_students,
        'count': len(evaluated_students),
    }


class PlacementDriveEligibilityViewSet(viewsets.ModelViewSet):
    queryset = PlacementDriveEligibility.objects.select_related(
        'drive',
        'drive__company',
        'created_by',
        'updated_by'
    ).prefetch_related(
        'departments',
        'batches',
        'batches__department'
    ).all().order_by('-created_at')
    serializer_class = PlacementDriveEligibilitySerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'drive__job_role',
        'drive__company__company_name',
        'departments__department_name',
        'departments__department_code',
        'batches__batch',
    ]

    filterset_fields = [
        'drive',
        'departments',
        'batches',
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('PlacementDriveEligibility', 'create', {
            'id': instance.id,
            'drive_id': instance.drive_id,
            'job_role': instance.drive.job_role
        })

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('PlacementDriveEligibility', 'update', {
            'id': instance.id,
            'drive_id': instance.drive_id,
            'job_role': instance.drive.job_role
        })

    def perform_destroy(self, instance):
        inst_id = instance.id
        drive_id = instance.drive_id
        role_name = instance.drive.job_role if instance.drive else 'Drive'
        instance.delete()
        broadcast_placement_event('PlacementDriveEligibility', 'delete', {
            'id': inst_id,
            'drive_id': drive_id,
            'job_role': role_name
        })

    def list(self, request, *args, **kwargs):
        # Support optional filter by ?drive_id=<id>
        drive_id = request.query_params.get('drive_id') or request.query_params.get('drive')
        if drive_id:
            self.queryset = self.queryset.filter(drive_id=drive_id)
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibilities retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibility details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement drive eligibility criteria created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibility criteria updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibility criteria deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='by-drive/(?P<drive_id>[^/.]+)')
    def by_drive(self, request, drive_id=None):
        eligibility = self.queryset.filter(drive_id=drive_id).first()
        if not eligibility:
            return Response({
                "code": 200,
                "message": "No eligibility criteria found for this drive",
                "data": None
            }, status=status.HTTP_200_OK)
        serializer = self.get_serializer(eligibility)
        return Response({
            "code": 200,
            "message": "Drive eligibility retrieved successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='eligible-students')
    def eligible_students(self, request, pk=None):
        eligibility = self.get_object()
        result_data = evaluate_drive_eligible_students(eligibility, request.query_params)
        return Response({
            "code": 200,
            "message": "Eligible students evaluated and retrieved successfully",
            "data": result_data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remove-student')
    def remove_ineligible_student(self, request, pk=None):
        """
        Removes an ineligible student from this placement drive evaluation list.
        Enforces that only ineligible students can be removed.
        """
        eligibility = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({
                "code": 400,
                "message": "student_id is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Student not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Calculate student's academic metrics
        grade_systems = list(GradeSystem.objects.filter(is_active=True).order_by('-points'))
        metrics = calculate_student_academic_metrics(student, grade_systems)
        cgpa = metrics['cgpa']
        standing_backlogs = metrics['standing_backlogs']
        min_cgpa = float(eligibility.minimum_cgpa or 0.0)
        max_backlogs = int(eligibility.max_backlogs or 0)

        is_cgpa_eligible = (cgpa >= min_cgpa)
        is_backlog_eligible = (standing_backlogs <= max_backlogs)
        is_eligible = (is_cgpa_eligible and is_backlog_eligible)

        # Check target department and batch constraints
        target_dept_ids = list(eligibility.departments.values_list('id', flat=True))
        target_batch_ids = list(eligibility.batches.values_list('id', flat=True))
        if target_dept_ids and student.department_id not in target_dept_ids:
            is_eligible = False
        if target_batch_ids and student.batch_id not in target_batch_ids:
            is_eligible = False

        if is_eligible:
            return Response({
                "code": 400,
                "message": "Only ineligible students can be removed from the drive evaluation list."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 1. Delete tracking record if exists
        StudentPlacementTracking.objects.filter(drive_id=eligibility.drive_id, student_id=student_id).delete()

        # 2. Add to excluded_students
        eligibility.excluded_students.add(student)

        broadcast_placement_event('PlacementDriveEligibility', 'update', {
            'id': eligibility.id,
            'drive_id': eligibility.drive_id,
            'action': 'remove_ineligible_student',
            'student_id': student_id
        })

        return Response({
            "code": 200,
            "message": f"Ineligible student removed successfully from drive.",
            "data": {
                "student_id": student.id,
                "eligibility_id": eligibility.id,
                "drive_id": eligibility.drive_id
            }
        }, status=status.HTTP_200_OK)


class StudentPlacementTrackingViewSet(viewsets.ModelViewSet):
    queryset = StudentPlacementTracking.objects.select_related(
        'student',
        'drive',
        'drive__company',
        'student__department',
        'student__batch',
        'created_by',
        'updated_by'
    ).all().order_by('-updated_at')
    serializer_class = StudentPlacementTrackingSerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'student__roll_number',
        'student__register_number',
        'drive__job_role',
        'drive__company__company_name',
    ]

    filterset_fields = [
        'student',
        'drive',
        'attendance_status',
        'final_status',
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('StudentPlacementTracking', 'create', {
            'id': instance.id,
            'student_id': instance.student_id,
            'drive_id': instance.drive_id,
            'attendance_status': instance.attendance_status,
            'final_status': instance.final_status
        })

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('StudentPlacementTracking', 'update', {
            'id': instance.id,
            'student_id': instance.student_id,
            'drive_id': instance.drive_id,
            'attendance_status': instance.attendance_status,
            'final_status': instance.final_status
        })

    def perform_destroy(self, instance):
        inst_id = instance.id
        s_id = instance.student_id
        d_id = instance.drive_id
        instance.delete()
        broadcast_placement_event('StudentPlacementTracking', 'delete', {
            'id': inst_id,
            'student_id': s_id,
            'drive_id': d_id
        })

    def list(self, request, *args, **kwargs):
        drive_id = request.query_params.get('drive_id') or request.query_params.get('drive')
        if drive_id:
            self.queryset = self.queryset.filter(drive_id=drive_id)
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement student trackings retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement student tracking detail retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement student tracking record created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement student tracking updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement student tracking deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='upsert')
    def upsert(self, request):
        drive_id = request.data.get('drive_id') or request.data.get('drive')
        student_id = request.data.get('student_id') or request.data.get('student')
        if not drive_id or not student_id:
            return Response({
                "code": 400,
                "message": "drive_id and student_id are required fields."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user if request.user and request.user.is_authenticated else None
        
        defaults = {
            'updated_by': user
        }

        if 'attendance_status' in request.data:
            att = request.data.get('attendance_status')
            if att in AttendanceStatusChoices.values:
                defaults['attendance_status'] = att
                if att == AttendanceStatusChoices.ABSENT:
                    if 'final_status' not in request.data:
                        defaults['final_status'] = PlacementOutcomeChoices.REJECTED
                    defaults['cleared_rounds'] = []

        if 'cleared_rounds' in request.data:
            cr = request.data.get('cleared_rounds')
            if isinstance(cr, list):
                defaults['cleared_rounds'] = cr

        if 'final_status' in request.data:
            fs = request.data.get('final_status')
            if fs in PlacementOutcomeChoices.values:
                defaults['final_status'] = fs

        if 'remarks' in request.data:
            defaults['remarks'] = request.data.get('remarks')

        # Fetch drive rounds to enforce completion before selection
        try:
            drive_obj = PlacementDrive.objects.get(id=drive_id)
            drive_rounds = drive_obj.rounds if (drive_obj and isinstance(drive_obj.rounds, list)) else []
        except PlacementDrive.DoesNotExist:
            drive_rounds = []

        # Check existing tracking object if any
        existing_tr = StudentPlacementTracking.objects.filter(student_id=student_id, drive_id=drive_id).first()
        cleared_rounds_to_check = defaults.get('cleared_rounds') if 'cleared_rounds' in defaults else (existing_tr.cleared_rounds if existing_tr else [])

        # If marking as SELECTED, verify all drive rounds are cleared
        if defaults.get('final_status') == PlacementOutcomeChoices.SELECTED:
            if drive_rounds and len(drive_rounds) > 0:
                missing_rounds = [r for r in drive_rounds if r not in (cleared_rounds_to_check or [])]
                if missing_rounds:
                    return Response({
                        "code": 400,
                        "message": f"Candidate cannot be marked as Selected until all {len(drive_rounds)} round(s) are cleared. Missing: {', '.join(missing_rounds)}"
                    }, status=status.HTTP_400_BAD_REQUEST)

        # If cleared rounds changed and missing some rounds, downgrade SELECTED to IN_PROGRESS
        if drive_rounds and len(drive_rounds) > 0 and cleared_rounds_to_check is not None:
            missing_rounds = [r for r in drive_rounds if r not in (cleared_rounds_to_check or [])]
            if missing_rounds:
                if defaults.get('final_status') == PlacementOutcomeChoices.SELECTED:
                    defaults['final_status'] = PlacementOutcomeChoices.IN_PROGRESS
                elif existing_tr and existing_tr.final_status == PlacementOutcomeChoices.SELECTED and 'final_status' not in request.data:
                    defaults['final_status'] = PlacementOutcomeChoices.IN_PROGRESS

        tracking_obj, created = StudentPlacementTracking.objects.get_or_create(
            student_id=student_id,
            drive_id=drive_id,
            defaults={
                'created_by': user,
                **defaults
            }
        )

        if not created:
            for k, v in defaults.items():
                setattr(tracking_obj, k, v)
            tracking_obj.save()

        # If student was excluded previously in eligibility, un-exclude them
        try:
            elig_obj = PlacementDriveEligibility.objects.filter(drive_id=drive_id).first()
            if elig_obj:
                elig_obj.excluded_students.remove(student_id)
        except Exception:
            pass

        serializer = self.get_serializer(tracking_obj)
        broadcast_placement_event('StudentPlacementTracking', 'update' if not created else 'create', {
            'id': tracking_obj.id,
            'student_id': tracking_obj.student_id,
            'drive_id': tracking_obj.drive_id,
            'attendance_status': tracking_obj.attendance_status,
            'final_status': tracking_obj.final_status
        })

        return Response({
            "code": 200,
            "message": f"Student tracking {'created' if created else 'updated'} successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='by-drive/(?P<drive_id>[^/.]+)')
    def by_drive(self, request, drive_id=None):
        records = self.queryset.filter(drive_id=drive_id)
        serializer = self.get_serializer(records, many=True)
        return Response({
            "code": 200,
            "message": "Placement student tracking records for drive retrieved successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='attendance-choices')
    def attendance_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in AttendanceStatusChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Attendance choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='outcome-choices')
    def outcome_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in PlacementOutcomeChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Outcome choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='search-student')
    def search_student(self, request):
        """
        Search for students by roll number, register number, phone number,
        candidate name, or email to manually add them to a placement drive.
        Calculates and returns current CGPA and standing backlogs.
        """
        query = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
        drive_id = request.query_params.get('drive_id') or request.query_params.get('drive')

        if not query:
            return Response({
                "code": 200,
                "message": "Please enter a search query.",
                "data": []
            }, status=status.HTTP_200_OK)

        q_filter = (
            Q(roll_number__icontains=query) |
            Q(register_number__icontains=query) |
            Q(application__candidate__phone_number__icontains=query) |
            Q(application__candidate__name__icontains=query) |
            Q(application__candidate__email__icontains=query) |
            Q(application__application_no__icontains=query)
        )

        students_qs = Student.objects.filter(q_filter).select_related(
            'department',
            'department__program',
            'batch',
            'section',
            'application',
            'application__candidate'
        ).prefetch_related(
            'marks',
            'marks__subject',
            'marks__exam',
            'marks__exam__exam_type'
        )[:30]

        # Check which students are already tracked for this drive
        existing_tracked_ids = set()
        if drive_id:
            existing_tracked_ids = set(
                StudentPlacementTracking.objects.filter(drive_id=drive_id).values_list('student_id', flat=True)
            )

        grade_systems = list(GradeSystem.objects.filter(is_active=True).order_by('-points'))
        results = []

        for student in students_qs:
            app = student.application
            candidate = app.candidate if app else None
            
            name_val = candidate.name if candidate else None
            email_val = candidate.email if candidate else None
            phone_val = candidate.phone_number if (candidate and getattr(candidate, 'phone_number', None)) else None
            photo_url = ""

            if app and app.form_data and isinstance(app.form_data, dict):
                fd = app.form_data
                pd = fd.get('personal_details', {})
                if isinstance(pd, dict):
                    if not name_val:
                        name_val = pd.get('candidate_name') or pd.get('name')
                    if not phone_val:
                        phone_val = pd.get('phone') or pd.get('mobile') or pd.get('phone_number')
                if not name_val:
                    name_val = fd.get('candidate_name') or fd.get('name')
                if not phone_val:
                    phone_val = fd.get('phone') or fd.get('mobile') or fd.get('phone_number')

                if not photo_url:
                    photo_url = fd.get('photo', '')

            # Calculate academic metrics
            metrics = calculate_student_academic_metrics(student, grade_systems)

            results.append({
                'student_id': student.id,
                'student_name': name_val or f"Student #{student.id}",
                'roll_number': student.roll_number or '—',
                'register_number': student.register_number or '—',
                'student_phone': phone_val or '—',
                'student_email': email_val or '—',
                'student_photo': photo_url,
                'department_id': student.department_id,
                'department_name': student.department.department_name if student.department else '—',
                'department_code': student.department.department_code if student.department else '—',
                'batch_id': student.batch_id,
                'batch_name': student.batch.batch if student.batch else '—',
                'cgpa': metrics['cgpa'],
                'standing_backlogs': metrics['standing_backlogs'],
                'total_earned_credits': metrics['total_earned_credits'],
                'history_arrears': metrics['history_arrears_count'],
                'is_already_added': student.id in existing_tracked_ids,
            })

        return Response({
            "code": 200,
            "message": f"Found {len(results)} student(s)",
            "data": results
        }, status=status.HTTP_200_OK)




