from users.permissions import BaseRolePermission
from rest_framework import permissions

class StudentStatusPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer', 'principal', 'vice_principal', 'hod']


class StudentPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = [
        'admin', 'administrator', 'office', 'manager', 'tech_supporter',
        'administration_officer', 'administrative_officer', 'principal',
        'vice_principal', 'hod', 'admissions_officer', 'hostel_warden',
        'warden', 'transport', 'placement_cell', 'placement_officer'
    ]

    def has_permission(self, request, view):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            try:
                user_role_name = getattr(request.user.role, 'role_name', '').upper().replace(' ', '_')
                return user_role_name in self.DELETE_ALLOWED_ROLES
            except Exception:
                return False

        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)

        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True

        user_role = getattr(request.user, 'role', None)
        if not user_role:
            return False

        # If role specifically has can_edit_student_profile toggle enabled
        if getattr(user_role, 'can_edit_student_profile', False):
            return True

        user_role_name = getattr(user_role, 'role_name', '').upper().replace(' ', '_')
        if user_role_name in self.ALL_ACCESS_ROLES:
            return True

        norm_write = [r.upper().replace(' ', '_') for r in self.write_roles]
        return user_role_name in norm_write


class MarksPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = [
        'admin', 'administrator', 'hod', 'faculty', 'principal',
        'vice_principal', 'tech_supporter', 'administration_officer',
        'exam_cell', 'exam cell', 'exam cell member', 'exam_officer'
    ]


class CounsellingReportPermission(BaseRolePermission):
    read_roles = ['authenticated']

    def has_permission(self, request, view):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            try:
                user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                return user_role in self.DELETE_ALLOWED_ROLES
            except Exception:
                return False

        if request.method in permissions.SAFE_METHODS:
            return super().has_permission(request, view)

        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True

        if getattr(view, 'action', None) in ['counselling_report_pdf', 'report_pdf']:
            return True

        try:
            user_role = request.user.role.role_name.upper().replace(' ', '_')
        except AttributeError:
            return False

        allowed = [
            'HOD', 'FACULTY', 'PRINCIPAL', 'VICE_PRINCIPAL',
            'ADMIN', 'ADMINISTRATOR', 'ADMINISTRATIVE_OFFICER',
            'ADMINISTRATION_OFFICER', 'ADMISSIONS_OFFICER',
            'TECH_SUPPORTER', 'TS'
        ]

        return user_role in allowed

    def has_object_permission(self, request, view, obj):
        # 1. Superusers and staff have full access automatically
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True

        # 2. Leadership and Admins have full access automatically
        try:
            user_role = request.user.role.role_name.upper().replace(' ', '_')
            if user_role in ['ADMIN', 'ADMINISTRATOR', 'ADMINISTRATIVE_OFFICER', 'ADMINISTRATION_OFFICER', 'TECH_SUPPORTER', 'TS', 'PRINCIPAL', 'VICE_PRINCIPAL']:
                return True
        except AttributeError:
            pass

        # 3. For editing/deleting, only the creator of the report is allowed
        if request.method not in ['GET', 'HEAD', 'OPTIONS']:
            is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
            if is_delete:
                user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                if not (getattr(request.user, 'is_superuser', False) or user_role in self.DELETE_ALLOWED_ROLES):
                    return False
            return obj.created_by == request.user

        return True


class AttendancePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'faculty', 'principal', 'vice principal']
