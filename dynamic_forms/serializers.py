from rest_framework import serializers
from .models import FormModule, FormField, Application, ApplicationStatus, ApplicationUser
from institution.models import Program


STATE_NAME_TO_CODE = {
    'tamil nadu': 'TN',
    'kerala': 'KL',
    'karnataka': 'KA',
    'andhra pradesh': 'AP',
    'telangana': 'TS',
    'puducherry': 'PY',
    'pondicherry': 'PY'
}

def normalize_state_value(val):
    if not val:
        return ''
    lower = str(val).strip().lower()
    return STATE_NAME_TO_CODE.get(lower, val)

def find_parent_value(field_key, choices, form_data, module_key=None):
    if not isinstance(choices, dict):
        return None
        
    key_map = {k.lower(): k for k in choices.keys()}
    possible_parent_keys = list(key_map.keys())
    if not possible_parent_keys:
        return None
        
    prefixes = ['', 'permanent_', 'communication_', 'present_', 'native_', 'parent_']
    base_names = ['state', 'country', 'region', 'nationality', 'category']
    
    current_prefix = ''
    for pf in prefixes:
        if pf and field_key.startswith(pf):
            current_prefix = pf
            break
            
    module_data = form_data.get(module_key, {}) if module_key else {}
    for base in base_names:
        candidate_key = current_prefix + base
        candidate_val = module_data.get(candidate_key)
        if candidate_val:
            lower_raw = str(candidate_val).strip().lower()
            if lower_raw in possible_parent_keys:
                return key_map[lower_raw]
            normalized = normalize_state_value(candidate_val)
            lower_val = str(normalized).lower()
            if lower_val in possible_parent_keys:
                return key_map[lower_val]
            
    for m_key, m_data in form_data.items():
        if not isinstance(m_data, dict):
            continue
        for base in base_names:
            candidate_key = current_prefix + base
            candidate_val = m_data.get(candidate_key)
            if candidate_val:
                lower_raw = str(candidate_val).strip().lower()
                if lower_raw in possible_parent_keys:
                    return key_map[lower_raw]
                normalized = normalize_state_value(candidate_val)
                lower_val = str(normalized).lower()
                if lower_val in possible_parent_keys:
                    return key_map[lower_val]
                
    best_match_val = None
    highest_score = -1
    for m_key, m_data in form_data.items():
        if not isinstance(m_data, dict):
            continue
        for f_key, val_raw in m_data.items():
            val = str(val_raw or '')
            if val:
                lower_raw = val.strip().lower()
                if lower_raw in possible_parent_keys:
                    score = 0
                    if current_prefix and f_key.startswith(current_prefix):
                        score += 10
                    if 'state' in f_key.lower():
                        score += 5
                    if f_key.lower() == 'state':
                        score += 8
                    if score > highest_score:
                        highest_score = score
                        best_match_val = key_map[lower_raw]
                else:
                    normalized = normalize_state_value(val)
                    lower_val = str(normalized).lower()
                    if lower_val in possible_parent_keys:
                        score = 0
                        if current_prefix and f_key.startswith(current_prefix):
                            score += 10
                        if 'state' in f_key.lower():
                            score += 5
                        if f_key.lower() == 'state':
                            score += 8
                        if score > highest_score:
                            highest_score = score
                            best_match_val = key_map[lower_val]
                    
    return best_match_val


def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."


class FormModuleListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        seen_keys = set()
        for idx, item in enumerate(attrs):
            module_key = item.get('module_key')
            if module_key:
                if module_key in seen_keys:
                    raise serializers.ValidationError(
                        f"Duplicate module_key '{module_key}' found in request payload at position {idx + 1}."
                    )
                seen_keys.add(module_key)
        return super().validate(attrs)

    def create(self, validated_data):
        return [FormModule.objects.create(**item) for item in validated_data]


class FormModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormModule
        list_serializer_class = FormModuleListSerializer
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


class FormFieldListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        seen_keys = set()
        for idx, item in enumerate(attrs):
            form_module = item.get('form_module')
            field_key = item.get('field_key')
            if form_module and field_key:
                mod_id = form_module.id if hasattr(form_module, 'id') else form_module
                pair = (mod_id, field_key)
                if pair in seen_keys:
                    raise serializers.ValidationError(
                        f"Duplicate field_key '{field_key}' for module ID {mod_id} found in request payload at position {idx + 1}."
                    )
                seen_keys.add(pair)
        return super().validate(attrs)

    def create(self, validated_data):
        return [FormField.objects.create(**item) for item in validated_data]


class FormFieldSerializer(serializers.ModelSerializer):
    form_module_id = serializers.PrimaryKeyRelatedField(
        source='form_module',
        queryset=FormModule.objects.all(),
        error_messages={'does_not_exist': 'Form module does not exist.'}
    )

    class Meta:
        model = FormField
        list_serializer_class = FormFieldListSerializer
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
                    'invalid_choice': 'Invalid field type. Choose from: text, number, email, date, select, checkbox, radio, textarea, file, array.'
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
            if choices is not None:
                if not isinstance(choices, (list, dict)):
                    raise serializers.ValidationError(
                        {"choices": "Choices must be a list of options or a dictionary mapping parent keys to lists of options."}
                    )
                if isinstance(choices, dict):
                    for key, val in choices.items():
                        if not isinstance(val, list):
                            raise serializers.ValidationError(
                                {"choices": f"Choices for key '{key}' must be a list of options."}
                            )
        elif field_type == 'array':
            if not choices:
                raise serializers.ValidationError(
                    {"choices": "Column choices definition is required for array field type."}
                )
            if not isinstance(choices, list):
                raise serializers.ValidationError(
                    {"choices": "Array choices must be a list of column objects."}
                )
            for idx, col in enumerate(choices):
                if not isinstance(col, dict) or 'key' not in col or 'label' not in col or 'type' not in col:
                    raise serializers.ValidationError(
                        {"choices": f"Column {idx + 1} must be an object with 'key', 'label', and 'type' attributes."}
                    )
        return data


class ApplicationStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationStatus
        fields = ['id', 'status_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'status_name': {
                'required': True,
                'error_messages': {'unique': 'This status name already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_status_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Status name cannot be empty.")
        return value.strip()


class ApplicationUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationUser
        fields = ['id', 'name', 'email', 'phone_number', 'password', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'password': {'write_only': True},
            'name': {'required': True},
            'email': {
                'required': True,
                'error_messages': {'unique': 'A candidate with this email already exists.'}
            },
            'phone_number': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()

    def validate_phone_number(self, value):
        if not value.strip():
            raise serializers.ValidationError("Phone number cannot be empty.")
        import re
        pattern = r'^\d{10}$'
        if not re.match(pattern, value.strip()):
            raise serializers.ValidationError("Phone number must be exactly 10 digits.")
        return value.strip()

    def validate_password(self, value):
        if not value.strip() or len(value) < 6:
            raise serializers.ValidationError("Password must be at least 6 characters long.")
        return value


class ApplicationSerializer(serializers.ModelSerializer):
    candidate_id = serializers.PrimaryKeyRelatedField(
        source='candidate',
        queryset=ApplicationUser.objects.all(),
        required=False,
        error_messages={'does_not_exist': 'Candidate does not exist.'}
    )
    program_id = serializers.PrimaryKeyRelatedField(
        source='program',
        queryset=Program.objects.all(),
        required=False,
        error_messages={'does_not_exist': 'Program does not exist.'}
    )
    status_id = serializers.PrimaryKeyRelatedField(
        source='status',
        queryset=ApplicationStatus.objects.all(),
        required=False,
        error_messages={'does_not_exist': 'Application status does not exist.'}
    )
    
    candidate_name = serializers.CharField(source='candidate.name', read_only=True)
    program_name = serializers.CharField(source='program.program_name', read_only=True)
    status_name = serializers.CharField(source='status.status_name', read_only=True)
    readable_form_data = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'candidate_id', 'candidate_name', 'program_id', 'program_name', 
            'application_no', 'form_data', 'readable_form_data', 'status_id', 'status_name', 
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'application_no']
        extra_kwargs = {
            'form_data': {'required': False, 'default': dict},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def get_readable_form_data(self, obj):
        form_data = obj.form_data or {}
        readable_data = {}
        
        # Load all form fields to lookup labels
        fields = FormField.objects.filter(is_active=True).select_related('form_module')
        fields_map = {f.field_key: f for f in fields}
        
        for module_key, module_payload in form_data.items():
            if not isinstance(module_payload, dict):
                readable_data[module_key] = module_payload
                continue
            readable_data[module_key] = {}
            for field_key, field_value in module_payload.items():
                field = fields_map.get(field_key)
                if field and field.field_type in ['select', 'radio'] and field.choices:
                    resolved_choices = []
                    if isinstance(field.choices, list):
                        resolved_choices = field.choices
                    elif isinstance(field.choices, dict):
                        parent_val = find_parent_value(field_key, field.choices, form_data, module_key)
                        resolved_choices = field.choices.get(parent_val) if parent_val else []
                        if not resolved_choices:
                            # Fallback: gather all options
                            for val in field.choices.values():
                                if isinstance(val, list):
                                    resolved_choices.extend(val)
                    
                    label = field_value
                    if isinstance(resolved_choices, list):
                        for opt in resolved_choices:
                            if isinstance(opt, dict):
                                val = opt.get('value', opt.get('id', opt.get('key', opt.get('name', ''))))
                                if str(val) == str(field_value):
                                    label = opt.get('label', opt.get('name', opt.get('display', field_value)))
                                    break
                            else:
                                if str(opt) == str(field_value):
                                    label = opt
                                    break
                    readable_data[module_key][field_key] = label
                else:
                    readable_data[module_key][field_key] = field_value
                    
        return readable_data

    def validate(self, data):
        # Auto-assign candidate from logged-in user if candidate is logged in
        request = self.context.get('request')
        user = request.user if request else None
        if user and user.is_authenticated:
            if user.__class__.__name__ == 'ApplicationUser':
                data['candidate'] = user
        
        if not data.get('candidate') and not (self.instance and self.instance.candidate):
            raise serializers.ValidationError({"candidate_id": "Candidate is required."})

        # Auto-assign default 'Submitted' status if status is not provided on creation
        if not data.get('status') and not (self.instance and self.instance.status):
            submitted_status = ApplicationStatus.objects.filter(status_name__iexact='Submitted').first()
            if not submitted_status:
                submitted_status = ApplicationStatus.objects.create(status_name='Submitted')
            data['status'] = submitted_status

        # Derive program if not explicitly provided
        if not data.get('program') and not (self.instance and self.instance.program):
            input_form_data = data.get('form_data', {})
            course_selection = input_form_data.get('course_selection', {})
            department_name = course_selection.get('department')
            if isinstance(department_name, list) and len(department_name) > 0:
                department_name = department_name[0]
            if department_name:
                from institution.models import Department
                try:
                    dept = Department.objects.get(department_name__iexact=str(department_name).strip())
                    data['program'] = dept.program
                except Department.DoesNotExist:
                    raise serializers.ValidationError({"program_id": f"Could not derive program: department '{department_name}' does not exist."})
            else:
                raise serializers.ValidationError({"program_id": "Program is required."})

        status_instance = data.get('status', self.instance.status if self.instance else None)
        status_name = status_instance.status_name.lower() if status_instance else 'submitted'


        # Filter and keep only dynamic fields that exist in the database
        if 'form_data' in data or self.instance is None:
            input_form_data = data.get('form_data', {})
            if not isinstance(input_form_data, dict):
                raise serializers.ValidationError({"form_data": "Form data must be a JSON object (key-value dictionary)."})
            
            active_modules = FormModule.objects.filter(is_active=True)
            cleaned_form_data = {}
            for module in active_modules:
                module_key = module.module_key
                if module_key in input_form_data:
                    module_payload = input_form_data.get(module_key)
                    if isinstance(module_payload, dict):
                        cleaned_form_data[module_key] = {}
                        active_fields = FormField.objects.filter(form_module=module, is_active=True)
                        for field in active_fields:
                            field_key = field.field_key
                            if field_key in module_payload:
                                cleaned_form_data[module_key][field_key] = module_payload[field_key]
            data['form_data'] = cleaned_form_data
            form_data = cleaned_form_data
        else:
            form_data = self.instance.form_data if self.instance else {}

        if status_name == 'submitted':
            active_modules = FormModule.objects.filter(is_active=True)
            errors = {}

            for module in active_modules:
                module_key = module.module_key
                module_data = form_data.get(module_key, {})

                active_fields = FormField.objects.filter(form_module=module, is_active=True)
                for field in active_fields:
                    field_key = field.field_key
                    field_value = module_data.get(field_key)

                    if field.field_type == 'array':
                        if field.required and (not field_value or not isinstance(field_value, list) or len(field_value) == 0):
                            if module_key not in errors:
                                errors[module_key] = {}
                            errors[module_key][field_key] = f"Field '{field.field_label}' requires at least one entry."
                            continue
                        
                        if field_value and isinstance(field_value, list):
                            columns = field.choices if isinstance(field.choices, list) else []
                            for row_idx, row in enumerate(field_value):
                                if not isinstance(row, dict):
                                    if module_key not in errors:
                                        errors[module_key] = {}
                                    errors[module_key][field_key] = f"Row {row_idx + 1} must be an object."
                                    break
                                for col in columns:
                                    if not isinstance(col, dict):
                                        continue
                                    col_key = col.get('key')
                                    col_label = col.get('label', col_key)
                                    col_val = row.get(col_key)
                                    if col.get('required') and (col_val is None or col_val == ''):
                                        if module_key not in errors:
                                            errors[module_key] = {}
                                        errors[module_key][field_key] = f"Row {row_idx + 1}: '{col_label}' is required."
                                        break
                                    if col_val is not None and col_val != '':
                                        col_type = col.get('type')
                                        if col_type == 'number':
                                            try:
                                                float(col_val)
                                            except ValueError:
                                                if module_key not in errors:
                                                    errors[module_key] = {}
                                                errors[module_key][field_key] = f"Row {row_idx + 1}: '{col_label}' must be a number."
                                                break
                                        elif col_type == 'email':
                                            from django.core.validators import validate_email
                                            from django.core.exceptions import ValidationError
                                            try:
                                                validate_email(col_val)
                                            except ValidationError:
                                                if module_key not in errors:
                                                    errors[module_key] = {}
                                                errors[module_key][field_key] = f"Row {row_idx + 1}: '{col_label}' has invalid email format."
                                                break
                                        elif col_type == 'select':
                                            opts = col.get('options')
                                            if opts and isinstance(opts, list) and col_val not in opts and str(col_val) not in [str(o) for o in opts]:
                                                if module_key not in errors:
                                                    errors[module_key] = {}
                                                errors[module_key][field_key] = f"Row {row_idx + 1}: Invalid option for '{col_label}'."
                                                break

                    else:
                        if field.required and (field_value is None or field_value == '' or (isinstance(field_value, list) and len(field_value) == 0)):
                            if module_key not in errors:
                                errors[module_key] = {}
                            errors[module_key][field_key] = f"Field '{field.field_label}' is required."
                            continue

                        if field_value is not None and field_value != '' and not (isinstance(field_value, list) and len(field_value) == 0):
                            if field.field_type == 'number':
                                try:
                                    float(field_value)
                                except ValueError:
                                    if module_key not in errors:
                                        errors[module_key] = {}
                                    errors[module_key][field_key] = "Value must be a number."
                                    continue

                            elif field.field_type == 'email':
                                from django.core.validators import validate_email
                                from django.core.exceptions import ValidationError
                                try:
                                    validate_email(field_value)
                                except ValidationError:
                                    if module_key not in errors:
                                        errors[module_key] = {}
                                    errors[module_key][field_key] = "Invalid email format."
                                    continue

                            elif field.field_type in ['select', 'radio']:
                                if field.choices:
                                    resolved_choices = []
                                    if isinstance(field.choices, list):
                                        resolved_choices = field.choices
                                    elif isinstance(field.choices, dict):
                                        parent_val = find_parent_value(field_key, field.choices, form_data, module_key)
                                        resolved_choices = field.choices.get(parent_val) if parent_val else []
                                    
                                    valid_option_values = []
                                    if isinstance(resolved_choices, list):
                                        for opt in resolved_choices:
                                            if isinstance(opt, dict):
                                                val = opt.get('value', opt.get('id', opt.get('key', opt.get('name', ''))))
                                                valid_option_values.append(str(val))
                                            else:
                                                valid_option_values.append(str(opt))
                                                
                                    if valid_option_values:
                                        if isinstance(field_value, list):
                                            invalid_opts = [str(val) for val in field_value if str(val) not in valid_option_values]
                                            if invalid_opts:
                                                if module_key not in errors:
                                                    errors[module_key] = {}
                                                errors[module_key][field_key] = f"Invalid options: {', '.join(invalid_opts)}."
                                                continue
                                        else:
                                            if str(field_value) not in valid_option_values:
                                                if module_key not in errors:
                                                    errors[module_key] = {}
                                                limit_options = valid_option_values[:10]
                                                opts_str = ", ".join(limit_options)
                                                if len(valid_option_values) > 10:
                                                    opts_str += f"... (+{len(valid_option_values)-10} more)"
                                                errors[module_key][field_key] = f"Invalid option. Must be one of: {opts_str}."
                                                continue

                            if field.validation:
                                import re
                                if not re.match(field.validation, str(field_value)):
                                    if module_key not in errors:
                                        errors[module_key] = {}
                                    errors[module_key][field_key] = f"Value does not match pattern format."

            # Register Number Uniqueness Validation
            submitted_reg_numbers = []
            for m_key, m_data in form_data.items():
                if isinstance(m_data, dict):
                    for f_key, f_val in m_data.items():
                        if isinstance(f_val, list):
                            for r_idx, row in enumerate(f_val):
                                if isinstance(row, dict) and 'register_number' in row:
                                    reg_no = str(row['register_number']).strip().upper()
                                    if reg_no:
                                        submitted_reg_numbers.append((m_key, f_key, r_idx, reg_no))

            seen_reg_nos = {}
            for m_key, f_key, r_idx, reg_no in submitted_reg_numbers:
                if reg_no in seen_reg_nos:
                    if m_key not in errors:
                        errors[m_key] = {}
                    errors[m_key][f_key] = f"Duplicate register number '{reg_no}' found in your qualifications list."
                else:
                    seen_reg_nos[reg_no] = (m_key, f_key, r_idx)

            # Check other applications for matching register numbers in database
            other_apps = Application.objects.all()
            if self.instance and self.instance.pk:
                other_apps = other_apps.exclude(pk=self.instance.pk)

            for other_app in other_apps:
                other_form_data = other_app.form_data or {}
                for o_m_key, o_m_data in other_form_data.items():
                    if isinstance(o_m_data, dict):
                        for o_f_key, o_f_val in o_m_data.items():
                            if isinstance(o_f_val, list):
                                for o_row in o_f_val:
                                    if isinstance(o_row, dict) and 'register_number' in o_row:
                                        o_reg_no = str(o_row['register_number']).strip().upper()
                                        if o_reg_no in seen_reg_nos:
                                            dup_m_key, dup_f_key, _ = seen_reg_nos[o_reg_no]
                                            if dup_m_key not in errors:
                                                errors[dup_m_key] = {}
                                            errors[dup_m_key][dup_f_key] = f"Register number '{o_reg_no}' is already registered in another candidate's application."

            if errors:
                raise serializers.ValidationError({"form_data": errors})

        return data


