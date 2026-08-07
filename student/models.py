from django.db import models
from common.models import TrackingModel


class StudentStatus(TrackingModel):
    status_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'student_status'

    def __str__(self):
        return self.status_name


class Student(TrackingModel):
    roll_number = models.CharField(max_length=50, unique=True)
    register_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='students'
    )
    section = models.ForeignKey(
        'institution.Section',
        on_delete=models.SET_NULL,
        db_column='section_id',
        related_name='students',
        null=True,
        blank=True
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='students'
    )
    user = models.OneToOneField(
        'dynamic_forms.ApplicationUser',
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='student'
    )
    lab_batch = models.CharField(max_length=50, null=True, blank=True)
    status = models.ForeignKey(
        StudentStatus,
        on_delete=models.CASCADE,
        db_column='status_id',
        related_name='students'
    )

    class Meta:
        db_table = 'students'

    def __str__(self):
        return f"{self.roll_number} - {self.user.name}"


class Marks(TrackingModel):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='marks'
    )
    exam = models.ForeignKey(
        'institution.Exam',
        on_delete=models.CASCADE,
        db_column='exam_id',
        related_name='marks'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        db_column='subject_id',
        related_name='marks'
    )
    marks_obtained = models.CharField(max_length=50)

    class Meta:
        db_table = 'marks'
        unique_together = ('student', 'exam', 'subject')

    def __str__(self):
        return f"{self.student.roll_number} - {self.subject.subject_code} ({self.exam.exam_name}): {self.marks_obtained}"


class CounsellingReport(TrackingModel):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='counselling_reports'
    )
    semester = models.ForeignKey(
        'institution.Semester',
        on_delete=models.CASCADE,
        db_column='semester_id',
        related_name='counselling_reports'
    )
    report_date = models.DateField()
    remarks = models.TextField()

    class Meta:
        db_table = 'counselling_reports'

    def __str__(self):
        return f"Counselling Report for {self.student.roll_number} on {self.report_date}"



