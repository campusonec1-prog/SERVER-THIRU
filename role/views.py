from django.db import transaction
from django.db.models import Count
from rest_framework.decorators import action
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from .models import Role
from .serializers import RoleSerializer
from .permissions import RolePermission

ADMIN_TECH_ROLES = {
    'ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'SUPER_ADMIN',
    'TECH_SUPPORTER', 'TECH SUPPORTER', 'TS'
}

class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.select_related('created_by', 'created_by__role', 'updated_by', 'updated_by__role').all().order_by('role_id')
    serializer_class = RoleSerializer
    permission_classes = [RolePermission]

    @action(detail=False, methods=['get', 'post', 'put'], url_path='student-profile-permissions')
    def student_profile_permissions(self, request, *args, **kwargs):
        """
        API for Admin and Tech Supporter to view and update student profile edit permissions across all roles.
        """
        user = request.user
        if not user or not user.is_authenticated:
            return Response({
                "code": 401,
                "message": "Authentication required."
            }, status=status.HTTP_401_UNAUTHORIZED)

        user_role_name = getattr(getattr(user, 'role', None), 'role_name', '').upper()
        is_admin_or_ts = (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            user_role_name in ADMIN_TECH_ROLES
        )

        # GET: List all roles with current student edit permission and assigned user count
        if request.method == 'GET':
            roles = Role.objects.annotate(users_count=Count('users')).order_by('role_id')
            data = [
                {
                    "role_id": r.role_id,
                    "role_name": r.role_name,
                    "can_edit_student_profile": bool(r.can_edit_student_profile),
                    "users_count": r.users_count,
                    "updated_at": r.updated_at
                }
                for r in roles
            ]
            return Response({
                "code": 200,
                "message": "Role student profile permissions retrieved successfully",
                "can_manage": is_admin_or_ts,
                "data": data
            }, status=status.HTTP_200_OK)

        # POST / PUT: Update permissions (Only Admin and Tech Supporter permitted)
        if not is_admin_or_ts:
            return Response({
                "code": 403,
                "message": "Permission denied. Only Administrators and Tech Supporters can modify student edit permissions."
            }, status=status.HTTP_403_FORBIDDEN)

        permissions_list = request.data.get('permissions')
        if permissions_list is None and isinstance(request.data, list):
            permissions_list = request.data

        if not isinstance(permissions_list, list):
            return Response({
                "code": 400,
                "message": "Invalid payload format. Expected a list of role permissions or { 'permissions': [...] }."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for item in permissions_list:
                role_id = item.get('role_id')
                can_edit = item.get('can_edit_student_profile')
                if role_id is not None and can_edit is not None:
                    Role.objects.filter(role_id=role_id).update(
                        can_edit_student_profile=bool(can_edit),
                        updated_by=user if hasattr(user, 'pk') else None
                    )

        # Return refreshed permissions list
        roles = Role.objects.annotate(users_count=Count('users')).order_by('role_id')
        data = [
            {
                "role_id": r.role_id,
                "role_name": r.role_name,
                "can_edit_student_profile": bool(r.can_edit_student_profile),
                "users_count": r.users_count,
                "updated_at": r.updated_at
            }
            for r in roles
        ]

        return Response({
            "code": 200,
            "message": "Student profile edit permissions updated successfully.",
            "data": data
        }, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Roles listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Role retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Role created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Role updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "deleted successfully"
        }, status=status.HTTP_200_OK)

    def handle_exception(self, exc):
        from django.http import Http404
        from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied

        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Role not found"
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

        return super().handle_exception(exc)

