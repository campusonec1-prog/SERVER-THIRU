from users.permissions import BaseRolePermission

class NoticeBoardPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'principal', 'vice principal', 'hod', 'faculty']

    def has_object_permission(self, request, view, obj):
        # 1. Superusers and staff have full access automatically
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True

        # 2. Admins, Administrators, Principals, Vice Principals have full access automatically
        try:
            user_role = request.user.role.role_name.upper().replace(' ', '_')
            if user_role in ['ADMIN', 'ADMINISTRATOR', 'PRINCIPAL', 'VICE_PRINCIPAL']:
                return True
        except AttributeError:
            pass

        # 3. For editing/deleting, only the creator (faculty) of the notice is allowed
        if request.method not in ['GET', 'HEAD', 'OPTIONS']:
            return obj.faculty == request.user

        return True
