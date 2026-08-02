from rest_framework import serializers
from .models import FormModule, FormField


def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."


class FormModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormModule
        fields = ['id', 'module_name', 'module_key', 'display_order', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'module_name': {'required': True},
            'module_key': {
                'required': True,
                'error_messages': {'unique': 'This module key is already in use.'}
            },
            'display_order': {'required': False},
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_module_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Module name cannot be empty.")
        return value.strip()

    def validate_module_key(self, value):
        if not value.strip():
            raise serializers.ValidationError("Module key cannot be empty.")
        return value.strip().lower()


class FormFieldSerializer(serializers.ModelSerializer):
    form_module_id = serializers.PrimaryKeyRelatedField(
        source='form_module',
        queryset=FormModule.objects.all(),
        error_messages={'does_not_exist': 'Form module does not exist.'}
    )

    class Meta:
        model = FormField
        fields = [
            'id', 'form_module_id', 'field_key', 'field_label', 'field_type', 
            'placeholder', 'default_value', 'required', 'unique', 'validation', 
            'choices', 'help_text', 'display_order', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'field_key': {'required': True},
            'field_label': {'required': True},
            'field_type': {
                'required': True,
                'error_messages': {
                    'invalid_choice': 'Invalid field type. Choose from: text, number, email, date, select, checkbox, radio, textarea, file.'
                }
            },
            'placeholder': {'required': False, 'allow_null': True},
            'default_value': {'required': False, 'allow_null': True},
            'required': {'required': False, 'default': False},
            'unique': {'required': False, 'default': False},
            'validation': {'required': False, 'allow_null': True},
            'choices': {'required': False, 'allow_null': True},
            'help_text': {'required': False, 'allow_null': True},
            'display_order': {'required': False},
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_field_key(self, value):
        if not value.strip():
            raise serializers.ValidationError("Field key cannot be empty.")
        return value.strip().lower()

    def validate_field_label(self, value):
        if not value.strip():
            raise serializers.ValidationError("Field label cannot be empty.")
        return value.strip()

    def validate(self, data):
        # Unique constraint check for unique_together: ('form_module', 'field_key')
        form_module = data.get('form_module')
        field_key = data.get('field_key')
        
        # Check uniqueness on create and updates where key or module changed
        if form_module and field_key:
            qs = FormField.objects.filter(form_module=form_module, field_key=field_key)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError(
                    {"field_key": f"Field key '{field_key}' already exists in this form module."}
                )

        # Choices validation for select/radio field types
        field_type = data.get('field_type')
        choices = data.get('choices')
        if field_type in ['select', 'radio']:
            if not choices:
                raise serializers.ValidationError(
                    {"choices": "Choices are required when field type is select or radio."}
                )
            if not isinstance(choices, list):
                raise serializers.ValidationError(
                    {"choices": "Choices must be a list of options (e.g. ['Option 1', 'Option 2'])."}
                )
        return data
