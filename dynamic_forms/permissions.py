from users.permissions import BaseRolePermission
from rest_framework import permissions

class FormModulePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']


class FormFieldPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']


class ApplicationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if view.action == 'list':
            # Only admin/administrator can list all applications, but candidate can list their own
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                return True
            try:
                role_name = request.user.role.role_name.upper()
                return role_name in ['ADMIN', 'ADMINISTRATOR', 'CANDIDATE']
            except AttributeError:
                return False

        return True


class ApplicationStatusPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']


class ApplicationUserPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']

    def has_permission(self, request, view):
        if view.action == 'create':
            return True

        if not request.user or not request.user.is_authenticated:
            return False

        if view.action in ['list', 'destroy']:
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                return True
            try:
                role_name = request.user.role.role_name.upper()
                return role_name in ['ADMIN', 'ADMINISTRATOR']
            except AttributeError:
                return False

        return True

