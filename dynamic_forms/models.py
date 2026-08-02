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


