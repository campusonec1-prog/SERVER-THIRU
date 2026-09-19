from rest_framework import serializers
from .models import NoticeBoard
from users.models import User


def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to required fields only."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        if getattr(field, 'required', False):
            field.error_messages['required'] = f"{friendly} is required."
        if not getattr(field, 'allow_blank', True):
            field.error_messages['blank'] = f"{friendly} cannot be empty."
        if not getattr(field, 'allow_null', True):
            field.error_messages['null'] = f"{friendly} cannot be null."


class NoticeBoardSerializer(serializers.ModelSerializer):
    faculty_id = serializers.PrimaryKeyRelatedField(
        source='faculty',
        read_only=True
    )
    faculty_name = serializers.CharField(
        source='faculty.name',
        read_only=True,
        default=''
    )
    department_name = serializers.CharField(
        source='department.department_name',
        read_only=True,
        default=''
    )

    class Meta:
        model = NoticeBoard
        fields = [
            'id', 'notice_title', 'notice_type', 'priority', 
            'publish_date', 'expire_date', 'description', 
            'is_active', 'faculty_id', 'faculty_name',
            'organizer', 'coordinator', 'sub_coordinators', 'poster_url',
            'target_audience_type', 'department', 'department_name', 'batch', 'section',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'faculty_id', 'faculty_name', 'department_name']
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
            'organizer': {'required': False, 'allow_null': True, 'allow_blank': True},
            'coordinator': {'required': False, 'allow_null': True, 'allow_blank': True},
            'sub_coordinators': {'required': False, 'allow_null': True},
            'poster_url': {'required': False, 'allow_null': True, 'allow_blank': True},
            'target_audience_type': {'required': False, 'default': 'global'},
            'department': {'required': False, 'allow_null': True},
            'batch': {'required': False, 'allow_null': True, 'allow_blank': True},
            'section': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            mutable_data = data.copy()
        elif isinstance(data, dict):
            mutable_data = data.copy()
        else:
            mutable_data = dict(data)

        for field in ['department', 'poster_url', 'organizer', 'coordinator', 'batch', 'section']:
            if field in mutable_data and (mutable_data[field] == '' or mutable_data[field] == 'null' or mutable_data[field] is None):
                mutable_data[field] = None

        return super().to_internal_value(mutable_data)

    def validate_notice_title(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Notice title cannot be empty.")
        return value.strip()

    def validate_description(self, value):
        if not value or not value.strip():
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
