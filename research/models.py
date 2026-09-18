from django.db import models
from common.models import TrackingModel


class FacultyResearchProject(TrackingModel):
    PROJECT_TYPE_CHOICES = [
        ('Funded', 'Funded'),
        ('Non-Funded', 'Non-Funded'),
        ('Consultancy', 'Consultancy'),
        ('Industry Sponsored', 'Industry Sponsored'),
        ('Institutional', 'Institutional'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('Proposed', 'Proposed'),
        ('Ongoing', 'Ongoing'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    project_title = models.CharField(max_length=300)
    project_code = models.CharField(max_length=100, unique=True, null=True, blank=True)
    principal_investigator = models.ForeignKey(
        'users.UserDetails',
        on_delete=models.PROTECT,
        related_name='research_projects'
    )
    co_investigators = models.ManyToManyField(
        'users.UserDetails',
        related_name='co_research_projects',
        blank=True
    )
    external_co_investigators = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="List of external/outer college co-investigators names and affiliations"
    )
    research_area = models.CharField(max_length=200)
    project_type = models.CharField(
        max_length=50,
        choices=PROJECT_TYPE_CHOICES,
        default='Funded'
    )
    funding_agency = models.CharField(max_length=200, null=True, blank=True)
    sanctioned_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )
    project_start_date = models.DateField()
    project_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='Proposed',
        db_index=True
    )
    description = models.TextField(null=True, blank=True)
    objectives = models.TextField(null=True, blank=True)
    outcomes = models.TextField(null=True, blank=True)
    site_name = models.CharField(max_length=200, null=True, blank=True)
    reference_url = models.URLField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = 'faculty_research_projects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project_title} ({self.project_code or self.id})"
