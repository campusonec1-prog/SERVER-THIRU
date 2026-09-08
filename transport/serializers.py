from rest_framework import serializers
from .models import Driver, Bus, TransportRoute, RouteStop


def apply_default_error_messages(fields):
    """Apply standard required/blank/null error messages to all fields."""
    for field_name, field in fields.items():
        friendly = field_name.replace('_', ' ').capitalize()
        if hasattr(field, 'error_messages'):
            field.error_messages['required'] = f"{friendly} is required."
            field.error_messages['blank'] = f"{friendly} cannot be empty."
            field.error_messages['null'] = f"{friendly} cannot be null."


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = [
            'id', 'driver_name', 'license_number', 'phone_number',
            'address', 'date_of_joining', 'is_active', 'created_at',
            'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_license_number(self, value):
        instance_id = getattr(self.instance, 'id', None)
        query = Driver.objects.filter(license_number__iexact=value)
        if instance_id:
            query = query.exclude(id=instance_id)
        if query.exists():
            raise serializers.ValidationError("Driver with this license number already exists.")
        return value


class BusSerializer(serializers.ModelSerializer):
    driver_id = serializers.PrimaryKeyRelatedField(
        source='driver',
        queryset=Driver.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Driver does not exist or is not active.'}
    )
    route_id = serializers.PrimaryKeyRelatedField(
        source='route',
        queryset=TransportRoute.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Route does not exist.'}
    )

    class Meta:
        model = Bus
        fields = [
            'id', 'bus_number', 'registration_number', 'capacity',
            'driver_id', 'route_id', 'fuel_type', 'fuel_tank_capacity',
            'is_active', 'status',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def validate_fuel_type(self, value):
        if value:
            val_upper = str(value).upper()
            valid_choices = [c[0] for c in Bus.FUEL_TYPE_CHOICES]
            if val_upper in valid_choices:
                return val_upper
        return value

    def validate(self, attrs):
        if 'is_active' in attrs:
            attrs['status'] = 'ACTIVE' if attrs['is_active'] else 'INACTIVE'
        elif 'status' in attrs:
            attrs['is_active'] = (attrs['status'] == 'ACTIVE')
        return super().validate(attrs)

    def validate_bus_number(self, value):
        instance_id = getattr(self.instance, 'id', None)
        query = Bus.objects.filter(bus_number__iexact=value)
        if instance_id:
            query = query.exclude(id=instance_id)
        if query.exists():
            raise serializers.ValidationError("Bus with this bus number already exists.")
        return value

    def validate_registration_number(self, value):
        instance_id = getattr(self.instance, 'id', None)
        query = Bus.objects.filter(registration_number__iexact=value)
        if instance_id:
            query = query.exclude(id=instance_id)
        if query.exists():
            raise serializers.ValidationError("Bus with this registration number already exists.")
        return value

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.driver:
            ret['driver_name'] = instance.driver.driver_name
            ret['driver_phone'] = instance.driver.phone_number
            ret['driver_license'] = instance.driver.license_number
        else:
            ret['driver_name'] = ''
            ret['driver_phone'] = ''
            ret['driver_license'] = ''

        if instance.route:
            ret['route_name'] = instance.route.route_name
            ret['start_location'] = instance.route.start_location
            ret['end_location'] = instance.route.end_location
        else:
            ret['route_name'] = ''
            ret['start_location'] = ''
            ret['end_location'] = ''

        ret['allocated_students_count'] = instance.students.count() if hasattr(instance, 'students') else 0
        return ret


class RouteStopSerializer(serializers.ModelSerializer):
    route_id = serializers.PrimaryKeyRelatedField(
        source='route',
        queryset=TransportRoute.objects.all(),
        error_messages={'does_not_exist': 'Route does not exist.'}
    )

    class Meta:
        model = RouteStop
        fields = [
            'id', 'route_id', 'stop_name', 'stop_order',
            'pickup_time', 'drop_time', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.route:
            ret['route_name'] = instance.route.route_name
        else:
            ret['route_name'] = ''
        ret['allocated_students_count'] = instance.students.count()
        return ret


class TransportRouteSerializer(serializers.ModelSerializer):
    bus_id = serializers.PrimaryKeyRelatedField(
        source='bus',
        queryset=Bus.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Bus does not exist.'}
    )
    stops = RouteStopSerializer(many=True, read_only=True)

    class Meta:
        model = TransportRoute
        fields = [
            'id', 'route_name', 'start_location', 'end_location',
            'bus_id', 'pickup_time', 'drop_time', 'is_active', 'stops',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.bus:
            ret['bus_number'] = instance.bus.bus_number
            ret['bus_registration'] = instance.bus.registration_number
            ret['bus_capacity'] = instance.bus.capacity
            ret['driver_name'] = instance.bus.driver.driver_name if instance.bus.driver else ''
        else:
            ret['bus_number'] = ''
            ret['bus_registration'] = ''
            ret['bus_capacity'] = 0
            ret['driver_name'] = ''

        ret['allocated_students_count'] = instance.students.count()
        return ret
