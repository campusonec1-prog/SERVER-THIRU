from django.db import models
from common.models import TrackingModel


class StudentStatus(TrackingModel):
    status_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'student_status'

    def __str__(self):
        return self.status_name
