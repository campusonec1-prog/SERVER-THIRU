from django.db import models
from common.models import TrackingModel


class Driver(TrackingModel):
    driver_name = models.CharField(max_length=150)
    license_number = models.CharField(max_length=50, unique=True)
    phone_number = models.CharField(max_length=20)
    address = models.TextField(null=True, blank=True)
    date_of_joining = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'transport_driver'
        ordering = ['driver_name']

    def __str__(self):
        return f"{self.driver_name} ({self.license_number})"


class Bus(TrackingModel):
    FUEL_TYPE_CHOICES = [
        ('DIESEL', 'Diesel'),
        ('PETROL', 'Petrol'),
        ('ELECTRIC', 'Electric'),
        ('CNG', 'CNG'),
        ('HYBRID', 'Hybrid'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('UNDER_MAINTENANCE', 'Under Maintenance'),
        ('INACTIVE', 'Inactive'),
    ]

    bus_number = models.CharField(max_length=50, unique=True)
    registration_number = models.CharField(max_length=50, unique=True)
    capacity = models.PositiveIntegerField(default=50)
    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        db_column='driver_id',
        related_name='buses',
        null=True,
        blank=True
    )
    fuel_type = models.CharField(max_length=20, choices=FUEL_TYPE_CHOICES, default='DIESEL')
    fuel_tank_capacity = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    route = models.ForeignKey(
        'TransportRoute',
        on_delete=models.SET_NULL,
        db_column='route_id',
        related_name='buses',
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    class Meta:
        db_table = 'transport_bus'
        ordering = ['bus_number']

    def __str__(self):
        return f"{self.bus_number} - {self.registration_number}"


class TransportRoute(TrackingModel):
    route_name = models.CharField(max_length=150)
    start_location = models.CharField(max_length=150)
    end_location = models.CharField(max_length=150)
    bus = models.ForeignKey(
        Bus,
        on_delete=models.SET_NULL,
        db_column='bus_id',
        related_name='routes',
        null=True,
        blank=True
    )
    pickup_time = models.TimeField()
    drop_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'transport_route'
        ordering = ['route_name']

    def __str__(self):
        return f"{self.route_name} ({self.start_location} -> {self.end_location})"


class RouteStop(TrackingModel):
    route = models.ForeignKey(
        TransportRoute,
        on_delete=models.CASCADE,
        db_column='route_id',
        related_name='stops'
    )
    stop_name = models.CharField(max_length=150)
    stop_order = models.PositiveIntegerField(default=1)
    pickup_time = models.TimeField(null=True, blank=True)
    drop_time = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = 'transport_route_stop'
        ordering = ['route', 'stop_order']

    def __str__(self):
        return f"{self.route.route_name} - Stop {self.stop_order}: {self.stop_name}"


class TransportExpense(TrackingModel):
    EXPENSE_TYPE_CHOICES = [
        ('fuel', 'Fuel'),
        ('service', 'Service'),
        ('maintenance', 'Maintenance'),
        ('repair', 'Repair'),
        ('tyre', 'Tyre'),
        ('battery', 'Battery'),
        ('insurance', 'Insurance'),
        ('tax', 'Tax'),
        ('permit', 'Permit'),
        ('cleaning', 'Cleaning'),
        ('other', 'Other'),
    ]

    PAYMENT_MODE_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('UPI', 'UPI'),
        ('CARD', 'Card'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    ]

    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        db_column='bus_id',
        related_name='expenses'
    )
    incharge_driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        db_column='incharge_driver_id',
        related_name='incharge_expenses',
        null=True,
        blank=True
    )
    expense_type = models.CharField(max_length=50, choices=EXPENSE_TYPE_CHOICES)

    expense_date_time = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    vendor = models.CharField(max_length=200)
    odometer_reading = models.DecimalField(max_digits=10, decimal_places=2)
    invoice_number = models.CharField(max_length=100)
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES)

    class Meta:
        db_table = 'transport_expense'
        ordering = ['-expense_date_time']

    def __str__(self):
        return f"{self.bus.bus_number} - {self.expense_type} ({self.amount})"

