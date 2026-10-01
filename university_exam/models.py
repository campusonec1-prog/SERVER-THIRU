from django.db import models
from common.models import TrackingModel


class UniversityExamHall(TrackingModel):
    hall = models.OneToOneField(
        'infrastructure.Hall',
        on_delete=models.CASCADE,
        db_column='hall_id',
        related_name='exam_config'
    )
    min_capacity = models.PositiveIntegerField(default=25)
    max_capacity = models.PositiveIntegerField(default=27)
    total_seats = models.PositiveIntegerField()
    rows_count = models.PositiveIntegerField()
    columns_count = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'university_exam_halls'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_capacity__gte=25) & models.Q(max_capacity__lte=27) & models.Q(min_capacity__lte=models.F('max_capacity')),
                name='chk_univ_exam_hall_capacity'
            ),
            models.CheckConstraint(
                condition=models.Q(total_seats__gte=models.F('min_capacity')),
                name='chk_univ_exam_hall_seats'
            ),
        ]

    def __str__(self):
        return f"{self.hall.hall_no} (Exam Config)"


class ExamHallDate(TrackingModel):
    SESSION_CHOICES = [('FN', 'Forenoon'), ('AN', 'Afternoon')]

    exam_hall = models.ForeignKey(
        UniversityExamHall,
        on_delete=models.CASCADE,
        db_column='exam_hall_id',
        related_name='hall_dates'
    )
    exam_date = models.DateField()
    session = models.CharField(max_length=2, choices=SESSION_CHOICES)
    is_available = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'university_exam_hall_dates'
        unique_together = ('exam_hall', 'exam_date', 'session')
        indexes = [
            models.Index(fields=['exam_date', 'session']),
            models.Index(fields=['exam_hall', 'exam_date']),
        ]

    def __str__(self):
        return f"{self.exam_hall.hall.hall_no} | {self.exam_date} {self.session} | {'Available' if self.is_available else 'Unavailable'}"


class ExamAttendanceImport(TrackingModel):
    """Staging table for raw PDF import data before normalization."""
    IMPORT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('MATCHED', 'Matched'),
        ('ERROR', 'Error'),
        ('IMPORTED', 'Imported'),
    ]
    SESSION_CHOICES = [('FN', 'Forenoon'), ('AN', 'Afternoon')]

    department = models.ForeignKey('institution.Department', null=True, blank=True, on_delete=models.SET_NULL, related_name='exam_imports')
    student = models.ForeignKey('student.Student', null=True, blank=True, on_delete=models.SET_NULL, related_name='exam_imports')
    subject = models.ForeignKey('subject.Subject', null=True, blank=True, on_delete=models.SET_NULL, related_name='exam_imports')
    exam_date = models.DateField(null=True, blank=True)
    session = models.CharField(max_length=2, choices=SESSION_CHOICES, null=True, blank=True)
    answer_book_no = models.CharField(max_length=50, null=True, blank=True)
    qp_code = models.CharField(max_length=50, null=True, blank=True)
    source_file = models.CharField(max_length=255, null=True, blank=True)
    source_page = models.IntegerField(null=True, blank=True)
    import_status = models.CharField(max_length=10, choices=IMPORT_STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'exam_attendance_import'
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['import_status']),
            models.Index(fields=['exam_date', 'session']),
        ]

    def __str__(self):
        return f"{self.register_no} | {self.subject_code} | {self.exam_date} | {self.import_status}"


class UniversityExamSchedule(TrackingModel):
    """One record = one subject exam for a department on a particular date+session."""
    SESSION_CHOICES = [('FN', 'Forenoon'), ('AN', 'Afternoon')]
    SEATING_STRATEGY_CHOICES = [
        ('SEQUENTIAL', 'Sequential'),
        ('DEPARTMENT_MIX', 'Department Mix'),
        ('SUBJECT_MIX', 'Subject Mix'),
        ('RANDOM', 'Random'),
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='university_exam_schedules'
    )
    exam_date = models.DateField()
    session = models.CharField(max_length=2, choices=SESSION_CHOICES)
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        db_column='subject_id',
        related_name='university_exam_schedules'
    )
    qp_code = models.CharField(max_length=50, null=True, blank=True)
    exam_type = models.CharField(max_length=50, default='UNIVERSITY')
    seating_strategy = models.CharField(
        max_length=20,
        choices=SEATING_STRATEGY_CHOICES,
        default='DEPARTMENT_MIX'
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='DRAFT')

    class Meta:
        db_table = 'university_exam_schedule'
        unique_together = ('department', 'exam_date', 'session', 'subject')
        indexes = [
            models.Index(fields=['exam_date', 'session']),
            models.Index(fields=['department', 'exam_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.department.department_code} | {self.subject.subject_code} | {self.exam_date} {self.session}"


class UniversityExamAttendance(TrackingModel):
    """Normalized attendance table linking schedule <-> student."""
    ATTENDANCE_STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('NOT_MARKED', 'Not Marked'),
    ]

    exam_schedule = models.ForeignKey(
        UniversityExamSchedule,
        on_delete=models.CASCADE,
        db_column='exam_schedule_id',
        related_name='attendances'
    )
    student = models.ForeignKey(
        'student.Student',
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='university_exam_attendances'
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='university_exam_attendances'
    )
    attendance_status = models.CharField(
        max_length=12,
        choices=ATTENDANCE_STATUS_CHOICES,
        default='NOT_MARKED'
    )
    answer_book_no = models.CharField(max_length=50, null=True, blank=True)
    qp_code = models.CharField(max_length=50, null=True, blank=True)
    attendance_marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'university_exam_attendance'
        unique_together = ('exam_schedule', 'student')
        indexes = [
            models.Index(fields=['exam_schedule']),
            models.Index(fields=['student']),
            models.Index(fields=['department']),
            models.Index(fields=['attendance_status']),
        ]

    def __str__(self):
        return f"{self.student.register_number} | {self.exam_schedule.subject.subject_code} | {self.attendance_status}"


class ExamHallAllocation(TrackingModel):
    """Which halls are allocated for a specific exam schedule."""
    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ALLOCATED', 'Allocated'),
        ('COMPLETED', 'Completed'),
    ]

    exam_schedule = models.ForeignKey(
        UniversityExamSchedule,
        on_delete=models.CASCADE,
        db_column='exam_schedule_id',
        related_name='hall_allocations'
    )
    exam_hall = models.ForeignKey(
        UniversityExamHall,
        on_delete=models.CASCADE,
        db_column='exam_hall_id',
        related_name='exam_allocations'
    )
    allocation_order = models.PositiveIntegerField()
    planned_capacity = models.PositiveIntegerField()
    allocated_students = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PLANNED')

    class Meta:
        db_table = 'exam_hall_allocation'
        unique_together = ('exam_schedule', 'exam_hall')
        indexes = [
            models.Index(fields=['exam_schedule']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(planned_capacity__gte=25) & models.Q(planned_capacity__lte=27),
                name='chk_hall_alloc_planned_capacity'
            ),
        ]

    def __str__(self):
        return f"{self.exam_schedule} | Hall: {self.exam_hall.hall.hall_no} | Order: {self.allocation_order}"


class ExamSeatAllocation(TrackingModel):
    """Individual student seat assignments."""
    ALLOCATION_STATUS_CHOICES = [
        ('ALLOCATED', 'Allocated'),
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('CANCELLED', 'Cancelled'),
    ]

    exam_schedule = models.ForeignKey(
        UniversityExamSchedule,
        on_delete=models.CASCADE,
        db_column='exam_schedule_id',
        related_name='seat_allocations'
    )
    hall_allocation = models.ForeignKey(
        ExamHallAllocation,
        on_delete=models.CASCADE,
        db_column='hall_allocation_id',
        related_name='seat_allocations'
    )
    student = models.ForeignKey(
        'student.Student',
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='seat_allocations'
    )
    seat_number = models.PositiveIntegerField()
    row_number = models.PositiveIntegerField(null=True, blank=True)
    column_number = models.PositiveIntegerField(null=True, blank=True)
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        db_column='department_id',
        related_name='seat_allocations'
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        db_column='subject_id',
        related_name='seat_allocations'
    )
    allocation_status = models.CharField(
        max_length=12,
        choices=ALLOCATION_STATUS_CHOICES,
        default='ALLOCATED'
    )

    class Meta:
        db_table = 'exam_seat_allocation'
        constraints = [
            models.UniqueConstraint(fields=['exam_schedule', 'student'], name='unique_seat_per_exam_student'),
            models.UniqueConstraint(fields=['hall_allocation', 'seat_number'], name='unique_seat_per_hall'),
        ]
        indexes = [
            models.Index(fields=['exam_schedule']),
            models.Index(fields=['hall_allocation']),
            models.Index(fields=['student']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        return f"Seat {self.seat_number} | {self.student.register_number} | Hall: {self.hall_allocation.exam_hall.hall.hall_no}"
