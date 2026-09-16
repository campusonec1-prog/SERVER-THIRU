from datetime import timedelta

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
        ordering = ['title', 'author']

    def __str__(self):
        return f'{self.title} - {self.author}'


class LibraryMember(TrackingModel):
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='library_membership',
        db_column='student_id',
    )
    membership_number = models.CharField(max_length=50, unique=True)
    joined_on = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'library_members'
        ordering = ['membership_number']

    def __str__(self):
        return f'{self.membership_number} - {self.student}'


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
