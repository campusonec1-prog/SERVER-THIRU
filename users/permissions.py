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

    ALL_ACCESS_ROLES = {
        'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
        'PRINCIPAL', 'VICE_PRINCIPAL',
        'TECH_SUPPORTER', 'TS',
        'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO'
    }

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
        if 'AUTHENTICATED' in norm_roles:
            return True
            
        # 5. Check specific roles and all-access roles
        try:
            user_role = request.user.role.role_name.upper().replace(' ', '_')
            if user_role in self.ALL_ACCESS_ROLES:
                return True
            return user_role in norm_roles
        except AttributeError:
            return False


# ─── Legacy Permission Classes (Refactored to subclass BaseRolePermission) ────

class IsAdminUser(BaseRolePermission):
    """
    Allows access only to authenticated admin / leadership / tech support users.
    """
    read_roles = ['admin', 'administrator', 'principal', 'vice_principal', 'tech_supporter', 'administration_officer', 'ao', 'ts']
    write_roles = ['admin', 'administrator', 'principal', 'vice_principal', 'tech_supporter', 'administration_officer', 'ao', 'ts']


class IsMarksManager(BaseRolePermission):
    """
    Allows access to HOD, Faculty, Principal, Vice Principal, AO, TS, and Admin.
    """
    read_roles = ['hod', 'faculty', 'principal', 'vice_principal', 'admin', 'administrator', 'administration_officer', 'tech_supporter']
    write_roles = ['hod', 'faculty', 'principal', 'vice_principal', 'admin', 'administrator', 'administration_officer', 'tech_supporter']


class IsCounsellingCreator(BaseRolePermission):
    """
    Allows access to HOD, Faculty, Principal, Vice Principal, Admin, Office.
    """
    read_roles = ['hod', 'faculty', 'principal', 'vice_principal', 'office', 'manager']
    write_roles = ['hod', 'faculty', 'principal', 'vice_principal', 'office', 'manager']


# ─── Users App Permission Classes ─────────────────────────────────────────────

class UserPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']

    def has_permission(self, request, view):
        if getattr(view, 'action', None) in ['login', 'change_password']:
            return True
        if getattr(view, 'action', None) == 'heartbeat':
            return bool(request.user and request.user.is_authenticated)
        if getattr(view, 'action', None) == 'online_users':
            return bool(request.user and request.user.is_authenticated)
        return super().has_permission(request, view)


class UserDetailsPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']






