from rest_framework import serializers
from .models import ExamTimetable, ClassTimetable, ActivityType
from institution.models import AcademicYear, Batch, Department, Exam, Section, Semester
from schedule.models import Session, Day, Period
from subject.models import Subject
from users.models import User as StandardUser

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

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        # 1. academic_year details
        if instance.academic_year:
            ret['academic_year_name'] = instance.academic_year.academic_year
        else:
            ret['academic_year_name'] = ''
            
        # 2. department details
        if instance.department:
            ret['department_name'] = instance.department.department_name
            ret['department_code'] = instance.department.department_code
        else:
            ret['department_name'] = ''
            ret['department_code'] = ''
            
        # 3. batch details
        if instance.batch:
            ret['batch_name'] = instance.batch.batch
        else:
            ret['batch_name'] = ''
            
        # 4. section details
        if instance.section:
            sec_str = ""
            if isinstance(instance.section.sections, list):
                sec_str = ", ".join(map(str, instance.section.sections))
            else:
                sec_str = str(instance.section.sections)
            ret['section_name'] = sec_str
        else:
            ret['section_name'] = ''
            
        # 5. semester details
        if instance.semester:
            ret['semester_name'] = f"Semester {instance.semester_id}"
        else:
            ret['semester_name'] = ''
            
        # 6. exam details
        if instance.exam:
            ret['exam_name'] = instance.exam.exam_name
        else:
            ret['exam_name'] = ''
            
        # 7. subject details
        if instance.subject:
            ret['subject_name'] = instance.subject.subject_name
            ret['subject_code'] = instance.subject.subject_code
        else:
            ret['subject_name'] = ''
            ret['subject_code'] = ''
            
        # 8. session details
        if instance.session:
            ret['session_name'] = instance.session.session_name
        else:
            ret['session_name'] = ''
            
        # 9. creator details
        if instance.created_by:
            ret['created_by_name'] = instance.created_by.name or instance.created_by.username
        else:
            ret['created_by_name'] = 'System'
            
        return ret


class ActivityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = ['id', 'activity_name', 'display_subject', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)


class ClassTimetableSerializer(serializers.ModelSerializer):
    academic_year_id = serializers.PrimaryKeyRelatedField(
        source='academic_year',
        queryset=AcademicYear.objects.filter(is_active=True),
        error_messages={'does_not_exist': 'Academic year does not exist or is not active.'}
    )
    day_id = serializers.PrimaryKeyRelatedField(
        source='day',
        queryset=Day.objects.all(),
        error_messages={'does_not_exist': 'Day does not exist.'}
    )
    period_id = serializers.PrimaryKeyRelatedField(
        source='period',
        queryset=Period.objects.all(),
        error_messages={'does_not_exist': 'Period does not exist.'}
    )
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )
    faculty_id = serializers.PrimaryKeyRelatedField(
        source='faculty',
        queryset=StandardUser.objects.all(),
        error_messages={'does_not_exist': 'Faculty does not exist.'}
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
    batch_id = serializers.PrimaryKeyRelatedField(
        source='batch',
        queryset=Batch.objects.all(),
        error_messages={'does_not_exist': 'Batch does not exist.'}
    )
    activity_type_id = serializers.PrimaryKeyRelatedField(
        source='activity_type',
        queryset=ActivityType.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Activity Type does not exist.'}
    )
    from_date = serializers.DateField(
        input_formats=['%Y-%m-%d', '%d-%m-%Y'],
        error_messages={'invalid': 'Date has wrong format. Use YYYY-MM-DD or DD-MM-YYYY.'}
    )
    to_date = serializers.DateField(
        input_formats=['%Y-%m-%d', '%d-%m-%Y'],
        error_messages={'invalid': 'Date has wrong format. Use YYYY-MM-DD or DD-MM-YYYY.'}
    )

    class Meta:
        model = ClassTimetable
        fields = [
            'id', 'academic_year_id', 'day_id', 'period_id', 'department_id',
            'faculty_id', 'section_id', 'semester_id', 'subject_id', 'batch_id',
            'activity_type_id', 'is_lab', 'room_no', 'from_date', 'to_date',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate(self, data):
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        if not from_date:
            raise serializers.ValidationError({
                "from_date": "From date is required."
            })
        if not to_date:
            raise serializers.ValidationError({
                "to_date": "To date is required."
            })
        if from_date and to_date and to_date < from_date:
            raise serializers.ValidationError({
                "to_date": "To date must be after or equal to from date."
            })

        academic_year = data.get('academic_year')
        if academic_year and not academic_year.is_active:
            raise serializers.ValidationError({
                "academic_year_id": "Academic year must be active."
            })
        
        activity_type = data.get('activity_type')
        subject = data.get('subject')
        if activity_type:
            if activity_type.display_subject and not subject:
                raise serializers.ValidationError({
                    "subject_id": "Subject is required for this activity type."
                })
            elif not activity_type.display_subject:
                data['subject'] = None
        return data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        # 1. academic_year details
        if instance.academic_year:
            ret['academic_year_name'] = instance.academic_year.academic_year
        else:
            ret['academic_year_name'] = ''
            
        # 2. day details
        if instance.day:
            ret['day_name'] = instance.day.day_name
            ret['day_code'] = instance.day.day_code
        else:
            ret['day_name'] = ''
            ret['day_code'] = ''

        # 3. period details
        if instance.period:
            ret['period_no'] = instance.period.period_no
            ret['start_time'] = instance.period.start_time.strftime('%H:%M:%S') if instance.period.start_time else ''
            ret['end_time'] = instance.period.end_time.strftime('%H:%M:%S') if instance.period.end_time else ''
        else:
            ret['period_no'] = None
            ret['start_time'] = ''
            ret['end_time'] = ''

        # 4. department details
        if instance.department:
            ret['department_name'] = instance.department.department_name
            ret['department_code'] = instance.department.department_code
            ret['short_name'] = instance.department.short_name
        else:
            ret['department_name'] = ''
            ret['department_code'] = ''
            ret['short_name'] = ''
            
        # 5. batch details
        if instance.batch:
            ret['batch_name'] = instance.batch.batch
        else:
            ret['batch_name'] = ''
            
        # 6. section details
        if instance.section:
            sec_str = ""
            if isinstance(instance.section.sections, list):
                sec_str = ", ".join(map(str, instance.section.sections))
            else:
                sec_str = str(instance.section.sections)
            ret['section_name'] = sec_str
        else:
            ret['section_name'] = ''
            
        # 7. semester details
        if instance.semester:
            ret['semester_name'] = f"Semester {instance.semester_id}"
        else:
            ret['semester_name'] = ''
            
        # 8. subject details
        if instance.subject:
            ret['subject_name'] = instance.subject.subject_name
            ret['subject_code'] = instance.subject.subject_code
        else:
            ret['subject_name'] = ''
            ret['subject_code'] = ''
            
        # 9. faculty details
        if instance.faculty:
            ret['faculty_name'] = instance.faculty.name
            ret['faculty_email'] = instance.faculty.mail
        else:
            ret['faculty_name'] = ''
            ret['faculty_email'] = ''
            
        # 10. creator details
        if instance.created_by:
            ret['created_by_name'] = instance.created_by.name or instance.created_by.username
        else:
            ret['created_by_name'] = 'System'
            
        # 11. activity type details
        if instance.activity_type:
            ret['activity_type_name'] = instance.activity_type.activity_name
            ret['display_subject'] = instance.activity_type.display_subject
        else:
            ret['activity_type_name'] = ''
            ret['display_subject'] = True

        return ret

