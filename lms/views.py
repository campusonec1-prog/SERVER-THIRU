from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.utils import timezone
from django.http import HttpResponse, Http404
from .models import LMSAssignment, LMSSubmission
from .serializers import LMSAssignmentSerializer, LMSSubmissionSerializer
from student.models import Student
import urllib.request
import urllib.error
import os
import mimetypes


def _proxy_download(request, file_url, filename=None):
    """
    Fetch a remote file (e.g. from Cloudflare R2) server-side and stream it
    back to the browser with Content-Disposition: attachment so it always
    downloads with its correct original file extension (pdf, docx, png, etc.).
    """
    if not file_url:
        raise Http404("No file URL provided.")

    # Extract original filename and extension from the URL
    orig_filename = os.path.basename(file_url.split("?")[0]) or "download"
    _, ext = os.path.splitext(orig_filename)

    try:
        req = urllib.request.Request(file_url, headers={"User-Agent": "IMS-Proxy/1.0"})
        with urllib.request.urlopen(req, timeout=30) as remote:
            content = remote.read()
            content_type = remote.headers.get("Content-Type", "application/octet-stream").split(";")[0]
            if not ext:
                guessed_ext = mimetypes.guess_extension(content_type)
                if guessed_ext:
                    ext = guessed_ext
    except urllib.error.HTTPError as e:
        raise Http404(f"Remote file returned {e.code}.")
    except Exception:
        raise Http404("Failed to fetch the remote file.")

    # If a custom filename was provided, ensure it keeps the true file extension
    if filename:
        if ext and not filename.lower().endswith(ext.lower()):
            filename = f"{filename}{ext}"
    else:
        filename = orig_filename

    # Sanitise filename for the Content-Disposition header
    safe_name = filename.encode("ascii", "ignore").decode("ascii") or "download"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    response["Access-Control-Expose-Headers"] = "Content-Disposition"
    response["Content-Length"] = len(content)
    return response



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

        # Auto-heal any existing records created with default HTML boolean parsing (is_active=False)
        LMSAssignment.objects.filter(is_active=False).update(is_active=True)

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
