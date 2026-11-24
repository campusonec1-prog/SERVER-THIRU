from django.contrib import admin

from .models import LibraryBook, LibraryMember, LibraryTransaction, LibraryFine


@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'total_copies', 'available_copies', 'is_active')
    search_fields = ('title', 'author', 'isbn')
    list_filter = ('category', 'is_active')


@admin.register(LibraryMember)
class LibraryMemberAdmin(admin.ModelAdmin):
    list_display = ('membership_number', 'student', 'joined_on', 'is_active')
    search_fields = ('membership_number', 'student__roll_number', 'student__register_number')
    list_filter = ('is_active',)


@admin.register(LibraryTransaction)
class LibraryTransactionAdmin(admin.ModelAdmin):
    list_display = ('book', 'member', 'issued_on', 'due_on', 'returned_on', 'status', 'renewal_count')
    search_fields = ('book__title', 'member__membership_number', 'member__student__roll_number')
    list_filter = ('status', 'issued_on', 'due_on')


@admin.register(LibraryFine)
class LibraryFineAdmin(admin.ModelAdmin):
    list_display = ('member', 'book', 'overdue_days', 'fine_rate_per_day', 'fine_amount', 'paid_amount', 'status', 'paid_on')
    search_fields = ('member__membership_number', 'book__title', 'book__acc_no', 'receipt_no')
    list_filter = ('status', 'due_on', 'paid_on')
