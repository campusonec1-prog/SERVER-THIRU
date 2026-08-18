from django.db import models
from django.core.exceptions import ValidationError
from common.models import TrackingModel

class ExamTimetable(TrackingModel):
    exam_date = models.DateField()
    session = models.ForeignKey(
        'schedule.Session',
        on_delete=models.CASCADE,
        db_column='session_id',
        related_name='exam_timetables'
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    academic_year = models.ForeignKey(
        'institution.AcademicYear',
        on_delete=models.CASCADE,
        db_column='academic_year_id',
        related_name='exam_timetables'
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='exam_timetables'
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='exam_timetables'
    )
    exam = models.ForeignKey(
        'institution.Exam',
        on_delete=models.CASCADE,
        db_column='exam_id',
        related_name='exam_timetables'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.CASCADE,
        db_column='section_id',
        related_name='exam_timetables'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        db_column='subject_id',
        related_name='exam_timetables',
        null=True,
        blank=True
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        db_column='semester_id',
        related_name='exam_timetables'
    )

    class Meta:
        db_table = 'exam_timetables'

    def __str__(self):
        return f"{self.exam.exam_name} - {self.department.department_name} ({self.exam_date})"

    def clean(self):
        super().clean()
        
        # Validate that the academic year is active
        if hasattr(self, 'academic_year') and self.academic_year and not self.academic_year.is_active:
            raise ValidationError({'academic_year': 'Academic year must be active.'})
            
        # Validate start and end times
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
