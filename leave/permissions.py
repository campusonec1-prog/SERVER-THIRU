from users.permissions import BaseRolePermission


class LeavePolicyPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'principal']


class FacultyLeavePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']


class ClassSubstitutionPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']


class NotificationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['authenticated']

