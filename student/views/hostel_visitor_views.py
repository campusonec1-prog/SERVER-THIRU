import logging
from django.http import Http404
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from ..models import HostelVisitorLog, Student
from ..serializers import HostelVisitorLogSerializer

logger = logging.getLogger(__name__)


class HostelVisitorLogViewSet(viewsets.ModelViewSet):
    queryset = HostelVisitorLog.objects.select_related(
        'student', 'student__department', 'student__section', 'student__batch', 'student__user'
    ).all().order_by('-check_in')
    serializer_class = HostelVisitorLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Visitor log entry not found."
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
        self._broadcast_change(instance, 'hostel_visitor_log_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'hostel_visitor_log_updated')

    def perform_destroy(self, instance):
        log_id = instance.id
        instance.delete()
        self._broadcast_delete(log_id)

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
                            'payload': HostelVisitorLogSerializer(instance).data
                        }
                    }
                )
        except Exception as e:
            logger.error(f"[WebSocket Broadcast Error] {e}")

    def _broadcast_delete(self, log_id):
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
                            'event': 'hostel_visitor_log_deleted',
                            'payload': {'id': log_id}
                        }
                    }
                )
        except Exception as e:
            logger.error(f"[WebSocket Broadcast Error] {e}")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        student_id = request.query_params.get('student_id')
        department_id = request.query_params.get('department_id')
        relationship = request.query_params.get('relationship')
        date_str = request.query_params.get('date')
        is_checked_in = request.query_params.get('is_checked_in')
        search = request.query_params.get('search')

        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if department_id:
            queryset = queryset.filter(student__department_id=department_id)
        if relationship:
            queryset = queryset.filter(relationship__iexact=relationship)
        if date_str:
            queryset = queryset.filter(check_in__date=date_str)
        if is_checked_in is not None:
            if is_checked_in.lower() in ['true', '1', 'yes']:
                queryset = queryset.filter(check_out__isnull=True)
            elif is_checked_in.lower() in ['false', '0', 'no']:
                queryset = queryset.filter(check_out__isnull=False)

        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(visitor_name__icontains=search) |
                Q(visitor_phone__icontains=search) |
                Q(student__roll_number__icontains=search) |
                Q(student__register_number__icontains=search) |
                Q(student__user__name__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Visitor logs retrieved successfully.",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Visitor logs retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Visitor log retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Visitor check-in log created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Visitor log updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Visitor log deleted successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        instance = self.get_object()
        if instance.check_out:
            return Response({
                "code": 400,
                "message": "Visitor is already checked out."
            }, status=status.HTTP_400_BAD_REQUEST)

        checkout_time_raw = request.data.get('check_out')
        if checkout_time_raw:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(checkout_time_raw)
            if not parsed:
                return Response({
                    "code": 400,
                    "message": "Invalid check_out timestamp format."
                }, status=status.HTTP_400_BAD_REQUEST)
            instance.check_out = parsed
        else:
            instance.check_out = timezone.now()

        user = request.user if request.user and request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance.updated_by = tracking_user
        instance.save(update_fields=['check_out', 'updated_by', 'updated_at'])

        self._broadcast_change(instance, 'hostel_visitor_log_updated')

        serializer = self.get_serializer(instance)
        return Response({
            "code": 200,
            "message": f"Visitor {instance.visitor_name} checked out successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
