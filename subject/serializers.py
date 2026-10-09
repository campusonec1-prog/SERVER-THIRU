from rest_framework import serializers
from django.db.models import Q
from common.serializers import TrackingModelSerializerMixin
from .models import Subject, SharedNotes
from institution.models import Regulation, Department, Semester, Batch, Section

def apply_default_error_messages(fields):
    for field_name, field in fields.items():
        friendly_name = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly_name} is required."
        field.error_messages['blank'] = f"{friendly_name} cannot be empty."
        field.error_messages['null'] = f"{friendly_name} cannot be null."

class SubjectSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
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
    regulation_code = serializers.CharField(source='regulation.regulation_code', read_only=True, default='')
    department_name = serializers.CharField(source='department.department_name', read_only=True, default='')
    department_code = serializers.CharField(source='department.department_code', read_only=True, default='')

    semester_number = serializers.IntegerField(source='semester.semester_number', read_only=True, default=None)
    semester_name = serializers.CharField(source='semester.semester_name', read_only=True, default='')

    class Meta:
        model = Subject
        fields = [
            'id', 'subject_code', 'subject_name', 'credits',
            'regulation_id', 'department_id', 'semester_id', 
            'regulation_code', 'department_name', 'department_code',
            'semester_number', 'semester_name',
            'is_theory', 'is_lab', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'created_by_name', 'created_by_username', 'created_by_role',
            'updated_by_name', 'updated_by_username', 'updated_by_role',
        ]
        read_only_fields = [
            'regulation_code', 'department_name', 'department_code',
            'semester_number', 'semester_name',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'created_by_name', 'created_by_username', 'created_by_role',
            'updated_by_name', 'updated_by_username', 'updated_by_role',
        ]
        extra_kwargs = {
            'subject_code': {'required': False, 'allow_null': True, 'allow_blank': True},
            'subject_name': {'required': True},
            'credits': {'required': False},
            'semester_id': {'required': True},
            'is_theory': {'required': False},
            'is_lab': {'required': False},
            'is_active': {'required': False},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_subject_code(self, value):
        if value and str(value).strip():
            return str(value).strip().upper()
        return None

    def validate_subject_name(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Subject name cannot be empty.")
        return str(value).strip()

    def validate_credits(self, value):
        if value is None:
            return 0.0
        if value < 0:
            raise serializers.ValidationError("Credits cannot be negative.")
        return value

    def validate(self, attrs):
        subject_code = attrs.get('subject_code', getattr(self.instance, 'subject_code', None))
        subject_name = attrs.get('subject_name', getattr(self.instance, 'subject_name', None))
        regulation = attrs.get('regulation', getattr(self.instance, 'regulation', None))
        department = attrs.get('department', getattr(self.instance, 'department', None))
        semester = attrs.get('semester', getattr(self.instance, 'semester', None))

        if department and semester and semester.department_id != department.id:
            raise serializers.ValidationError({
                "semester_id": f"Selected semester '{semester.semester_name}' belongs to department '{semester.department.department_name}', not '{department.department_name}'."
            })

        if subject_name and str(subject_name).strip() and regulation and department and semester:
            qs = Subject.objects.filter(
                subject_name__iexact=str(subject_name).strip(),
                regulation=regulation,
                department=department,
                semester=semester
            )
            if subject_code and str(subject_code).strip():
                qs = qs.filter(subject_code__iexact=str(subject_code).strip())
            else:
                qs = qs.filter(Q(subject_code__isnull=True) | Q(subject_code=''))
                
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "subject_name": f"Subject '{subject_code + ' - ' if subject_code else ''}{subject_name}' already exists for the selected regulation, department, and semester."
                })
        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['regulation_code'] = instance.regulation.regulation_code if instance.regulation else None
        ret['department_name'] = instance.department.department_name if instance.department else None
        ret['department_code'] = instance.department.department_code if instance.department else None
        ret['semester_number'] = instance.semester.semester_number if instance.semester else None
        ret['semester_name'] = instance.semester.semester_name if instance.semester else ''
        return ret


class SharedNotesSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
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
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = ['id', 'uploaded_by', 'created_at', 'updated_at'] + TrackingModelSerializerMixin.TRACKING_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['department_name'] = instance.department.department_name if instance.department else None
        ret['department_code'] = instance.department.department_code if instance.department else None
        
        batch_val = getattr(instance.batch, 'batch', None) or getattr(instance.batch, 'batch_name', None) if instance.batch else None
        ret['batch_name'] = batch_val or (str(instance.batch.id) if instance.batch else None)

        ret['semester_number'] = instance.semester.semester_number if instance.semester else None
        ret['semester_name'] = instance.semester.semester_name if instance.semester else ''

        sec_val = getattr(instance.section, 'sections', None) or getattr(instance.section, 'section_name', None) if instance.section else None
        ret['section_name'] = sec_val or (str(instance.section.id) if instance.section else None)

        ret['subject_code'] = instance.subject.subject_code if instance.subject else None
        ret['subject_name'] = instance.subject.subject_name if instance.subject else None
        
        uploader_name = "System"
        if instance.uploaded_by:
            uploader_name = getattr(instance.uploaded_by, 'name', None) or getattr(instance.uploaded_by, 'first_name', None) or instance.uploaded_by.username
        ret['uploaded_by_name'] = uploader_name
        return ret


