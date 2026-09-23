from rest_framework import serializers
from django.utils import timezone
from .models import LMSAssignment, LMSSubmission, AssessmentQuestion, AssessmentOption, LMSAssessment, LMSAssessmentQuestionItem
from student.models import Student
from institution.models import Department, Batch, Section, Semester, Regulation, Exam
from subject.models import Subject
from users.models import User


class AttachmentField(serializers.Field):
    """
    Custom field for assignment attachments and submissions that accepts uploaded
    File objects (which are processed by perform_create/perform_update via Cloudflare R2 upload),
    existing string URLs, or None/blank without throwing 'Not a valid string' validation errors.
    """
    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if not data or data == 'null' or data == 'undefined':
            return None
        if isinstance(data, str):
            return data
        # If an uploaded File object (or binary payload) is passed in request.data,
        # return None so serializer validation succeeds. The view's perform_create/perform_update
        # retrieves request.FILES['attachment'] directly and uploads to Cloudflare R2.
        return None


class LMSAssignmentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    batch_name = serializers.CharField(source='batch.batch', read_only=True)
    section_name = serializers.CharField(source='section.sections', read_only=True)
    target_student_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    attachment = AttachmentField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True, required=False)

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
    submission_file = AttachmentField(required=False, allow_null=True)

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
            if hasattr(value, 'size') and value.size > 25 * 1024 * 1024:
                raise serializers.ValidationError("Submission file size cannot exceed 25 MB.")
            
            if hasattr(value, 'name'):
                ext = value.name.split('.')[-1].lower()
                allowed = ['pdf', 'doc', 'docx', 'zip', 'rar', 'txt', 'png', 'jpg', 'jpeg', 'xlsx', 'pptx']
                if ext not in allowed:
                    raise serializers.ValidationError(f"File extension '.{ext}' is not supported. Allowed formats: {', '.join(allowed)}")
        return value


class AssessmentOptionSerializer(serializers.ModelSerializer):
    option_text = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = AssessmentOption
        fields = ['id', 'option_code', 'option_text', 'is_correct', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    department_id = serializers.IntegerField(source='subject.department.id', read_only=True)
    department_name = serializers.CharField(source='subject.department.department_name', read_only=True)
    regulation_id = serializers.IntegerField(source='subject.regulation.id', read_only=True)
    regulation_code = serializers.CharField(source='subject.regulation.regulation_code', read_only=True)
    semester_id = serializers.IntegerField(source='subject.semester.id', read_only=True)
    exam = serializers.PrimaryKeyRelatedField(queryset=Exam.objects.all(), required=False, allow_null=True)
    exam_name = serializers.CharField(source='exam.exam_name', read_only=True)
    exam_type_id = serializers.IntegerField(source='exam.exam_type.id', read_only=True)
    exam_type_name = serializers.CharField(source='exam.exam_type.exam_type_name', read_only=True)

    options = AssessmentOptionSerializer(many=True, required=False)
    question_image = AttachmentField(required=False, allow_null=True)

    class Meta:
        model = AssessmentQuestion
        fields = [
            'id', 'subject', 'subject_code', 'subject_name',
            'department_id', 'department_name', 'regulation_id', 'regulation_code', 'semester_id',
            'question_type', 'exam', 'exam_name', 'exam_type_id', 'exam_type_name',
            'question_text', 'question_image', 'marks', 'answer', 'is_active',
            'options', 'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def validate_question_text(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Question text cannot be empty.")
        return value.strip()

    def validate_marks(self, value):
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive number.")
        return value

    def validate(self, attrs):
        q_type = (attrs.get('question_type') or (self.instance.question_type if self.instance else '') or '').strip().lower()
        
        # If question_type is non-choice (Short Answers or File Ups), clear options
        if 'short' in q_type or 'file' in q_type:
            attrs['options'] = []
        return attrs

    def create(self, validated_data):
        options_data = validated_data.pop('options', [])
        question = AssessmentQuestion.objects.create(**validated_data)
        
        user = question.created_by
        for index, opt in enumerate(options_data):
            code = opt.get('option_code') or chr(65 + index)  # Default 'A', 'B', 'C'...
            AssessmentOption.objects.create(
                question=question,
                option_code=code,
                option_text=opt.get('option_text', ''),
                is_correct=opt.get('is_correct', False),
                created_by=user,
                updated_by=user
            )
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop('options', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if options_data is not None:
            user = instance.updated_by or instance.created_by
            instance.options.all().delete()
            for index, opt in enumerate(options_data):
                code = opt.get('option_code') or chr(65 + index)
                AssessmentOption.objects.create(
                    question=instance,
                    option_code=code,
                    option_text=opt.get('option_text', ''),
                    is_correct=opt.get('is_correct', False),
                    created_by=instance.created_by or user,
                    updated_by=user
                )
        return instance


class LMSAssessmentQuestionItemSerializer(serializers.ModelSerializer):
    question_details = AssessmentQuestionSerializer(source='question', read_only=True)

    class Meta:
        model = LMSAssessmentQuestionItem
        fields = ['id', 'assessment', 'question', 'question_details', 'order', 'marks']
        read_only_fields = ['id', 'assessment']


class LMSAssessmentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    batch_name = serializers.CharField(source='batch.batch', read_only=True)
    section_name = serializers.CharField(source='section.sections', read_only=True)
    semester_name = serializers.SerializerMethodField()
    regulation_code = serializers.CharField(source='regulation.regulation_code', read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    items = LMSAssessmentQuestionItemSerializer(many=True, read_only=True)
    question_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = LMSAssessment
        fields = [
            'id', 'title', 'description',
            'department', 'department_name',
            'batch', 'batch_name',
            'section', 'section_name',
            'semester', 'semester_name',
            'regulation', 'regulation_code',
            'subject', 'subject_code', 'subject_name',
            'shuffle_questions', 'shuffle_options',
            'start_time', 'end_time', 'duration_minutes',
            'total_questions', 'total_marks',
            'items', 'question_ids',
            'created_at', 'updated_at', 'created_by', 'created_by_name',
            'is_active'
        ]
        read_only_fields = [
            'id', 'duration_minutes', 'total_questions', 'total_marks',
            'created_at', 'updated_at', 'created_by'
        ]

    def get_semester_name(self, obj):
        if obj.semester:
            return f"Semester {obj.semester.id}"
        return None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.name or obj.created_by.username
        return 'System'

    def validate(self, attrs):
        start_time = attrs.get('start_time') or (self.instance.start_time if self.instance else None)
        end_time = attrs.get('end_time') or (self.instance.end_time if self.instance else None)

        if start_time and end_time:
            if start_time >= end_time:
                raise serializers.ValidationError({
                    "end_time": "End time must be after the start time."
                })
            # Calculate duration in minutes
            diff_seconds = (end_time - start_time).total_seconds()
            attrs['duration_minutes'] = max(1, int(diff_seconds // 60))

        question_ids = attrs.get('question_ids')
        if not self.instance and not question_ids:
            raise serializers.ValidationError({
                "question_ids": "At least one question must be selected for the assessment."
            })

        return attrs

    def create(self, validated_data):
        question_ids = validated_data.pop('question_ids', [])
        user = self.context.get('request').user if self.context.get('request') else None
        if user and user.is_authenticated:
            validated_data['created_by'] = user

        assessment = LMSAssessment.objects.create(**validated_data)

        # Process question allocations
        if question_ids:
            # Auto-heal any questions
            AssessmentQuestion.objects.filter(id__in=question_ids, is_active=False).update(is_active=True)
            questions = AssessmentQuestion.objects.filter(id__in=question_ids)
            total_marks = 0
            items_to_create = []

            for index, q in enumerate(questions, start=1):
                total_marks += float(q.marks)
                items_to_create.append(
                    LMSAssessmentQuestionItem(
                        assessment=assessment,
                        question=q,
                        order=index,
                        marks=q.marks,
                        created_by=user,
                        updated_by=user
                    )
                )

            LMSAssessmentQuestionItem.objects.bulk_create(items_to_create)
            assessment.total_questions = len(items_to_create)
            assessment.total_marks = total_marks
            assessment.save(update_fields=['total_questions', 'total_marks'])

        return assessment

    def update(self, instance, validated_data):
        question_ids = validated_data.pop('question_ids', None)
        user = self.context.get('request').user if self.context.get('request') else None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if user and user.is_authenticated:
            instance.updated_by = user

        instance.save()

        if question_ids is not None:
            instance.items.all().delete()
            AssessmentQuestion.objects.filter(id__in=question_ids, is_active=False).update(is_active=True)
            questions = AssessmentQuestion.objects.filter(id__in=question_ids)
            total_marks = 0
            items_to_create = []

            for index, q in enumerate(questions, start=1):
                total_marks += float(q.marks)
                items_to_create.append(
                    LMSAssessmentQuestionItem(
                        assessment=instance,
                        question=q,
                        order=index,
                        marks=q.marks,
                        created_by=user,
                        updated_by=user
                    )
                )

            LMSAssessmentQuestionItem.objects.bulk_create(items_to_create)
            instance.total_questions = len(items_to_create)
            instance.total_marks = total_marks
            instance.save(update_fields=['total_questions', 'total_marks'])

        return instance


