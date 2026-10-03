from rest_framework import serializers


class TrackingModelSerializerMixin(serializers.Serializer):
    """
    Reusable serializer mixin for models extending common.models.TrackingModel.
    Provides human-readable tracking details for audit log tooltips/hover cards.
    """
    TRACKING_FIELDS = [
        'created_by_name',
        'created_by_username',
        'created_by_role',
        'updated_by_name',
        'updated_by_username',
        'updated_by_role',
    ]

    created_by_name = serializers.SerializerMethodField(read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, default=None)
    created_by_role = serializers.CharField(source='created_by.role.role_name', read_only=True, default=None)
    
    updated_by_name = serializers.SerializerMethodField(read_only=True)
    updated_by_username = serializers.CharField(source='updated_by.username', read_only=True, default=None)
    updated_by_role = serializers.CharField(source='updated_by.role.role_name', read_only=True, default=None)

    def get_created_by_name(self, obj):
        if hasattr(obj, 'created_by') and obj.created_by:
            return obj.created_by.name or obj.created_by.username
        return None

    def get_updated_by_name(self, obj):
        if hasattr(obj, 'updated_by') and obj.updated_by:
            return obj.updated_by.name or obj.updated_by.username
        return None

