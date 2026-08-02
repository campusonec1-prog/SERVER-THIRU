from rest_framework import serializers
from .models import User
from role.models import Role
import bcrypt

class UserSerializer(serializers.ModelSerializer):
    role_id = serializers.PrimaryKeyRelatedField(
        source='role',
        queryset=Role.objects.all(),
        error_messages={'does_not_exist': 'Role does not exist.'}
    )

    class Meta:
        model = User
        fields = ['id', 'name', 'username', 'password', 'mobile_number', 'mail', 'role_id', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'password': {'write_only': True},  # Secure password by not returning it in reads
            'mail': {
                'error_messages': {
                    'invalid': 'Please enter a valid email address.',
                    'unique': 'This email address is already in use.'
                }
            },
            'username': {
                'error_messages': {
                    'unique': 'This username is already in use.'
                }
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            friendly_name = field_name.replace('_', ' ').capitalize()
            field.error_messages['required'] = f"{friendly_name} is required."
            field.error_messages['blank'] = f"{friendly_name} cannot be empty."
            field.error_messages['null'] = f"{friendly_name} cannot be null."

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value

    def validate_mobile_number(self, value):
        import re
        pattern = r'^\d{10}$'
        if not re.match(pattern, value):
            raise serializers.ValidationError("Mobile number must be exactly 10 digits.")
        return value

    def create(self, validated_data):
        password = validated_data.get('password')
        if password:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            validated_data['password'] = hashed_password
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.get('password')
        if password:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            validated_data['password'] = hashed_password
        return super().update(instance, validated_data)
