from users.permissions import BaseRolePermission

class RolePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']
