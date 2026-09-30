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
    IndustryChoices,
    DriveTypeChoices,
    DriveStatusChoices
)
from .serializers import (
    PlacementCompanySerializer,
    PlacementDriveSerializer,
    PlacementDriveEligibilitySerializer
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


def evaluate_drive_eligible_students(eligibility, query_params):
    """
    Evaluates students across target batches and departments against drive eligibility criteria:
    - Minimum CGPA (calculated dynamically using Anna University earned credit points formula)
    - Maximum Allowed Standing Backlogs (latest university attempt != PASS)
    - Target Departments (empty = all)
    - Target Batches (empty = all)
    """
    min_cgpa = float(eligibility.minimum_cgpa or 0.0)
    max_backlogs = int(eligibility.max_backlogs or 0)

    target_dept_ids = list(eligibility.departments.values_list('id', flat=True))
    target_batch_ids = list(eligibility.batches.values_list('id', flat=True))

    grade_systems = list(GradeSystem.objects.filter(is_active=True).order_by('-points'))

    def get_grade_point_and_pass(val):
        if val is None or str(val).strip() == '':
            return 0.0, False, '—'
        str_val = str(val).strip().upper()
        
        # 1. Match by Grade Letter in GradeSystem table
        for g in grade_systems:
            if g.grade.strip().upper() == str_val:
                return float(g.points), bool(g.is_pass), g.grade
        
        # 2. Match by Numeric Mark range
        try:
            num = float(str_val)
            for g in grade_systems:
                if g.min_mark is not None and g.max_mark is not None:
                    if float(g.min_mark) <= num <= float(g.max_mark):
                        return float(g.points), bool(g.is_pass), g.grade
        except ValueError:
            pass
        
        return 0.0, False, str_val

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

    if target_dept_ids:
        students_qs = students_qs.filter(department_id__in=target_dept_ids)
    if target_batch_ids:
        students_qs = students_qs.filter(batch_id__in=target_batch_ids)

    # Optional department or batch filter from UI
    dept_filter = query_params.get('department_id') or query_params.get('department')
    if dept_filter:
        students_qs = students_qs.filter(department_id=dept_filter)

    batch_filter = query_params.get('batch_id') or query_params.get('batch')
    if batch_filter:
        students_qs = students_qs.filter(batch_id=batch_filter)

    status_filter = query_params.get('status', 'all').lower()  # 'all', 'eligible', 'ineligible'
    search_query = query_params.get('search', '').strip().lower()

    evaluated_students = []
    total_eligible = 0
    total_ineligible = 0
    sum_eligible_cgpa = 0.0

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

        # Gather university examination marks
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
                gp, is_pass_val, grade_letter = get_grade_point_and_pass(m.marks_obtained)
                
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

        # Calculate student's latest CGPA and standing backlogs
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
        }

        # Apply search filter
        if search_query:
            match_str = f"{student_data['student_name']} {student_data['roll_number']} {student_data['register_number']} {student_data['student_email'] or ''} {student_data['department_name']} {student_data['batch_name']}".lower()
            if search_query not in match_str:
                continue

        # Apply status filter
        if status_filter == 'eligible' and not is_eligible:
            continue
        if status_filter == 'ineligible' and is_eligible:
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
            'job_role': eligibility.drive.job_role if eligibility.drive else 'Recruitment Drive',
            'company_name': eligibility.drive.company.company_name if (eligibility.drive and eligibility.drive.company) else 'Hiring Company',
            'drive_type': eligibility.drive.drive_type if eligibility.drive else 'FULL_TIME',
            'drive_type_display': eligibility.drive.get_drive_type_display() if eligibility.drive else 'Full Time',
            'minimum_cgpa': min_cgpa,
            'max_backlogs': max_backlogs,
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


