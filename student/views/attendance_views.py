import logging
from django.http import Http404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from ..models import Student, FacultyActivity, StudentAttendance
from ..serializers import FacultyActivitySerializer, StudentAttendanceSerializer
from ..permissions import AttendancePermission

logger = logging.getLogger(__name__)


class FacultyActivityViewSet(viewsets.ModelViewSet):
    queryset = FacultyActivity.objects.all().order_by('-date', '-id')
    serializer_class = FacultyActivitySerializer
    permission_classes = [AttendancePermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Faculty activity not found"
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
                "message": str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'activity_created')

    def perform_update(self, serializer):
        user = self.request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'activity_updated')

    def perform_destroy(self, instance):
        activity_id = instance.id
        instance.delete()
        self._broadcast_change({'id': activity_id}, 'activity_deleted')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        user = request.user
        role_name = ""
        if user and user.is_authenticated and hasattr(user, 'role') and user.role:
            role_name = user.role.role_name.upper().replace(' ', '_')

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        date = request.query_params.get('date')
        timetable_id = request.query_params.get('timetable_id')
        timetable_ids = request.query_params.get('timetable_ids')

        if role_name not in ['ADMIN', 'ADMINISTRATOR']:
            if not (date_from or date_to or date or timetable_id or timetable_ids):
                queryset = queryset.filter(created_by=user)

        if date:
            queryset = queryset.filter(date=date)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if timetable_id:
            queryset = queryset.filter(timetable_id=timetable_id)
        if timetable_ids:
            id_list = [tid.strip() for tid in timetable_ids.split(',') if tid.strip().isdigit()]
            if id_list:
                queryset = queryset.filter(timetable_id__in=id_list)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Faculty activities listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Faculty activity retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Faculty activity registered successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Faculty activity updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Faculty activity deleted successfully"
        }, status=status.HTTP_200_OK)

    def _broadcast_change(self, instance, event_name):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                payload = FacultyActivitySerializer(instance).data if hasattr(instance, 'date') else instance
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': event_name,
                            'payload': payload
                        }
                    }
                )
        except Exception:
            pass


class StudentAttendanceViewSet(viewsets.ModelViewSet):
    queryset = StudentAttendance.objects.all().order_by('id')
    serializer_class = StudentAttendanceSerializer
    permission_classes = [AttendancePermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Attendance record not found"
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
                "message": str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        activity_id = request.query_params.get('faculty_activity_id')
        queryset = self.get_queryset()
        if activity_id:
            queryset = queryset.filter(faculty_activity_id=activity_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Student attendance listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='submit')
    def bulk_submit(self, request):
        activity_id = request.data.get('faculty_activity_id')
        attendance_entries = request.data.get('attendance_entries')

        if not activity_id or not isinstance(attendance_entries, list):
            return Response({
                "code": 400,
                "message": "faculty_activity_id and a list of attendance_entries are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            activity = FacultyActivity.objects.get(pk=activity_id)
        except FacultyActivity.DoesNotExist:
            return Response({
                "code": 400,
                "message": f"Faculty activity with ID {activity_id} does not exist."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        saved_entries = []
        from django.db import transaction

        try:
            with transaction.atomic():
                for entry in attendance_entries:
                    student_id = entry.get('student_id')
                    status_val = entry.get('status', 'P').strip().upper()

                    if status_val not in ['P', 'AB', 'OD']:
                        raise ValidationError(f"Invalid status '{status_val}'. Allowed values are P, AB, OD.")

                    try:
                        student = Student.objects.get(pk=student_id)
                    except Student.DoesNotExist:
                        raise ValidationError(f"Student with ID {student_id} does not exist.")

                    attendance_instance, created = StudentAttendance.objects.get_or_create(
                        faculty_activity=activity,
                        student=student,
                        defaults={
                            'status': status_val,
                            'created_by': tracking_user,
                            'updated_by': tracking_user
                        }
                    )

                    if not created:
                        attendance_instance.status = status_val
                        attendance_instance.updated_by = tracking_user
                        attendance_instance.save()

                    saved_entries.append(attendance_instance)
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
                            'event': 'attendance_submitted',
                            'payload': {
                                'faculty_activity_id': activity.id,
                                'count': len(saved_entries)
                            }
                        }
                    }
                )
        except Exception:
            pass

        return Response({
            "code": 200,
            "message": f"Successfully registered attendance for {len(saved_entries)} students.",
            "data": StudentAttendanceSerializer(saved_entries, many=True).data
        }, status=status.HTTP_200_OK)
