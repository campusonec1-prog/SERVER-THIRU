from rest_framework import serializers
from .models import Subject, SharedNotes
from institution.models import Regulation, Department, Semester, Batch, Section

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
            'regulation_id', 'department_id', 'semester_id', 
            'is_theory', 'is_lab', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'subject_code': {'required': True},
            'subject_name': {'required': True},
            'credits': {'required': True},
            'semester_id': {'required': True},
            'is_theory': {'required': False},
            'is_lab': {'required': False},
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
            raise serializers.ValidationError("Credits must be a positive number.")
        return value

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['regulation_code'] = instance.regulation.regulation_code if instance.regulation else None
        ret['department_name'] = instance.department.department_name if instance.department else None
        ret['department_code'] = instance.department.department_code if instance.department else None
        
        sec_str = ""
        if instance.semester:
            if isinstance(instance.semester.semesters, list):
                sec_str = ", ".join(map(str, instance.semester.semesters))
            else:
                sec_str = str(instance.semester.semesters)
        ret['semester_name'] = f"Semester {sec_str}" if sec_str else ""
        return ret


class SharedNotesSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source='batch',
        queryset=Batch.objects.all(),
        error_messages={'does_not_exist': 'Batch does not exist.'}
    )
    semester_id = serializers.PrimaryKeyRelatedField(
        source='semester',
        queryset=Semester.objects.all(),
        error_messages={'does_not_exist': 'Semester does not exist.'}
    )
    section_id = serializers.PrimaryKeyRelatedField(
        source='section',
        queryset=Section.objects.all(),
        error_messages={'does_not_exist': 'Section does not exist.'}
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject',
        queryset=Subject.objects.all(),
        error_messages={'does_not_exist': 'Subject does not exist.'}
    )

    class Meta:
        model = SharedNotes
        fields = [
            'id', 'department_id', 'batch_id', 'semester_id', 'section_id', 'subject_id',
            'folder_name', 'title', 'file_name', 'file_url', 'file_size', 'file_type',
            'uploaded_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['department_name'] = instance.department.department_name if instance.department else None
        ret['department_code'] = instance.department.department_code if instance.department else None
        
        batch_val = getattr(instance.batch, 'batch', None) or getattr(instance.batch, 'batch_name', None) if instance.batch else None
        ret['batch_name'] = batch_val or (str(instance.batch.id) if instance.batch else None)

        sem_val = getattr(instance.semester, 'semester_name', None)
        if not sem_val and instance.semester:
            sem_num = getattr(instance.semester, 'semester_number', None) or getattr(instance.semester, 'id', None)
            sem_val = f"Semester {sem_num}"
        ret['semester_name'] = sem_val

        sec_val = getattr(instance.section, 'sections', None) or getattr(instance.section, 'section_name', None) if instance.section else None
        ret['section_name'] = sec_val or (str(instance.section.id) if instance.section else None)

        ret['subject_code'] = instance.subject.subject_code if instance.subject else None
        ret['subject_name'] = instance.subject.subject_name if instance.subject else None
        
        uploader_name = "System"
        if instance.uploaded_by:
            uploader_name = getattr(instance.uploaded_by, 'name', None) or getattr(instance.uploaded_by, 'first_name', None) or instance.uploaded_by.username
        ret['uploaded_by_name'] = uploader_name
        return ret

