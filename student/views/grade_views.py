import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from django.http import Http404
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from ..models import GradeSystem
from ..serializers import GradeSystemSerializer

logger = logging.getLogger(__name__)


class GradeSystemViewSet(viewsets.ModelViewSet):
    queryset = GradeSystem.objects.all().order_by('-points')
    serializer_class = GradeSystemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Grade system record not found"
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
                "message": first_msg,
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        logger.error(f"Unhandled exception in GradeSystemViewSet: {exc}", exc_info=True)
        return Response({
            "code": 500,
            "message": "An unexpected error occurred."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _auto_seed_grades(self):
        if not GradeSystem.objects.exists():
            default_grades = [
                {'grade': 'O',  'points': 10.0, 'min_mark': 91.0, 'max_mark': 100.0, 'is_pass': True,  'description': 'Outstanding'},
                {'grade': 'S',  'points': 10.0, 'min_mark': 91.0, 'max_mark': 100.0, 'is_pass': True,  'description': 'Outstanding (Regulation 2025)'},
                {'grade': 'A+', 'points': 9.0,  'min_mark': 81.0, 'max_mark': 90.0,  'is_pass': True,  'description': 'Excellent'},
                {'grade': 'A',  'points': 8.0,  'min_mark': 71.0, 'max_mark': 80.0,  'is_pass': True,  'description': 'Very Good'},
                {'grade': 'B+', 'points': 7.0,  'min_mark': 61.0, 'max_mark': 70.0,  'is_pass': True,  'description': 'Good'},
                {'grade': 'B',  'points': 6.0,  'min_mark': 56.0, 'max_mark': 60.0,  'is_pass': True,  'description': 'Above Average'},
                {'grade': 'C+', 'points': 6.0,  'min_mark': 56.0, 'max_mark': 60.0,  'is_pass': True,  'description': 'Average (Regulation 2025)'},
                {'grade': 'C',  'points': 5.0,  'min_mark': 50.0, 'max_mark': 55.0,  'is_pass': True,  'description': 'Average'},
                {'grade': 'P',  'points': 5.0,  'min_mark': 50.0, 'max_mark': 55.0,  'is_pass': True,  'description': 'Pass'},
                {'grade': 'U',  'points': 0.0,  'min_mark': 0.0,  'max_mark': 49.0,  'is_pass': False, 'description': 'Fail'},
                {'grade': 'UA', 'points': 0.0,  'min_mark': 0.0,  'max_mark': 0.0,   'is_pass': False, 'description': 'Absent'},
                {'grade': 'RA', 'points': 0.0,  'min_mark': 0.0,  'max_mark': 49.0,  'is_pass': False, 'description': 'Re-appear'},
                {'grade': 'SA', 'points': 0.0,  'min_mark': 0.0,  'max_mark': 0.0,   'is_pass': False, 'description': 'Shortage of Attendance'},
                {'grade': 'W',  'points': 0.0,  'min_mark': 0.0,  'max_mark': 0.0,   'is_pass': False, 'description': 'Withdrawal'},
            ]
            for item in default_grades:
                GradeSystem.objects.create(**item)

    def list(self, request, *args, **kwargs):
        self._auto_seed_grades()
        qs = GradeSystem.objects.all().order_by('-points')

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            if is_active.lower() in ['true', '1']:
                qs = qs.filter(is_active=True)
            elif is_active.lower() in ['false', '0']:
                qs = qs.filter(is_active=False)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(Q(grade__icontains=search) | Q(description__icontains=search))

        pagination = request.query_params.get('pagination')
        if pagination and pagination.lower() == 'false':
            serializer = self.get_serializer(qs, many=True)
            return Response({"code": 200, "data": serializer.data}, status=status.HTTP_200_OK)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response({"code": 200, "data": serializer.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            "code": 201,
            "message": "Grade system entry created successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            "code": 200,
            "message": "Grade system entry updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({
            "code": 200,
            "message": "Grade system entry deleted successfully."
        }, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        self._broadcast_change(instance, 'grade_system_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        self._broadcast_change(instance, 'grade_system_updated')

    def perform_destroy(self, instance):
        item_id = instance.id
        instance.delete()
        self._broadcast_delete(item_id)

    def _broadcast_change(self, instance, event_name):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'dashboard_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'model': 'GradeSystem',
                            'event': event_name,
                            'id': instance.id,
                            'grade': instance.grade,
                            'points': float(instance.points),
                            'is_active': instance.is_active
                        }
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to broadcast GradeSystem change: {e}")

    def _broadcast_delete(self, item_id):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'dashboard_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'model': 'GradeSystem',
                            'event': 'grade_system_deleted',
                            'id': item_id
                        }
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to broadcast GradeSystem delete: {e}")
