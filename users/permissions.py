from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Allows access only to authenticated admin users.
    """
    def has_permission(self, request, view):
        # Must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if their role name is ADMIN or ADMINISTRATOR
        try:
            role_name = request.user.role.role_name.upper()
            return role_name in ['ADMIN', 'ADMINISTRATOR']
        except AttributeError:
            return False
