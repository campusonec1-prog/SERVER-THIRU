from users.permissions import BaseRolePermission


class PlacementCompanyPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = [
        'admin',
        'administrator',
        'super_admin',
        'superadmin',
        'principal',
        'vice_principal',
        'placement_cell',
        'placement_officer',
        'placement',
        'ao',
        'administrative_officer',
        'administration_officer',
        'tech_supporter',
        'ts',
    ]
