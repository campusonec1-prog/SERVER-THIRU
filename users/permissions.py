from rest_framework import permissions

class BaseRolePermission(permissions.BasePermission):
    """
    Base permission for role-based access.
    Subclasses must define:
      - read_roles: list of roles allowed to read (list, retrieve).
                    Can include 'anyone' for public access, 'authenticated' for any logged-in user.
      - write_roles: list of roles allowed to write (create, update, partial_update, destroy).
    """
    read_roles = []
    write_roles = []

    def has_permission(self, request, view):
        is_read = request.method in permissions.SAFE_METHODS
        
        # Normalize allowed roles
        roles_to_check = self.read_roles if is_read else self.write_roles
        norm_roles = [r.upper().replace(' ', '_') for r in roles_to_check]
        
        # 1. Check public access (for both read and write)
        if 'ANYONE' in norm_roles:
            return True
            
        # 2. All other access requires authentication
        if not request.user or not request.user.is_authenticated:
            return False
            
        # 3. Superusers and staff have full access automatically
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True
            
        # 4. Check for 'authenticated' placeholder (any logged-in user allowed)
        if is_read and 'AUTHENTICATED' in norm_roles:
            return True
            
        # 5. Check specific roles
        try:
            user_role = request.user.role.role_name.upper().replace(' ', '_')
            return user_role in norm_roles
        except AttributeError:
            return False


# ─── Legacy Permission Classes (Refactored to subclass BaseRolePermission) ────

class IsAdminUser(BaseRolePermission):
    """
    Allows access only to authenticated admin users.
    """
    read_roles = ['admin', 'administrator']
    write_roles = ['admin', 'administrator']


class IsMarksManager(BaseRolePermission):
    """
    Allows access only to HOD, Faculty, Principal, Vice Principal, and Admin.
    """
    read_roles = ['hod', 'faculty', 'principal', 'vice principal', 'admin', 'administrator']
    write_roles = ['hod', 'faculty', 'principal', 'vice principal', 'admin', 'administrator']


class IsCounsellingCreator(BaseRolePermission):
    """
    Allows access only to HOD, Faculty, Principal, Vice Principal.
    """
    read_roles = ['hod', 'faculty', 'principal', 'vice principal']
    write_roles = ['hod', 'faculty', 'principal', 'vice principal']


# ─── Users App Permission Classes ─────────────────────────────────────────────

class UserPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']

    def has_permission(self, request, view):
        if view.action == 'login':
            return True
        return super().has_permission(request, view)



class UserDetailsPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']






