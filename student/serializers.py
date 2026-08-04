from rest_framework import serializers
from .models import StudentStatus, Student
from institution.models import Department, Section, Batch
from users.models import User
from dynamic_forms.models import ApplicationUser


def apply_default_error_messages(fields):
    for field_name, field in fields.items():
        friendly_name = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly_name} is required."
        field.error_messages['blank'] = f"{friendly_name} cannot be empty."
        field.error_messages['null'] = f"{friendly_name} cannot be null."


class StudentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentStatus
        fields = ['id', 'status_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'status_name': {
                'required': True,
                'error_messages': {'unique': 'This student status already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_status_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Status name cannot be empty.")
        qs = StudentStatus.objects.filter(status_name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This student status already exists.")
        return value.strip()


class StudentSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )
    section_id = serializers.PrimaryKeyRelatedField(
        source='section',
        queryset=Section.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Section does not exist.'}
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source='batch',
        queryset=Batch.objects.all(),
        error_messages={'does_not_exist': 'Batch does not exist.'}
    )
    user_id = serializers.PrimaryKeyRelatedField(
        source='user',
        queryset=ApplicationUser.objects.all(),
        error_messages={'does_not_exist': 'Application user does not exist.'}
    )
    status_id = serializers.PrimaryKeyRelatedField(
        source='status',
        queryset=StudentStatus.objects.all(),
        error_messages={'does_not_exist': 'Student status does not exist.'}
    )

    class Meta:
        model = Student
        fields = [
            'id', 'roll_number', 'register_number', 'department_id',
            'section_id', 'batch_id', 'user_id', 'lab_batch', 'status_id',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'roll_number': {
                'required': True,
                'error_messages': {'unique': 'This roll number already exists.'}
            },
            'register_number': {
                'required': False,
                'allow_null': True,
                'allow_blank': True,
                'error_messages': {'unique': 'This register number already exists.'}
            },
            'department_id': {'required': True},
            'batch_id': {'required': True},
            'user_id': {'required': True},
            'status_id': {'required': True},
            'lab_batch': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_roll_number(self, value):
        if not value.strip():
            raise serializers.ValidationError("Roll number cannot be empty.")
        qs = Student.objects.filter(roll_number__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This roll number already exists.")
        return value.strip()

    def validate_register_number(self, value):
        if value is None or not str(value).strip():
            return None
        val_str = str(value).strip()
        qs = Student.objects.filter(register_number__iexact=val_str)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This register number already exists.")
        return val_str

