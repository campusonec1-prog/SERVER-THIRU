from rest_framework import serializers
from .models import NoticeBoard
from users.models import User


def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."


class NoticeBoardSerializer(serializers.ModelSerializer):
    faculty_id = serializers.PrimaryKeyRelatedField(
        source='faculty',
        read_only=True
    )

    class Meta:
        model = NoticeBoard
        fields = [
            'id', 'notice_title', 'notice_type', 'priority', 
            'publish_date', 'expire_date', 'description', 
            'is_active', 'faculty_id', 
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'faculty_id']
        extra_kwargs = {
            'notice_title': {'required': True},
            'notice_type': {
                'required': True,
                'error_messages': {
                    'invalid_choice': 'Invalid notice type. Choose from: general, academic, exam, holiday, event, fees.'
                }
            },
            'priority': {
                'required': True,
                'error_messages': {
                    'invalid_choice': 'Invalid priority. Choose from: low, medium, high.'
                }
            },
            'publish_date': {'required': True},
            'expire_date': {'required': True},
            'description': {'required': True},
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_notice_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Notice title cannot be empty.")
        return value.strip()

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Description cannot be empty.")
        return value.strip()

    def validate(self, data):
        publish_date = data.get('publish_date')
        expire_date = data.get('expire_date')
        if publish_date and expire_date and expire_date <= publish_date:
            raise serializers.ValidationError(
                {"expire_date": "Expire date must be after the publish date."}
            )
        return data
