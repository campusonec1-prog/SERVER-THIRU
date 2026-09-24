from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.utils import timezone
from django.http import HttpResponse, Http404
from .models import (
    LMSAssignment, LMSSubmission, AssessmentQuestion, AssessmentOption,
    LMSAssessment, LMSAssessmentQuestionItem, LMSAssessmentAttempt, LMSAssessmentStudentAnswer
)
from .serializers import (
    LMSAssignmentSerializer, LMSSubmissionSerializer,
    AssessmentQuestionSerializer, AssessmentOptionSerializer,
    LMSAssessmentSerializer, LMSAssessmentQuestionItemSerializer,
    StudentAssessmentOptionTakeSerializer, StudentAssessmentQuestionTakeSerializer,
    StudentAssessmentItemTakeSerializer, LMSAssessmentStudentAnswerSerializer,
    LMSAssessmentAttemptSerializer, StudentAssessmentListSerializer
)
from .permissions import LMSPermission, AssessmentQuestionPermission
from common.caching import get_option_cache_version, invalidate_option_cache
from common.r2 import upload_file_to_r2, delete_file_from_r2
from student.models import Student
import urllib.request
import urllib.error
import os
import mimetypes


from django.http import HttpResponse, HttpResponseRedirect, Http404

def _proxy_download(request, file_url, filename=None):
    """
    Directly redirect client to Cloudflare R2 / public URL so large files
    download at high speed without blocking Django Gunicorn web workers.
    """
    if not file_url:
        raise Http404("No file URL provided.")

    file_url_str = str(file_url).strip()
    if file_url_str.startswith("http://") or file_url_str.startswith("https://"):
        return HttpResponseRedirect(file_url_str)

    if os.path.exists(file_url_str):
        from django.http import FileResponse
        return FileResponse(open(file_url_str, 'rb'), as_attachment=True, filename=filename or os.path.basename(file_url_str))

    raise Http404("File not found.")



class LMSPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class LMSAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = LMSAssignmentSerializer
    pagination_class = LMSPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role_name = (user.role.role_name if hasattr(user, 'role') and user.role else '').upper()

        queryset = LMSAssignment.objects.filter(is_active=True).select_related(
            'department', 'batch', 'section', 'subject', 'target_student', 'created_by'
        )

        # Filters from query params
        search = self.request.query_params.get('search')
        work_type = self.request.query_params.get('work_type')
        subject_id = self.request.query_params.get('subject')
        department_id = self.request.query_params.get('department')
        batch_id = self.request.query_params.get('batch')
        section_id = self.request.query_params.get('section')

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        if work_type:
            queryset = queryset.filter(work_type=work_type)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        # Student specific targeted filter
        student_id_param = self.request.query_params.get('student_id')
        if role_name == 'STUDENT' or student_id_param:
            student = None
            if student_id_param and student_id_param.isdigit():
                student = Student.objects.filter(id=student_id_param).first()
            
            if not student and hasattr(user, 'student'):
                student = user.student

            if not student:
                # Try finding student by mobile/name
                student = Student.objects.filter(
                    Q(roll_number__iexact=user.username) | 
                    Q(user__phone_number=user.mobile_number) | 
                    Q(user__name=user.name)
                ).first()

            if student:
                queryset = queryset.filter(
                    Q(target_type='ALL') |
                    Q(target_type='STUDENT', target_student=student) |
                    Q(target_type='SECTION', section=student.section) |
                    Q(target_type='BATCH', batch=student.batch) |
                    Q(target_type='DEPARTMENT', department=student.department)
                )

        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if section_id:
            queryset = queryset.filter(section_id=section_id)

        return queryset.order_by('-id').distinct()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Assignments listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Assignment retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Assignment created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Assignment updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Assignment deleted successfully"
        }, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        # Handle attachment upload to Cloudflare R2
        attachment_file = self.request.FILES.get('attachment')
        save_kwargs = {'created_by': self.request.user, 'is_active': True}
        if attachment_file:
            from common.r2 import upload_file_to_r2
            attachment_url = upload_file_to_r2(attachment_file, folder_name='lms/attachments')
            save_kwargs['attachment'] = attachment_url
        serializer.save(**save_kwargs)

    def perform_update(self, serializer):
        # Handle attachment replacement — upload new file to R2
        attachment_file = self.request.FILES.get('attachment')
        save_kwargs = {'updated_by': self.request.user}
        if attachment_file:
            from common.r2 import upload_file_to_r2
            attachment_url = upload_file_to_r2(attachment_file, folder_name='lms/attachments')
            save_kwargs['attachment'] = attachment_url
        serializer.save(**save_kwargs)

    @action(detail=True, methods=['get'], url_path='download-attachment')
    def download_attachment(self, request, pk=None):
        """Proxy-download the assignment attachment so it forces a file save."""
        assignment = self.get_object()
        if not assignment.attachment:
            raise Http404("This assignment has no attachment.")
        filename = os.path.basename(assignment.attachment.split('?')[0]) or f"assignment_{pk}_attachment"
        return _proxy_download(request, assignment.attachment, filename)

    @action(detail=True, methods=['get'])
    def submissions(self, request, pk=None):
        assignment = self.get_object()
        submissions = assignment.submissions.all().select_related('student', 'student__user', 'evaluated_by')

        status_param = request.query_params.get('status')
        if status_param:
            submissions = submissions.filter(status=status_param)

        paginator = LMSPagination()
        page = paginator.paginate_queryset(submissions, request)
        if page is not None:
            serializer = LMSSubmissionSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        serializer = LMSSubmissionSerializer(submissions, many=True, context={'request': request})
        return Response({
            "code": 200,
            "data": serializer.data
        })


class LMSSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = LMSSubmissionSerializer
    pagination_class = LMSPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role_name = (user.role.role_name if hasattr(user, 'role') and user.role else '').upper()
        
        queryset = LMSSubmission.objects.all().select_related(
            'assignment', 'student', 'student__user', 'evaluated_by'
        )

        assignment_id = self.request.query_params.get('assignment')
        student_id = self.request.query_params.get('student')
        status_param = self.request.query_params.get('status')

        if assignment_id:
            queryset = queryset.filter(assignment_id=assignment_id)
        if status_param:
            queryset = queryset.filter(status=status_param)

        if role_name == 'STUDENT':
            student = getattr(user, 'student', None) or Student.objects.filter(
                Q(user__phone_number=user.mobile_number) | Q(user__name=user.name)
            ).first()
            if student:
                queryset = queryset.filter(student=student)

        elif student_id:
            queryset = queryset.filter(student_id=student_id)

        return queryset

    @action(detail=False, methods=['post'])
    def submit_work(self, request):
        assignment_id = request.data.get('assignment')
        submission_file = request.FILES.get('submission_file')
        student_notes = request.data.get('student_notes', '')
        student_id_param = request.data.get('student_id')

        if not assignment_id or not submission_file:
            return Response({
                "code": 400,
                "message": "Assignment ID and submission_file are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        assignment = LMSAssignment.objects.filter(id=assignment_id, is_active=True).first()
        if not assignment:
            return Response({
                "code": 444,
                "message": "Assignment not found or inactive."
            }, status=status.HTTP_404_NOT_FOUND)

        # Resolve student
        student = None
        if student_id_param and str(student_id_param).isdigit():
            student = Student.objects.filter(id=student_id_param).first()

        if not student and hasattr(request.user, 'student'):
            student = request.user.student

        if not student:
            student = Student.objects.filter(
                Q(roll_number__iexact=request.user.username) | 
                Q(user__phone_number=request.user.mobile_number) | 
                Q(user__name=request.user.name)
            ).first()

        if not student:
            return Response({
                "code": 400,
                "message": "Student profile record not found for your user account."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Determine submission status
        is_late = timezone.now() > assignment.due_date
        sub_status = 'LATE' if is_late else 'SUBMITTED'

        # Upload submission file to Cloudflare R2
        from common.r2 import upload_file_to_r2
        try:
            submission_file_url = upload_file_to_r2(submission_file, folder_name='lms/submissions')
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Failed to upload file to storage: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        submission, created = LMSSubmission.objects.get_or_create(
            assignment=assignment,
            student=student,
            defaults={
                'submission_file': submission_file_url,
                'student_notes': student_notes,
                'status': sub_status,
                'created_by': request.user
            }
        )

        if not created:
            submission.submission_file = submission_file_url
            submission.student_notes = student_notes
            submission.status = sub_status
            submission.submitted_at = timezone.now()
            submission.updated_by = request.user
            submission.save()

        serializer = LMSSubmissionSerializer(submission, context={'request': request})
        return Response({
            "code": 200,
            "message": "Assignment submitted successfully!",
            "data": serializer.data
        }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def evaluate(self, request, pk=None):
        submission = self.get_object()
        obtained_marks = request.data.get('obtained_marks')
        faculty_feedback = request.data.get('faculty_feedback', '')
        status_param = request.data.get('status', 'EVALUATED')

        if obtained_marks is None:
            return Response({
                "code": 400,
                "message": "obtained_marks is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            obtained_marks = float(obtained_marks)
            if obtained_marks < 0 or obtained_marks > float(submission.assignment.total_marks):
                return Response({
                    "code": 400,
                    "message": f"Obtained marks must be between 0 and {submission.assignment.total_marks}."
                }, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({
                "code": 400,
                "message": "obtained_marks must be a valid number."
            }, status=status.HTTP_400_BAD_REQUEST)

        submission.obtained_marks = obtained_marks
        submission.faculty_feedback = faculty_feedback
        submission.status = status_param
        submission.evaluated_at = timezone.now()
        submission.evaluated_by = request.user
        submission.save()

        serializer = LMSSubmissionSerializer(submission, context={'request': request})
        return Response({
            "code": 200,
            "message": "Submission evaluated successfully!",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='download-file')
    def download_file(self, request, pk=None):
        """Proxy-download the student submission file so it forces a file save."""
        submission = self.get_object()
        if not submission.submission_file:
            raise Http404("This submission has no file uploaded.")
        filename = os.path.basename(submission.submission_file.split('?')[0]) or f"submission_{pk}"
        return _proxy_download(request, submission.submission_file, filename)


class AssessmentQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentQuestionSerializer
    permission_classes = [AssessmentQuestionPermission]

    def get_queryset(self):
        return AssessmentQuestion.objects.filter(is_active=True).select_related(
            'subject', 'subject__department', 'subject__regulation', 'subject__semester',
            'exam', 'exam__exam_type'
        ).prefetch_related('options').order_by('-id')

    def _broadcast_change(self, instance, event_name):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': event_name,
                            'payload': AssessmentQuestionSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, question_id):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': 'question_deleted',
                            'payload': {'id': question_id}
                        }
                    }
                )
        except Exception:
            pass

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        department_id = request.query_params.get('department_id') or request.query_params.get('department')
        regulation_id = request.query_params.get('regulation_id') or request.query_params.get('regulation')
        semester_ids = request.query_params.get('semester_ids') or request.query_params.get('semester_id') or request.query_params.get('semester')
        subject_id = request.query_params.get('subject_id') or request.query_params.get('subject')
        question_type = request.query_params.get('question_type')
        exam_id = request.query_params.get('exam_id')
        exam_type_id = request.query_params.get('exam_type_id')
        is_active = request.query_params.get('is_active')
        search = request.query_params.get('search')

        if department_id:
            queryset = queryset.filter(subject__department_id=department_id)
        if regulation_id:
            queryset = queryset.filter(subject__regulation_id=regulation_id)
        
        # Support array / multi-semester filtering
        if semester_ids:
            if isinstance(semester_ids, str):
                sem_list = [s.strip() for s in semester_ids.split(',') if s.strip().isdigit()]
                if sem_list:
                    queryset = queryset.filter(subject__semester_id__in=sem_list)
            elif isinstance(semester_ids, (list, tuple)):
                queryset = queryset.filter(subject__semester_id__in=semester_ids)

        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if question_type:
            queryset = queryset.filter(question_type__iexact=question_type.strip())
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if exam_type_id:
            queryset = queryset.filter(exam__exam_type_id=exam_type_id)
        if is_active:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1', 'yes'])

        if search:
            queryset = queryset.filter(
                Q(question_text__icontains=search) |
                Q(question_type__icontains=search) |
                Q(subject__subject_code__icontains=search) |
                Q(subject__subject_name__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Assessment questions fetched successfully.",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Assessment questions fetched successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "code": 200,
            "message": "Assessment question retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        # Check for uploaded diagram file
        image_file = self.request.FILES.get('question_image')
        question_image_url = None
        if image_file:
            try:
                question_image_url = upload_file_to_r2(image_file, folder_name="assessment_diagrams")
            except Exception as e:
                question_image_url = None

        save_kwargs = {'created_by': tracking_user, 'updated_by': tracking_user}
        if question_image_url:
            save_kwargs['question_image'] = question_image_url

        instance = serializer.save(**save_kwargs)
        self._broadcast_change(instance, 'question_created')

    def create(self, request, *args, **kwargs):
        # Support JSON string parsed options if sent via FormData
        import json
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if isinstance(data.get('options'), str):
            try:
                data['options'] = json.loads(data['options'])
            except Exception:
                pass

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({
            "code": 201,
            "message": "Question created successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        instance = serializer.instance
        image_file = self.request.FILES.get('question_image')
        remove_image = str(self.request.data.get('remove_question_image', '')).lower() in ['true', '1']

        save_kwargs = {'updated_by': tracking_user}

        if image_file:
            if instance and instance.question_image:
                try:
                    delete_file_from_r2(instance.question_image)
                except Exception:
                    pass
            try:
                question_image_url = upload_file_to_r2(image_file, folder_name="assessment_diagrams")
                save_kwargs['question_image'] = question_image_url
            except Exception:
                pass
        elif remove_image:
            if instance and instance.question_image:
                try:
                    delete_file_from_r2(instance.question_image)
                except Exception:
                    pass
            save_kwargs['question_image'] = None

        instance = serializer.save(**save_kwargs)
        self._broadcast_change(instance, 'question_updated')

    def update(self, request, *args, **kwargs):
        import json
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if isinstance(data.get('options'), str):
            try:
                data['options'] = json.loads(data['options'])
            except Exception:
                pass

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            "code": 200,
            "message": "Question updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        question_id = instance.id
        self.perform_destroy(instance)
        self._broadcast_delete(question_id)
        return Response({
            "code": 200,
            "message": "Question deleted successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        """
        Endpoint for creating multiple questions at once from the Question Bank Builder.
        Payload format:
        {
          "questions": [
             { "subject": 1, "exam": 8, "question_text": "...", "marks": 1, "options": [...], "answer": "..." },
             ...
          ]
        }
        """
        questions_data = request.data.get('questions', [])
        if not questions_data or not isinstance(questions_data, list):
            return Response({
                "code": 400,
                "message": "A valid 'questions' array is required for bulk creation."
            }, status=status.HTTP_400_BAD_REQUEST)

        created_instances = []
        errors = []

        user = request.user if request.user and request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        for idx, q_item in enumerate(questions_data):
            serializer = self.get_serializer(data=q_item)
            if serializer.is_valid():
                instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
                created_instances.append(instance)
                self._broadcast_change(instance, 'question_created')
            else:
                errors.append({"item": idx + 1, "errors": serializer.errors})

        if errors and not created_instances:
            return Response({
                "code": 400,
                "message": "Failed to create questions due to validation errors.",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        result_serializer = self.get_serializer(created_instances, many=True)
        return Response({
            "code": 201,
            "message": f"Successfully created {len(created_instances)} question(s).",
            "data": result_serializer.data,
            "errors": errors if errors else None
        }, status=status.HTTP_201_CREATED)


class LMSAssessmentViewSet(viewsets.ModelViewSet):
    serializer_class = LMSAssessmentSerializer
    pagination_class = LMSPagination
    permission_classes = [LMSPermission]

    def get_queryset(self):
        queryset = LMSAssessment.objects.filter(is_active=True).select_related(
            'department', 'batch', 'section', 'semester', 'regulation', 'subject', 'created_by'
        ).prefetch_related('items__question__options').order_by('-id')

        search = self.request.query_params.get('search')
        department_id = self.request.query_params.get('department')
        batch_id = self.request.query_params.get('batch')
        section_id = self.request.query_params.get('section')
        semester_id = self.request.query_params.get('semester')
        regulation_id = self.request.query_params.get('regulation')
        subject_id = self.request.query_params.get('subject')

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if regulation_id:
            queryset = queryset.filter(regulation_id=regulation_id)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        return queryset

    def _broadcast_change(self, instance, event_name):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': event_name,
                            'payload': LMSAssessmentSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, assessment_id):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': 'assessment_deleted',
                            'payload': {'id': assessment_id}
                        }
                    }
                )
        except Exception:
            pass

    def perform_create(self, serializer):
        instance = serializer.save()
        self._broadcast_change(instance, 'assessment_created')

    def perform_update(self, serializer):
        instance = serializer.save()
        self._broadcast_change(instance, 'assessment_updated')

    def perform_destroy(self, instance):
        assessment_id = instance.id
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        self._broadcast_delete(assessment_id)


# ─── Student Assessment ViewSet ──────────────────────────────────────────────

class StudentAssessmentViewSet(viewsets.ViewSet):
    """
    Handles student assessment workflows:
    - Listing assessments (Ongoing, Upcoming, Completed, Missed)
    - Starting an assessment session (returns question paper without solutions)
    - Submitting an assessment with instant evaluation and database score storage
    - Viewing completed assessment results and solutions review
    """
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_student(self, request):
        student_id = request.query_params.get('student_id') or request.data.get('student_id')
        if student_id:
            try:
                return Student.objects.select_related('department', 'batch', 'section').get(id=student_id)
            except Student.DoesNotExist:
                return None
        
        # Try from user profile
        if hasattr(request.user, 'student_profile') and request.user.student_profile:
            return request.user.student_profile
        
        # Try finding student where user_id or email matches
        student = Student.objects.filter(user__email=request.user.email).select_related('department', 'batch', 'section').first()
        return student

    @action(detail=False, methods=['get'])
    def list_student_assessments(self, request):
        student = self._resolve_student(request)
        if not student:
            return Response({
                "code": 400,
                "message": "Student record not found. Please provide a valid student_id.",
                "data": []
            }, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()

        # Query assessments targeting this student's exact department, batch, and section criteria
        filter_kwargs = {
            'is_active': True,
            'department_id': student.department_id,
            'batch_id': student.batch_id,
        }
        if student.section_id:
            filter_kwargs['section_id'] = student.section_id
        else:
            filter_kwargs['section__isnull'] = True

        assessments_qs = LMSAssessment.objects.filter(
            **filter_kwargs
        ).select_related('subject', 'department', 'batch', 'section', 'semester', 'regulation').order_by('-id')

        # Prefetch attempts by this student
        attempts_map = {
            att.assessment_id: att
            for att in LMSAssessmentAttempt.objects.filter(student=student, assessment__in=assessments_qs)
        }

        assessments_list = []
        counts = {
            'all': 0,
            'ongoing': 0,
            'upcoming': 0,
            'completed': 0,
            'missed': 0
        }

        for ass in assessments_qs:
            ass.user_attempt = attempts_map.get(ass.id)
            serialized = StudentAssessmentListSerializer(ass, context={'student': student}).data
            assessments_list.append(serialized)
            
            st = serialized.get('status')
            counts['all'] += 1
            if st == 'ONGOING':
                counts['ongoing'] += 1
            elif st == 'UPCOMING':
                counts['upcoming'] += 1
            elif st == 'COMPLETED':
                counts['completed'] += 1
            elif st == 'MISSED':
                counts['missed'] += 1

        return Response({
            "code": 200,
            "message": "Student assessments retrieved successfully",
            "data": assessments_list,
            "counts": counts
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def start_assessment(self, request, pk=None):
        student = self._resolve_student(request)
        if not student:
            return Response({
                "code": 400,
                "message": "Student record not found.",
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            assessment = LMSAssessment.objects.select_related('subject', 'department', 'batch', 'section').get(pk=pk, is_active=True)
        except LMSAssessment.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Assessment not found or is inactive."
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate that student strictly matches the assessment criteria: department, batch, section
        if assessment.department_id != student.department_id:
            dept_name = assessment.department.department_name if assessment.department else ''
            return Response({
                "code": 403,
                "message": f"This assessment is restricted to {dept_name} department students."
            }, status=status.HTTP_403_FORBIDDEN)

        if assessment.batch_id != student.batch_id:
            batch_name = assessment.batch.batch if assessment.batch else ''
            return Response({
                "code": 403,
                "message": f"This assessment is restricted to batch {batch_name} students."
            }, status=status.HTTP_403_FORBIDDEN)

        if assessment.section_id and assessment.section_id != student.section_id:
            sec_name = assessment.section.section_name if assessment.section else ''
            return Response({
                "code": 403,
                "message": f"This assessment is restricted to Section {sec_name} students."
            }, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()

        # Check start time
        if now < assessment.start_time:
            return Response({
                "code": 400,
                "message": f"This assessment is scheduled to start at {assessment.start_time.strftime('%d %b %Y, %I:%M %p')}."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check end time
        if now > assessment.end_time:
            return Response({
                "code": 400,
                "message": f"This assessment window ended on {assessment.end_time.strftime('%d %b %Y, %I:%M %p')}."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check existing attempt
        attempt, created = LMSAssessmentAttempt.objects.get_or_create(
            assessment=assessment,
            student=student,
            defaults={
                'status': 'IN_PROGRESS',
                'total_questions': assessment.total_questions,
                'total_marks': assessment.total_marks
            }
        )

        if not created and attempt.status in ['SUBMITTED', 'AUTO_SUBMITTED', 'EVALUATED']:
            return Response({
                "code": 400,
                "message": "You have already completed this assessment."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate time remaining
        remaining_window_seconds = max(0, int((assessment.end_time - now).total_seconds()))
        if assessment.duration_minutes > 0:
            elapsed_seconds = max(0, int((now - attempt.started_at).total_seconds()))
            allowed_seconds = assessment.duration_minutes * 60
            remaining_seconds = max(0, min(allowed_seconds - elapsed_seconds, remaining_window_seconds))
        else:
            remaining_seconds = remaining_window_seconds

        # Fetch question items
        items = list(
            LMSAssessmentQuestionItem.objects.filter(assessment=assessment)
            .select_related('question')
            .prefetch_related('question__options')
            .order_by('order', 'id')
        )

        if assessment.shuffle_questions:
            import random
            random.shuffle(items)

        items_data = StudentAssessmentItemTakeSerializer(
            items,
            many=True,
            context={'shuffle_options': assessment.shuffle_options}
        ).data

        return Response({
            "code": 200,
            "message": "Assessment started successfully",
            "data": {
                "assessment_id": assessment.id,
                "title": assessment.title,
                "description": assessment.description,
                "subject_name": assessment.subject.subject_name,
                "subject_code": assessment.subject.subject_code,
                "total_questions": len(items),
                "total_marks": float(assessment.total_marks),
                "duration_minutes": assessment.duration_minutes,
                "remaining_seconds": remaining_seconds,
                "started_at": attempt.started_at,
                "end_time": assessment.end_time,
                "questions": items_data
            }
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def submit_assessment(self, request, pk=None):
        student = self._resolve_student(request)
        if not student:
            return Response({
                "code": 400,
                "message": "Student record not found."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            assessment = LMSAssessment.objects.select_related('subject', 'department', 'batch', 'section').get(pk=pk)
        except LMSAssessment.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Assessment not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate that student strictly matches the assessment criteria
        if (
            assessment.department_id != student.department_id or
            assessment.batch_id != student.batch_id or
            (assessment.section_id and assessment.section_id != student.section_id)
        ):
            return Response({
                "code": 403,
                "message": "You are not authorized to submit this assessment as your department, batch, or section does not match."
            }, status=status.HTTP_403_FORBIDDEN)

        attempt = LMSAssessmentAttempt.objects.filter(assessment=assessment, student=student).first()
        if not attempt:
            attempt = LMSAssessmentAttempt.objects.create(
                assessment=assessment,
                student=student,
                status='IN_PROGRESS'
            )

        if attempt.status in ['SUBMITTED', 'AUTO_SUBMITTED', 'EVALUATED']:
            # Already submitted, return result
            return Response({
                "code": 200,
                "message": "Assessment was already submitted.",
                "data": LMSAssessmentAttemptSerializer(attempt).data
            }, status=status.HTTP_200_OK)

        answers_payload = request.data.get('answers', [])
        time_taken_seconds = request.data.get('time_taken_seconds', 0)
        is_auto_submit = request.data.get('is_auto_submit', False)

        # Index answers payload by question_id
        answers_dict = {}
        for ans in answers_payload:
            qid = ans.get('question_id')
            if qid is not None:
                answers_dict[int(qid)] = ans

        # Fetch all questions and options for this assessment
        items = list(
            LMSAssessmentQuestionItem.objects.filter(assessment=assessment)
            .select_related('question')
            .prefetch_related('question__options')
        )

        total_questions = len(items)
        attempted_count = 0
        correct_count = 0
        wrong_count = 0
        skipped_count = 0
        total_obtained_marks = 0.0
        calculated_total_marks = 0.0

        for item in items:
            q = item.question
            q_marks = float(item.marks or q.marks or 1.0)
            calculated_total_marks += q_marks

            ans_entry = answers_dict.get(q.id)
            selected_option_ids = []
            text_answer = None

            if ans_entry:
                selected_option_ids = [int(oid) for oid in ans_entry.get('selected_option_ids', []) if str(oid).isdigit()]
                text_answer = ans_entry.get('text_answer', '').strip()

            has_answered = bool(selected_option_ids) or bool(text_answer)

            is_correct = False
            marks_awarded = 0.0

            if not has_answered:
                skipped_count += 1
            else:
                attempted_count += 1

                if q.question_type in ['Single Choice', 'True OR False']:
                    correct_option = q.options.filter(is_correct=True).first()
                    if correct_option and len(selected_option_ids) == 1 and selected_option_ids[0] == correct_option.id:
                        is_correct = True
                        marks_awarded = q_marks
                        correct_count += 1
                        total_obtained_marks += q_marks
                    else:
                        wrong_count += 1

                elif q.question_type == 'Multiple Choice':
                    correct_option_ids = set(q.options.filter(is_correct=True).values_list('id', flat=True))
                    student_chosen_ids = set(selected_option_ids)
                    if correct_option_ids == student_chosen_ids and len(correct_option_ids) > 0:
                        is_correct = True
                        marks_awarded = q_marks
                        correct_count += 1
                        total_obtained_marks += q_marks
                    else:
                        wrong_count += 1

                elif q.question_type == 'Short Answers':
                    # Exact or case-insensitive match with model answer if specified
                    if q.answer and text_answer and q.answer.strip().lower() == text_answer.strip().lower():
                        is_correct = True
                        marks_awarded = q_marks
                        correct_count += 1
                        total_obtained_marks += q_marks
                    else:
                        wrong_count += 1
                else:
                    # File Ups / other
                    wrong_count += 1

            # Save student answer record
            LMSAssessmentStudentAnswer.objects.update_or_create(
                attempt=attempt,
                question=q,
                defaults={
                    'selected_option_ids': selected_option_ids,
                    'text_answer': text_answer,
                    'is_correct': is_correct,
                    'marks_awarded': marks_awarded
                }
            )

        now = timezone.now()
        percentage = (total_obtained_marks / calculated_total_marks * 100) if calculated_total_marks > 0 else 0.0

        attempt.submitted_at = now
        attempt.status = 'AUTO_SUBMITTED' if is_auto_submit else 'SUBMITTED'
        attempt.total_questions = total_questions
        attempt.attempted_count = attempted_count
        attempt.correct_count = correct_count
        attempt.wrong_count = wrong_count
        attempt.skipped_count = skipped_count
        attempt.total_marks = calculated_total_marks
        attempt.obtained_marks = total_obtained_marks
        attempt.percentage = round(percentage, 2)
        attempt.time_taken_seconds = int(time_taken_seconds) or max(0, int((now - attempt.started_at).total_seconds()))
        attempt.save()

        # WebSocket broadcast for real-time tracking
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': 'student_assessment_submitted',
                            'payload': {
                                'assessment_id': assessment.id,
                                'student_id': student.id,
                                'obtained_marks': float(attempt.obtained_marks),
                                'total_marks': float(attempt.total_marks),
                                'percentage': float(attempt.percentage)
                            }
                        }
                    }
                )
        except Exception:
            pass

        result_data = LMSAssessmentAttemptSerializer(attempt).data
        return Response({
            "code": 200,
            "message": "Assessment submitted and evaluated successfully",
            "data": result_data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        student = self._resolve_student(request)
        if not student:
            return Response({
                "code": 400,
                "message": "Student record not found."
            }, status=status.HTTP_400_BAD_REQUEST)

        attempt = LMSAssessmentAttempt.objects.filter(
            assessment_id=pk,
            student=student
        ).select_related('assessment', 'assessment__subject', 'student').prefetch_related(
            'student_answers__question__options'
        ).first()

        if not attempt:
            return Response({
                "code": 404,
                "message": "No completed attempt found for this assessment."
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "code": 200,
            "message": "Assessment result retrieved successfully",
            "data": LMSAssessmentAttemptSerializer(attempt).data
        }, status=status.HTTP_200_OK)



