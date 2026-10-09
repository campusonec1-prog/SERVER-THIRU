from django.db import models
from common.models import TrackingModel


class SMSLog(TrackingModel):
    RECIPIENT_CHOICES = [
        ('PARENT', 'Parent'),
        ('STUDENT', 'Student'),
        ('BOTH', 'Both'),
    ]

    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('PENDING', 'Pending'),
    ]

    student = models.ForeignKey(
        'student.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='student_id',
        related_name='sms_logs'
    )
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_CHOICES, default='PARENT')
    phone_number = models.CharField(max_length=20)
    student_name = models.CharField(max_length=255, blank=True, null=True)
    register_number = models.CharField(max_length=100, blank=True, null=True)
    sms_type = models.CharField(max_length=50, default='FULL_DAY_ABSENT')
    template_id = models.CharField(max_length=100, blank=True, null=True)
    message = models.TextField()
    sent_date = models.DateField(help_text="The date of absence or event")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    gateway_response = models.JSONField(default=dict, blank=True)
    response_id = models.CharField(max_length=150, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sms_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sent_date', 'sms_type']),
            models.Index(fields=['student', 'sent_date']),
            models.Index(fields=['status']),
            models.Index(fields=['phone_number']),
        ]

    def __str__(self):
        return f"SMS to {self.phone_number} on {self.sent_date} ({self.status})"
