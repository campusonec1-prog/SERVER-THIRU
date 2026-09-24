from django.db import models
from common.models import TrackingModel


class LMSAssignment(TrackingModel):
    WORK_TYPE_CHOICES = [
        ('ASSIGNMENT', 'Assignment'),
        ('PROJECT', 'Project Work'),
        ('LAB_WORK', 'Lab Work'),
        ('OTHER', 'Other Task'),
    ]

    TARGET_TYPE_CHOICES = [
        ('STUDENT', 'Specific Student'),
        ('SECTION', 'Section'),
        ('BATCH', 'Batch'),
        ('DEPARTMENT', 'Department'),
        ('ALL', 'All Students'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    work_type = models.CharField(max_length=20, choices=WORK_TYPE_CHOICES, default='ASSIGNMENT')
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_assignments'
    )
    
    # Targeting criteria
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES, default='ALL')
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_assignments'
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_assignments'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_assignments'
    )
    target_student = models.ForeignKey(
        'student.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='targeted_lms_assignments'
    )

    due_date = models.DateTimeField()
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    attachment = models.TextField(blank=True, null=True)  # Cloudflare R2 public URL
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'lms_assignment'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['department', 'batch', 'section', 'is_active']),
            models.Index(fields=['is_active', 'due_date']),
        ]

    def __str__(self):
        return f"{self.title} ({self.work_type}) - Due: {self.due_date}"


class LMSSubmission(TrackingModel):
    STATUS_CHOICES = [
        ('SUBMITTED', 'Submitted'),
        ('EVALUATED', 'Evaluated / Graded'),
        ('LATE', 'Late Submission'),
        ('REJECTED', 'Needs Revision / Rejected'),
    ]

    assignment = models.ForeignKey(
        LMSAssignment,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    student = models.ForeignKey(
        'student.Student',
        on_delete=models.CASCADE,
        related_name='lms_submissions'
    )
    submission_file = models.TextField()  # Cloudflare R2 public URL
    student_notes = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUBMITTED')
    obtained_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    faculty_feedback = models.TextField(blank=True, null=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    evaluated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluated_lms_submissions'
    )

    class Meta:
        db_table = 'lms_submission'
        unique_together = ('assignment', 'student')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['assignment', 'student']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Submission by {self.student} for {self.assignment.title}"


class AssessmentQuestion(TrackingModel):
    QUESTION_TYPE_CHOICES = [
        ('Single Choice', 'Single Choice'),
        ('Multiple Choice', 'Multiple Choice'),
        ('True OR False', 'True OR False'),
        ('File Ups', 'File Ups'),
        ('Short Answers', 'Short Answers'),
    ]

    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        db_column='subject_id',
        related_name='assessment_questions'
    )
    question_type = models.CharField(
        max_length=50,
        choices=QUESTION_TYPE_CHOICES,
        default='Single Choice'
    )
    exam = models.ForeignKey(
        'institution.Exam',
        on_delete=models.SET_NULL,
        db_column='exam_id',
        related_name='assessment_questions',
        null=True,
        blank=True
    )
    question_text = models.TextField()
    question_image = models.TextField(blank=True, null=True)  # URL or Cloudflare R2 file path
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)
    answer = models.TextField(blank=True, null=True)  # Model answer / solution / explanation
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'assessment_questions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subject', 'question_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"Q#{self.id} - {self.subject.subject_code} - {self.question_type}"


class AssessmentOption(TrackingModel):
    question = models.ForeignKey(
        AssessmentQuestion,
        on_delete=models.CASCADE,
        db_column='question_id',
        related_name='options'
    )
    option_code = models.CharField(max_length=10, blank=True, null=True)  # e.g., 'A', 'B', 'C', 'D'
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        db_table = 'assessment_options'
        ordering = ['id']

    def __str__(self):
        return f"Option {self.option_code or self.id} for Q#{self.question_id}"


class LMSAssessment(TrackingModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        related_name='lms_assessments'
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        related_name='lms_assessments'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.CASCADE,
        related_name='lms_assessments'
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        related_name='lms_assessments'
    )
    regulation = models.ForeignKey(
        'institution.Regulation',
        on_delete=models.CASCADE,
        related_name='lms_assessments'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        related_name='lms_assessments'
    )

    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=0)

    total_questions = models.PositiveIntegerField(default=0)
    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)

    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_lms_assessments'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'lms_assessment'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['department', 'batch', 'section', 'subject']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.title} - {self.subject.subject_code} ({self.total_questions} Questions)"


class LMSAssessmentQuestionItem(TrackingModel):
    assessment = models.ForeignKey(
        LMSAssessment,
        on_delete=models.CASCADE,
        related_name='items'
    )
    question = models.ForeignKey(
        AssessmentQuestion,
        on_delete=models.CASCADE,
        related_name='assessment_allocations'
    )
    order = models.PositiveIntegerField(default=1)
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)

    class Meta:
        db_table = 'lms_assessment_question_item'
        ordering = ['order', 'id']
        unique_together = ('assessment', 'question')

    def __str__(self):
        return f"Q#{self.question_id} in Assessment #{self.assessment_id}"


class LMSAssessmentAttempt(TrackingModel):
    STATUS_CHOICES = [
        ('IN_PROGRESS', 'In Progress'),
        ('SUBMITTED', 'Submitted'),
        ('AUTO_SUBMITTED', 'Auto Submitted'),
        ('EVALUATED', 'Evaluated'),
    ]

    assessment = models.ForeignKey(
        LMSAssessment,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    student = models.ForeignKey(
        'student.Student',
        on_delete=models.CASCADE,
        related_name='lms_assessment_attempts'
    )
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS')

    total_questions = models.PositiveIntegerField(default=0)
    attempted_count = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)

    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    obtained_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    time_taken_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'lms_assessment_attempt'
        unique_together = ('assessment', 'student')
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['assessment', 'student']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Attempt by {self.student} on {self.assessment.title} - {self.obtained_marks}/{self.total_marks}"


class LMSAssessmentStudentAnswer(TrackingModel):
    attempt = models.ForeignKey(
        LMSAssessmentAttempt,
        on_delete=models.CASCADE,
        related_name='student_answers'
    )
    question = models.ForeignKey(
        AssessmentQuestion,
        on_delete=models.CASCADE,
        related_name='student_attempt_answers'
    )
    selected_option_ids = models.JSONField(default=list, blank=True)
    text_answer = models.TextField(blank=True, null=True)
    is_correct = models.BooleanField(default=False)
    marks_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'lms_assessment_student_answer'
        unique_together = ('attempt', 'question')
        ordering = ['id']

    def __str__(self):
        return f"Answer for Q#{self.question_id} in Attempt #{self.attempt_id} (Correct: {self.is_correct})"


