from users.permissions import BaseRolePermission


class AssetCategoryPermission(BaseRolePermission):
    """
    Permission class for Asset Category operations.
    Allows authenticated users to read, and admin/administrator users to perform write actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']


class AssetPermission(BaseRolePermission):
    """
    Permission class for Asset operations.
    Allows authenticated users to read, and admin/administrator users to perform write actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator']


class AssetAllocationPermission(BaseRolePermission):
    """
    Permission class for Asset Allocation operations.
    Allows authenticated users to read, and admin/administrator users to perform assign/return actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod']


class AssetTransferPermission(BaseRolePermission):
    """
    Permission class for Asset Transfer operations.
    Allows authenticated users to read, and admin/administrator/hod users to perform transfer actions.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod']


class AssetMaintenancePermission(BaseRolePermission):
    """
    Permission class for Asset Maintenance operations.
    Allows authenticated users to read, and admin/administrator/hod users to create/manage maintenance.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod']


class AssetDisposalPermission(BaseRolePermission):
    """
    Permission class for Asset Disposal operations.
    Allows authenticated users to read, and admin/administrator/hod users to create/approve/manage disposal.
    """
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod']

