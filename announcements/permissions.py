from rest_framework import permissions


class IsNoticeManager(permissions.BasePermission):
    """
    Allows write access only to authenticated Admin, Principal, or Vice Principal users.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            role_name = request.user.role.role_name.upper()
            return role_name in ['ADMIN', 'ADMINISTRATOR', 'PRINCIPAL', 'VICE PRINCIPAL', 'VICE_PRINCIPAL']
        except AttributeError:
            return False
