from rest_framework import serializers
from .models import Program, Department, AcademicYear, Batch, Regulation, Semester, Section, CollegeHeader, ExamType, Exam, Quota, FeesStructure
from users.models import User


# ─── Helpers ────────────────────────────────────────────────────────────────

def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."


# ─── Program ─────────────────────────────────────────────────────────────────

class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ['id', 'program_name', 'program_level', 'duration', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'program_level': {
                'error_messages': {
                    'invalid_choice': 'Invalid program level. Choose from: UG, PG, PhD, Diploma.'
                }
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_program_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Program name cannot be empty.")
        return value

    def validate_program_level(self, value):
        valid_choices = [c[0] for c in Program.PROGRAM_LEVEL_CHOICES]
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid program level. Valid choices are: {', '.join(valid_choices)}."
            )
        return value

    def validate_duration(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration must be greater than 0.")
        return value


# ─── Department ──────────────────────────────────────────────────────────────

class DepartmentSerializer(serializers.ModelSerializer):
    program_id = serializers.PrimaryKeyRelatedField(
        source='program',
        queryset=Program.objects.all(),
        error_messages={'does_not_exist': 'Program does not exist.'}
    )
    hod_id = serializers.PrimaryKeyRelatedField(
        source='hod',
        queryset=User.objects.all(),
        allow_null=True,
        required=False,
        error_messages={'does_not_exist': 'User does not exist.'}
    )
    # Read-only: allows frontend to disambiguate departments with the same name
    program_name = serializers.CharField(source='program.program_name', read_only=True)
    program_level = serializers.CharField(source='program.program_level', read_only=True)

    class Meta:
        model = Department
        fields = [
            'id', 'department_name', 'department_code', 'short_name',
            'program_id', 'program_name', 'program_level',
            'hod_id', 'is_active', 'is_display',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]

        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'department_name': {'required': True},
            'department_code': {
                'required': True,
                'error_messages': {'unique': 'This department code is already in use.'}
            },
            'short_name': {'required': True},
            'is_active': {'required': False, 'default': True},
            'is_display': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_department_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Department name cannot be empty.")
        return value

    def validate_department_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Department code cannot be empty.")
        return value

    def validate_short_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Short name cannot be empty.")
        return value

    def validate_hod_id(self, value):
        """Ensure the selected user has the HOD role."""
        if value is not None:
            role_name = value.role.role_name.upper()
            if role_name != 'HOD':
                raise serializers.ValidationError(
                    f"Selected user does not have the HOD role. Their role is '{value.role.role_name}'."
                )
        return value


# ─── Academic Year ───────────────────────────────────────────────────────────

class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = [
            'id', 'academic_year', 
            'start_date', 'end_date',
            'odd_sem_start_date', 'odd_sem_end_date',
            'even_sem_start_date', 'even_sem_end_date',
            'is_active', 'is_display', 
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'academic_year': {
                'required': True,
                'error_messages': {'unique': 'This academic year already exists.'}
            },
            'start_date': {'required': False, 'allow_null': True},
            'end_date': {'required': False, 'allow_null': True},
            'odd_sem_start_date': {'required': False, 'allow_null': True},
            'odd_sem_end_date': {'required': False, 'allow_null': True},
            'even_sem_start_date': {'required': False, 'allow_null': True},
            'even_sem_end_date': {'required': False, 'allow_null': True},
            'is_active': {'required': False, 'default': True},
            'is_display': {'required': False, 'default': False},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_academic_year(self, value):
        if not value.strip():
            raise serializers.ValidationError("Academic year cannot be empty.")
        return value

    def validate(self, data):
        start_date = data.get('start_date', self.instance.start_date if self.instance else None)
        end_date = data.get('end_date', self.instance.end_date if self.instance else None)
        odd_start = data.get('odd_sem_start_date', self.instance.odd_sem_start_date if self.instance else None)
        odd_end = data.get('odd_sem_end_date', self.instance.odd_sem_end_date if self.instance else None)
        even_start = data.get('even_sem_start_date', self.instance.even_sem_start_date if self.instance else None)
        even_end = data.get('even_sem_end_date', self.instance.even_sem_end_date if self.instance else None)

        if odd_start and odd_end and odd_end <= odd_start:
            raise serializers.ValidationError({"odd_sem_end_date": "Odd semester end date must be after odd semester start date."})

        if even_start and even_end and even_end <= even_start:
            raise serializers.ValidationError({"even_sem_end_date": "Even semester end date must be after even semester start date."})

        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({"end_date": "End date must be after the start date."})

        is_display = data.get('is_display', self.instance.is_display if self.instance else False)
        if is_display:
            qs = AcademicYear.objects.filter(is_display=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"is_display": "Only one academic year can be set as display."}
                )
        return data



# ─── Batch ───────────────────────────────────────────────────────────────────

class BatchSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )

    class Meta:
        model = Batch
        fields = ['id', 'department_id', 'batch', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'department_id': {'required': True},
            'batch': {'required': True},
            'is_active': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_batch(self, value):
        if not value.strip():
            raise serializers.ValidationError("Batch cannot be empty.")
        return value.strip()

    def validate(self, data):
        department = data.get('department', self.instance.department if self.instance else None)
        batch_val = data.get('batch', self.instance.batch if self.instance else None)
        if department and batch_val:
            batch_val = str(batch_val).strip()
            qs = Batch.objects.filter(department=department, batch__iexact=batch_val)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "batch": "This batch already exists for the selected department."
                })
        return data



# ─── Regulation ──────────────────────────────────────────────────────────────

class RegulationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regulation
        fields = ['id', 'regulation_code', 'effective_from_year', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'regulation_code': {
                'required': True,
                'error_messages': {'unique': 'This regulation code already exists.'}
            },
            'effective_from_year': {'required': True},
            'is_active': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_regulation_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Regulation code cannot be empty.")
        return value

    def validate_effective_from_year(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Effective from year must be a valid positive year.")
        return value


# ─── Semester ──────────────────────────────────────────────────

class SemesterSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )

    class Meta:
        model = Semester
        fields = ['id', 'department_id', 'semesters', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'department_id': {'required': True},
            'semesters': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_semesters(self, value):
        """Validate that semesters is a non-empty list of positive integers."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Semesters must be an array, e.g. [1, 2, 3].")
        if len(value) == 0:
            raise serializers.ValidationError("Semesters array cannot be empty.")
        for item in value:
            if not isinstance(item, int):
                raise serializers.ValidationError(
                    f"Each semester must be an integer. Got '{item}' which is not valid."
                )
            if item <= 0:
                raise serializers.ValidationError(
                    f"Each semester number must be greater than 0. Got '{item}'."
                )
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate semester numbers are not allowed.")
        return sorted(value)


# ─── Section ──────────────────────────────────────────────────

class SectionSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )

    class Meta:
        model = Section
        fields = ['id', 'department_id', 'sections', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'department_id': {'required': True},
            'sections': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_sections(self, value):
        """Validate that sections is a non-empty string."""
        if not value or not str(value).strip():
            raise serializers.ValidationError("Section name cannot be empty.")
        return str(value).strip().upper()

    def validate(self, attrs):
        department = attrs.get('department')
        sections_val = attrs.get('sections')
        if department and sections_val:
            sections_val = str(sections_val).strip().upper()
            qs = Section.objects.filter(department=department, sections__iexact=sections_val)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "sections": "This section already exists for the selected department."
                })
        return attrs


# ─── College Header ────────────────────────────────────────────

class LogoField(serializers.Field):
    """
    Custom field that handles both uploaded files (which get uploaded to Cloudflare R2)
    and existing URL strings.
    """
    def to_internal_value(self, data):
        if not data:
            return None
        # If it's a string, it's the existing public URL or empty string
        if isinstance(data, str):
            return data
        # If it's a file, accept it
        from django.core.files.uploadedfile import UploadedFile
        if isinstance(data, UploadedFile) or hasattr(data, 'file'):
            return data
        raise serializers.ValidationError("Must be a file upload or a valid URL string.")

    def to_representation(self, value):
        return value


class CollegeHeaderSerializer(serializers.ModelSerializer):
    primary_logo = LogoField(required=False, allow_null=True)
    secondary_logo = LogoField(required=False, allow_null=True)

    class Meta:
        model = CollegeHeader
        fields = ['id', 'college_name', 'address', 'header_type', 'primary_logo', 'secondary_logo', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'college_name': {'required': True},
            'address': {'required': True},
            'header_type': {
                'required': True,
                'error_messages': {'unique': 'This header type is already in use.'}
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_college_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("College name cannot be empty.")
        return value

    def validate_address(self, value):
        if not value.strip():
            raise serializers.ValidationError("Address cannot be empty.")
        return value

    def validate_header_type(self, value):
        if not value.strip():
            raise serializers.ValidationError("Header type cannot be empty.")
        return value

    def _upload_logos(self, validated_data):
        from common.r2 import upload_file_to_r2
        primary = validated_data.get('primary_logo')
        secondary = validated_data.get('secondary_logo')

        if primary and not isinstance(primary, str):
            validated_data['primary_logo'] = upload_file_to_r2(primary)
        if secondary and not isinstance(secondary, str):
            validated_data['secondary_logo'] = upload_file_to_r2(secondary)

    def create(self, validated_data):
        self._upload_logos(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._upload_logos(validated_data)
        return super().update(instance, validated_data)


# ─── Exam Type ─────────────────────────────────────────────────

class ExamTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamType
        fields = ['id', 'exam_type_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'exam_type_name': {
                'required': True,
                'error_messages': {'unique': 'This exam type already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_exam_type_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Exam type name cannot be empty.")
        return value.strip()


# ─── Exam ──────────────────────────────────────────────────────

class ExamSerializer(serializers.ModelSerializer):
    exam_type_id = serializers.PrimaryKeyRelatedField(
        source='exam_type',
        queryset=ExamType.objects.all(),
        error_messages={'does_not_exist': 'Exam type does not exist.'}
    )
    exam_type_name = serializers.CharField(
        source='exam_type.exam_type_name',
        read_only=True
    )

    class Meta:
        model = Exam
        fields = ['id', 'exam_name', 'exam_type_id', 'exam_type_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'exam_name': {
                'required': True,
                'error_messages': {'unique': 'This exam name already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_exam_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Exam name cannot be empty.")
        return value.strip()


# ─── Quota ─────────────────────────────────────────────────────

class QuotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quota
        fields = ['id', 'quota_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'quota_name': {
                'required': True,
                'error_messages': {'unique': 'This quota already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_quota_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Quota name cannot be empty.")
        return value.strip()


# ─── Fees Structure ───────────────────────────────────────────

class FeesStructureSerializer(serializers.ModelSerializer):
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
    quota_id = serializers.PrimaryKeyRelatedField(
        source='quota',
        queryset=Quota.objects.all(),
        error_messages={'does_not_exist': 'Quota does not exist.'}
    )
    
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    batch_name = serializers.CharField(source='batch.batch', read_only=True)
    quota_name = serializers.CharField(source='quota.quota_name', read_only=True)

    class Meta:
        model = FeesStructure
        fields = [
            'id', 'department_id', 'department_name', 
            'batch_id', 'batch_name', 'quota_id', 'quota_name',
            'fees', 'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'fees': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_fees(self, value):
        if value <= 0:
            raise serializers.ValidationError("Fees must be a positive number.")
        return value

    def validate(self, attrs):
        department = attrs.get('department')
        batch = attrs.get('batch')
        quota = attrs.get('quota')

        qs = FeesStructure.objects.filter(
            department=department,
            batch=batch,
            quota=quota
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({
                "non_field_errors": "Fees structure for this department, batch, and quota already exists."
            })
        return attrs





