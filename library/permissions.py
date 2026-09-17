from users.permissions import BaseRolePermission


class LibraryPermission(BaseRolePermission):
    read_roles = ['admin', 'administrator']
    write_roles = ['admin', 'administrator']
