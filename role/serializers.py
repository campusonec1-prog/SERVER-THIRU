from rest_framework import serializers
from .models import Role

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['role_id', 'role_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            friendly_name = field_name.replace('_', ' ').capitalize()
            field.error_messages['required'] = f"{friendly_name} is required."
            field.error_messages['blank'] = f"{friendly_name} cannot be empty."
            field.error_messages['null'] = f"{friendly_name} cannot be null."
