from django.db import models
from common.models import TrackingModel

class Subject(TrackingModel):
    COURSE_TYPE_CHOICES = [
        ('PCC', 'Professional Core Course (PCC)'),
        ('PEC', 'Professional Elective Course (PEC)'),
        ('OEC', 'Open Elective Course (OEC)'),
        ('MC', 'Mandatory Course (MC)'),
        ('EEC', 'Employability Enhancement / Skill Development (EEC)'),
        ('HSMC', 'Humanities, Social Sciences & Management (HSMC)'),
        ('BSC', 'Basic Science Course (BSC)'),
        ('ESC', 'Engineering Science Course (ESC)'),
        ('AC', 'Audit Course (AC)'),
        ('VAC', 'Value Added Course (VAC)'),
    ]

    subject_code = models.CharField(max_length=50, blank=True, null=True)
    subject_name = models.CharField(max_length=150)
    credits = models.FloatField(default=0.0)
    course_type = models.CharField(
        max_length=50,
        choices=COURSE_TYPE_CHOICES,
        default=None,
        blank=True,
        null=True
    )
    regulation = models.ForeignKey(
        'institution.Regulation',
        on_delete=models.CASCADE,
        db_column='regulation_id',
        related_name='subjects'
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='subjects'
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        db_column='semester_id',
        related_name='subjects'
    )
    is_theory = models.BooleanField(default=True)
    is_lab = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'subjects'
        constraints = [
            models.UniqueConstraint(
                fields=['subject_code', 'regulation', 'department', 'semester'],
                name='unique_subject_curriculum'
            )
        ]
        indexes = [
            models.Index(fields=['department', 'regulation']),
            models.Index(fields=['department', 'semester']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        if self.subject_code:
            return f"{self.subject_code} - {self.subject_name}"
        return self.subject_name


class SharedNotes(TrackingModel):
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='shared_notes'
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='shared_notes'
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        db_column='semester_id',
        related_name='shared_notes'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.CASCADE,
        db_column='section_id',
        related_name='shared_notes'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        db_column='subject_id',
        related_name='shared_notes'
    )
    folder_name = models.CharField(max_length=150)
    title = models.CharField(max_length=255, blank=True, null=True)
    file_name = models.CharField(max_length=255)
    file_url = models.URLField(max_length=1000)
    file_size = models.BigIntegerField(default=0)
    file_type = models.CharField(max_length=50)
    uploaded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        db_column='uploaded_by',
        related_name='shared_notes'
    )

    class Meta:
        db_table = 'shared_notes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['department', 'batch', 'semester', 'section']),
            models.Index(fields=['subject']),
        ]

    def __str__(self):
        sub_title = (self.subject.subject_code if self.subject and self.subject.subject_code else (self.subject.subject_name if self.subject else "Subject"))
        return f"{sub_title} - {self.folder_name} - {self.file_name}"

