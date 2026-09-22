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

