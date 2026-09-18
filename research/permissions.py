from users.permissions import BaseRolePermission


class ResearchProjectPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'principal', 'vice_principal', 'hod', 'faculty']
