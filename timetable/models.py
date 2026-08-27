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


class ActivityType(TrackingModel):
    activity_name = models.CharField(max_length=100, unique=True)
    display_subject = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'activity_types'

    def __str__(self):
        return self.activity_name


class ClassTimetable(TrackingModel):
    academic_year = models.ForeignKey(
        'institution.AcademicYear',
        on_delete=models.CASCADE,
        db_column='academic_year_id',
        related_name='class_timetables'
    )
    day = models.ForeignKey(
        'schedule.Day',
        on_delete=models.CASCADE,
        db_column='day_id',
        related_name='class_timetables'
    )
    period = models.ForeignKey(
        'schedule.Period',
        on_delete=models.CASCADE,
        db_column='period_id',
        related_name='class_timetables'
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='class_timetables'
    )
    faculty = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        db_column='faculty_id',
        related_name='class_timetables'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.CASCADE,
        db_column='section_id',
        related_name='class_timetables'
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        db_column='semester_id',
        related_name='class_timetables'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.SET_NULL,
        db_column='subject_id',
        related_name='class_timetables',
        null=True,
        blank=True
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='class_timetables'
    )
    activity_type = models.ForeignKey(
        ActivityType,
        on_delete=models.SET_NULL,
        db_column='activity_type_id',
        related_name='class_timetables',
        null=True,
        blank=True
    )
    is_lab = models.BooleanField(default=False, blank=True)
    room_no = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'class_timetables'
        unique_together = ('academic_year', 'day', 'period', 'department', 'batch', 'semester', 'section')

    def __str__(self):
        subject_str = f" - {self.subject.subject_code}" if self.subject else ""
        activity_str = f" ({self.activity_type.activity_name})" if self.activity_type else ""
        return f"{self.department.department_code} - Sem {self.semester_id} - Section {self.section_id} ({self.day.day_code} P{self.period.period_no}{subject_str}){activity_str}"

    def clean(self):
        super().clean()
        if hasattr(self, 'academic_year') and self.academic_year and not self.academic_year.is_active:
            raise ValidationError({'academic_year': 'Academic year must be active.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
