from django.db import models
from common.models import TrackingModel


class Day(TrackingModel):
    day_name = models.CharField(max_length=50, unique=True)
    day_code = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'days'

    def __str__(self):
        return f"{self.day_name} ({self.day_code})"


class Session(TrackingModel):
    session_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'sessions'

    def __str__(self):
        return self.session_name


class Period(TrackingModel):
    period_no = models.PositiveIntegerField(unique=True)
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        db_column='session_id',
        related_name='periods'
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        db_table = 'periods'

    def __str__(self):
        return f"Period {self.period_no} ({self.session.session_name}): {self.start_time} - {self.end_time}"


class AcademicCalendarEvent(TrackingModel):
    EVENT_TYPE_CHOICES = [
        ('DAY_ORDER', 'Working Day Order'),
        ('DAY_ORDER_SWAP', 'Working Day Order'),
        ('HOLIDAY', 'Holiday'),
        ('SUSPENSION', 'Class Suspension'),
    ]
    SESSION_SCOPE_CHOICES = [
        ('FULL_DAY', 'Full Day'),
        ('FORENOON', 'Half Day (Forenoon FN)'),
        ('AFTERNOON', 'Half Day (Afternoon AN)'),
        ('SPECIFIC_PERIODS', 'Specific Periods'),
    ]
    HOLIDAY_CATEGORY_CHOICES = [
        ('GOVERNMENT', 'Government Holiday'),
        ('FESTIVAL', 'Festival Holiday'),
        ('RAIN', 'Rain Holiday'),
        ('INSTITUTIONAL', 'Institutional Holiday'),
        ('EMERGENCY', 'Emergency Suspension'),
        ('OTHER', 'Other Holiday'),
    ]


    date = models.DateField()
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    target_day = models.ForeignKey(
        Day,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='target_day_id',
        related_name='day_order_overrides'
    )
    session_scope = models.CharField(max_length=30, choices=SESSION_SCOPE_CHOICES, default='FULL_DAY')
    holiday_category = models.CharField(max_length=30, choices=HOLIDAY_CATEGORY_CHOICES, null=True, blank=True)
    title = models.CharField(max_length=200)
    reason = models.TextField(null=True, blank=True)

    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='department_id',
        related_name='calendar_events'
    )
    batch = models.ForeignKey(
        'institution.Batch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='batch_id',
        related_name='calendar_events'
    )
    academic_year = models.ForeignKey(
        'institution.AcademicYear',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='academic_year_id',
        related_name='calendar_events'
    )

    class Meta:
        db_table = 'academic_calendar_events'
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.title} ({self.get_event_type_display()})"

