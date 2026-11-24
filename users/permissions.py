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
        'TECH_SUPPORTER', 'TECH_SUPPORT', 'TS', 'TECHNICAL_SUPPORTER', 'TECHNICAL_SUPPORT',
        'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO',
        'ADMISSIONS_OFFICER', 'ADMISSION_OFFICER'
    }

    # Strict Delete Access: ONLY Tech Supporter and Superuser are permitted to delete records.
    # ADMIN, AO, and other leadership roles have EDIT access only across all modules.
    DELETE_ALLOWED_ROLES = {
        'TECH_SUPPORTER', 'TS', 'TECHNICAL_SUPPORT', 'TECH SUPPORTER', 'TECHNICAL_SUPPORTER', 'TECH_SUPPORT'
    }

    BLOCKED_EDIT_ROLES = {'PRINCIPAL'}

    def has_permission(self, request, view):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])

        # Check delete permissions first
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            try:
                user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                return user_role in self.DELETE_ALLOWED_ROLES
            except Exception:
                return False

        # Block edit for Principal (except profile details, password changes, and approvals)
        is_profile_or_pwd = (
            getattr(view, 'action', None) in ['change_password', 'me', 'my_profile', 'approve', 'reject', 'recommend', 'principal_approve', 'principal_reject'] or
            view.__class__.__name__ in ['UserDetailsViewSet', 'ProfileViewSet']
        )
        is_edit = (request.method in ['PUT', 'PATCH']) or (getattr(view, 'action', None) in ['update', 'partial_update', 'edit', 'full_profile_update'])
        if is_edit and not is_profile_or_pwd:
            if not request.user or not request.user.is_authenticated:
                return False
            if not getattr(request.user, 'is_superuser', False):
                try:
                    user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                    if user_role in self.BLOCKED_EDIT_ROLES:
                        return False
                except Exception:
                    pass

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

    def has_object_permission(self, request, view, obj):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            try:
                user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                return user_role in self.DELETE_ALLOWED_ROLES
            except Exception:
                return False

        is_profile_or_pwd = (
            getattr(view, 'action', None) in ['change_password', 'me', 'my_profile', 'approve', 'reject', 'recommend', 'principal_approve', 'principal_reject'] or
            view.__class__.__name__ in ['UserDetailsViewSet', 'ProfileViewSet']
        )
        is_edit = (request.method in ['PUT', 'PATCH']) or (getattr(view, 'action', None) in ['update', 'partial_update', 'edit', 'full_profile_update'])
        if is_edit and not is_profile_or_pwd:
            if not request.user or not request.user.is_authenticated:
                return False
            if not getattr(request.user, 'is_superuser', False):
                try:
                    user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
                    if user_role in self.BLOCKED_EDIT_ROLES:
                        return False
                except Exception:
                    pass

        return True


class RestrictDeleteToTechSupporterPermission(permissions.BasePermission):
    """
    Global standalone permission rule:
    DELETE / destroy requests are restricted strictly to TECH_SUPPORTER and Superuser.
    All other roles (including ADMIN and AO) are blocked from DELETE (403 Forbidden).
    EDIT (PUT/PATCH/update) requests are blocked for PRINCIPAL role.
    Other non-DELETE/non-edit methods pass through.
    """
    DELETE_ALLOWED_ROLES = {
        'TECH_SUPPORTER', 'TS', 'TECHNICAL_SUPPORT', 'TECH SUPPORTER', 'TECHNICAL_SUPPORTER', 'TECH_SUPPORT'
    }
    BLOCKED_EDIT_ROLES = {'PRINCIPAL'}

    def has_permission(self, request, view):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
            return user_role in self.DELETE_ALLOWED_ROLES

        is_profile_or_pwd = (
            getattr(view, 'action', None) in ['change_password', 'me', 'my_profile', 'approve', 'reject', 'recommend', 'principal_approve', 'principal_reject'] or
            view.__class__.__name__ in ['UserDetailsViewSet', 'ProfileViewSet']
        )
        is_edit = (request.method in ['PUT', 'PATCH']) or (getattr(view, 'action', None) in ['update', 'partial_update', 'edit', 'full_profile_update'])
        if is_edit and not is_profile_or_pwd:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
            if user_role in self.BLOCKED_EDIT_ROLES:
                return False

        return True

    def has_object_permission(self, request, view, obj):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
            return user_role in self.DELETE_ALLOWED_ROLES

        is_profile_or_pwd = (
            getattr(view, 'action', None) in ['change_password', 'me', 'my_profile', 'approve', 'reject', 'recommend', 'principal_approve', 'principal_reject'] or
            view.__class__.__name__ in ['UserDetailsViewSet', 'ProfileViewSet']
        )
        is_edit = (request.method in ['PUT', 'PATCH']) or (getattr(view, 'action', None) in ['update', 'partial_update', 'edit', 'full_profile_update'])
        if is_edit and not is_profile_or_pwd:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
            if user_role in self.BLOCKED_EDIT_ROLES:
                return False

        return True


# ─── Legacy Permission Classes (Refactored to subclass BaseRolePermission) ────

class IsAdminUser(BaseRolePermission):
    """
    Allows access only to authenticated admin / leadership / tech support users.
    """
    read_roles = ['admin', 'administrator', 'principal', 'vice_principal', 'tech_supporter', 'administration_officer', 'ao', 'ts']
    write_roles = ['admin', 'administrator', 'vice_principal', 'tech_supporter', 'administration_officer', 'ao', 'ts']


class IsMarksManager(BaseRolePermission):
    """
    Allows access to HOD, Faculty, Principal, Vice Principal, AO, TS, and Admin.
    """
    read_roles = ['hod', 'faculty', 'principal', 'vice_principal', 'admin', 'administrator', 'administration_officer', 'tech_supporter']
    write_roles = ['hod', 'faculty', 'vice_principal', 'admin', 'administrator', 'administration_officer', 'tech_supporter']


class IsCounsellingCreator(BaseRolePermission):
    """
    Allows access to HOD, Faculty, Principal, Vice Principal, Admin, Office.
    """
    read_roles = ['hod', 'faculty', 'principal', 'vice_principal', 'office', 'manager']
    write_roles = ['hod', 'faculty', 'vice_principal', 'office', 'manager']


# ─── Users App Permission Classes ─────────────────────────────────────────────

class UserPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'office', 'manager', 'tech_supporter', 'administration_officer']

    def has_permission(self, request, view):
        if getattr(view, 'action', None) in ['login', 'change_password']:
            return True
        if getattr(view, 'action', None) == 'faculty_report_pdf':
            if not request.user or not request.user.is_authenticated:
                return False
            user_role = getattr(request.user.role, 'role_name', '').upper().replace(' ', '_')
            allowed = {
                'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
                'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO',
                'HOD', 'PRINCIPAL', 'VICE_PRINCIPAL', 'TS', 'TECH_SUPPORTER'
            }
            return user_role in allowed
        if getattr(view, 'action', None) == 'heartbeat':
            return bool(request.user and request.user.is_authenticated)
        if getattr(view, 'action', None) == 'online_users':
            return bool(request.user and request.user.is_authenticated)
        return super().has_permission(request, view)


class UserDetailsPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = [
        'admin', 'administrator', 'office', 'manager', 'tech_supporter',
        'administration_officer', 'principal', 'vice_principal', 'authenticated'
    ]

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        # Any authenticated user can manage and edit their own UserDetails profile
        if hasattr(obj, 'user_id') and obj.user_id == request.user.id:
            return True
        return super().has_object_permission(request, view, obj)






