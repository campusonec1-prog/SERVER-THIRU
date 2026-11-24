from rest_framework import permissions
from users.permissions import BaseRolePermission


class LibraryPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'library', 'librarian', 'tech_supporter', 'administration_officer']


class LibraryReservationPermission(permissions.BasePermission):
    """
    Allows all authenticated users (students, faculty, staff, admins) to view
    and create reservations for library books, and cancel their own reservations.
    Staff roles retain oversight to approve and issue held books.
    """
    STAFF_ROLES = {
        'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN',
        'LIBRARY', 'LIBRARIAN', 'TECH_SUPPORTER', 'TECH_SUPPORT', 'TS',
        'ADMINISTRATION_OFFICER', 'ADMINISTRATIVE_OFFICER', 'AO'
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Staff-exclusive actions (e.g. approve hold, counter issue)
        if getattr(view, 'action', None) in ['approve', 'issue', 'fulfill']:
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                return True
            user_role = getattr(getattr(request.user, 'role', None), 'role_name', '').upper().replace(' ', '_')
            return user_role in self.STAFF_ROLES

        # All authenticated users (including students and faculty) can list, create, and cancel
        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return True
