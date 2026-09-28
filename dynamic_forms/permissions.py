from users.permissions import BaseRolePermission
from rest_framework import permissions

class FormModulePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']


class FormFieldPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']


class ApplicationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if view.action == 'list':
            # Allow leadership, administration, office, manager, and candidates for their own
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                return True
            try:
                role_name = request.user.role.role_name.upper().replace(' ', '_')
                allowed_list = [
                    'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
                    'PRINCIPAL', 'VICE_PRINCIPAL',
                    'OFFICE', 'MANAGER',
                    'TECH_SUPPORTER', 'TS',
                    'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO',
                    'CANDIDATE'
                ]
                return role_name in allowed_list
            except AttributeError:
                return False

        return True


class ApplicationStatusPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']


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
                role_name = request.user.role.role_name.upper().replace(' ', '_')
                allowed_manage = [
                    'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
                    'PRINCIPAL', 'VICE_PRINCIPAL',
                    'OFFICE', 'MANAGER',
                    'TECH_SUPPORTER', 'TS',
                    'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO'
                ]
                return role_name in allowed_manage
            except AttributeError:
                return False

        return True


class ApplicationFeePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']
