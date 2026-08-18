from rest_framework import serializers
from .models import ExamTimetable
from institution.models import AcademicYear, Batch, Department, Exam, Section, Semester
from schedule.models import Session
from subject.models import Subject

def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."

class ExamTimetableSerializer(serializers.ModelSerializer):
    exam_date = serializers.DateField(
        input_formats=['%Y-%m-%d', '%d-%m-%Y'],
        error_messages={'invalid': 'Date has wrong format. Use YYYY-MM-DD or DD-MM-YYYY.'}
    )
    session_id = serializers.PrimaryKeyRelatedField(
        source='session',
        queryset=Session.objects.all(),
        error_messages={'does_not_exist': 'Session does not exist.'}
    )
    academic_year_id = serializers.PrimaryKeyRelatedField(
        source='academic_year',
        queryset=AcademicYear.objects.filter(is_active=True),
        error_messages={'does_not_exist': 'Academic year does not exist or is not active.'}
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source='batch',
        queryset=Batch.objects.all(),
        error_messages={'does_not_exist': 'Batch does not exist.'}
    )
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )
    exam_id = serializers.PrimaryKeyRelatedField(
        source='exam',
        queryset=Exam.objects.all(),
        error_messages={'does_not_exist': 'Exam does not exist.'}
    )
    section_id = serializers.PrimaryKeyRelatedField(
        source='section',
        queryset=Section.objects.all(),
        error_messages={'does_not_exist': 'Section does not exist.'}
    )
    semester_id = serializers.PrimaryKeyRelatedField(
        source='semester',
        queryset=Semester.objects.all(),
        error_messages={'does_not_exist': 'Semester does not exist.'}
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject',
        queryset=Subject.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Subject does not exist.'}
    )

    class Meta:
        model = ExamTimetable
        fields = [
            'id', 'exam_date', 'session_id', 'start_time', 'end_time',
            'academic_year_id', 'batch_id', 'department_id', 'exam_id',
            'section_id', 'semester_id', 'subject_id', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate(self, data):
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({
                "end_time": "End time must be after the start time."
            })
            
        academic_year = data.get('academic_year')
        if academic_year and not academic_year.is_active:
            raise serializers.ValidationError({
                "academic_year_id": "Academic year must be active."
            })
            
        return data
