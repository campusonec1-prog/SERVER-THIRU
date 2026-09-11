from rest_framework import serializers
from django.utils import timezone
from .models import LMSAssignment, LMSSubmission
from student.models import Student
from institution.models import Department, Batch, Section
from subject.models import Subject
from users.models import User


class LMSAssignmentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    batch_name = serializers.CharField(source='batch.batch', read_only=True)
    section_name = serializers.CharField(source='section.sections', read_only=True)
    target_student_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    total_submissions = serializers.SerializerMethodField()
    total_evaluated = serializers.SerializerMethodField()
    total_target_students = serializers.SerializerMethodField()
    my_submission = serializers.SerializerMethodField()

    class Meta:
        model = LMSAssignment
        fields = [
            'id', 'title', 'description', 'work_type', 'subject', 'subject_name',
            'target_type', 'department', 'department_name', 'batch', 'batch_name',
            'section', 'section_name', 'target_student', 'target_student_name',
            'due_date', 'total_marks', 'attachment', 'is_active',
            'created_at', 'updated_at', 'created_by', 'created_by_name',
            'total_submissions', 'total_evaluated', 'total_target_students', 'my_submission'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def get_target_student_name(self, obj):
        if obj.target_student and obj.target_student.user:
            return f"{obj.target_student.user.name} ({obj.target_student.roll_number or ''})"
        return None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.name or obj.created_by.username
        return 'System'

    def get_total_submissions(self, obj):
        return obj.submissions.count()

    def get_total_evaluated(self, obj):
        return obj.submissions.filter(status='EVALUATED').count()

    def get_total_target_students(self, obj):
        if obj.target_type == 'STUDENT':
            return 1 if obj.target_student_id else 0

        qs = Student.objects.all()
        if obj.department_id:
            qs = qs.filter(department_id=obj.department_id)
        if obj.batch_id:
            qs = qs.filter(batch_id=obj.batch_id)
        if obj.section_id:
            qs = qs.filter(section_id=obj.section_id)

        return qs.count()

    def get_my_submission(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'user') or not request.user:
            return None
        
        # Check if user is a student
        student = getattr(request.user, 'student', None)
        if not student:
            # Fallback lookup student profile by user mobile/username
            student = Student.objects.filter(
                user__phone_number=request.user.mobile_number
            ).first() or Student.objects.filter(
                user__name=request.user.name
            ).first()

        if student:
            sub = obj.submissions.filter(student=student).first()
            if sub:
                return LMSSubmissionSerializer(sub, context=self.context).data
        return None

    def validate_total_marks(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total marks must be greater than zero.")
        return value

    def validate_due_date(self, value):
        if value < timezone.now() and not self.instance:
            raise serializers.ValidationError("Due date cannot be set in the past.")
        return value


class LMSSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source='student.roll_number', read_only=True)
    student_register = serializers.CharField(source='student.register_number', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    assignment_due_date = serializers.DateTimeField(source='assignment.due_date', read_only=True)
    assignment_total_marks = serializers.DecimalField(source='assignment.total_marks', max_digits=5, decimal_places=2, read_only=True)
    evaluated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LMSSubmission
        fields = [
            'id', 'assignment', 'assignment_title', 'assignment_due_date', 'assignment_total_marks',
            'student', 'student_name', 'student_roll', 'student_register',
            'submission_file', 'student_notes', 'submitted_at', 'status',
            'obtained_marks', 'faculty_feedback', 'evaluated_at', 'evaluated_by', 'evaluated_by_name'
        ]
        read_only_fields = ['id', 'submitted_at', 'evaluated_at', 'evaluated_by']

    def get_student_name(self, obj):
        if obj.student and obj.student.user:
            return obj.student.user.name
        return "Student"

    def get_evaluated_by_name(self, obj):
        if obj.evaluated_by:
            return obj.evaluated_by.name or obj.evaluated_by.username
        return None

    def validate_submission_file(self, value):
        if value:
            # Max size limit 25MB
            if value.size > 25 * 1024 * 1024:
                raise serializers.ValidationError("Submission file size cannot exceed 25 MB.")
            
            ext = value.name.split('.')[-1].lower()
            allowed = ['pdf', 'doc', 'docx', 'zip', 'rar', 'txt', 'png', 'jpg', 'jpeg', 'xlsx', 'pptx']
            if ext not in allowed:
                raise serializers.ValidationError(f"File extension '.{ext}' is not supported. Allowed formats: {', '.join(allowed)}")
        return value
