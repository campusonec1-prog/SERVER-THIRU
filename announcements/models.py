from django.db import models
from common.models import TrackingModel


class NoticeBoard(TrackingModel):
    NOTICE_TYPE_CHOICES = [
        ('general', 'General'),
        ('academic', 'Academic'),
        ('exam', 'Exam'),
        ('holiday', 'Holiday'),
        ('event', 'Event'),
        ('fees', 'Fees'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    notice_title = models.CharField(max_length=255)
    notice_type = models.CharField(max_length=20, choices=NOTICE_TYPE_CHOICES)
    priority = models.CharField(max_length=15, choices=PRIORITY_CHOICES)
    publish_date = models.DateTimeField()
    expire_date = models.DateTimeField()
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    faculty = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        db_column='faculty_id',
        related_name='notices'
    )

    class Meta:
        db_table = 'notice_board'

    def __str__(self):
        return f"{self.notice_title} ({self.notice_type})"
