from users.permissions import BaseRolePermission


class AssetCategoryPermission(BaseRolePermission):
    """
    Permission class for Asset Category operations.
    Allows authenticated users to read, and authorized admin/office/manager roles to perform write actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'office', 'manager', 'tech_supporter', 'administration_officer']


class AssetPermission(BaseRolePermission):
    """
    Permission class for Asset operations.
    Allows authenticated users to read, and authorized admin/office/manager roles to perform write actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'office', 'manager', 'tech_supporter', 'administration_officer']


class AssetAllocationPermission(BaseRolePermission):
    """
    Permission class for Asset Allocation operations.
    Allows authenticated users to read, and admin/hod/faculty/office roles to perform assign/return actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'faculty', 'office', 'manager', 'tech_supporter', 'administration_officer']


class AssetTransferPermission(BaseRolePermission):
    """
    Permission class for Asset Transfer operations.
    Allows authenticated users to read, and admin/hod/office roles to perform transfer actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'office', 'manager', 'tech_supporter', 'administration_officer']


class AssetMaintenancePermission(BaseRolePermission):
    """
    Permission class for Asset Maintenance operations.
    Allows authenticated users to read, and admin/hod/office roles to create/manage maintenance.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'office', 'manager', 'tech_supporter', 'administration_officer']


class AssetDisposalPermission(BaseRolePermission):
    """
    Permission class for Asset Disposal operations.
    Allows authenticated users to read, and admin/hod/office roles to create/approve/manage disposal.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'office', 'manager', 'tech_supporter', 'administration_officer']

