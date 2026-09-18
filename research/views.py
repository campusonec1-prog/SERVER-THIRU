from django.db.models import Q
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, NotAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.http import Http404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from common.pagination import CustomPageNumberPagination
from .models import FacultyResearchProject
from .serializers import FacultyResearchProjectSerializer
from .permissions import ResearchProjectPermission
from users.models import UserDetails


def broadcast_research_project_event(event_name, data):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': 'FacultyResearchProject',
                        'event': event_name,
                        'data': data
                    }
                }
            )
        except Exception:
            pass


class FacultyResearchProjectViewSet(viewsets.ModelViewSet):
    serializer_class = FacultyResearchProjectSerializer
    permission_classes = [ResearchProjectPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    
    search_fields = [
        'project_title',
        'project_code',
        'principal_investigator__user__name',
        'co_investigators__user__name',
        'research_area',
        'funding_agency',
        'site_name'
    ]

    filterset_fields = [
        'status',
        'project_type',
        'principal_investigator',
        'funding_agency',
        'project_start_date',
        'project_end_date'
    ]

    def get_queryset(self):
        user = self.request.user
        qs = FacultyResearchProject.objects.select_related(
            'principal_investigator',
            'principal_investigator__user',
            'principal_investigator__department'
        ).prefetch_related(
            'co_investigators',
            'co_investigators__user',
            'co_investigators__department'
        ).all().order_by('-created_at')

        if not user or not user.is_authenticated:
            return qs.none()

        role_name = getattr(user.role, 'role_name', '').upper() if hasattr(user, 'role') and user.role else ''

        # Admin / Superuser / Staff / Principal / Vice Principal view all
        if user.is_superuser or user.is_staff or role_name in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL', 'VICE_PRINCIPAL']:
            return qs

        # HOD views projects within their department or projects where they are PI/co-investigator/creator
        if role_name == 'HOD':
            user_details = UserDetails.objects.filter(user=user).first()
            if user_details and user_details.department_id:
                return qs.filter(
                    Q(principal_investigator__department_id=user_details.department_id) |
                    Q(principal_investigator__user=user) |
                    Q(co_investigators__user=user) |
                    Q(created_by=user)
                ).distinct()

        # Regular Faculty: ONLY see research projects where they are PI, Co-Investigator, or Creator
        user_details = UserDetails.objects.filter(user=user).first()
        if user_details:
            return qs.filter(
                Q(principal_investigator=user_details) |
                Q(co_investigators=user_details) |
                Q(created_by=user)
            ).distinct()

        return qs.filter(created_by=user).distinct()

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "success": False,
                "message": "Research project not found.",
                "errors": {"detail": "Research project not found."}
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "success": False,
                "message": "Authentication credentials were not provided.",
                "errors": {"detail": "Authentication credentials were not provided."}
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "success": False,
                "message": "You are not authorized to manage research projects.",
                "errors": {"detail": "You are not authorized to manage research projects."}
            }, status=status.HTTP_403_FORBIDDEN)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Support faculty filter if passed via query params
        faculty_id = request.query_params.get('faculty_id') or request.query_params.get('principal_investigator')
        if faculty_id:
            queryset = queryset.filter(principal_investigator_id=faculty_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "success": True,
                "message": "Research projects retrieved successfully.",
                "data": paginated_res.data
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "message": "Research projects retrieved successfully.",
            "data": serializer.data
        })

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "message": "Research project details retrieved successfully.",
            "data": serializer.data
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            user = request.user if request.user and request.user.is_authenticated else None
            instance = serializer.save(created_by=user, updated_by=user)

        broadcast_research_project_event('research_project_created', {
            'id': instance.id,
            'title': instance.project_title,
            'status': instance.status
        })

        return Response({
            "success": True,
            "message": "Research project created successfully.",
            "data": self.get_serializer(instance).data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            user = request.user if request.user and request.user.is_authenticated else None
            instance = serializer.save(updated_by=user)

        broadcast_research_project_event('research_project_updated', {
            'id': instance.id,
            'title': instance.project_title,
            'status': instance.status
        })

        return Response({
            "success": True,
            "message": "Research project updated successfully.",
            "data": self.get_serializer(instance).data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        project_id = instance.id
        project_title = instance.project_title
        
        with transaction.atomic():
            instance.delete()

        broadcast_research_project_event('research_project_deleted', {
            'id': project_id,
            'title': project_title
        })

        return Response({
            "success": True,
            "message": "Research project deleted successfully.",
            "data": {"id": project_id}
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path=r'faculty/(?P<faculty_id>\d+)')
    def faculty_projects(self, request, faculty_id=None):
        try:
            faculty = UserDetails.objects.get(pk=faculty_id)
        except UserDetails.DoesNotExist:
            return Response({
                "success": False,
                "message": "Principal investigator not found.",
                "errors": {"detail": "Principal investigator not found."}
            }, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        role_name = getattr(user.role, 'role_name', '').upper() if hasattr(user, 'role') and user.role else ''
        if role_name == 'FACULTY':
            my_details = UserDetails.objects.filter(user=user).first()
            if my_details and my_details.id != faculty.id:
                return Response({
                    "success": False,
                    "message": "You are not authorized to view research projects of another faculty.",
                    "errors": {"detail": "You are not authorized to view research projects of another faculty."}
                }, status=status.HTTP_403_FORBIDDEN)

        queryset = self.filter_queryset(
            self.get_queryset().filter(principal_investigator=faculty)
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "success": True,
                "message": f"Research projects for faculty {faculty.user.name if faculty.user else faculty.faculty_code} retrieved successfully.",
                "data": paginated_res.data
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "message": f"Research projects for faculty {faculty.user.name if faculty.user else faculty.faculty_code} retrieved successfully.",
            "data": serializer.data
        })
