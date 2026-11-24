from datetime import timedelta
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from common.models import TrackingModel
from student.models import Student


class LibraryBook(TrackingModel):
    call_no = models.CharField(max_length=100, blank=True)
    acc_no = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=200, blank=True)
    author1 = models.CharField(max_length=200, blank=True)
    author2 = models.CharField(max_length=200, blank=True)
    author3 = models.CharField(max_length=200, blank=True)
    language = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    sub_header = models.CharField(max_length=255, blank=True)
    isbn = models.CharField(max_length=20, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    shelf_location = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    date_of_purchase = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=50, default='AVAILABLE', blank=True)
    max_times_issued = models.PositiveIntegerField(default=2)
    pub_id = models.CharField(max_length=100, blank=True)
    ven_id = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=200, blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True)
    year_of_pub = models.PositiveIntegerField(null=True, blank=True)
    curr_name = models.CharField(max_length=50, blank=True)
    remarks = models.TextField(blank=True)
    catalog_details = models.JSONField(default=dict, blank=True)
    total_copies = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    available_copies = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'library_books'
        ordering = ['acc_no', 'title', 'author']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['department']),
            models.Index(fields=['acc_no']),
            models.Index(fields=['isbn']),
            models.Index(fields=['call_no']),
            models.Index(fields=['title']),
            models.Index(fields=['author']),
        ]

    def __str__(self):
        return f'{self.title} - {self.author}'


class LibraryMember(TrackingModel):
    MEMBER_TYPE_CHOICES = [
        ('STUDENT', 'Student'),
        ('STAFF', 'Staff / Faculty / Other'),
    ]

    member_type = models.CharField(max_length=20, choices=MEMBER_TYPE_CHOICES, default='STUDENT')
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='library_membership',
        db_column='student_id',
    )
    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='library_membership',
        db_column='user_id',
    )
    membership_number = models.CharField(max_length=50, unique=True, verbose_name='Library Code')
    joined_on = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'library_members'
        ordering = ['membership_number']

    def __str__(self):
        return f'{self.membership_number} - {self.borrower_name}'

    @property
    def borrower_name(self):
        if self.student:
            if self.student.student_name:
                return self.student.student_name
            if hasattr(self.student, 'application') and self.student.application and hasattr(self.student.application, 'candidate'):
                return self.student.application.candidate.name or ''
            return f"Student #{self.student.id}"
        if self.user:
            return self.user.name or self.user.username
        return "Unknown"

    @property
    def borrower_role(self):
        if self.student:
            return 'STUDENT'
        if self.user:
            return getattr(self.user.role, 'role_name', 'STAFF') if getattr(self.user, 'role', None) else 'STAFF'
        return 'STAFF'

    @property
    def borrower_code(self):
        return self.membership_number

    @classmethod
    def generate_code_for_student(cls, student):
        import re
        dept_short = 'STU'
        if student.department and student.department.short_name:
            cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.short_name)).upper()
            if cleaned:
                dept_short = cleaned
        
        existing_codes = cls.objects.filter(membership_number__startswith=dept_short).values_list('membership_number', flat=True)
        max_num = 0
        for code in existing_codes:
            num_part = code[len(dept_short):]
            if num_part.isdigit():
                val = int(num_part)
                if val > max_num:
                    max_num = val
        next_num = max_num + 1
        return f"{dept_short}{next_num:03d}"

    @classmethod
    def generate_code_for_user(cls, user):
        import re
        raw_prefix = re.sub(r'[^A-Za-z0-9]', '', str(user.username or '')).upper()
        prefix = raw_prefix[:4] if len(raw_prefix) >= 4 else raw_prefix.ljust(4, '0')
        if not prefix:
            prefix = 'USER'

        existing_codes = cls.objects.filter(membership_number__startswith=prefix).values_list('membership_number', flat=True)
        max_num = 0
        for code in existing_codes:
            num_part = code[len(prefix):]
            if num_part.isdigit():
                val = int(num_part)
                if val > max_num:
                    max_num = val
        next_num = max_num + 1
        return f"{prefix}{next_num:03d}"


class LibraryTransaction(TrackingModel):
    STATUS_CHOICES = [
        ('ISSUED', 'Issued'),
        ('RETURNED', 'Returned'),
        ('OVERDUE', 'Overdue'),
    ]

    book = models.ForeignKey(LibraryBook, on_delete=models.PROTECT, related_name='transactions')
    member = models.ForeignKey(LibraryMember, on_delete=models.PROTECT, related_name='transactions')
    issued_on = models.DateField(default=timezone.now)
    due_on = models.DateField()
    returned_on = models.DateField(blank=True, null=True)
    renewal_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')
    notes = models.TextField(blank=True)
    history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'library_transactions'
        ordering = ['-issued_on', '-id']
        indexes = [
            models.Index(fields=['status', 'due_on']),
            models.Index(fields=['member', 'status']),
            models.Index(fields=['book', 'returned_on']),
        ]

    def save(self, *args, **kwargs):
        if not self.due_on:
            self.due_on = self.issued_on + timedelta(days=14)
        if self.returned_on:
            self.status = 'RETURNED'
        elif self.due_on < timezone.localdate():
            self.status = 'OVERDUE'
        else:
            self.status = 'ISSUED'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.book.title} / {self.member.membership_number}'


class LibraryFine(TrackingModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Payment'),
        ('PAID', 'Paid in Full'),
        ('PARTIAL', 'Partially Paid'),
    ]

    transaction = models.ForeignKey(
        LibraryTransaction,
        on_delete=models.CASCADE,
        related_name='fines',
        null=True,
        blank=True,
    )
    member = models.ForeignKey(
        LibraryMember,
        on_delete=models.PROTECT,
        related_name='fines',
    )
    book = models.ForeignKey(
        LibraryBook,
        on_delete=models.PROTECT,
        related_name='fines',
    )
    due_on = models.DateField()
    returned_on = models.DateField(null=True, blank=True)
    overdue_days = models.PositiveIntegerField(default=0)
    fine_rate_per_day = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('2.00'))
    fine_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    waived_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    paid_on = models.DateTimeField(null=True, blank=True)
    receipt_no = models.CharField(max_length=50, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'library_fines'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['member', 'status']),
            models.Index(fields=['transaction']),
        ]

    def __str__(self):
        return f'{self.member.membership_number} - Rs. {self.fine_amount} ({self.status})'


class LibraryReservation(TrackingModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending (In Queue)'),
        ('AVAILABLE', 'Ready for Pickup'),
        ('FULFILLED', 'Fulfilled / Borrowed'),
        ('CANCELLED', 'Cancelled by User'),
        ('EXPIRED', 'Pickup Window Expired'),
    ]

    book = models.ForeignKey(
        LibraryBook,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    book_title = models.CharField(max_length=255, blank=True)
    member = models.ForeignKey(
        LibraryMember,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    queue_position = models.PositiveIntegerField(default=1)
    reserved_on = models.DateTimeField(auto_now_add=True)
    notified_on = models.DateTimeField(null=True, blank=True)
    available_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'library_reservations'
        ordering = ['reserved_on', 'id']
        indexes = [
            models.Index(fields=['status', 'book']),
            models.Index(fields=['member', 'status']),
            models.Index(fields=['available_until']),
        ]

    def save(self, *args, **kwargs):
        if not self.book_title and self.book:
            self.book_title = self.book.title or ''
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.book_title} - {self.member.borrower_code} ({self.status})'

