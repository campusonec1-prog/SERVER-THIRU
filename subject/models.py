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
