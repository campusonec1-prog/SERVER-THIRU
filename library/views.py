from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from student.models import Student
from .permissions import LibraryPermission

from .models import LibraryBook, LibraryMember, LibraryTransaction
from .serializers import (
    LibraryBookSerializer,
    LibraryMemberSerializer,
    LibraryTransactionSerializer,
    StudentLookupSerializer,
)


class LibraryViewSetMixin:
    permission_classes = [LibraryPermission]

    def _tracking_user(self):
        return self.request.user if self.request.user.is_authenticated else None

    def _success(self, message, data=None, code=200):
        payload = {'code': code, 'message': message}
        if data is not None:
            payload['data'] = data
        return Response(payload, status=code)


class LibraryBookViewSet(LibraryViewSetMixin, viewsets.ModelViewSet):
    queryset = LibraryBook.objects.select_related('created_by', 'created_by__role', 'updated_by', 'updated_by__role').all()
    serializer_class = LibraryBookSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(author__icontains=query)
                | Q(author1__icontains=query) | Q(call_no__icontains=query)
                | Q(acc_no__icontains=query) | Q(isbn__icontains=query)
            )
        return queryset.order_by('title', 'author')

    def perform_create(self, serializer):
        serializer.save(created_by=self._tracking_user(), updated_by=self._tracking_user())

    def perform_update(self, serializer):
        serializer.save(updated_by=self._tracking_user())

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return self._success('Library books listed successfully', response.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return self._success('Book added successfully', response.data, status.HTTP_201_CREATED)

    @transaction.atomic
    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        books_data = request.data.get('books', [])
        if not books_data:
            return Response({'code': 400, 'message': 'No book data provided.'}, status=400)

        errors = []
        validated_books = []

        def parse_bool(value, default=True):
            if value is None or str(value).strip().lower() in {'', '-', '—', 'n/a', 'na'}:
                return default
            return str(value).strip().lower() in {'true', 'yes', 'y', '1', 'active'}

        def clean_value(value):
            if value is None:
                return ''
            cleaned = str(value).strip()
            # If Excel exported numeric string with .0 (e.g. "123.0" -> "123")
            if cleaned.endswith('.0') and cleaned[:-2].replace('-', '').replace('/', '').isdigit():
                cleaned = cleaned[:-2]
            return '' if cleaned.lower() in {'-', '—', 'n/a', 'na', 'null', 'none'} else cleaned

        def parse_date(value):
            if not value:
                return None
            if isinstance(value, datetime):
                return value.date()
            for date_format in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
                try:
                    return datetime.strptime(str(value).strip(), date_format).date()
                except ValueError:
                    continue
            return None

        def parse_int(value, min_val=0, max_val=2147483647):
            if value in (None, ''):
                return None
            try:
                s = str(value).strip().replace(',', '')
                if s.endswith('.0'):
                    s = s[:-2]
                val = int(float(s))
                if val < min_val or val > max_val:
                    return None
                return val
            except (TypeError, ValueError, OverflowError):
                return None

        def parse_decimal(value, max_val=999999999.99):
            if value in (None, ''):
                return None
            try:
                cleaned = re.sub(r'[^\d.-]', '', str(value).strip())
                if not cleaned:
                    return None
                val = round(float(cleaned), 2)
                if val < 0 or val > max_val:
                    return None
                return Decimal(str(val))
            except (TypeError, ValueError, InvalidOperation):
                return None

        core_fields = {
            'call_no', 'acc_no', 'title', 'author', 'author1', 'author2', 'author3',
            'language', 'subject', 'sub_header', 'isbn', 'category', 'publisher', 'shelf_location',
            'price', 'date_of_purchase', 'location', 'status', 'max_times_issued',
            'pub_id', 'ven_id', 'department', 'pages', 'year_of_pub', 'curr_name',
            'remarks', 'total_copies', 'is_active',
        }
        detail_fields = {'sub_title', 'sub_header', 'sub_header2', 'series', 'notes', 'keyword', 'type', 'pono', 'price_of_curr', 'conver_rate', 'list_price', 'discount', 'vpp'}

        for index, row in enumerate(books_data, start=1):
            row_number = row.get('s_no', index)
            title = clean_value(row.get('title'))
            author = clean_value(row.get('author') or row.get('author1'))
            isbn = clean_value(row.get('isbn')) or None
            row_errors = []

            if not title:
                row_errors.append('Title is required.')

            raw_copies = clean_value(row.get('total_copies'))
            parsed_copies = parse_int(raw_copies, min_val=1, max_val=10000)
            total_copies = parsed_copies if parsed_copies is not None else 1

            if row_errors:
                errors.append({'row': row_number, 'errors': row_errors})
                continue

            details = {key: row.get(key) for key in detail_fields if row.get(key) not in (None, '')}
            validated_books.append({
                'call_no': clean_value(row.get('call_no')),
                'acc_no': clean_value(row.get('acc_no')),
                'title': title,
                'author': author,
                'author1': clean_value(row.get('author1')),
                'author2': clean_value(row.get('author2')),
                'author3': clean_value(row.get('author3')),
                'language': clean_value(row.get('language')),
                'subject': clean_value(row.get('subject')),
                'sub_header': clean_value(row.get('sub_header')),
                'isbn': isbn,
                'category': clean_value(row.get('category')),
                'publisher': clean_value(row.get('publisher')),
                'shelf_location': clean_value(row.get('shelf_location')),
                'price': parse_decimal(row.get('price')),
                'date_of_purchase': parse_date(row.get('date_of_purchase')),
                'location': clean_value(row.get('location')),
                'status': clean_value(row.get('status')) or 'AVAILABLE',
                'max_times_issued': parse_int(row.get('max_times_issued'), min_val=0, max_val=100) or 2,
                'pub_id': clean_value(row.get('pub_id')),
                'ven_id': clean_value(row.get('ven_id')),
                'department': clean_value(row.get('department')),
                'pages': parse_int(row.get('pages'), min_val=1, max_val=100000),
                'year_of_pub': parse_int(row.get('year_of_pub'), min_val=1000, max_val=2100),
                'curr_name': clean_value(row.get('curr_name')),
                'remarks': clean_value(row.get('remarks') or row.get('notes')),
                'catalog_details': details,
                'total_copies': total_copies,
                'available_copies': total_copies,
                'is_active': parse_bool(row.get('is_active'), True),
            })

        if errors:
            return Response({
                'code': 400,
                'message': 'Some book rows failed validation.',
                'errors': errors,
            }, status=400)

        tracking_user = self._tracking_user()
        created_count = 0
        updated_count = 0
        model_fields = {
            field.name for field in LibraryBook._meta.fields
            if field.name not in {'id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'available_copies'}
        }

        with transaction.atomic():
            for book_data in validated_books:
                # Find existing book to update:
                matching_qs = None
                if book_data['acc_no']:
                    matching_qs = LibraryBook.objects.filter(acc_no__iexact=book_data['acc_no'])
                if (not matching_qs or not matching_qs.exists()) and book_data['isbn']:
                    matching_qs = LibraryBook.objects.filter(isbn__iexact=book_data['isbn'])
                if (not matching_qs or not matching_qs.exists()) and book_data['call_no'] and book_data['title']:
                    matching_qs = LibraryBook.objects.filter(call_no__iexact=book_data['call_no'], title__iexact=book_data['title'])
                if (not matching_qs or not matching_qs.exists()) and book_data['title'] and book_data['author']:
                    matching_qs = LibraryBook.objects.filter(title__iexact=book_data['title'], author__iexact=book_data['author'])
                if (not matching_qs or not matching_qs.exists()) and book_data['title'] and not book_data['author']:
                    matching_qs = LibraryBook.objects.filter(title__iexact=book_data['title'], author='')

                existing = matching_qs.first() if matching_qs and matching_qs.exists() else None
                if existing:
                    # Clean up any leftover duplicate rows in DB if they don't have active transactions
                    if matching_qs.count() > 1:
                        for dup in matching_qs.exclude(id=existing.id):
                            if not dup.transactions.filter(returned_on__isnull=True).exists():
                                dup.delete()

                    issued_copies = max(0, existing.total_copies - existing.available_copies)
                    if book_data['total_copies'] < issued_copies:
                        book_data['total_copies'] = issued_copies
                    book_data['available_copies'] = book_data['total_copies'] - issued_copies

                    for field_name in model_fields:
                        new_val = book_data.get(field_name)
                        if new_val not in (None, ''):
                            setattr(existing, field_name, new_val)

                    if book_data.get('catalog_details'):
                        current_catalog = getattr(existing, 'catalog_details', {}) or {}
                        current_catalog.update(book_data['catalog_details'])
                        existing.catalog_details = current_catalog

                    existing.available_copies = book_data['available_copies']
                    existing.updated_by = tracking_user
                    existing.save()
                    updated_count += 1
                else:
                    LibraryBook.objects.create(**book_data, created_by=tracking_user, updated_by=tracking_user)
                    created_count += 1

        return self._success('Books imported successfully', {
            'count': created_count + updated_count,
            'created': created_count,
            'updated': updated_count,
        }, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return self._success('Book updated successfully', response.data)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().transactions.filter(returned_on__isnull=True).exists():
            return Response({'message': 'Return active loans before deleting this book.'}, status=400)
        super().destroy(request, *args, **kwargs)
        return self._success('Book deleted successfully')


class LibraryMemberViewSet(LibraryViewSetMixin, viewsets.ModelViewSet):
    queryset = LibraryMember.objects.select_related('student__application', 'student__application__candidate', 'created_by', 'created_by__role', 'updated_by', 'updated_by__role')
    serializer_class = LibraryMemberSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        if query:
            queryset = queryset.filter(
                Q(membership_number__icontains=query)
                | Q(student__roll_number__icontains=query)
                | Q(student__register_number__icontains=query)
                | Q(student__application__candidate__name__icontains=query)
            )
        return queryset.order_by('membership_number')

    def perform_create(self, serializer):
        serializer.save(created_by=self._tracking_user(), updated_by=self._tracking_user())

    def perform_update(self, serializer):
        serializer.save(updated_by=self._tracking_user())

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return self._success('Library members listed successfully', response.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return self._success('Library member added successfully', response.data, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return self._success('Library member updated successfully', response.data)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().transactions.filter(returned_on__isnull=True).exists():
            return Response({'message': 'Return active loans before deleting this member.'}, status=400)
        super().destroy(request, *args, **kwargs)
        return self._success('Library member deleted successfully')


class LibraryTransactionViewSet(LibraryViewSetMixin, viewsets.ModelViewSet):
    queryset = LibraryTransaction.objects.select_related('book', 'member__student__application', 'member__student__application__candidate', 'created_by', 'created_by__role', 'updated_by', 'updated_by__role')
    serializer_class = LibraryTransactionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        status_filter = self.request.query_params.get('status')
        if query:
            queryset = queryset.filter(Q(book__title__icontains=query) | Q(member__membership_number__icontains=query) | Q(member__student__roll_number__icontains=query))
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by('-issued_on', '-id')

    @transaction.atomic
    def perform_create(self, serializer):
        book = LibraryBook.objects.select_for_update().get(pk=serializer.validated_data['book'].pk)
        if book.available_copies < 1:
            raise serializers.ValidationError({'book': 'No available copies for this book.'})
        book.available_copies -= 1
        book.save(update_fields=['available_copies', 'updated_at'])
        serializer.save(created_by=self._tracking_user(), updated_by=self._tracking_user())

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        was_returned = bool(instance.returned_on)
        response = super().update(request, *args, **kwargs)
        instance.refresh_from_db()
        if not was_returned and instance.returned_on:
            instance.book.available_copies = min(instance.book.total_copies, instance.book.available_copies + 1)
            instance.book.save(update_fields=['available_copies', 'updated_at'])
            
            instance.history.append({
                'action': 'Returned',
                'date': str(timezone.localdate()),
                'user': getattr(self._tracking_user(), 'name', 'System') if self._tracking_user() else 'System'
            })
            instance.save(update_fields=['history'])
        else:
            instance.history.append({
                'action': 'Edited',
                'date': str(timezone.localdate()),
                'user': getattr(self._tracking_user(), 'name', 'System') if self._tracking_user() else 'System'
            })
            instance.save(update_fields=['history'])
            
        return self._success('Transaction updated successfully', response.data)

    def perform_update(self, serializer):
        serializer.save(updated_by=self._tracking_user())

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return self._success('Library transactions listed successfully', response.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            transaction_id = response.data.get('id')
            if transaction_id:
                loan = LibraryTransaction.objects.get(id=transaction_id)
                loan.history.append({
                    'action': 'Issued',
                    'date': str(timezone.localdate()),
                    'user': getattr(self._tracking_user(), 'name', 'System') if self._tracking_user() else 'System'
                })
                loan.save(update_fields=['history'])
        return self._success('Book issued successfully', response.data, status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def return_book(self, request, pk=None):
        loan = self.get_object()
        if loan.returned_on:
            return Response({'message': 'This book has already been returned.'}, status=400)
        loan.returned_on = timezone.localdate()
        loan.updated_by = self._tracking_user()
        loan.save()
        book = LibraryBook.objects.select_for_update().get(pk=loan.book_id)
        book.available_copies = min(book.total_copies, book.available_copies + 1)
        book.save(update_fields=['available_copies', 'updated_at'])
        
        loan.history.append({
            'action': 'Returned',
            'date': str(timezone.localdate()),
            'user': getattr(self._tracking_user(), 'name', 'System') if self._tracking_user() else 'System'
        })
        loan.save(update_fields=['history'])
        
        return self._success('Book returned successfully', self.get_serializer(loan).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def renew(self, request, pk=None):
        loan = self.get_object()
        if loan.returned_on:
            return Response({'message': 'Returned books cannot be renewed.'}, status=400)
        loan.due_on = loan.due_on + timedelta(days=14)
        loan.renewal_count += 1
        loan.updated_by = self._tracking_user()
        
        loan.history.append({
            'action': 'Renewed',
            'date': str(timezone.localdate()),
            'new_due_on': str(loan.due_on),
            'user': getattr(self._tracking_user(), 'name', 'System') if self._tracking_user() else 'System'
        })
        
        loan.save()
        return self._success('Book renewed successfully', self.get_serializer(loan).data)


class LibraryDashboardViewSet(LibraryViewSetMixin, viewsets.ViewSet):
    @action(detail=False, methods=['get'])
    def summary(self, request):
        today = timezone.localdate()
        active_loans = LibraryTransaction.objects.filter(returned_on__isnull=True)
        overdue = active_loans.filter(due_on__lt=today)
        recent = LibraryTransaction.objects.select_related('book', 'member__student__application', 'member__student__application__candidate').order_by('-id')[:8]
        
        from django.db.models import Sum
        books_qs = LibraryBook.objects.filter(is_active=True)
        totals = books_qs.aggregate(
            total=Sum('total_copies'),
            available=Sum('available_copies')
        )
        
        return self._success('Library dashboard loaded successfully', {
            'books': books_qs.count(),
            'total_copies': totals['total'] or 0,
            'available_copies': totals['available'] or 0,
            'members': LibraryMember.objects.filter(is_active=True).count(),
            'active_loans': active_loans.count(),
            'overdue_loans': overdue.count(),
            'recent_transactions': LibraryTransactionSerializer(recent, many=True).data,
        })


class LibraryStudentLookupViewSet(LibraryViewSetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StudentLookupSerializer
    queryset = Student.objects.select_related('application', 'application__candidate', 'department', 'batch', 'section').order_by('roll_number')

    def get_queryset(self):
        queryset = super().get_queryset()
        register_number = self.request.query_params.get('register_number')
        query = register_number or self.request.query_params.get('search')
        if query:
            queryset = queryset.filter(Q(roll_number__icontains=query) | Q(register_number__icontains=query) | Q(application__candidate__name__icontains=query))
        filter_keys = {
            'program_id': 'department__program_id',
            'department_id': 'department_id',
            'batch_id': 'batch_id',
            'section_id': 'section_id',
        }
        for key, lookup in filter_keys.items():
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{lookup: value})
        return queryset
