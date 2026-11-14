from users.permissions import BaseRolePermission

class NoticeBoardPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = [
        'admin', 'administrator', 'principal', 'vice_principal', 'hod', 'faculty',
        'office', 'manager', 'tech_supporter', 'administration_officer',
        'transport', 'hostel_warden', 'warden', 'library', 'placement_cell', 'exam_cell'
    ]

    def has_object_permission(self, request, view, obj):
        is_delete = (request.method == 'DELETE') or (getattr(view, 'action', None) in ['destroy', 'bulk_destroy', 'bulk_delete', 'remove', 'delete'])
        if is_delete:
            if not request.user or not request.user.is_authenticated:
                return False
            if getattr(request.user, 'is_superuser', False):
                return True
            user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
            return user_role in self.DELETE_ALLOWED_ROLES

        # 1. Superusers and staff have full access automatically
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True

        # 2. Authorized roles have full management access
        try:
            user_role = request.user.role.role_name.upper().replace(' ', '_')
            if user_role in [
                'ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL', 'VICE_PRINCIPAL',
                'HOD', 'FACULTY', 'OFFICE', 'MANAGER', 'TECH_SUPPORTER', 'ADMINISTRATION_OFFICER',
                'TRANSPORT', 'HOSTEL_WARDEN', 'WARDEN', 'LIBRARY', 'PLACEMENT_CELL', 'EXAM_CELL'
            ]:
                return True
        except AttributeError:
            pass

        # 3. For editing/deleting, allow creator or authorized write roles
        if request.method not in ['GET', 'HEAD', 'OPTIONS']:
            return obj.faculty == request.user or obj.created_by == request.user

        return True
