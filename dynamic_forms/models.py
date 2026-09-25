import bcrypt
from django.core.validators import RegexValidator
from django.db import models
from common.models import TrackingModel


class FormModule(TrackingModel):
    module_name = models.CharField(max_length=150)
    module_key = models.CharField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'form_modules'
        ordering = ['display_order', 'id']

    def __str__(self):
        return self.module_name


class FormField(TrackingModel):
    FIELD_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('email', 'Email'),
        ('date', 'Date'),
        ('select', 'Select Dropdown'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio Button'),
        ('textarea', 'Text Area'),
        ('file', 'File Upload'),
        ('array', 'Array'),
    ]

    form_module = models.ForeignKey(
        FormModule,
        on_delete=models.CASCADE,
        db_column='form_module_id',
        related_name='fields'
    )
    field_key = models.CharField(max_length=100)
    field_label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=30, choices=FIELD_TYPE_CHOICES)
    placeholder = models.CharField(max_length=255, null=True, blank=True)
    default_value = models.CharField(max_length=255, null=True, blank=True)
    required = models.BooleanField(default=False)
    unique = models.BooleanField(default=False)
    validation = models.CharField(max_length=255, null=True, blank=True) # Regex pattern
    choices = models.JSONField(null=True, blank=True) # For dropdown/radio option lists e.g. ["Male", "Female"]
    help_text = models.TextField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'form_fields'
        unique_together = ('form_module', 'field_key')
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.field_label} ({self.form_module.module_name})"


class ApplicationStatus(TrackingModel):
    status_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'application_status'

    def __str__(self):
        return self.status_name


class DummyRole:
    role_name = 'CANDIDATE'


class ApplicationUser(TrackingModel):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\d{10}$', message='Phone number must be exactly 10 digits.')],
        db_index=True
    )
    password = models.CharField(max_length=255)

    class Meta:
        db_table = 'application_users'

    def __str__(self):
        return self.name

    @property
    def is_authenticated(self):
        return True

    @property
    def role(self):
        return DummyRole()

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith('$2b$'):
            self.password = bcrypt.hashpw(self.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Explicitly call app.delete() for every linked application before removing
        the user record.
        """
        import logging
        logger = logging.getLogger(__name__)

        for app in list(self.applications.all()):
            try:
                app.delete()
            except Exception as e:
                logger.error(
                    f"[ApplicationUser Delete] Failed to clean up application "
                    f"{getattr(app, 'application_no', app.pk)} for user {self.email}: {e}"
                )

        super().delete(*args, **kwargs)


class ApplicationFee(TrackingModel):
    program = models.ForeignKey(
        'institution.Program',
        on_delete=models.CASCADE,
        db_column='program_id',
        related_name='application_fees',
        null=True,
        blank=True
    )
    academic_year = models.ForeignKey(
        'institution.AcademicYear',
        on_delete=models.CASCADE,
        db_column='academic_year_id',
        related_name='application_fees',
        null=True,
        blank=True
    )
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'application_fees'
        ordering = ['-id']

    def __str__(self):
        program_str = self.program.program_name if self.program else "All Programs"
        ay_str = self.academic_year.academic_year if self.academic_year else "All Academic Years"
        return f"{program_str} ({ay_str}) - App Fee: {self.application_fee}, Platform Fee: {self.platform_fee}"

    @property
    def total_fee(self):
        app_fee = self.application_fee or 0
        plat_fee = self.platform_fee or 0
        return app_fee + plat_fee


class Application(TrackingModel):
    candidate = models.ForeignKey(
        ApplicationUser,
        on_delete=models.CASCADE,
        db_column='candidate_id',
        related_name='applications'
    )
    program = models.ForeignKey(
        'institution.Program',
        on_delete=models.CASCADE,
        db_column='program_id',
        related_name='applications'
    )
    application_no = models.CharField(max_length=50, unique=True, blank=True)
    form_data = models.JSONField(default=dict)
    status = models.ForeignKey(
        ApplicationStatus,
        on_delete=models.PROTECT,
        db_column='status_id',
        related_name='applications'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ('UNPAID', 'Unpaid'),
            ('PENDING', 'Pending'),
            ('PAID', 'Paid'),
            ('FAILED', 'Failed'),
        ],
        default='UNPAID',
        db_index=True
    )
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'applications'

    def __str__(self):
        return f"{self.application_no} - {self.candidate.name} ({self.status.status_name}) - Payment: {self.payment_status}"

    def delete(self, *args, **kwargs):
        # ── 1. Clean up files in Cloudflare R2 before deleting the application record ──
        try:
            from common.r2 import delete_file_from_r2
            from django.conf import settings
            
            public_url_base = settings.CLOUDFLARE_R2_PUBLIC_URL.rstrip('/')
            
            def extract_urls(data):
                found = []
                if isinstance(data, str):
                    if data.startswith(public_url_base):
                        found.append(data)
                elif isinstance(data, dict):
                    for v in data.values():
                        found.extend(extract_urls(v))
                elif isinstance(data, list):
                    for item in data:
                        found.extend(extract_urls(item))
                return found

            urls = extract_urls(self.form_data or {})
            for url in urls:
                delete_file_from_r2(url)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[R2 Delete Error] Failed to delete files for application {self.application_no}: {e}")

        # ── 2. Delete the linked Student record (cascades to admission slip,
        #        fees, marks and counselling reports automatically) ──────────
        try:
            from student.models import Student
            candidate = self.candidate
            if candidate:
                student = getattr(candidate, 'student', None)
                if student:
                    student.delete()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[Student Delete Error] Failed to delete student for application {self.application_no}: {e}")

        super().delete(*args, **kwargs)


class PaymentStatus(models.TextChoices):
    CREATED = 'CREATED', 'Created'
    PENDING = 'PENDING', 'Pending'
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentTransaction(TrackingModel):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        db_column='application_id',
        related_name='payment_transactions',
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        ApplicationUser,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='payment_transactions'
    )
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True, unique=True, db_index=True)
    razorpay_signature = models.CharField(max_length=255, null=True, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Total amount in INR
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=10, default='INR')

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.CREATED,
        db_index=True
    )
    payment_method = models.CharField(max_length=50, null=True, blank=True)

    razorpay_order_response = models.JSONField(null=True, blank=True)
    razorpay_payment_response = models.JSONField(null=True, blank=True)
    razorpay_signature_verification_response = models.JSONField(null=True, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-id']

    def __str__(self):
        return f"Payment {self.razorpay_order_id} - App {self.application.application_no} - ₹{self.amount} ({self.status})"
