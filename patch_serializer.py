"""Script to append AssetMaintenanceSerializer to asset/serializers.py"""
import re

with open('asset/serializers.py', 'r', encoding='utf-8') as f:
    data = f.read()

# Remove the test stub if present
stub = "\n\nclass AssetMaintenanceSerializer(__import__('rest_framework').serializers.ModelSerializer):\n    pass\r\n"
data = data.replace(stub, '')
data = data.rstrip()

# Check if already added
if 'class AssetMaintenanceSerializer' in data:
    # Remove existing one to replace cleanly
    idx = data.index('\n\nclass AssetMaintenanceSerializer')
    data = data[:idx]

maintenance_serializer = """

class AssetMaintenanceSerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source='asset.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset.asset_name', read_only=True)
    serial_number = serializers.CharField(source='asset.serial_number', read_only=True)
    category_name = serializers.CharField(source='asset.category.name', read_only=True)
    asset_status = serializers.CharField(source='asset.status', read_only=True)
    asset_status_display = serializers.CharField(source='asset.get_status_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    maintenance_type_display = serializers.CharField(source='get_maintenance_type_display', read_only=True)
    previous_status_display = serializers.SerializerMethodField()

    asset = serializers.PrimaryKeyRelatedField(
        queryset=Asset.objects.all(),
        required=True,
        error_messages={
            'required': 'Asset is required.',
            'does_not_exist': 'Asset not found.',
        }
    )
    maintenance_type = serializers.ChoiceField(
        choices=MaintenanceType.choices,
        required=True,
        error_messages={
            'required': 'Maintenance type is required.',
            'invalid_choice': 'Invalid maintenance type.',
        }
    )
    issue_description = serializers.CharField(
        required=True,
        error_messages={
            'required': 'Issue description is required.',
            'blank': 'Issue description cannot be blank.',
        }
    )
    maintenance_date = serializers.DateField(
        required=True,
        error_messages={
            'required': 'Maintenance date is required.',
        }
    )
    vendor_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    technician_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    completion_date = serializers.DateField(required=False, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = AssetMaintenance
        fields = [
            'id',
            'asset',
            'asset_code',
            'asset_name',
            'serial_number',
            'category_name',
            'asset_status',
            'asset_status_display',
            'maintenance_type',
            'maintenance_type_display',
            'issue_description',
            'maintenance_date',
            'vendor_name',
            'technician_name',
            'cost',
            'status',
            'status_display',
            'completion_date',
            'remarks',
            'previous_status',
            'previous_status_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'status', 'previous_status', 'created_at', 'updated_at']

    def get_previous_status_display(self, obj):
        if obj.previous_status == 'available':
            return 'Available'
        elif obj.previous_status == 'assigned':
            return 'Assigned'
        return None

    def validate_issue_description(self, value):
        if value is None:
            raise serializers.ValidationError('Issue description is required.')
        trimmed = str(value).strip()
        if not trimmed:
            raise serializers.ValidationError('Issue description cannot be empty or whitespace only.')
        return trimmed

    def validate_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Cost cannot be negative.')
        return value

    def validate_vendor_name(self, value):
        if value is not None:
            trimmed = str(value).strip()
            return trimmed or None
        return value

    def validate_technician_name(self, value):
        if value is not None:
            trimmed = str(value).strip()
            return trimmed or None
        return value

    def validate_remarks(self, value):
        if value is not None:
            trimmed = str(value).strip()
            return trimmed or None
        return value

    def validate(self, attrs):
        maintenance_date = attrs.get(
            'maintenance_date',
            getattr(self.instance, 'maintenance_date', None)
        )
        completion_date = attrs.get(
            'completion_date',
            getattr(self.instance, 'completion_date', None)
        )
        if maintenance_date and completion_date and completion_date < maintenance_date:
            raise serializers.ValidationError({
                'completion_date': ['Completion date cannot be before maintenance date.']
            })
        return attrs
"""

data = data + maintenance_serializer + '\n'

with open('asset/serializers.py', 'w', encoding='utf-8') as f:
    f.write(data)

print('Done. Total lines:', data.count('\n'))
