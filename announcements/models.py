from django.db import models
from common.models import TrackingModel


class NoticeBoard(TrackingModel):
    NOTICE_TYPE_CHOICES = [
        ('general', 'General'),
        ('academic', 'Academic'),
        ('exam', 'Exam'),
        ('holiday', 'Holiday'),
        ('holidays', 'Holidays'),
        ('event', 'Event'),
        ('events', 'Events'),
        ('fees', 'Fees'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    TARGET_AUDIENCE_CHOICES = [
        ('global', 'Global (All Departments)'),
        ('targeted', 'Targeted'),
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

    # Event details
    organizer = models.CharField(max_length=255, null=True, blank=True)
    coordinator = models.CharField(max_length=255, null=True, blank=True)
    sub_coordinators = models.JSONField(default=list, blank=True, null=True)
    poster_url = models.TextField(null=True, blank=True)

    # Target audience fields
    target_audience_type = models.CharField(
        max_length=20,
        choices=TARGET_AUDIENCE_CHOICES,
        default='global'
    )
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notices'
    )
    batch = models.CharField(max_length=50, null=True, blank=True)
    section = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'notice_board'
        indexes = [
            models.Index(fields=['is_active', 'expire_date']),
            models.Index(fields=['department', 'is_active']),
            models.Index(fields=['notice_type']),
        ]

    def __str__(self):
        return f"{self.notice_title} ({self.notice_type})"

