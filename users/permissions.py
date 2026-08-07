from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Allows access only to authenticated admin users.
    """
    def has_permission(self, request, view):
        # Must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers and staff have full admin access
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True
            
        # Check if their role name is ADMIN or ADMINISTRATOR
        try:
            role_name = request.user.role.role_name.upper()
            return role_name in ['ADMIN', 'ADMINISTRATOR']
        except AttributeError:
            return False


class IsMarksManager(permissions.BasePermission):
    """
    Allows access only to HOD, Faculty, Principal, Vice Principal, and Admin.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Superusers and staff have full manager access
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True
            
        try:
            role_name = request.user.role.role_name.upper()
            return role_name in ['HOD', 'FACULTY', 'PRINCIPAL', 'VICE PRINCIPAL', 'VICE_PRINCIPAL', 'ADMIN', 'ADMINISTRATOR']
        except AttributeError:
            return False


