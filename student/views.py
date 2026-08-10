from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from .models import StudentStatus, Student
from .serializers import StudentStatusSerializer, StudentSerializer
from users.permissions import IsAdminUser


class StudentStatusViewSet(viewsets.ModelViewSet):
    queryset = StudentStatus.objects.all().order_by('id')
    serializer_class = StudentStatusSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Student status not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student statuses listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student status retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Student status created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student status updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student status deleted successfully"
        }, status=status.HTTP_200_OK)


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all().order_by('id')
    serializer_class = StudentSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Student not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Students listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Student created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student deleted successfully"
        }, status=status.HTTP_200_OK)


from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsMarksManager
from .models import Marks
from .serializers import MarksSerializer
from institution.models import Exam
from subject.models import Subject

class MarksViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ['create', 'update']:
            return [IsAuthenticated(), IsMarksManager()]
        # Token is needed for GET, but no role restriction is required
        return [IsAuthenticated()]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Marks records not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            return Response({
                "code": 400,
                "message": str(exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request):
        queryset = Marks.objects.all().order_by('id')
        exam_id = request.query_params.get('exam_id')
        subject_id = request.query_params.get('subject_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')

        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if batch_id:
            queryset = queryset.filter(student__batch_id=batch_id)
        if section_id:
            queryset = queryset.filter(student__section_id=section_id)

        serializer = MarksSerializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Marks records listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        # pk represents student_id
        student_id = pk
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            raise Http404()
        
        queryset = Marks.objects.filter(student_id=student_id).order_by('id')
        serializer = MarksSerializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": f"Marks records for student {student_id} retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def create(self, request):
        # We handle bulk insert/update in create endpoint
        return self._save_marks(request, is_create=True)

    def update(self, request, pk=None):
        # Update can also do bulk update/insert of entries
        return self._save_marks(request, is_create=False)

    def _save_marks(self, request, is_create):
        exam_id = request.data.get('exam_id')
        subject_id = request.data.get('subject_id')
        marks_entries = request.data.get('marks_entries')

        if not exam_id or not subject_id or not isinstance(marks_entries, list):
            return Response({
                "code": 400,
                "message": "exam_id, subject_id and a list of marks_entries are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check for duplicate student_id in the payload
        seen_students = set()
        for entry in marks_entries:
            student_id = entry.get('student_id')
            if student_id in seen_students:
                return Response({
                    "code": 400,
                    "message": f"Duplicate student entry with ID {student_id} found in the payload."
                }, status=status.HTTP_400_BAD_REQUEST)
            seen_students.add(student_id)

        # Validate exam and subject exist
        try:
            exam = Exam.objects.get(pk=exam_id)
            subject = Subject.objects.get(pk=subject_id)
        except Exam.DoesNotExist:
            return Response({
                "code": 400,
                "message": f"Exam with ID {exam_id} does not exist."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Subject.DoesNotExist:
            return Response({
                "code": 400,
                "message": f"Subject with ID {subject_id} does not exist."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        saved_marks = []
        broadcast_payload_entries = []

        try:
            with transaction.atomic():
                for entry in marks_entries:
                    student_id = entry.get('student_id')
                    marks_obtained = str(entry.get('marks_obtained', '')).strip()

                    if not student_id or marks_obtained == '':
                        raise ValidationError("student_id and marks_obtained are required for each entry.")

                    try:
                        student = Student.objects.get(pk=student_id)
                    except Student.DoesNotExist:
                        raise ValidationError(f"Student with ID {student_id} does not exist.")

                    if is_create:
                        if Marks.objects.filter(student=student, exam=exam, subject=subject).exists():
                            raise ValidationError(f"Marks record already exists for student ID {student_id}, exam ID {exam_id}, and subject ID {subject_id}.")

                    # Create or update marks record
                    marks_instance, created = Marks.objects.get_or_create(
                        student=student,
                        exam=exam,
                        subject=subject,
                        defaults={
                            'marks_obtained': marks_obtained,
                            'created_by': tracking_user,
                            'updated_by': tracking_user
                        }
                    )

                    if not created:
                        marks_instance.marks_obtained = marks_obtained
                        marks_instance.updated_by = tracking_user
                        marks_instance.save()

                    saved_marks.append(marks_instance)
                    broadcast_payload_entries.append({
                        'student_id': student.id,
                        'roll_number': student.roll_number,
                        'student_name': student.user.name if hasattr(student, 'user') else "",
                        'marks_obtained': marks_obtained
                    })
        except ValidationError as e:
            return Response({
                "code": 400,
                "message": str(e.detail[0] if isinstance(e.detail, list) else e.detail)
            }, status=status.HTTP_400_BAD_REQUEST)

        # Websocket Broadcast
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
                            'event': 'marks_created' if is_create else 'marks_updated',
                            'payload': {
                                'exam_id': exam.id,
                                'exam_name': exam.exam_name,
                                'subject_id': subject.id,
                                'subject_code': subject.subject_code,
                                'entries': broadcast_payload_entries
                            }
                        }
                    }
                )
        except Exception as e:
            # Prevent failure to broadcast from failing the HTTP request
            pass

        serializer = MarksSerializer(saved_marks, many=True)
        return Response({
            "code": 201 if is_create else 200,
            "message": "Marks recorded successfully." if is_create else "Marks updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED if is_create else status.HTTP_200_OK)


from .models import CounsellingReport
from .serializers import CounsellingReportSerializer

class CounsellingReportViewSet(viewsets.ModelViewSet):
    queryset = CounsellingReport.objects.all().order_by('-report_date', '-id')
    serializer_class = CounsellingReportSerializer

    def get_permissions(self):
        if self.action == 'create':
            from users.permissions import IsCounsellingCreator
            return [IsAuthenticated(), IsCounsellingCreator()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsMarksManager()]
        # Token is needed for GET, but no role restriction is required
        return [IsAuthenticated()]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Counselling report not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'counselling_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'counselling_updated')

    def perform_destroy(self, instance):
        report_id = instance.id
        student_id = instance.student.id
        instance.delete()
        self._broadcast_delete(report_id, student_id)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        student_id = request.query_params.get('student_id')
        semester_id = request.query_params.get('semester_id')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Counselling reports listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Counselling report created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report deleted successfully."
        }, status=status.HTTP_200_OK)

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
                            'payload': CounsellingReportSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, report_id, student_id):
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
                            'event': 'counselling_deleted',
                            'payload': {
                                'id': report_id,
                                'student_id': student_id
                            }
                        }
                    }
                )
        except Exception:
            pass



