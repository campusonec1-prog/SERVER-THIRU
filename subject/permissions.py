from users.permissions import BaseRolePermission

class SubjectPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'vice principal', 'office', 'manager', 'tech_supporter', 'administration_officer']
