from rest_framework import serializers
from .models import LeavePolicy, FacultyLeave, ClassSubstitution, Notification, HostelLeaveRequest
from users.models import User
from institution.models import AcademicYear, Department, Batch, Semester, Section
from schedule.models import Period, Day
from subject.models import Subject


def apply_default_error_messages(fields):
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."


class LeavePolicySerializer(serializers.ModelSerializer):
    academic_year_id = serializers.PrimaryKeyRelatedField(
        source='academic_year',
        queryset=AcademicYear.objects.all(),
        error_messages={'does_not_exist': 'Academic year does not exist.'}
    )
    academic_year_title = serializers.CharField(source='academic_year.academic_year', read_only=True)

    class Meta:
        model = LeavePolicy
        fields = [
            'id', 'academic_year_id', 'academic_year_title',
            'total_cl', 'total_od', 'total_permissions', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)


class ClassSubstitutionSerializer(serializers.ModelSerializer):
    period_no = serializers.IntegerField(source='period.period_no', read_only=True)
    period_time = serializers.SerializerMethodField()
    day_code = serializers.CharField(source='day.day_code', read_only=True)
    
    original_faculty_name = serializers.SerializerMethodField()
    substitute_faculty_name = serializers.SerializerMethodField()
    
    department_code = serializers.CharField(source='department.department_code', read_only=True)
    batch_name = serializers.CharField(source='batch.batch', read_only=True)
    section_name = serializers.CharField(source='section.sections', read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    leave_status = serializers.CharField(source='leave_application.status', read_only=True)

    class Meta:
        model = ClassSubstitution
        fields = [
            'id', 'leave_application', 'leave_status', 'date', 'period', 'period_no', 'period_time',
            'day', 'day_code', 'original_faculty', 'original_faculty_name',
            'substitute_faculty', 'substitute_faculty_name', 'class_timetable',
            'department', 'department_code', 'batch', 'batch_name',
            'semester', 'section', 'section_name', 'subject', 'subject_code', 'subject_name',
            'status', 'rejection_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_period_time(self, obj):
        if obj.period:
            return f"{obj.period.start_time.strftime('%I:%M %p')} - {obj.period.end_time.strftime('%I:%M %p')}"
        return ""

    def get_original_faculty_name(self, obj):
        if obj.original_faculty:
            return obj.original_faculty.name or obj.original_faculty.username
        return ""

    def get_substitute_faculty_name(self, obj):
        if obj.substitute_faculty:
            return obj.substitute_faculty.name or obj.substitute_faculty.username
        return ""



class FacultyLeaveSerializer(serializers.ModelSerializer):
    applicant_id = serializers.PrimaryKeyRelatedField(
        source='applicant',
        queryset=User.objects.all()
    )
    applicant_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    academic_year_title = serializers.CharField(source='academic_year.academic_year', read_only=True)
    substitutions = ClassSubstitutionSerializer(many=True, read_only=True)

    class Meta:
        model = FacultyLeave
        fields = [
            'id', 'applicant_id', 'applicant_name', 'department', 'department_name',
            'academic_year', 'academic_year_title', 'leave_type', 'from_date', 'to_date',
            'total_days', 'reason', 'status', 'approved_by', 'rejection_reason',
            'substitutions', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_applicant_name(self, obj):
        if obj.applicant:
            return obj.applicant.name or obj.applicant.username
        return ""


from student.models import Student

class HostelLeaveRequestSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        required=False,
        allow_null=True
    )
    student_name = serializers.SerializerMethodField()
    roll_number = serializers.CharField(source='student.roll_number', read_only=True)
    register_number = serializers.CharField(source='student.register_number', read_only=True)
    department_name = serializers.CharField(source='student.department.department_name', read_only=True)
    department_code = serializers.CharField(source='student.department.department_code', read_only=True)
    batch_name = serializers.CharField(source='student.batch.batch', read_only=True)
    section_name = serializers.CharField(source='student.section.sections', read_only=True)
    hostel_building_type = serializers.CharField(source='student.hostel_building_type', read_only=True)
    hostel_room_number = serializers.CharField(source='student.hostel_room_number', read_only=True)
    
    hostel_approved_by_name = serializers.SerializerMethodField()
    hod_approved_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)


    class Meta:
        model = HostelLeaveRequest
        fields = [
            'id', 'student', 'student_name', 'roll_number', 'register_number',
            'department_name', 'department_code', 'batch_name', 'section_name',
            'hostel_building_type', 'hostel_room_number',
            'from_date', 'to_date', 'total_days', 'reason', 'status', 'status_display',
            'hostel_approved_by', 'hostel_approved_by_name', 'hostel_approved_at', 'hostel_remarks',
            'hod_approved_by', 'hod_approved_by_name', 'hod_approved_at', 'hod_remarks',
            'rejection_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'total_days', 'status', 'hostel_approved_by', 'hostel_approved_at',
            'hod_approved_by', 'hod_approved_at', 'created_at', 'updated_at'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def get_student_name(self, obj):
        if obj.student and obj.student.user:
            return getattr(obj.student.user, 'name', '') or getattr(obj.student.user, 'username', '')
        return f"Student #{obj.student_id}"

    def get_hostel_approved_by_name(self, obj):
        if obj.hostel_approved_by:
            return getattr(obj.hostel_approved_by, 'name', '') or obj.hostel_approved_by.username
        return ""

    def get_hod_approved_by_name(self, obj):
        if obj.hod_approved_by:
            return getattr(obj.hod_approved_by, 'name', '') or obj.hod_approved_by.username
        return ""

    def validate(self, attrs):
        from_date = attrs.get('from_date') or (self.instance.from_date if self.instance else None)
        to_date = attrs.get('to_date') or (self.instance.to_date if self.instance else None)
        
        if from_date and to_date and from_date > to_date:
            raise serializers.ValidationError({
                "to_date": "To Date cannot be earlier than From Date."
            })

        student = attrs.get('student')
        if student and not student.is_hostler:
            student_name = getattr(student.user, 'name', '') if getattr(student, 'user', None) else f"Student #{student.id}"
            raise serializers.ValidationError({
                "student": f"Student '{student_name}' is marked as a Day Scholar (not a Hostler). Only verified Hostler students can apply for hostel leave."
            })

        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    related_substitution_detail = ClassSubstitutionSerializer(source='related_substitution', read_only=True)
    related_leave_detail = FacultyLeaveSerializer(source='related_leave', read_only=True)
    related_hostel_leave_detail = HostelLeaveRequestSerializer(source='related_hostel_leave', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'sender', 'sender_name', 'title', 'message',
            'notification_type', 'related_substitution', 'related_substitution_detail',
            'related_leave', 'related_leave_detail',
            'related_hostel_leave', 'related_hostel_leave_detail',
            'is_read', 'created_at'
        ]
        read_only_fields = ['created_at']


    def get_sender_name(self, obj):
        if obj.sender:
            return obj.sender.name or obj.sender.username
        return "System"
