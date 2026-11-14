from users.permissions import BaseRolePermission
from rest_framework import permissions

MANAGEMENT_ROLES = [
    'admin', 'administrator', 'super_admin', 'superadmin',
    'principal', 'vice_principal',
    'office', 'manager',
    'tech_supporter', 'tech_support', 'ts', 'technical_supporter', 'technical_support',
    'administration_officer', 'administrative_officer', 'ao',
    'admissions_officer', 'admission_officer'
]


class FormModulePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = MANAGEMENT_ROLES


class FormFieldPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = MANAGEMENT_ROLES


class ApplicationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if getattr(request.user, 'is_superuser', False):
                return True
            try:
                role_name = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                if role_name in self.DELETE_ALLOWED_ROLES:
                    return True
                if request.user.__class__.__name__ == 'ApplicationUser' or role_name == 'CANDIDATE':
                    return True
                return False
            except Exception:
                return False

        if view.action == 'list':
            # Allow leadership, administration, office, manager, staff, and candidates
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                return True
            if request.user.__class__.__name__ == 'ApplicationUser':
                return True
            try:
                role_name = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                allowed_list = [
                    'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
                    'PRINCIPAL', 'VICE_PRINCIPAL',
                    'OFFICE', 'MANAGER',
                    'TECH_SUPPORTER', 'TECH_SUPPORT', 'TS', 'TECHNICAL_SUPPORTER', 'TECHNICAL_SUPPORT',
                    'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO',
                    'ADMISSIONS_OFFICER', 'ADMISSION_OFFICER',
                    'CANDIDATE', 'FACULTY', 'HOD', 'STAFF'
                ]
                return role_name in allowed_list or not role_name
            except Exception:
                return True

        return True


class ApplicationStatusPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = MANAGEMENT_ROLES


class ApplicationUserPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']

    def has_permission(self, request, view):
        if view.action == 'create':
            return True

        if not request.user or not request.user.is_authenticated:
            return False

        if view.action in ['destroy', 'remove', 'delete'] or request.method == 'DELETE':
            if getattr(request.user, 'is_superuser', False):
                return True
            try:
                role_name = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                return role_name in self.DELETE_ALLOWED_ROLES
            except Exception:
                return False

        if view.action == 'list':
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                return True
            try:
                role_name = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                allowed_manage = [
                    'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
                    'PRINCIPAL', 'VICE_PRINCIPAL',
                    'OFFICE', 'MANAGER',
                    'TECH_SUPPORTER', 'TECH_SUPPORT', 'TS', 'TECHNICAL_SUPPORTER', 'TECHNICAL_SUPPORT',
                    'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO',
                    'ADMISSIONS_OFFICER', 'ADMISSION_OFFICER',
                    'STAFF'
                ]
                return role_name in allowed_manage or not role_name
            except Exception:
                return True

        return True


class ApplicationFeePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = MANAGEMENT_ROLES
