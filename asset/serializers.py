from rest_framework import serializers
from .models import AssetCategory, Asset, AssetCondition, AssetStatus


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
