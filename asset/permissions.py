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
