from rest_framework import serializers
from users.models import User
from institution.models import Department
from .models import (
    AssetCategory, Asset, AssetCondition, AssetStatus, AssetAllocation, AssetTransfer,
    AssetMaintenance, MaintenanceType, MaintenanceStatus, PreviousAssetStatus
)


class AssetCategorySerializer(serializers.ModelSerializer):
    name = serializers.CharField(
        max_length=100,
        required=True,
        error_messages={
            'required': 'Category name is required.',
            'blank': 'Category name cannot be blank.',
        }
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=''
    )
    is_active = serializers.BooleanField(default=True)

    class Meta:
        model = AssetCategory
        fields = ['id', 'name', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        if value is None:
            raise serializers.ValidationError("Category name is required.")
        
        trimmed_name = str(value).strip()
        if not trimmed_name:
            raise serializers.ValidationError("Category name cannot be empty or whitespace only.")

        if len(trimmed_name) > 100:
            raise serializers.ValidationError("Category name must not exceed 100 characters.")

        # Uniqueness check (case-insensitive)
        queryset = AssetCategory.objects.filter(name__iexact=trimmed_name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError("An asset category with this name already exists.")

        return trimmed_name

    def validate_description(self, value):
        if value is not None and isinstance(value, str):
            return value.strip()
        return value


class AssetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    condition_display = serializers.CharField(source='get_condition_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    category = serializers.PrimaryKeyRelatedField(
        queryset=AssetCategory.objects.all(),
        required=True,
        error_messages={
            'required': 'Asset category is required.',
            'does_not_exist': 'Selected asset category does not exist.',
        }
    )

    asset_code = serializers.CharField(
        max_length=50,
        required=True,
        error_messages={
            'required': 'Asset code is required.',
            'blank': 'Asset code cannot be blank.',
        }
    )

    asset_name = serializers.CharField(
        max_length=200,
        required=True,
        error_messages={
            'required': 'Asset name is required.',
            'blank': 'Asset name cannot be blank.',
        }
    )

    class Meta:
        model = Asset
        fields = [
            'id',
            'asset_code',
            'asset_name',
            'category',
            'category_name',
            'brand',
            'model_number',
            'serial_number',
            'purchase_date',
            'purchase_price',
            'vendor_name',
            'invoice_number',
            'warranty_expiry',
            'condition',
            'condition_display',
            'status',
            'status_display',
            'location',
            'description',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_asset_code(self, value):
        if value is None:
            raise serializers.ValidationError("Asset code is required.")
        trimmed = str(value).strip()
        if not trimmed:
            raise serializers.ValidationError("Asset code cannot be empty or whitespace only.")
        if len(trimmed) > 50:
            raise serializers.ValidationError("Asset code must not exceed 50 characters.")

        qs = Asset.objects.filter(asset_code__iexact=trimmed)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An asset with this asset code already exists.")

        return trimmed

    def validate_asset_name(self, value):
        if value is None:
            raise serializers.ValidationError("Asset name is required.")
        trimmed = str(value).strip()
        if not trimmed:
            raise serializers.ValidationError("Asset name cannot be empty or whitespace only.")
        if len(trimmed) > 200:
            raise serializers.ValidationError("Asset name must not exceed 200 characters.")
        return trimmed

    def validate_category(self, value):
        if not value:
            raise serializers.ValidationError("Asset category is required.")
        # When creating new asset, verify category is active
        if not self.instance and not value.is_active:
            raise serializers.ValidationError("Cannot assign an inactive category to a new asset.")
        return value

    def validate_serial_number(self, value):
        if value is None:
            return None
        trimmed = str(value).strip()
        if not trimmed:
            return None
        if len(trimmed) > 150:
            raise serializers.ValidationError("Serial number must not exceed 150 characters.")

        qs = Asset.objects.filter(serial_number__iexact=trimmed)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An asset with this serial number already exists.")

        return trimmed

    def validate_purchase_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Purchase price cannot be negative.")
        return value

    def validate_brand(self, value):
        if value is not None:
            trimmed = str(value).strip()
            if len(trimmed) > 100:
                raise serializers.ValidationError("Brand name must not exceed 100 characters.")
            return trimmed or None
        return value

    def validate_model_number(self, value):
        if value is not None:
            trimmed = str(value).strip()
            if len(trimmed) > 100:
                raise serializers.ValidationError("Model number must not exceed 100 characters.")
            return trimmed or None
        return value

    def validate_vendor_name(self, value):
        if value is not None:
            trimmed = str(value).strip()
            if len(trimmed) > 200:
                raise serializers.ValidationError("Vendor name must not exceed 200 characters.")
            return trimmed or None
        return value

    def validate_invoice_number(self, value):
        if value is not None:
            trimmed = str(value).strip()
            if len(trimmed) > 100:
                raise serializers.ValidationError("Invoice number must not exceed 100 characters.")
            return trimmed or None
        return value

    def validate_location(self, value):
        if value is not None:
            trimmed = str(value).strip()
            if len(trimmed) > 200:
                raise serializers.ValidationError("Location must not exceed 200 characters.")
            return trimmed or None
        return value

    def validate_description(self, value):
        if value is not None:
            trimmed = str(value).strip()
            return trimmed or None
        return value

    def validate(self, attrs):
        purchase_date = attrs.get('purchase_date', getattr(self.instance, 'purchase_date', None))
        warranty_expiry = attrs.get('warranty_expiry', getattr(self.instance, 'warranty_expiry', None))

        if purchase_date and warranty_expiry and warranty_expiry < purchase_date:
            raise serializers.ValidationError({
                'warranty_expiry': ["Warranty expiry date cannot be earlier than purchase date."]
            })

        return attrs


class AssetAllocationSerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source='asset.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset.asset_name', read_only=True)
    serial_number = serializers.CharField(source='asset.serial_number', read_only=True)
    category_name = serializers.CharField(source='asset.category.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.name', read_only=True, default=None)
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True, default=None)
    department_name = serializers.CharField(source='department.department_name', read_only=True, default=None)
    department_code = serializers.CharField(source='department.department_code', read_only=True, default=None)

    asset = serializers.PrimaryKeyRelatedField(
        queryset=Asset.objects.all(),
        required=True,
        error_messages={
            'required': 'Asset is required.',
            'does_not_exist': 'Asset not found.',
        }
    )
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
        error_messages={
            'does_not_exist': 'Assigned user does not exist.',
        }
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
        error_messages={
            'does_not_exist': 'Department does not exist.',
        }
    )
    location = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = AssetAllocation
        fields = [
            'id',
            'asset',
            'asset_code',
            'asset_name',
            'serial_number',
            'category_name',
            'location',
            'assigned_to',
            'assigned_to_name',
            'assigned_to_username',
            'department',
            'department_name',
            'department_code',
            'assigned_date',
            'returned_date',
            'remarks',
            'is_current',
            'created_at',
        ]
        read_only_fields = ['id', 'assigned_date', 'returned_date', 'is_current', 'created_at']

    def validate_location(self, value):
        if value is not None:
            trimmed = str(value).strip()
            if len(trimmed) > 200:
                raise serializers.ValidationError("Location must not exceed 200 characters.")
            return trimmed or None
        return value

    def validate_remarks(self, value):
        if value is not None:
            trimmed = str(value).strip()
            return trimmed or None
        return value

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if not ret.get('location') and getattr(instance, 'asset', None) and getattr(instance.asset, 'location', None):
            ret['location'] = instance.asset.location
        return ret


class AssetTransferSerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source='asset.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset.asset_name', read_only=True)
    serial_number = serializers.CharField(source='asset.serial_number', read_only=True)
    from_user_name = serializers.CharField(source='from_user.name', read_only=True, default=None)
    from_user_username = serializers.CharField(source='from_user.username', read_only=True, default=None)
    to_user_name = serializers.CharField(source='to_user.name', read_only=True, default=None)
    to_user_username = serializers.CharField(source='to_user.username', read_only=True, default=None)
    from_department_name = serializers.CharField(source='from_department.department_name', read_only=True, default=None)
    from_department_code = serializers.CharField(source='from_department.department_code', read_only=True, default=None)
    to_department_name = serializers.CharField(source='to_department.department_name', read_only=True, default=None)
    to_department_code = serializers.CharField(source='to_department.department_code', read_only=True, default=None)

    asset = serializers.PrimaryKeyRelatedField(
        queryset=Asset.objects.all(),
        required=True,
        error_messages={
            'required': 'Asset is required.',
            'does_not_exist': 'Asset not found.',
        }
    )
    from_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    from_department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all(), required=False, allow_null=True)
    to_department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all(), required=False, allow_null=True)
    from_location = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    to_location = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = AssetTransfer
        fields = [
            'id',
            'asset',
            'asset_code',
            'asset_name',
            'serial_number',
            'from_user',
            'from_user_name',
            'from_user_username',
            'to_user',
            'to_user_name',
            'to_user_username',
            'from_department',
            'from_department_name',
            'from_department_code',
            'to_department',
            'to_department_name',
            'to_department_code',
            'from_location',
            'to_location',
            'transfer_date',
            'remarks',
            'created_at',
        ]
        read_only_fields = ['id', 'transfer_date', 'created_at']

    def validate_remarks(self, value):
        if value is not None:
            trimmed = str(value).strip()
            return trimmed or None
        return value


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

