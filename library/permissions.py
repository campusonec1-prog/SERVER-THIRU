from users.permissions import BaseRolePermission


class LibraryPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'library', 'librarian']
