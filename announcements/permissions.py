from users.permissions import BaseRolePermission

class NoticeBoardPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'principal', 'vice principal']
