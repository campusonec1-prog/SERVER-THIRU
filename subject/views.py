from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import Subject
from .serializers import SubjectSerializer
from .permissions import SubjectPermission


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all().order_by('id')
    serializer_class = SubjectSerializer
    permission_classes = [SubjectPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Subject not found"
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

        # Standard DRF ValidationError handles status 400 automatically, but let's format it nicely if it has detail dict
        from rest_framework.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            # Extract first error message
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
                first_msg = errors[0]
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
        self._broadcast_change(instance, 'subject_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'subject_updated')

    def perform_destroy(self, instance):
        subject_id = instance.id
        instance.delete()
        self._broadcast_delete(subject_id)

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
                            'payload': SubjectSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, subject_id):
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
                            'event': 'subject_deleted',
                            'payload': {
                                'id': subject_id
                            }
                        }
                    }
                )
        except Exception:
            pass

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Filtering parameters
        department_id = request.query_params.get('department_id')
        regulation_id = request.query_params.get('regulation_id')
        semester_id = request.query_params.get('semester_id')
        is_theory = request.query_params.get('is_theory')
        is_lab = request.query_params.get('is_lab')
        is_active = request.query_params.get('is_active')
        search = request.query_params.get('search')

        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if regulation_id:
            queryset = queryset.filter(regulation_id=regulation_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if is_theory:
            queryset = queryset.filter(is_theory=is_theory.lower() in ['true', 'yes', '1'])
        if is_lab:
            queryset = queryset.filter(is_lab=is_lab.lower() in ['true', 'yes', '1'])
        if is_active:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', 'yes', '1'])
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(subject_code__icontains=search) |
                Q(subject_name__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Subjects listed successfully",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Subjects listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Subject retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Subject created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Subject updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Subject deleted successfully"
        }, status=status.HTTP_200_OK)
