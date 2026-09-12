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
