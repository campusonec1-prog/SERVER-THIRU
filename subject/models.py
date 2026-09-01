from django.db import models
from common.models import TrackingModel

class Subject(TrackingModel):
    subject_code = models.CharField(max_length=50, unique=True)
    subject_name = models.CharField(max_length=150)
    credits = models.FloatField()
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

    def __str__(self):
        return f"{self.subject_code} - {self.subject_name}"


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

    def __str__(self):
        return f"{self.subject.subject_code} - {self.folder_name} - {self.file_name}"

