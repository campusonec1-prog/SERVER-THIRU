from rest_framework import serializers
from .models import Day, Period, Session


def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly} is required."
        field.error_messages['blank'] = f"{friendly} cannot be empty."
        field.error_messages['null'] = f"{friendly} cannot be null."


class DaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Day
        fields = ['id', 'day_name', 'day_code', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'day_name': {
                'required': True,
                'error_messages': {'unique': 'This day name already exists.'}
            },
            'day_code': {
                'required': True,
                'error_messages': {'unique': 'This day code already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_day_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Day name cannot be empty.")
        return value.strip()

    def validate_day_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Day code cannot be empty.")
        return value.strip().upper()


class PeriodSerializer(serializers.ModelSerializer):
    session_id = serializers.PrimaryKeyRelatedField(
        source='session',
        queryset=Session.objects.all(),
        error_messages={'does_not_exist': 'Session does not exist.'}
    )

    class Meta:
        model = Period
        fields = ['id', 'period_no', 'session_id', 'start_time', 'end_time', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'period_no': {
                'required': True,
                'error_messages': {'unique': 'This period number already exists.'}
            },
            'start_time': {'required': True},
            'end_time': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_period_no(self, value):
        if value <= 0:
            raise serializers.ValidationError("Period number must be greater than 0.")
        return value

    def validate(self, data):
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after the start time."}
            )
        return data


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['id', 'session_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'session_name': {
                'required': True,
                'error_messages': {'unique': 'This session name already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_session_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Session name cannot be empty.")
        return value.strip()


