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
