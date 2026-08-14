from django.db import models
from common.models import TrackingModel


class Program(TrackingModel):
    PROGRAM_LEVEL_CHOICES = [
        ('UG', 'Under Graduate'),
        ('PG', 'Post Graduate'),
        ('PhD', 'Doctor of Philosophy'),
        ('Diploma', 'Diploma'),
    ]

    program_name = models.CharField(max_length=200, unique=True)
    program_level = models.CharField(max_length=20, choices=PROGRAM_LEVEL_CHOICES)
    duration = models.PositiveIntegerField()

    class Meta:
        db_table = 'programs'

    def __str__(self):
        return self.program_name


class Department(TrackingModel):
    department_name = models.CharField(max_length=200)
    department_code = models.CharField(max_length=20, unique=True)
    short_name = models.CharField(max_length=50)
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        db_column='program_id',
        related_name='departments'
    )
    hod = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        db_column='hod_id',
        related_name='hod_departments',
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)
    is_display = models.BooleanField(default=True)


    class Meta:
        db_table = 'departments'

    def __str__(self):
        return f"{self.department_name} ({self.department_code})"


class AcademicYear(TrackingModel):
    academic_year = models.CharField(max_length=20, unique=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_display = models.BooleanField(default=False)

    class Meta:
        db_table = 'academic_years'

    def __str__(self):
        return self.academic_year

    def clean(self):
        super().clean()
        if self.is_display:
            qs = AcademicYear.objects.filter(is_display=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                from django.core.exceptions import ValidationError
                raise ValidationError({'is_display': 'Only one academic year can be set as display.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)



class Batch(TrackingModel):
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='batches'
    )
    batch = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'batches'
        unique_together = ('department', 'batch')

    def __str__(self):
        return f"{self.batch} ({self.department.department_name})"



class Regulation(TrackingModel):
    regulation_code = models.CharField(max_length=50, unique=True)
    effective_from_year = models.PositiveIntegerField(default=2024)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'regulation'

    def __str__(self):
        return f"{self.regulation_code} ({self.effective_from_year})"


class Semester(TrackingModel):
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='semesters'
    )
    semesters = models.JSONField(default=list)

    class Meta:
        db_table = 'semesters'

    def __str__(self):
        return f"Semesters for {self.department.department_name}"


class Section(TrackingModel):
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='sections'
    )
    sections = models.JSONField(default=list)

    class Meta:
        db_table = 'sections'

    def __str__(self):
        return f"Sections for {self.department.department_name}"


class CollegeHeader(TrackingModel):
    college_name = models.CharField(max_length=255)
    address = models.TextField()
    header_type = models.CharField(max_length=100, unique=True)
    primary_logo = models.CharField(max_length=500, null=True, blank=True)
    secondary_logo = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = 'college_header'

    def __str__(self):
        return f"{self.college_name} - {self.header_type}"


class ExamType(TrackingModel):
    exam_type_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'exam_type'

    def __str__(self):
        return self.exam_type_name


class Exam(TrackingModel):
    exam_name = models.CharField(max_length=150, unique=True)
    exam_type = models.ForeignKey(
        ExamType,
        on_delete=models.CASCADE,
        db_column='exam_type_id',
        related_name='exams'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'exams'

    def __str__(self):
        return f"{self.exam_name} ({self.exam_type.exam_type_name})"


class Quota(TrackingModel):
    quota_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'quotas'

    def __str__(self):
        return self.quota_name


class FeesStructure(TrackingModel):
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        db_column='academic_year_id',
        related_name='fees_structures'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='fees_structures'
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='fees_structures'
    )
    quota = models.ForeignKey(
        Quota,
        on_delete=models.CASCADE,
        db_column='quota_id',
        related_name='fees_structures'
    )
    fees = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'fees_structure'
        unique_together = ('academic_year', 'department', 'batch', 'quota')

    def __str__(self):
        return f"{self.academic_year.academic_year} - {self.department.department_code} - {self.batch.batch} - {self.quota.quota_name}: {self.fees}"






