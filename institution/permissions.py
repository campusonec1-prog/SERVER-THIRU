from rest_framework import permissions
from users.permissions import BaseRolePermission

# ─── Public Read, Admin/HOD/Principal/Office Write ───────────

class ProgramPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class DepartmentPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class AcademicYearPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


# ─── Authenticated Read, Admin/HOD/Principal/Office Write ─────

class BatchPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class RegulationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class SemesterPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class SectionPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class CollegeHeaderPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class ExamTypePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'exam_cell', 'exam cell', 'exam cell member', 'exam_officer', 'office', 'manager']


class ExamPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'exam_cell', 'exam cell', 'exam cell member', 'exam_officer', 'office', 'manager']


class QuotaPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager', 'tech_supporter', 'administration_officer']


class FeesStructurePermission(permissions.BasePermission):
    """
    Fees Structure is STRICTLY restricted to Admin and Tech Supporter roles only.
    No other role (Principal, Vice Principal, AO, Office, Manager, HOD, Faculty, Student) has access.
    Tech Supporter and Superuser only are permitted to delete.
    """
    ALLOWED_ROLES = {
        'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
        'TECH_SUPPORTER', 'TECH_SUPPORT', 'TS', 'TECHNICAL_SUPPORTER', 'TECHNICAL_SUPPORT'
    }
    DELETE_ALLOWED_ROLES = {
        'TECH_SUPPORTER', 'TS', 'TECHNICAL_SUPPORT', 'TECHNICAL_SUPPORTER', 'TECH_SUPPORT'
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, 'is_superuser', False):
            return True

        user_role = getattr(getattr(request.user, 'role', None), 'role_name', '')
        normalized_role = str(user_role or '').upper().strip().replace(' ', '_')

        if normalized_role not in self.ALLOWED_ROLES:
            return False

        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            return normalized_role in self.DELETE_ALLOWED_ROLES

        return True


class SemesterFeeStructurePermission(FeesStructurePermission):
    """
    Inherits strict Admin and Tech Supporter access restrictions from FeesStructurePermission.
    """
    pass

