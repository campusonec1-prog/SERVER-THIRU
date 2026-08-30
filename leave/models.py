from django.db import models
from common.models import TrackingModel


class LeavePolicy(TrackingModel):
    academic_year = models.OneToOneField(
        'institution.AcademicYear',
        on_delete=models.CASCADE,
        db_column='academic_year_id',
        related_name='leave_policy'
    )
    total_cl = models.PositiveIntegerField(default=12)
    total_od = models.PositiveIntegerField(default=6)
    total_permissions = models.PositiveIntegerField(default=12)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'leave_policies'

    def __str__(self):
        return f"Leave Policy for {self.academic_year.academic_year}"


class FacultyLeave(TrackingModel):
    LEAVE_TYPE_CHOICES = [
        ('FULL_DAY', 'Full Day Leave'),
        ('HALF_DAY_FN', 'Half Day (Forenoon)'),
        ('HALF_DAY_AN', 'Half Day (Afternoon)'),
        ('OD', 'On Duty (OD)'),
        ('PERMISSION', 'Hourly Permission'),
    ]

    STATUS_CHOICES = [
        ('PENDING_SUBSTITUTION', 'Pending Substitutions'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]

    applicant = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        db_column='applicant_id',
        related_name='leave_applications'
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='leave_applications'
    )
    academic_year = models.ForeignKey(
        'institution.AcademicYear',
        on_delete=models.SET_NULL,
        db_column='academic_year_id',
        related_name='leave_applications',
        null=True,
        blank=True
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    from_date = models.DateField()
    to_date = models.DateField()
    total_days = models.DecimalField(max_digits=5, decimal_places=1, default=1.0)
    reason = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING_SUBSTITUTION')
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        db_column='approved_by_id',
        related_name='approved_leaves',
        null=True,
        blank=True
    )
    rejection_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'faculty_leaves'
        ordering = ['-id']

    def __str__(self):
        return f"{self.applicant.username} - {self.leave_type} ({self.from_date} to {self.to_date})"


class ClassSubstitution(TrackingModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Acceptance'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]

    leave_application = models.ForeignKey(
        FacultyLeave,
        on_delete=models.CASCADE,
        db_column='leave_application_id',
        related_name='substitutions'
    )
    date = models.DateField()
    period = models.ForeignKey(
        'schedule.Period',
        on_delete=models.CASCADE,
        db_column='period_id',
        related_name='substitutions'
    )
    day = models.ForeignKey(
        'schedule.Day',
        on_delete=models.CASCADE,
        db_column='day_id',
        related_name='substitutions'
    )
    original_faculty = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        db_column='original_faculty_id',
        related_name='original_substitutions'
    )
    substitute_faculty = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        db_column='substitute_faculty_id',
        related_name='assigned_substitutions'
    )
    class_timetable = models.ForeignKey(
        'timetable.ClassTimetable',
        on_delete=models.CASCADE,
        db_column='class_timetable_id',
        related_name='substitutions',
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='substitutions'
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='substitutions'
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        db_column='semester_id',
        related_name='substitutions'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.CASCADE,
        db_column='section_id',
        related_name='substitutions'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.SET_NULL,
        db_column='subject_id',
        related_name='substitutions',
        null=True,
        blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    rejection_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'class_substitutions'
        ordering = ['date', 'period_id']

    def __str__(self):
        return f"{self.date} P{self.period_id}: {self.original_faculty.username} -> {self.substitute_faculty.username} ({self.status})"


class Notification(TrackingModel):
    NOTIFICATION_TYPE_CHOICES = [
        ('SUBSTITUTION_REQUEST', 'Substitution Request'),
        ('SUBSTITUTION_RESPONSE', 'Substitution Response'),
        ('LEAVE_STATUS', 'Leave Status Update'),
        ('GENERAL', 'General Notice'),
    ]

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='inbox_notifications'
    )
    sender = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        db_column='sender_id',
        related_name='sent_notifications',
        null=True,
        blank=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES, default='SUBSTITUTION_REQUEST')
    related_substitution = models.ForeignKey(
        ClassSubstitution,
        on_delete=models.CASCADE,
        db_column='related_substitution_id',
        related_name='notifications',
        null=True,
        blank=True
    )
    related_leave = models.ForeignKey(
        FacultyLeave,
        on_delete=models.CASCADE,
        db_column='related_leave_id',
        related_name='notifications',
        null=True,
        blank=True
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title} (Read: {self.is_read})"
