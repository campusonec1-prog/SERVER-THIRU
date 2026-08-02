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
