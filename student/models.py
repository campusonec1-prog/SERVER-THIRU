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
    roll_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
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
    quota = models.ForeignKey(
        'institution.Quota',
        on_delete=models.SET_NULL,
        db_column='quota_id',
        related_name='students',
        null=True,
        blank=True
    )
    is_hostler = models.BooleanField(default=False)
    is_day_scholar = models.BooleanField(default=False)
    is_bus = models.BooleanField(default=False)
    bus_from = models.CharField(max_length=150, null=True, blank=True)
    bus_to = models.CharField(max_length=150, null=True, blank=True)
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


class StudentAdmissionSlip(TrackingModel):
    """Stores admission-specific information for the admission slip."""
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='admission_slip'
    )
    # Identity / credentials
    aadhaar_number = models.CharField(max_length=20, null=True, blank=True)
    emis_number = models.CharField(max_length=50, null=True, blank=True)
    umis_number = models.CharField(max_length=50, null=True, blank=True)

    # Academic qualification details
    qualification = models.CharField(max_length=50, null=True, blank=True)  # HSC, CBSE, DIPLOMA
    community = models.CharField(max_length=50, null=True, blank=True)       # OC, BC, MBC, SC, ST
    marks_maths = models.IntegerField(null=True, blank=True)
    marks_physics = models.IntegerField(null=True, blank=True)
    marks_chemistry = models.IntegerField(null=True, blank=True)
    marks_total = models.IntegerField(null=True, blank=True)
    marks_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mode_of_admission = models.CharField(max_length=50, default='I Sem')

    # Certificates submitted at admission
    certificates_surrendered = models.JSONField(default=dict)

    # Staff recommendation (person through whom the candidate seeks admission)
    recommendation = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='recommendation_id',
        related_name='recommended_students'
    )

    class Meta:
        db_table = 'students_admission_slip'

    def __str__(self):
        return f"Admission Slip for {self.student.user.name if self.student.user else 'Student'}"


class StudentFees(TrackingModel):
    """Stores fee payment information for a student."""
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='fees_payment'
    )
    total_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    payment_mode = models.CharField(max_length=50, default='Cash')

    # Books, Uniforms & Internet fee tracking
    books_fees_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    books_fees_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    # Due date for balance fees
    due_date = models.DateField(null=True, blank=True)

    remarks = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'students_fees'

    def __str__(self):
        return f"Fees Payment for {self.student.user.name if self.student.user else 'Student'}"


class FacultyActivity(TrackingModel):
    ACTIVITY_CHOICES = [
        ('lecture', 'Lecture'),
        ('laboratory', 'Laboratory'),
        ('discussion', 'Discussion'),
        ('test_or_exam', 'Test or exam'),
        ('seminar', 'Seminar'),
        ('others', 'Others'),
    ]
    timetable = models.ForeignKey(
        'timetable.ClassTimetable',
        on_delete=models.CASCADE,
        db_column='timetable_id',
        related_name='activities'
    )
    date = models.DateField()
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_CHOICES)
    other_activity = models.CharField(max_length=255, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    total_students = models.IntegerField(default=0)
    total_present = models.IntegerField(default=0)
    total_absentees = models.IntegerField(default=0)
    total_od = models.IntegerField(default=0)

    class Meta:
        db_table = 'faculty_activities'

    def __str__(self):
        return f"Activity on {self.date} for {self.timetable}"


class StudentAttendance(TrackingModel):
    STATUS_CHOICES = [
        ('P', 'Present'),
        ('AB', 'Absent'),
        ('OD', 'On Duty'),
    ]
    faculty_activity = models.ForeignKey(
        FacultyActivity,
        on_delete=models.CASCADE,
        db_column='faculty_activity_id',
        related_name='attendances'
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='attendances'
    )
    status = models.CharField(max_length=5, choices=STATUS_CHOICES, default='P')

    class Meta:
        db_table = 'student_attendances'
        unique_together = ('faculty_activity', 'student')

    def __str__(self):
        return f"{self.student.roll_number} - {self.status} (Activity {self.faculty_activity.id})"



