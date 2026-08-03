from rest_framework import serializers
from .models import Subject
from institution.models import Regulation, Department, Semester

def apply_default_error_messages(fields):
    for field_name, field in fields.items():
        friendly_name = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly_name} is required."
        field.error_messages['blank'] = f"{friendly_name} cannot be empty."
        field.error_messages['null'] = f"{friendly_name} cannot be null."

class SubjectSerializer(serializers.ModelSerializer):
    regulation_id = serializers.PrimaryKeyRelatedField(
        source='regulation',
        queryset=Regulation.objects.all(),
        error_messages={'does_not_exist': 'Regulation does not exist.'}
    )
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )
    semester_id = serializers.PrimaryKeyRelatedField(
        source='semester',
        queryset=Semester.objects.all(),
        error_messages={'does_not_exist': 'Semester does not exist.'}
    )

    class Meta:
        model = Subject
        fields = [
            'id', 'subject_code', 'subject_name', 'credits', 
            'regulation_id', 'department_id', 'semester_id', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'subject_code': {'required': True},
            'subject_name': {'required': True},
            'credits': {'required': True},
            'semester_id': {'required': True},
            'is_active': {'required': False},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_subject_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Subject code cannot be empty.")
        # Check uniqueness
        qs = Subject.objects.filter(subject_code__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This subject code already exists.")
        return value.strip()

    def validate_subject_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Subject name cannot be empty.")
        return value.strip()

    def validate_credits(self, value):
        if value <= 0:
            raise serializers.ValidationError("Credits must be a positive integer.")
        return value
