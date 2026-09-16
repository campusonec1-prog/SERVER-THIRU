from django.db import models


class AssetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, null=False, blank=False)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'asset_categories'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class AssetCondition(models.TextChoices):
    NEW = 'new', 'New'
    GOOD = 'good', 'Good'
    FAIR = 'fair', 'Fair'
    POOR = 'poor', 'Poor'
    DAMAGED = 'damaged', 'Damaged'


class AssetStatus(models.TextChoices):
    AVAILABLE = 'available', 'Available'
    ASSIGNED = 'assigned', 'Assigned'
    MAINTENANCE = 'maintenance', 'Under Maintenance'
    DAMAGED = 'damaged', 'Damaged'
    LOST = 'lost', 'Lost'
    DISPOSED = 'disposed', 'Disposed'


class Asset(models.Model):
    asset_code = models.CharField(max_length=50, unique=True, null=False, blank=False)
    asset_name = models.CharField(max_length=200, null=False, blank=False)
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name='assets'
    )
    brand = models.CharField(max_length=100, blank=True, null=True)
    model_number = models.CharField(max_length=100, blank=True, null=True)
    serial_number = models.CharField(max_length=150, unique=True, blank=True, null=True)
    purchase_date = models.DateField(blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    vendor_name = models.CharField(max_length=200, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    warranty_expiry = models.DateField(blank=True, null=True)
    condition = models.CharField(
        max_length=20,
        choices=AssetCondition.choices,
        default=AssetCondition.NEW
    )
    status = models.CharField(
        max_length=20,
        choices=AssetStatus.choices,
        default=AssetStatus.AVAILABLE
    )
    location = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assets'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.asset_name} ({self.asset_code})"
