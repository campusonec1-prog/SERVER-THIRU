import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from django.http import Http404
from common.caching import CachedOptionViewSetMixin, invalidate_option_cache
from ..models import StudentStatus
from ..serializers import StudentStatusSerializer
from ..permissions import StudentStatusPermission

logger = logging.getLogger(__name__)


def broadcast_event(model_name, event_name, payload):
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
                        'model': model_name,
                        'event': event_name,
                        'payload': payload
                    }
                }
            )
    except Exception:
        pass


class StudentStatusViewSet(CachedOptionViewSetMixin, viewsets.ModelViewSet):
    queryset = StudentStatus.objects.all().order_by('id')
    serializer_class = StudentStatusSerializer
    permission_classes = [StudentStatusPermission]

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
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        invalidate_option_cache(self.get_cache_model_name())
        broadcast_event('StudentStatus', 'status_created', StudentStatusSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        invalidate_option_cache(self.get_cache_model_name())
        broadcast_event('StudentStatus', 'status_updated', StudentStatusSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        super().perform_destroy(instance)
        invalidate_option_cache(self.get_cache_model_name())
        broadcast_event('StudentStatus', 'status_deleted', {'id': inst_id})

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
