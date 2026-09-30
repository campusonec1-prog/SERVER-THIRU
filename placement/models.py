from django.db import models
from common.models import TrackingModel


class IndustryChoices(models.TextChoices):
    IT_SOFTWARE = 'IT_SOFTWARE', 'Information Technology & Software'
    FINANCE_BANKING = 'FINANCE_BANKING', 'Finance, Banking & Fintech'
    CORE_ENGINEERING = 'CORE_ENGINEERING', 'Core Engineering & Manufacturing'
    HEALTHCARE_PHARMA = 'HEALTHCARE_PHARMA', 'Healthcare & Pharmaceuticals'
    ECOMMERCE_RETAIL = 'ECOMMERCE_RETAIL', 'E-Commerce & Retail'
    CONSULTING_ANALYTICS = 'CONSULTING_ANALYTICS', 'Consulting & Business Analytics'
    EDTECH_EDUCATION = 'EDTECH_EDUCATION', 'Education & EdTech'
    TELECOM = 'TELECOM', 'Telecommunications & Networks'
    LOGISTICS_SUPPLY_CHAIN = 'LOGISTICS_SUPPLY_CHAIN', 'Logistics & Supply Chain'
    AUTOMOTIVE = 'AUTOMOTIVE', 'Automotive & EV'
    ENERGY_POWER = 'ENERGY_POWER', 'Energy, Oil & Clean Power'
    MEDIA_ENTERTAINMENT = 'MEDIA_ENTERTAINMENT', 'Media & Entertainment'
    CONSTRUCTION = 'CONSTRUCTION', 'Civil & Construction'
    OTHER = 'OTHER', 'Other'


class DriveTypeChoices(models.TextChoices):
    FULL_TIME = 'FULL_TIME', 'Full Time'
    INTERNSHIP = 'INTERNSHIP', 'Internship'
    INTERNSHIP_PPO = 'INTERNSHIP_PPO', 'Internship + PPO'
    CONTRACT = 'CONTRACT', 'Contract'
    APPRENTICESHIP = 'APPRENTICESHIP', 'Apprenticeship'
    OTHER = 'OTHER', 'Other'


class DriveStatusChoices(models.TextChoices):
    UPCOMING = 'UPCOMING', 'Upcoming'
    REGISTRATION_OPEN = 'REGISTRATION_OPEN', 'Registration Open'
    REGISTRATION_CLOSED = 'REGISTRATION_CLOSED', 'Registration Closed'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PlacementCompany(TrackingModel):
    company_name = models.CharField(max_length=200, db_index=True)
    industry = models.CharField(
        max_length=50,
        choices=IndustryChoices.choices,
        default=IndustryChoices.IT_SOFTWARE,
        db_index=True
    )
    company_website = models.URLField(max_length=500, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # Contact Person Details (Optional)
    contact_person_name = models.CharField(max_length=150, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True, db_index=True)
    contact_phone_number = models.CharField(max_length=20, blank=True, null=True)

    # Location Details
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    state = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'placement_companies'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_name', 'is_active']),
            models.Index(fields=['industry', 'is_active']),
        ]

    def __str__(self):
        return f"{self.company_name} ({self.get_industry_display()})"


class PlacementDrive(TrackingModel):
    company = models.ForeignKey(
        PlacementCompany,
        on_delete=models.CASCADE,
        related_name='drives',
        db_column='company_id'
    )
    job_role = models.CharField(max_length=200, db_index=True)
    drive_type = models.CharField(
        max_length=30,
        choices=DriveTypeChoices.choices,
        default=DriveTypeChoices.FULL_TIME,
        db_index=True
    )
    job_description = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=250, blank=True, null=True)
    ctc = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="e.g., 6.5 LPA, 30,000 / month, Best in Industry"
    )

    # Key Recruitment Dates
    application_start_date = models.DateField(db_index=True)
    application_end_date = models.DateField(db_index=True)
    drive_date = models.DateField(blank=True, null=True, db_index=True)

    # Attachment / JD Document (Stored in Cloudflare R2)
    document_url = models.URLField(
        max_length=600,
        blank=True,
        null=True,
        help_text="Cloudflare R2 document URL for Job Description/Circular"
    )
    document_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Original file name of uploaded JD document"
    )

    # Current Status
    status = models.CharField(
        max_length=30,
        choices=DriveStatusChoices.choices,
        default=DriveStatusChoices.UPCOMING,
        db_index=True
    )

    class Meta:
        db_table = 'placement_drives'
        ordering = ['-application_start_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['drive_type', 'status']),
            models.Index(fields=['application_start_date', 'application_end_date']),
        ]

    def __str__(self):
        return f"{self.job_role} - {self.company.company_name} ({self.get_status_display()})"


class PlacementDriveEligibility(TrackingModel):
    drive = models.ForeignKey(
        PlacementDrive,
        on_delete=models.CASCADE,
        related_name='eligibility_criteria',
        db_column='drive_id'
    )
    minimum_cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.00,
        help_text="Minimum required CGPA (e.g. 6.50, 7.00)"
    )
    max_backlogs = models.PositiveIntegerField(
        default=0,
        help_text="Maximum allowed standing/active backlogs (0 for no backlogs)"
    )
    departments = models.ManyToManyField(
        'institution.Department',
        related_name='placement_eligibilities',
        blank=True
    )
    batches = models.ManyToManyField(
        'institution.Batch',
        related_name='placement_eligibilities',
        blank=True
    )

    class Meta:
        db_table = 'placement_drive_eligibility'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['drive']),
            models.Index(fields=['minimum_cgpa', 'max_backlogs']),
        ]

    def __str__(self):
        return f"Eligibility for {self.drive.job_role} - {self.drive.company.company_name} (Min CGPA: {self.minimum_cgpa}, Max Backlogs: {self.max_backlogs})"
