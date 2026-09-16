from rest_framework import serializers
from .models import AssetCategory


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
