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
        validators=[RegexValidator(r'^\d{10}$', message='Phone number must be exactly 10 digits.')]
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

        Django's CASCADE uses a bulk SQL DELETE that bypasses overridden delete()
        methods on child objects, so without this loop:
          - Uploaded R2 documents (photos, certificates, etc.) would be orphaned.
          - Student admission slip, fees, marks and counselling records would not
            be wiped (the Application.delete() logic added in Step 2 never fires).

        By calling app.delete() here we guarantee the Application-level cleanup
        runs for every application before Django removes the user row.
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

    class Meta:
        db_table = 'applications'

    def __str__(self):
        return f"{self.application_no} - {self.candidate.name} ({self.status.status_name})"

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
            # Silent fallback to prevent database delete blocks on R2 connectivity issues
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



