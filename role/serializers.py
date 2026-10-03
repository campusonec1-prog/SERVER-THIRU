from rest_framework import serializers
from common.serializers import TrackingModelSerializerMixin
from .models import Role

class RoleSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            'role_id', 'role_name',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'created_by_name', 'created_by_username', 'created_by_role',
            'updated_by_name', 'updated_by_username', 'updated_by_role',
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'created_by_name', 'created_by_username', 'created_by_role',
            'updated_by_name', 'updated_by_username', 'updated_by_role',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            friendly_name = field_name.replace('_', ' ').capitalize()
            field.error_messages['required'] = f"{friendly_name} is required."
            field.error_messages['blank'] = f"{friendly_name} cannot be empty."
            field.error_messages['null'] = f"{friendly_name} cannot be null."
