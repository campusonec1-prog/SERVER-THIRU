from rest_framework import permissions

class IsTimetableManager(permissions.BasePermission):
    """
    Allows write access only to authenticated Admin, HOD, or Exam Cell members.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Superusers and staff have full access
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True
            
        try:
            role_name = request.user.role.role_name.upper()
            return role_name in [
                'ADMIN', 
                'ADMINISTRATOR', 
                'HOD', 
                'EXAM CELL'
            ]
        except AttributeError:
            return False
