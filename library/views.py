from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import re

from django.db import transaction
from django.db.models import Q, Case, When, Value, IntegerField, F
from django.db.models.functions import Length
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from student.models import Student
from common.signals import send_targeted_broadcast
from .permissions import LibraryPermission, LibraryReservationPermission

from .models import LibraryBook, LibraryMember, LibraryTransaction, LibraryFine, LibraryReservation
from .serializers import (
    LibraryBookSerializer,
    LibraryBookQuickSerializer,
    LibraryMemberSerializer,
    LibraryMemberQuickSerializer,
    LibraryTransactionSerializer,
    LibraryFineSerializer,
    LibraryReservationSerializer,
    StudentLookupSerializer,
)
from users.models import User


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
        category = self.request.query_params.get('category')
        status_val = self.request.query_params.get('status')
        department = self.request.query_params.get('department')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(author__icontains=query)
                | Q(author1__icontains=query) | Q(call_no__icontains=query)
                | Q(acc_no__icontains=query) | Q(isbn__icontains=query)
            )
        if category:
            queryset = queryset.filter(category__iexact=category)
        if status_val:
            queryset = queryset.filter(status__iexact=status_val)
        if department:
            queryset = queryset.filter(department__iexact=department)

        ordering = self.request.query_params.get('ordering')
        if ordering:
            order_fields = [f.strip() for f in str(ordering).split(',') if f.strip()]
            if order_fields:
                if 'acc_no' in order_fields:
                    return queryset.annotate(
                        acc_empty=Case(
                            When(Q(acc_no__isnull=True) | Q(acc_no=''), then=Value(1)),
                            default=Value(0),
                            output_field=IntegerField()
                        ),
                        acc_len=Length('acc_no')
                    ).order_by('acc_empty', 'acc_len', 'acc_no', 'title')
                elif '-acc_no' in order_fields:
                    return queryset.annotate(
                        acc_empty=Case(
                            When(Q(acc_no__isnull=True) | Q(acc_no=''), then=Value(1)),
                            default=Value(0),
                            output_field=IntegerField()
                        ),
                        acc_len=Length('acc_no')
                    ).order_by('acc_empty', '-acc_len', '-acc_no', '-id')
                else:
                    return queryset.order_by(*order_fields)

        # Default ordering: Order books by accession number (acc_no) ascending
        return queryset.annotate(
            acc_empty=Case(
                When(Q(acc_no__isnull=True) | Q(acc_no=''), then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            acc_len=Length('acc_no')
        ).order_by('acc_empty', 'acc_len', 'acc_no', 'title')

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

    @action(detail=False, methods=['get'], url_path='barcode-lookup')
    def barcode_lookup(self, request):
        barcode = str(
            request.query_params.get('barcode')
            or request.query_params.get('acc_no')
            or request.query_params.get('q')
            or ''
        ).strip()
        if not barcode:
            return Response({'code': 400, 'message': 'Barcode / Accession number parameter is required.'}, status=400)

        # 1. Exact match on acc_no
        book = LibraryBook.objects.filter(acc_no__iexact=barcode).first()

        # 2. Match on isbn
        if not book:
            book = LibraryBook.objects.filter(isbn__iexact=barcode).first()

        # 3. Match numeric ID
        if not book and barcode.isdigit():
            book = LibraryBook.objects.filter(id=int(barcode)).first()

        # 4. Match call_no
        if not book:
            book = LibraryBook.objects.filter(call_no__iexact=barcode).first()

        if not book:
            return Response({'code': 404, 'message': f'No book found matching barcode "{barcode}".'}, status=404)

        data = LibraryBookSerializer(book, context={'request': request}).data

        # Check for active loan on this book
        active_loan = LibraryTransaction.objects.filter(book=book, returned_on__isnull=True).select_related(
            'book', 'member__student__application', 'member__student__application__candidate', 'member__student__department'
        ).first()

        if active_loan:
            data['active_loan'] = LibraryTransactionSerializer(active_loan, context={'request': request}).data
            data['has_active_loan'] = True
        else:
            data['active_loan'] = None
            data['has_active_loan'] = False

        return self._success('Book found successfully', data)

    @action(detail=False, methods=['get'], url_path='quick-search')
    def quick_search(self, request):
        query = (request.query_params.get('search') or request.query_params.get('query') or request.query_params.get('q') or '').strip()
        limit = min(int(request.query_params.get('limit', 25)), 100)
        only_available = request.query_params.get('only_available') in ('true', '1')

        qs = LibraryBook.objects.filter(is_active=True)
        if only_available:
            qs = qs.filter(available_copies__gt=0)

        if query:
            qs = qs.filter(
                Q(acc_no__icontains=query)
                | Q(title__icontains=query)
                | Q(author__icontains=query)
                | Q(isbn__icontains=query)
                | Q(call_no__icontains=query)
            )

        results = qs.only(
            'id', 'title', 'author', 'acc_no', 'call_no', 'isbn',
            'status', 'total_copies', 'available_copies', 'shelf_location', 'department', 'is_active'
        ).annotate(
            acc_empty=Case(
                When(Q(acc_no__isnull=True) | Q(acc_no=''), then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            acc_len=Length('acc_no')
        ).order_by('acc_empty', 'acc_len', 'acc_no', 'title')[:limit]

        data = LibraryBookQuickSerializer(results, many=True).data
        return self._success('Books searched successfully', data)

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        books_data = (
            request.data.get('books') or
            request.data.get('data') or
            request.data.get('rows') or
            []
        )
        if isinstance(request.data, list):
            books_data = request.data

        if not books_data:
            return Response({'code': 400, 'message': 'No book data provided.'}, status=400)

        task_id = request.data.get('task_id') if isinstance(request.data, dict) else None
        total_rows = len(books_data)

        if task_id:
            send_targeted_broadcast(f'task_{task_id}', {
                'type': 'import_progress',
                'task_id': task_id,
                'progress': 10,
                'processed': 0,
                'total': total_rows,
                'status': 'Validating book records...'
            })

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
            if cleaned.endswith('.0') and cleaned[:-2].replace('-', '').replace('/', '').isdigit():
                cleaned = cleaned[:-2]
            return '' if cleaned.lower() in {'-', '—', 'n/a', 'na', 'null', 'none'} else cleaned

        def parse_date(value):
            if not value:
                return None
            if isinstance(value, datetime):
                return value.date()
            if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
                return value
            val_str = str(value).strip()
            # Numeric Excel serial date number
            try:
                num_val = float(val_str)
                if 1000 <= num_val <= 100000:
                    excel_base = datetime(1899, 12, 30).date()
                    import timedelta as td
                    from datetime import timedelta
                    return excel_base + timedelta(days=int(num_val))
            except (ValueError, TypeError):
                pass

            for date_format in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d.%m.%Y'):
                try:
                    return datetime.strptime(val_str.split('T')[0].split(' ')[0], date_format).date()
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

        detail_fields = {'sub_title', 'sub_header', 'sub_header2', 'series', 'notes', 'keyword', 'type', 'pono', 'price_of_curr', 'conver_rate', 'list_price', 'discount', 'vpp'}

        for index, row in enumerate(books_data, start=1):
            row_number = row.get('s_no', index)
            title = clean_value(row.get('title') or row.get('book_title') or row.get('name'))
            author = clean_value(row.get('author') or row.get('author1') or row.get('author_name'))
            isbn = clean_value(row.get('isbn')) or None
            acc_no = clean_value(row.get('acc_no') or row.get('accession_no') or row.get('accession_number'))
            call_no = clean_value(row.get('call_no') or row.get('call_number'))
            category = clean_value(row.get('category') or row.get('category_name') or row.get('book_category'))
            department = clean_value(row.get('department') or row.get('dept') or row.get('department_name'))

            # Check if row has any actual content (skip completely blank rows)
            has_content = any([
                title, author, isbn, acc_no, call_no, category, department,
                row.get('subject'), row.get('publisher'), row.get('shelf_location'),
                row.get('price'), row.get('date_of_purchase')
            ])
            if not has_content:
                continue

            row_errors = []
            if not title:
                row_errors.append('Title is required.')

            raw_copies = clean_value(row.get('total_copies') or row.get('copies') or row.get('quantity'))
            parsed_copies = parse_int(raw_copies, min_val=1, max_val=100000)
            total_copies = parsed_copies if parsed_copies is not None else 1

            if row_errors:
                errors.append({'row': row_number, 'errors': row_errors})
                continue

            details = {key: row.get(key) for key in detail_fields if row.get(key) not in (None, '')}
            validated_books.append({
                'call_no': call_no,
                'acc_no': acc_no,
                'title': title,
                'author': author,
                'author1': clean_value(row.get('author1')),
                'author2': clean_value(row.get('author2')),
                'author3': clean_value(row.get('author3')),
                'language': clean_value(row.get('language') or row.get('lang')),
                'subject': clean_value(row.get('subject')),
                'sub_header': clean_value(row.get('sub_header')),
                'isbn': isbn,
                'category': category,
                'publisher': clean_value(row.get('publisher')),
                'shelf_location': clean_value(row.get('shelf_location') or row.get('shelf') or row.get('rack')),
                'price': parse_decimal(row.get('price') or row.get('cost') or row.get('amount')),
                'date_of_purchase': parse_date(row.get('date_of_purchase') or row.get('purchase_date')),
                'location': clean_value(row.get('location')),
                'status': clean_value(row.get('status')).upper() or 'AVAILABLE',
                'max_times_issued': parse_int(row.get('max_times_issued'), min_val=0, max_val=100) or 2,
                'pub_id': clean_value(row.get('pub_id')),
                'ven_id': clean_value(row.get('ven_id')),
                'department': department,
                'pages': parse_int(row.get('pages'), min_val=1, max_val=100000),
                'year_of_pub': parse_int(row.get('year_of_pub') or row.get('publication_year') or row.get('year'), min_val=1000, max_val=2100),
                'curr_name': clean_value(row.get('curr_name')) or 'INR',
                'remarks': clean_value(row.get('remarks') or row.get('notes') or row.get('description')),
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

        if not validated_books:
            return Response({
                'code': 400,
                'message': 'No valid book records found to import.',
            }, status=400)

        tracking_user = self._tracking_user()

        # High-speed pre-caching for 25,000+ records
        all_existing = list(LibraryBook.objects.all())
        existing_by_acc_no = {}

        for b in all_existing:
            if b.acc_no:
                existing_by_acc_no[b.acc_no.strip().upper()] = b

        books_to_create = []
        books_to_update = []
        seen_keys_in_batch = set()

        updatable_fields = [
            'call_no', 'acc_no', 'title', 'author', 'author1', 'author2', 'author3',
            'language', 'subject', 'sub_header', 'isbn', 'category', 'publisher',
            'shelf_location', 'price', 'date_of_purchase', 'location', 'status',
            'max_times_issued', 'pub_id', 'ven_id', 'department', 'pages', 'year_of_pub',
            'curr_name', 'remarks', 'catalog_details', 'total_copies', 'available_copies',
            'is_active', 'updated_by'
        ]

        for bdata in validated_books:
            acc_key = bdata['acc_no'].strip().upper() if bdata['acc_no'] else None

            # In library systems, each row represents a distinct physical book / accession record.
            # Match ONLY if an explicit Accession Number is provided and matches an existing record.
            existing = None
            if acc_key and acc_key in existing_by_acc_no:
                existing = existing_by_acc_no[acc_key]

            if existing:
                issued_copies = max(0, existing.total_copies - existing.available_copies)
                if bdata['total_copies'] < issued_copies:
                    bdata['total_copies'] = issued_copies
                bdata['available_copies'] = bdata['total_copies'] - issued_copies

                for f in updatable_fields:
                    if f in bdata and bdata[f] not in (None, ''):
                        setattr(existing, f, bdata[f])

                if bdata.get('catalog_details'):
                    curr_cat = getattr(existing, 'catalog_details', {}) or {}
                    curr_cat.update(bdata['catalog_details'])
                    existing.catalog_details = curr_cat

                existing.updated_by = tracking_user
                if getattr(existing, 'id', None):
                    if existing.id not in seen_keys_in_batch:
                        seen_keys_in_batch.add(existing.id)
                        books_to_update.append(existing)
            else:
                new_book = LibraryBook(
                    **bdata,
                    created_by=tracking_user,
                    updated_by=tracking_user
                )
                books_to_create.append(new_book)
                # Register accession number in memory so subsequent rows in the same sheet with the exact same acc_no update
                if acc_key:
                    existing_by_acc_no[acc_key] = new_book

        # Execute high-speed chunked database transactions
        if task_id:
            send_targeted_broadcast(f'task_{task_id}', {
                'type': 'import_progress',
                'task_id': task_id,
                'progress': 75,
                'processed': len(validated_books),
                'total': total_rows,
                'status': 'Saving book records to database...'
            })

        with transaction.atomic():
            if books_to_update:
                LibraryBook.objects.bulk_update(books_to_update, fields=updatable_fields, batch_size=2000)
            if books_to_create:
                LibraryBook.objects.bulk_create(books_to_create, batch_size=2000)

        if task_id:
            send_targeted_broadcast(f'task_{task_id}', {
                'type': 'import_progress',
                'task_id': task_id,
                'progress': 100,
                'processed': total_rows,
                'total': total_rows,
                'created': len(books_to_create),
                'updated': len(books_to_update),
                'status': 'Completed successfully!'
            })

        return self._success('Books imported successfully', {
            'count': len(books_to_create) + len(books_to_update),
            'created': len(books_to_create),
            'updated': len(books_to_update),
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
    queryset = LibraryMember.objects.select_related(
        'student__application', 'student__application__candidate', 'student__department',
        'student__batch', 'student__section', 'user', 'user__role',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    )
    serializer_class = LibraryMemberSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        is_active = self.request.query_params.get('is_active')
        member_type = self.request.query_params.get('member_type')
        department = self.request.query_params.get('department')

        if query:
            queryset = queryset.filter(
                Q(membership_number__icontains=query)
                | Q(student__roll_number__icontains=query)
                | Q(student__register_number__icontains=query)
                | Q(student__student_name__icontains=query)
                | Q(student__application__candidate__name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(user__name__icontains=query)
            )
        if is_active is not None and is_active != '' and is_active != 'ALL':
            val = is_active.lower() in ('true', '1', 'yes', 'active')
            queryset = queryset.filter(is_active=val)
        if member_type and member_type != 'ALL':
            queryset = queryset.filter(member_type__iexact=member_type)
        if department and department != 'ALL':
            if str(department).isdigit():
                queryset = queryset.filter(student__department_id=department)
            else:
                queryset = queryset.filter(student__department__department_name__iexact=department)
        return queryset.order_by('membership_number')

    def perform_create(self, serializer):
        serializer.save(created_by=self._tracking_user(), updated_by=self._tracking_user())

    def perform_update(self, serializer):
        serializer.save(updated_by=self._tracking_user())

    def _sync_library_members_and_statuses(self):
        """
        1. Auto-provisions missing LibraryMember records for all Students.
        2. Auto-provisions missing LibraryMember records for all staff Users.
        3. Synchronizes active/inactive status across all members based on actual Student & User states.
        4. Updates legacy student membership codes to batch prefix (e.g. IT001 -> 23IT001).
        """
        import re
        try:
            # 1. Provision missing student members
            missing_students = Student.objects.filter(library_membership__isnull=True).select_related('department', 'batch', 'status')[:250]
            for stu in missing_students:
                code = LibraryMember.generate_code_for_student(stu)
                user_obj = None
                if stu.roll_number:
                    user_obj = User.objects.filter(username__iexact=stu.roll_number).first()
                if not user_obj and stu.register_number:
                    user_obj = User.objects.filter(username__iexact=stu.register_number).first()

                stu_active = True
                if stu.status:
                    if not getattr(stu.status, 'is_active', True):
                        stu_active = False
                    elif getattr(stu.status, 'status_name', '').upper() in ['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']:
                        stu_active = False
                if user_obj and not getattr(user_obj, 'is_active', True):
                    stu_active = False

                LibraryMember.objects.create(
                    student=stu,
                    user=user_obj,
                    member_type='STUDENT',
                    membership_number=code,
                    is_active=stu_active,
                )

            # 2. Provision missing staff members
            student_usernames = set(Student.objects.filter(roll_number__isnull=False).values_list('roll_number', flat=True))
            missing_users = User.objects.exclude(
                role__role_name__iexact='STUDENT'
            ).filter(
                library_membership__isnull=True
            )[:150]

            for u in missing_users:
                if u.username in student_usernames:
                    continue
                code = LibraryMember.generate_code_for_user(u)
                LibraryMember.objects.create(
                    user=u,
                    member_type='STAFF',
                    membership_number=code,
                    is_active=bool(getattr(u, 'is_active', True)),
                )

            # 3. Synchronize is_active status for existing members
            # Inactive students -> member.is_active = False
            inactive_student_members = LibraryMember.objects.filter(
                student__isnull=False,
                is_active=True
            ).filter(
                Q(student__status__is_active=False) |
                Q(student__status__status_name__in=['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']) |
                Q(user__is_active=False)
            )[:100]
            for m in inactive_student_members:
                m.is_active = False
                m.save(update_fields=['is_active', 'updated_at'])

            # Active students -> member.is_active = True
            active_student_members = LibraryMember.objects.filter(
                student__isnull=False,
                is_active=False
            ).exclude(
                Q(student__status__is_active=False) |
                Q(student__status__status_name__in=['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']) |
                Q(user__is_active=False)
            )[:100]
            for m in active_student_members:
                m.is_active = True
                m.save(update_fields=['is_active', 'updated_at'])

            # Inactive staff -> member.is_active = False
            inactive_staff_members = LibraryMember.objects.filter(
                user__isnull=False,
                student__isnull=True,
                is_active=True,
                user__is_active=False
            )[:50]
            for m in inactive_staff_members:
                m.is_active = False
                m.save(update_fields=['is_active', 'updated_at'])

            # Active staff -> member.is_active = True
            active_staff_members = LibraryMember.objects.filter(
                user__isnull=False,
                student__isnull=True,
                is_active=False,
                user__is_active=True
            )[:50]
            for m in active_staff_members:
                m.is_active = True
                m.save(update_fields=['is_active', 'updated_at'])

            # 4. Batch prefix updates for student codes
            self._ensure_student_batch_codes()
        except Exception:
            pass

    def _ensure_student_batch_codes(self):
        """Auto-detects and updates legacy student codes directly in DB to include batch prefix (e.g. IT001 -> 23IT001)."""
        import re
        try:
            legacy_members = LibraryMember.objects.filter(
                student__isnull=False,
                student__batch__isnull=False
            ).exclude(
                membership_number__regex=r'^\d{2}[A-Za-z]'
            ).select_related('student__batch', 'student__department')[:100]

            for member in legacy_members:
                student = member.student
                if not student:
                    continue
                dept_short = 'STU'
                if student.department and student.department.short_name:
                    cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.short_name)).upper()
                    if cleaned:
                        dept_short = cleaned

                batch_prefix = ''
                if getattr(student, 'batch', None) and getattr(student.batch, 'batch', None):
                    batch_str = str(student.batch.batch).strip()
                    match = re.search(r'(\d{4})', batch_str)
                    if match:
                        batch_prefix = match.group(1)[-2:]
                    else:
                        m2 = re.search(r'(\d{2})', batch_str)
                        if m2:
                            batch_prefix = m2.group(1)

                if not batch_prefix:
                    continue

                expected_prefix = f"{batch_prefix}{dept_short}"
                current_code = str(member.membership_number or '').strip().upper()
                if not current_code.startswith(expected_prefix):
                    num_match = re.search(r'(\d+)$', current_code)
                    num_val = int(num_match.group(1)) if num_match else 1
                    new_code = f"{expected_prefix}{num_val:03d}"
                    if LibraryMember.objects.filter(membership_number=new_code).exclude(id=member.id).exists():
                        new_code = LibraryMember.generate_code_for_student(student)
                    member.membership_number = new_code
                    member.save(update_fields=['membership_number', 'updated_at'])
        except Exception:
            pass

    def list(self, request, *args, **kwargs):
        self._sync_library_members_and_statuses()
        response = super().list(request, *args, **kwargs)
        return self._success('Library members listed successfully', response.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return self._success('Library member added successfully', response.data, status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='barcode-lookup')
    def barcode_lookup(self, request):
        barcode = str(request.query_params.get('barcode') or request.query_params.get('q') or '').strip()
        if not barcode:
            return Response({'code': 400, 'message': 'Barcode / Membership ID is required.'}, status=400)

        lookup_q = (
            Q(membership_number__iexact=barcode)
            | Q(student__roll_number__iexact=barcode)
            | Q(student__register_number__iexact=barcode)
            | Q(user__username__iexact=barcode)
        )
        if len(barcode) >= 4:
            lookup_q |= Q(membership_number__iendswith=barcode)

        member = LibraryMember.objects.select_related(
            'student__application', 'student__application__candidate', 'student__department',
            'student__batch', 'student__section', 'user', 'user__role'
        ).filter(lookup_q).first()

        if not member:
            return Response({'code': 404, 'message': f'No borrower member found matching "{barcode}".'}, status=404)

        data = LibraryMemberSerializer(member, context={'request': request}).data
        data['active_loans_count'] = LibraryTransaction.objects.filter(member=member, returned_on__isnull=True).count()
        return self._success('Member found successfully', data)

    @action(detail=False, methods=['post'], url_path='sync-batch-codes')
    def sync_batch_codes(self, request):
        """
        Migrates existing student library membership numbers to include their 2-digit batch prefix
        (e.g., IT001 -> 23IT001 for batch 2023-2027, 25IT001 for batch 2025-2029).
        """
        import re
        student_members = LibraryMember.objects.filter(student__isnull=False).select_related('student__batch', 'student__department')
        updated_count = 0
        for member in student_members:
            student = member.student
            if not student:
                continue
            dept_short = 'STU'
            if student.department and student.department.short_name:
                cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.short_name)).upper()
                if cleaned:
                    dept_short = cleaned

            batch_prefix = ''
            if getattr(student, 'batch', None) and getattr(student.batch, 'batch', None):
                batch_str = str(student.batch.batch).strip()
                match = re.search(r'(\d{4})', batch_str)
                if match:
                    batch_prefix = match.group(1)[-2:]
                else:
                    m2 = re.search(r'(\d{2})', batch_str)
                    if m2:
                        batch_prefix = m2.group(1)

            if not batch_prefix:
                continue

            expected_prefix = f"{batch_prefix}{dept_short}"
            current_code = str(member.membership_number or '').strip().upper()

            if not current_code.startswith(expected_prefix):
                num_match = re.search(r'(\d+)$', current_code)
                num_val = int(num_match.group(1)) if num_match else 1
                new_code = f"{expected_prefix}{num_val:03d}"

                if LibraryMember.objects.filter(membership_number=new_code).exclude(id=member.id).exists():
                    new_code = LibraryMember.generate_code_for_student(student)

                member.membership_number = new_code
                member.save(update_fields=['membership_number', 'updated_at'])
                updated_count += 1

        return self._success(f'Updated {updated_count} student library member ID(s) with batch prefix.', {'updated': updated_count})

    @action(detail=False, methods=['get'], url_path='quick-search')
    def quick_search(self, request):
        query = (request.query_params.get('search') or request.query_params.get('query') or request.query_params.get('q') or '').strip()
        limit = min(int(request.query_params.get('limit', 25)), 100)

        qs = LibraryMember.objects.select_related(
            'student__application', 'student__application__candidate', 'student__department',
            'user', 'user__role'
        ).filter(is_active=True)

        if query:
            qs = qs.filter(
                Q(membership_number__icontains=query)
                | Q(student__roll_number__icontains=query)
                | Q(student__register_number__icontains=query)
                | Q(student__student_name__icontains=query)
                | Q(student__application__candidate__name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(user__name__icontains=query)
            )

        results = qs.order_by('membership_number')[:limit]
        data = LibraryMemberQuickSerializer(results, many=True).data
        return self._success('Members searched successfully', data)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return self._success('Library member updated successfully', response.data)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().transactions.filter(returned_on__isnull=True).exists():
            return Response({'message': 'Return active loans before deleting this member.'}, status=400)
        super().destroy(request, *args, **kwargs)
        return self._success('Library member deleted successfully')


class LibraryTransactionViewSet(LibraryViewSetMixin, viewsets.ModelViewSet):
    queryset = LibraryTransaction.objects.select_related(
        'book', 'member__student__application', 'member__student__application__candidate',
        'member__student__department', 'member__user', 'member__user__role',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    )
    serializer_class = LibraryTransactionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        status_filter = self.request.query_params.get('status')
        department = self.request.query_params.get('department')
        if query:
            queryset = queryset.filter(
                Q(book__title__icontains=query)
                | Q(book__acc_no__icontains=query)
                | Q(member__membership_number__icontains=query)
                | Q(member__student__roll_number__icontains=query)
                | Q(member__student__register_number__icontains=query)
                | Q(member__student__student_name__icontains=query)
                | Q(member__student__application__candidate__name__icontains=query)
                | Q(member__user__username__icontains=query)
                | Q(member__user__name__icontains=query)
            )
        if status_filter and status_filter != 'ALL':
            today = timezone.localdate()
            status_clean = str(status_filter).strip().upper()
            if status_clean in ('ACTIVE', 'ISSUED'):
                queryset = queryset.filter(returned_on__isnull=True)
            elif status_clean == 'OVERDUE':
                queryset = queryset.filter(returned_on__isnull=True, due_on__lt=today)
            elif status_clean == 'RETURNED':
                queryset = queryset.filter(returned_on__isnull=False)
            else:
                queryset = queryset.filter(status=status_filter)
        if department and department != 'ALL':
            if str(department).isdigit():
                queryset = queryset.filter(
                    Q(member__student__department_id=department) | Q(book__department__iexact=department)
                )
            else:
                queryset = queryset.filter(
                    Q(member__student__department__department_name__iexact=department) | Q(book__department__iexact=department)
                )
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

                # Fulfill any active reservation for this member & book
                LibraryReservation.objects.filter(
                    member=loan.member,
                    book=loan.book,
                    status__in=['AVAILABLE', 'PENDING']
                ).update(
                    status='FULFILLED',
                    updated_by=self._tracking_user(),
                    updated_at=timezone.now()
                )
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

        # Persist overdue fine record if returned past due date
        if loan.due_on and loan.returned_on > loan.due_on:
            days = (loan.returned_on - loan.due_on).days
            if days > 0:
                rate_param = request.data.get('fine_per_day') or request.query_params.get('fine_per_day')
                try:
                    fine_rate = Decimal(str(rate_param)) if rate_param is not None and str(rate_param).strip() != '' else Decimal('1.00')
                except Exception:
                    fine_rate = Decimal('1.00')
                fine_amt = Decimal(str(days)) * fine_rate
                fine_rec, created = LibraryFine.objects.get_or_create(
                    transaction=loan,
                    defaults={
                        'member': loan.member,
                        'book': loan.book,
                        'due_on': loan.due_on,
                        'returned_on': loan.returned_on,
                        'overdue_days': days,
                        'fine_rate_per_day': fine_rate,
                        'fine_amount': fine_amt,
                        'status': 'PENDING',
                        'created_by': self._tracking_user(),
                        'updated_by': self._tracking_user(),
                    }
                )
                if not created and fine_rec.status == 'PENDING':
                    fine_rec.returned_on = loan.returned_on
                    fine_rec.overdue_days = days
                    fine_rec.fine_rate_per_day = fine_rate
                    fine_rec.fine_amount = fine_amt
                    fine_rec.updated_by = self._tracking_user()
                    fine_rec.save()

        # Check reservation queue for this returned book
        reservation_alert = None
        pending_res = LibraryReservation.objects.filter(
            Q(book=loan.book) | Q(book_title__iexact=loan.book.title),
            status='PENDING'
        ).order_by('reserved_on', 'id').first()

        if pending_res:
            hold_days = 2
            hold_until = timezone.localdate() + timedelta(days=hold_days)
            pending_res.status = 'AVAILABLE'
            pending_res.book = loan.book
            pending_res.available_until = hold_until
            pending_res.notified_on = timezone.now()
            pending_res.updated_by = self._tracking_user()
            pending_res.save()

            # Create in-app notification to the reserving borrower
            try:
                target_user = None
                if pending_res.member.user:
                    target_user = pending_res.member.user
                elif pending_res.member.student:
                    stu = pending_res.member.student
                    target_user = User.objects.filter(
                        Q(username=stu.roll_number) | Q(username=stu.register_number)
                    ).first()
                if target_user:
                    from leave.models import Notification
                    Notification.objects.create(
                        user=target_user,
                        title='Reserved Library Book Ready for Pickup!',
                        message=f'Good news! Your reserved book "{loan.book.title}" is now returned and ready at the Central Library desk. Please pick it up by {hold_until}.',
                        notification_type='GENERAL',
                    )
            except Exception:
                pass

            reservation_alert = {
                'reserved': True,
                'reservation_id': pending_res.id,
                'borrower_name': pending_res.member.borrower_name,
                'borrower_code': pending_res.member.borrower_code,
                'available_until': str(hold_until),
                'message': f'HOLD ALERT: Book is reserved for {pending_res.member.borrower_name} ({pending_res.member.borrower_code}). Hold until {hold_until}.'
            }

        data = self.get_serializer(loan).data
        if reservation_alert:
            data['reservation_alert'] = reservation_alert
            return self._success(
                f"Book returned. NOTE: Reserved for {reservation_alert['borrower_name']} ({reservation_alert['borrower_code']}) until {reservation_alert['available_until']}.",
                data
            )

        return self._success('Book returned successfully', data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def renew(self, request, pk=None):
        loan = self.get_object()
        if loan.returned_on:
            return Response({'message': 'Returned books cannot be renewed.'}, status=400)
        loan.due_on = loan.due_on + timedelta(days=15)
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

    @action(detail=False, methods=['get'], url_path='lookup-by-barcode')
    def lookup_by_barcode(self, request):
        barcode = str(request.query_params.get('barcode') or request.query_params.get('q') or '').strip()
        if not barcode:
            return Response({'code': 400, 'message': 'Barcode is required.'}, status=400)

        # 1. Search for book by acc_no, isbn, id, or call_no
        book = LibraryBook.objects.filter(
            Q(acc_no__iexact=barcode)
            | Q(isbn__iexact=barcode)
            | (Q(id=int(barcode)) if barcode.isdigit() else Q(pk__isnull=True))
            | Q(call_no__iexact=barcode)
        ).first()

        if book:
            active_loan = LibraryTransaction.objects.filter(book=book, returned_on__isnull=True).select_related(
                'book', 'member__student__application', 'member__student__application__candidate', 'member__student__department'
            ).first()

            return self._success('Barcode lookup result', {
                'match_type': 'book',
                'book': LibraryBookQuickSerializer(book).data,
                'active_loan': LibraryTransactionSerializer(active_loan, context={'request': request}).data if active_loan else None,
                'has_active_loan': bool(active_loan),
                'available_copies': book.available_copies,
            })

        # 2. If not a book, check if it is a member barcode (membership_number, student roll, student register, user username)
        member = LibraryMember.objects.select_related(
            'student__application', 'student__application__candidate', 'student__department',
            'user', 'user__role'
        ).filter(
            Q(membership_number__iexact=barcode)
            | Q(student__roll_number__iexact=barcode)
            | Q(student__register_number__iexact=barcode)
            | Q(user__username__iexact=barcode)
        ).first()

        if member:
            active_loans = LibraryTransaction.objects.filter(member=member, returned_on__isnull=True).select_related('book')
            return self._success('Member lookup result', {
                'match_type': 'member',
                'member': LibraryMemberSerializer(member, context={'request': request}).data,
                'active_loans': LibraryTransactionSerializer(active_loans, many=True, context={'request': request}).data,
            })

        return Response({'code': 404, 'message': f'No book or member found matching barcode "{barcode}".'}, status=404)

    @action(detail=False, methods=['post'], url_path='scan-action')
    @transaction.atomic
    def scan_action(self, request):
        raw_barcode = request.data.get('barcode')
        if raw_barcode is None or raw_barcode == '':
            raw_barcode = request.data.get('acc_no') or request.data.get('book_id') or ''
        barcode = str(raw_barcode).strip()

        raw_action = request.data.get('action') or ''
        action_type = str(raw_action).strip().upper()

        loan_id = request.data.get('loan_id') or request.data.get('transaction_id')

        loan = None
        book = None
        if loan_id:
            try:
                loan = LibraryTransaction.objects.select_for_update().filter(pk=int(loan_id), returned_on__isnull=True).first()
            except (ValueError, TypeError):
                loan = None

        if loan:
            book = loan.book
        else:
            if not barcode:
                return Response({'code': 400, 'message': 'Barcode is required.'}, status=400)
            if action_type not in ('RETURN', 'RENEW'):
                return Response({'code': 400, 'message': 'Action must be RETURN or RENEW.'}, status=400)

            book = LibraryBook.objects.select_for_update().filter(
                Q(acc_no__iexact=barcode)
                | Q(isbn__iexact=barcode)
                | (Q(id=int(barcode)) if barcode.isdigit() else Q(pk__isnull=True))
                | Q(call_no__iexact=barcode)
            ).first()

            if not book:
                return Response({'code': 404, 'message': f'Book with barcode "{barcode}" was not found.'}, status=404)

            loan = LibraryTransaction.objects.select_for_update().filter(book=book, returned_on__isnull=True).first()

        if not loan:
            book_label = getattr(book, 'title', '') if book else barcode
            acc_label = f" (ACC: {book.acc_no or book.id})" if book and getattr(book, 'acc_no', None) else ""
            return Response({
                'code': 400,
                'message': f'Book "{book_label}"{acc_label} has no active circulation loan to {action_type.lower()}. It is currently available in stacks.'
            }, status=400)

        tracking_user = self._tracking_user()
        user_name = getattr(tracking_user, 'name', 'System') if tracking_user else 'System'

        if action_type == 'RETURN':
            loan.returned_on = timezone.localdate()
            loan.status = 'RETURNED'
            loan.updated_by = tracking_user
            loan.history.append({
                'action': 'Returned via Barcode Scan',
                'date': str(timezone.localdate()),
                'user': user_name,
            })
            loan.save()

            book.available_copies = min(book.total_copies, book.available_copies + 1)
            book.save(update_fields=['available_copies', 'updated_at'])

            # Promote next reservation in queue if any
            pending_res = LibraryReservation.objects.filter(
                book=book,
                status='PENDING'
            ).order_by('reserved_on', 'id').first()

            reservation_msg = ''
            if pending_res:
                hold_until = timezone.localdate() + timedelta(days=2)
                pending_res.status = 'AVAILABLE'
                pending_res.available_until = hold_until
                pending_res.notified_on = timezone.now()
                pending_res.updated_by = tracking_user
                pending_res.save()
                reservation_msg = f" Note: Reserved for {pending_res.member.borrower_name} ({pending_res.member.borrower_code}) - hold until {hold_until}."

            send_targeted_broadcast('realtime_updates', {
                'model': 'LibraryTransaction',
                'action': 'returned',
                'id': loan.id
            })
            send_targeted_broadcast('realtime_updates', {
                'model': 'LibraryBook',
                'action': 'updated',
                'id': book.id
            })

            return self._success(
                f'Book "{book.title}" returned successfully via Barcode scan.{reservation_msg}',
                LibraryTransactionSerializer(loan, context={'request': request}).data
            )

        elif action_type == 'RENEW':
            loan.due_on = loan.due_on + timedelta(days=15)
            loan.renewal_count += 1
            loan.updated_by = tracking_user
            loan.history.append({
                'action': 'Renewed via Barcode Scan',
                'date': str(timezone.localdate()),
                'new_due_on': str(loan.due_on),
                'user': user_name,
            })
            loan.save()

            send_targeted_broadcast('realtime_updates', {
                'model': 'LibraryTransaction',
                'action': 'renewed',
                'id': loan.id
            })

            return self._success(
                f'Book "{book.title}" renewed successfully until {loan.due_on}.',
                LibraryTransactionSerializer(loan, context={'request': request}).data
            )


class LibraryDashboardViewSet(LibraryViewSetMixin, viewsets.ViewSet):
    @action(detail=False, methods=['get'])
    def summary(self, request):
        today = timezone.localdate()
        try:
            fine_per_day = max(0.0, float(request.query_params.get('fine_per_day', 1.0)))
        except (ValueError, TypeError):
            fine_per_day = 1.0

        active_loans_qs = LibraryTransaction.objects.filter(returned_on__isnull=True)
        active_loans_count = active_loans_qs.count()
        overdue_qs = active_loans_qs.filter(due_on__lt=today)
        overdue_count = overdue_qs.count()

        # Dynamic Fine Calculation across all active overdue loans (read-only aggregation)
        total_overdue_days = 0
        for due_on in overdue_qs.values_list('due_on', flat=True):
            if due_on and due_on < today:
                total_overdue_days += (today - due_on).days

        total_fine_pending = round(total_overdue_days * fine_per_day, 2)

        # Today's circulation metrics
        issued_today = LibraryTransaction.objects.filter(issued_on=today).count()
        returned_today = LibraryTransaction.objects.filter(returned_on=today).count()

        # Recent transactions (10)
        recent = LibraryTransaction.objects.select_related(
            'book', 'member__student__application', 'member__student__application__candidate',
            'member__student', 'member__user', 'member__user__role'
        ).order_by('-id')[:10]

        from django.db.models import Sum, Count
        books_qs = LibraryBook.objects.filter(is_active=True)
        totals = books_qs.aggregate(
            total=Sum('total_copies'),
            available=Sum('available_copies')
        )
        total_copies = totals['total'] or 0
        available_copies = totals['available'] or 0

        # Status counts
        status_counts = dict(
            books_qs.values_list('status').annotate(c=Count('id'))
        )
        maintenance_count = status_counts.get('MAINTENANCE', 0)
        lost_count = status_counts.get('LOST', 0) + status_counts.get('DAMAGED', 0)
        reference_count = status_counts.get('REFERENCE', 0)

        # Department distribution (Top 6 departments)
        dept_breakdown = list(
            books_qs.exclude(department='').values('department')
            .annotate(titles=Count('id'), copies=Sum('total_copies'))
            .order_by('-titles')[:6]
        )

        serializer_context = {'request': request, 'fine_per_day': fine_per_day}

        return self._success('Library dashboard loaded successfully', {
            'books': books_qs.count(),
            'total_copies': total_copies,
            'available_copies': available_copies,
            'members': LibraryMember.objects.filter(is_active=True).count(),
            'active_loans': active_loans_count,
            'overdue_loans': overdue_count,
            'issued_today': issued_today,
            'returned_today': returned_today,
            'fine_per_day': fine_per_day,
            'total_overdue_days': total_overdue_days,
            'total_fine_pending': total_fine_pending,
            'maintenance_count': maintenance_count,
            'lost_count': lost_count,
            'reference_count': reference_count,
            'dept_breakdown': dept_breakdown,
            'recent_transactions': LibraryTransactionSerializer(recent, many=True, context=serializer_context).data,
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


class LibraryFineViewSet(LibraryViewSetMixin, viewsets.ModelViewSet):
    queryset = LibraryFine.objects.select_related(
        'transaction', 'member', 'member__student', 'member__student__application__candidate',
        'member__student__department', 'member__user', 'member__user__role', 'book'
    ).all()
    serializer_class = LibraryFineSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        status_val = self.request.query_params.get('status')
        member_id = self.request.query_params.get('member_id')
        if query:
            queryset = queryset.filter(
                Q(book__title__icontains=query)
                | Q(book__acc_no__icontains=query)
                | Q(member__membership_number__icontains=query)
                | Q(member__student__roll_number__icontains=query)
                | Q(member__student__register_number__icontains=query)
                | Q(member__student__student_name__icontains=query)
                | Q(member__student__application__candidate__name__icontains=query)
                | Q(member__user__username__icontains=query)
                | Q(member__user__name__icontains=query)
                | Q(receipt_no__icontains=query)
            )
        if status_val:
            queryset = queryset.filter(status__iexact=status_val)
        if member_id:
            queryset = queryset.filter(member_id=member_id)

        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering:
            order_fields = [f.strip() for f in str(ordering).split(',') if f.strip()]
            if order_fields:
                queryset = queryset.order_by(*order_fields)
        return queryset

    def _sync_active_overdue_fines(self, fine_per_day=None):
        today = timezone.localdate()
        try:
            if fine_per_day is None:
                rate_param = self.request.query_params.get('fine_per_day') or (self.request.data.get('fine_per_day') if hasattr(self.request, 'data') else None)
                fine_per_day = float(rate_param) if rate_param is not None and str(rate_param).strip() != '' else 1.0
            fine_per_day = max(0.0, float(fine_per_day))
        except (ValueError, TypeError):
            fine_per_day = 1.0

        overdue_loans = LibraryTransaction.objects.filter(
            returned_on__isnull=True,
            due_on__lt=today
        ).select_related('member', 'book')

        synced_count = 0
        for loan in overdue_loans:
            if loan.due_on:
                days = (today - loan.due_on).days
                if days > 0:
                    fine_amt = Decimal(str(days)) * Decimal(str(fine_per_day))
                    fine_rec = LibraryFine.objects.filter(transaction=loan).first()
                    if not fine_rec:
                        LibraryFine.objects.create(
                            transaction=loan,
                            member=loan.member,
                            book=loan.book,
                            due_on=loan.due_on,
                            overdue_days=days,
                            fine_rate_per_day=Decimal(str(fine_per_day)),
                            fine_amount=fine_amt,
                            status='PENDING',
                        )
                        synced_count += 1
                    elif fine_rec.status == 'PENDING':
                        fine_rec.overdue_days = days
                        fine_rec.fine_rate_per_day = Decimal(str(fine_per_day))
                        fine_rec.fine_amount = fine_amt
                        fine_rec.save(update_fields=['overdue_days', 'fine_rate_per_day', 'fine_amount', 'updated_at'])
                        synced_count += 1
        return synced_count

    def list(self, request, *args, **kwargs):
        # Automatically synchronize overdue checkouts instantly on fetch
        self._sync_active_overdue_fines()
        response = super().list(request, *args, **kwargs)
        return self._success('Library fines retrieved successfully', response.data)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        fine = self.get_object()
        if fine.status == 'PAID':
            return Response({'code': 400, 'message': 'This fine has already been paid in full.'}, status=400)

        paid_amount = Decimal(str(request.data.get('paid_amount', fine.fine_amount - fine.paid_amount)))
        receipt_no = (request.data.get('receipt_no') or f"REC-{timezone.now().strftime('%y%m%d%H%M%S')}").strip()
        remarks = request.data.get('remarks', '')

        fine.paid_amount = (fine.paid_amount or Decimal('0.00')) + paid_amount
        if fine.paid_amount >= fine.fine_amount:
            fine.status = 'PAID'
        else:
            fine.status = 'PARTIAL'
        fine.paid_on = timezone.now()
        fine.receipt_no = receipt_no
        if remarks:
            fine.remarks = f"{fine.remarks}\n{remarks}".strip()
        fine.updated_by = self._tracking_user()
        fine.save()

        return self._success('Fine payment recorded successfully', LibraryFineSerializer(fine).data)

    @action(detail=False, methods=['post'], url_path='sync-overdue')
    def sync_overdue(self, request):
        try:
            fine_per_day = max(0.0, float(request.data.get('fine_per_day', 1.0)))
        except (ValueError, TypeError):
            fine_per_day = 1.0
        synced_count = self._sync_active_overdue_fines(fine_per_day=fine_per_day)
        return self._success(f'Successfully synced {synced_count} overdue fine records', {'synced_count': synced_count})


class LibraryReservationViewSet(LibraryViewSetMixin, viewsets.ModelViewSet):
    queryset = LibraryReservation.objects.select_related(
        'book', 'member', 'member__student', 'member__user', 'created_by'
    ).all()
    serializer_class = LibraryReservationSerializer
    permission_classes = [LibraryReservationPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # If user is student, filter only their own reservations
        if hasattr(user, 'role') and getattr(user.role, 'role_name', '').upper() == 'STUDENT':
            qs = qs.filter(
                Q(member__user=user) |
                Q(member__student__roll_number=user.username) |
                Q(member__student__register_number=user.username)
            )

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())

        book_id = self.request.query_params.get('book_id')
        if book_id:
            qs = qs.filter(book_id=book_id)

        member_id = self.request.query_params.get('member_id')
        if member_id:
            qs = qs.filter(member_id=member_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(book_title__icontains=search) |
                Q(book__acc_no__icontains=search) |
                Q(member__membership_number__icontains=search) |
                Q(member__student__student_name__icontains=search) |
                Q(member__user__name__icontains=search)
            )

        ordering = self.request.query_params.get('ordering')
        if ordering:
            order_fields = [f.strip() for f in str(ordering).split(',') if f.strip()]
            if order_fields:
                return qs.order_by(*order_fields)
        return qs.order_by('-reserved_on', '-id')

    def create(self, request, *args, **kwargs):
        book_id = request.data.get('book_id') or request.data.get('book')
        member_id = request.data.get('member_id') or request.data.get('member')

        if not book_id:
            return Response({'code': 400, 'message': 'Book ID is required to reserve.'}, status=400)

        book = LibraryBook.objects.filter(pk=book_id).first()
        if not book:
            return Response({'code': 404, 'message': 'Book not found.'}, status=404)

        # Resolve member
        member = None
        user = request.user
        if member_id:
            member = LibraryMember.objects.filter(pk=member_id).first()
        elif user and user.is_authenticated:
            # Prioritize student membership if user account belongs to a student
            member = LibraryMember.objects.filter(
                Q(student__roll_number__iexact=user.username) |
                Q(student__register_number__iexact=user.username)
            ).first()
            if not member:
                member = LibraryMember.objects.filter(user=user, student__isnull=False).first()
            if not member:
                member = LibraryMember.objects.filter(user=user).first()
            
            # If member exists for this student but user FK wasn't linked, link it now
            if member and not member.user and (
                member.student and (
                    member.student.roll_number == user.username or
                    member.student.register_number == user.username
                )
            ):
                member.user = user
                member.save(update_fields=['user', 'updated_at'])

        if not member:
            return Response({'code': 400, 'message': 'Unable to identify active library member record.'}, status=400)

        # Check if already has active reservation for this book
        existing_res = LibraryReservation.objects.filter(
            book=book,
            member=member,
            status__in=['PENDING', 'AVAILABLE']
        ).first()
        if existing_res:
            return Response({
                'code': 400,
                'message': f'You already have an active reservation for this book (Status: {existing_res.status}, Position #{existing_res.queue_position}).'
            }, status=400)

        # Check if member already has this book borrowed
        already_borrowed = LibraryTransaction.objects.filter(
            book=book,
            member=member,
            returned_on__isnull=True
        ).exists()
        if already_borrowed:
            return Response({
                'code': 400,
                'message': 'You currently have this book checked out. No need to reserve.'
            }, status=400)

        # Calculate queue position
        pending_count = LibraryReservation.objects.filter(
            book=book,
            status='PENDING'
        ).count()
        queue_pos = pending_count + 1

        reservation = LibraryReservation.objects.create(
            book=book,
            book_title=book.title,
            member=member,
            status='PENDING',
            queue_position=queue_pos,
            notes=request.data.get('notes', ''),
            created_by=self._tracking_user(),
            updated_by=self._tracking_user(),
        )

        serializer = self.get_serializer(reservation)
        avail_msg = ''
        if book.available_copies > 0:
            avail_msg = ' (Note: Copies are currently in stacks; you can also borrow directly at the desk).'

        send_targeted_broadcast('realtime_updates', {
            'model': 'LibraryReservation',
            'action': 'created',
            'id': reservation.id
        })

        return self._success(
            f'Book reserved successfully. You are #{queue_pos} in queue{avail_msg}.',
            serializer.data,
            code=201
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        reservation = LibraryReservation.objects.filter(pk=pk).first()
        if not reservation:
            return Response({'code': 404, 'message': 'Reservation not found.'}, status=404)
        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'role_name', '').upper().replace(' ', '_')
        staff_roles = {'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN', 'LIBRARY', 'LIBRARIAN', 'TECH_SUPPORTER', 'ADMINISTRATION_OFFICER', 'AO'}
        is_staff = getattr(user, 'is_superuser', False) or (role_name in staff_roles)

        if not is_staff:
            is_owner = (
                (reservation.member and reservation.member.user_id and reservation.member.user_id == user.id) or
                (reservation.member and reservation.member.student and (
                    reservation.member.student.roll_number == user.username or
                    reservation.member.student.register_number == user.username
                ))
            )
            if not is_owner:
                return Response({'code': 403, 'message': 'You can only cancel your own reservation.'}, status=403)

        if reservation.status in ['FULFILLED', 'CANCELLED', 'EXPIRED']:
            return Response({'code': 400, 'message': f'Cannot cancel reservation with status {reservation.status}.'}, status=400)

        was_available = (reservation.status == 'AVAILABLE')
        reservation.status = 'CANCELLED'
        reservation.updated_by = self._tracking_user()
        reservation.save()

        # If it was available and cancelled, promote next in line
        if was_available:
            next_res = LibraryReservation.objects.filter(
                book=reservation.book,
                status='PENDING'
            ).order_by('reserved_on', 'id').first()
            if next_res:
                hold_until = timezone.localdate() + timedelta(days=2)
                next_res.status = 'AVAILABLE'
                next_res.available_until = hold_until
                next_res.notified_on = timezone.now()
                next_res.updated_by = self._tracking_user()
                next_res.save()

                try:
                    target_user = next_res.member.user if next_res.member else None
                    if not target_user and next_res.member and next_res.member.student:
                        stu = next_res.member.student
                        target_user = User.objects.filter(
                            Q(username=stu.roll_number) | Q(username=stu.register_number)
                        ).first()
                    if target_user:
                        from leave.models import Notification
                        Notification.objects.create(
                            user=target_user,
                            title='Reserved Library Book Ready for Pickup!',
                            message=f'Good news! Your reserved book "{reservation.book.title}" is now available at the Central Library desk. Please pick it up by {hold_until}.',
                            notification_type='GENERAL',
                        )
                except Exception:
                    pass

        send_targeted_broadcast('realtime_updates', {
            'model': 'LibraryReservation',
            'action': 'cancelled',
            'id': reservation.id
        })

        return self._success('Reservation cancelled successfully.', self.get_serializer(reservation).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Staff marks reservation as AVAILABLE / Ready for Pickup and holds it for 2 days."""
        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'role_name', '').upper().replace(' ', '_')
        staff_roles = {'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN', 'LIBRARY', 'LIBRARIAN', 'TECH_SUPPORTER', 'ADMINISTRATION_OFFICER', 'AO'}
        is_staff = getattr(user, 'is_superuser', False) or (role_name in staff_roles)
        if not is_staff:
            return Response({'code': 403, 'message': 'Only library staff are permitted to approve reservations.'}, status=403)

        reservation = LibraryReservation.objects.filter(pk=pk).first()
        if not reservation:
            return Response({'code': 404, 'message': 'Reservation not found.'}, status=404)
        if reservation.status not in ['PENDING']:
            return Response({'code': 400, 'message': f'Cannot approve reservation with status {reservation.status}.'}, status=400)

        hold_until = timezone.localdate() + timedelta(days=2)
        reservation.status = 'AVAILABLE'
        reservation.available_until = hold_until
        reservation.notified_on = timezone.now()
        reservation.updated_by = self._tracking_user()
        reservation.save()

        try:
            target_user = reservation.member.user if reservation.member else None
            if not target_user and reservation.member and reservation.member.student:
                stu = reservation.member.student
                target_user = User.objects.filter(
                    Q(username=stu.roll_number) | Q(username=stu.register_number)
                ).first()
            if target_user:
                from leave.models import Notification
                Notification.objects.create(
                    user=target_user,
                    title='Reserved Library Book Ready for Pickup!',
                    message=f'Your reserved book "{reservation.book.title}" is now ready at Central Library desk. Held until {hold_until}.',
                    notification_type='GENERAL',
                )
        except Exception:
            pass

        send_targeted_broadcast('realtime_updates', {
            'model': 'LibraryReservation',
            'action': 'approved',
            'id': reservation.id
        })

        return self._success(f'Reservation approved. Book held for pickup until {hold_until}.', self.get_serializer(reservation).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def issue(self, request, pk=None):
        """Staff directly issues the reserved book to the borrower, converting reservation to checkout loan."""
        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'role_name', '').upper().replace(' ', '_')
        staff_roles = {'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN', 'LIBRARY', 'LIBRARIAN', 'TECH_SUPPORTER', 'ADMINISTRATION_OFFICER', 'AO'}
        is_staff = getattr(user, 'is_superuser', False) or (role_name in staff_roles)
        if not is_staff:
            return Response({'code': 403, 'message': 'Only library staff are permitted to issue books.'}, status=403)

        reservation = LibraryReservation.objects.filter(pk=pk).first()
        if not reservation:
            return Response({'code': 404, 'message': 'Reservation not found.'}, status=404)
        if reservation.status in ['FULFILLED', 'CANCELLED']:
            return Response({'code': 400, 'message': f'Cannot issue book for reservation with status {reservation.status}.'}, status=400)

        book = reservation.book
        member = reservation.member
        if not member:
            return Response({'code': 400, 'message': 'Reservation does not have an associated borrower member record.'}, status=400)

        # Check borrower limit (3 for students, 5 for staff)
        max_books = getattr(member, 'max_books_allowed', 3)
        active_count = LibraryTransaction.objects.filter(member=member, returned_on__isnull=True).count()
        if active_count >= max_books:
            return Response({'code': 400, 'message': f'Borrower has reached max limit of {max_books} books.'}, status=400)

        # Decrement available copies if > 0
        if book.available_copies > 0:
            book.available_copies -= 1
            book.save(update_fields=['available_copies', 'updated_at'])

        issue_date = timezone.localdate()
        loan_days = getattr(member, 'max_days_allowed', 15)
        due_date = issue_date + timedelta(days=loan_days)

        loan = LibraryTransaction.objects.create(
            member=member,
            book=book,
            issued_on=issue_date,
            due_on=due_date,
            status='ISSUED',
            history=[{
                'action': 'Issued from Reservation',
                'date': str(issue_date),
                'user': getattr(self._tracking_user(), 'name', 'Librarian') if self._tracking_user() else 'Librarian'
            }],
            created_by=self._tracking_user(),
            updated_by=self._tracking_user(),
        )

        reservation.status = 'FULFILLED'
        reservation.updated_by = self._tracking_user()
        reservation.save()

        try:
            target_user = member.user
            if not target_user and member.student:
                stu = member.student
                target_user = User.objects.filter(
                    Q(username=stu.roll_number) | Q(username=stu.register_number)
                ).first()
            if target_user:
                from leave.models import Notification
                Notification.objects.create(
                    user=target_user,
                    title='Library Book Issued',
                    message=f'Book "{book.title}" (ACC: {book.acc_no}) has been checked out to you. Due date is {due_date}.',
                    notification_type='GENERAL',
                )
        except Exception:
            pass

        send_targeted_broadcast('realtime_updates', {
            'model': 'LibraryReservation',
            'action': 'fulfilled',
            'id': reservation.id
        })
        send_targeted_broadcast('realtime_updates', {
            'model': 'LibraryTransaction',
            'action': 'issued',
            'id': loan.id
        })

        return self._success(f'Book "{book.title}" issued successfully to {member.borrower_name or "borrower"}. Due date: {due_date}.', {
            'reservation': self.get_serializer(reservation).data,
            'loan': LibraryTransactionSerializer(loan).data
        })

    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'role_name', '').upper().replace(' ', '_')
        staff_roles = {'ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN', 'LIBRARY', 'LIBRARIAN', 'TECH_SUPPORTER', 'ADMINISTRATION_OFFICER', 'AO'}
        is_staff = getattr(user, 'is_superuser', False) or (role_name in staff_roles)
        if not is_staff:
            return Response({'code': 403, 'message': 'Only library staff are permitted to fulfill reservations.'}, status=403)

        reservation = LibraryReservation.objects.filter(pk=pk).first()
        if not reservation:
            return Response({'code': 404, 'message': 'Reservation not found.'}, status=404)
        reservation.status = 'FULFILLED'
        reservation.updated_by = self._tracking_user()
        reservation.save()

        send_targeted_broadcast('realtime_updates', {
            'model': 'LibraryReservation',
            'action': 'fulfilled',
            'id': reservation.id
        })

        return self._success('Reservation marked as fulfilled.', self.get_serializer(reservation).data)


class MyLibraryViewSet(LibraryViewSetMixin, viewsets.ViewSet):
    """Provides personalized library oversight for students and faculty."""

    def my_library(self, request):
        user = request.user
        today = timezone.localdate()

        # Allow staff/admin to inspect a specific member via query params
        member_id = request.query_params.get('member_id')
        code = request.query_params.get('code')
        roll_number = request.query_params.get('roll_number')

        member = None
        if member_id:
            member = LibraryMember.objects.filter(pk=member_id).first()
        elif code:
            member = LibraryMember.objects.filter(membership_number__iexact=code).first()
        elif roll_number:
            member = LibraryMember.objects.filter(
                Q(student__roll_number__iexact=roll_number) |
                Q(user__username__iexact=roll_number)
            ).first()
        elif user and user.is_authenticated:
            # Prioritize student membership if user account belongs to a student
            member = LibraryMember.objects.filter(
                Q(student__roll_number__iexact=user.username) |
                Q(student__register_number__iexact=user.username)
            ).first()
            if not member:
                member = LibraryMember.objects.filter(user=user, student__isnull=False).first()
            if not member:
                member = LibraryMember.objects.filter(user=user).first()
            
            # If member exists for this student but user FK wasn't linked, link it now
            if member and not member.user and (
                member.student and (
                    member.student.roll_number == user.username or
                    member.student.register_number == user.username
                )
            ):
                member.user = user
                member.save(update_fields=['user', 'updated_at'])

        # Auto-provision library member on the fly if missing for authenticated user
        if not member and user and user.is_authenticated:
            try:
                matching_student = Student.objects.filter(roll_number__iexact=user.username).first()
                if not matching_student:
                    matching_student = Student.objects.filter(register_number__iexact=user.username).first()

                is_student_role = (
                    (hasattr(user, 'role') and getattr(user.role, 'role_name', '').upper() == 'STUDENT') or
                    bool(matching_student)
                )

                if is_student_role and matching_student:
                    code = LibraryMember.generate_code_for_student(matching_student)
                    stu_active = True
                    if matching_student.status:
                        if not getattr(matching_student.status, 'is_active', True):
                            stu_active = False
                        elif getattr(matching_student.status, 'status_name', '').upper() in ['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']:
                            stu_active = False
                    if not getattr(user, 'is_active', True):
                        stu_active = False

                    member = LibraryMember.objects.create(
                        student=matching_student,
                        user=user,
                        member_type='STUDENT',
                        membership_number=code,
                        is_active=stu_active,
                    )
                else:
                    code = LibraryMember.generate_code_for_user(user)
                    member = LibraryMember.objects.create(
                        user=user,
                        member_type='STAFF',
                        membership_number=code,
                        is_active=getattr(user, 'is_active', True),
                    )
            except Exception:
                member = LibraryMember.objects.filter(user=user).first()

        if not member:
            return Response({
                'code': 404,
                'message': 'No library member record associated with your account. Please contact the librarian.'
            }, status=404)

        # 1. Member Profile & Barcode
        member_info = LibraryMemberSerializer(member).data

        # 2. Active Loans
        active_loans_qs = LibraryTransaction.objects.filter(
            member=member,
            returned_on__isnull=True
        ).select_related('book').order_by('due_on')

        active_loans = []
        overdue_count = 0
        total_overdue_fines = Decimal('0.00')

        for loan in active_loans_qs:
            is_overdue = bool(loan.due_on and loan.due_on < today)
            overdue_days = (today - loan.due_on).days if is_overdue else 0
            fine_settled = False
            fine_status = 'NONE'
            fine_paid = 0.0

            if is_overdue:
                overdue_count += 1
                fine_rec = loan.fines.filter(status__in=['PENDING', 'PARTIAL']).first() or loan.fines.first()
                if fine_rec:
                    accrued_fine = max(
                        Decimal('0.00'),
                        (fine_rec.fine_amount or Decimal('0.00')) -
                        (fine_rec.paid_amount or Decimal('0.00'))
                    )
                    fine_status = fine_rec.status
                    fine_paid = float(fine_rec.paid_amount or Decimal('0.00'))
                    if fine_rec.status == 'PAID' and accrued_fine == Decimal('0.00'):
                        fine_settled = True
                else:
                    accrued_fine = Decimal(str(overdue_days)) * Decimal('1.00')
                    fine_status = 'PENDING'
                total_overdue_fines += accrued_fine
            else:
                accrued_fine = Decimal('0.00')

            status_text = 'OVERDUE' if is_overdue else 'ISSUED'
            if is_overdue and fine_settled:
                status_text = 'FINE SETTLED (RETURN PENDING)'

            active_loans.append({
                'id': loan.id,
                'book_id': loan.book_id,
                'book_title': loan.book.title,
                'book_acc_no': loan.book.acc_no,
                'book_call_no': loan.book.call_no,
                'author': loan.book.author,
                'shelf_location': loan.book.shelf_location,
                'issued_on': str(loan.issued_on),
                'due_on': str(loan.due_on),
                'renewal_count': loan.renewal_count,
                'status': status_text,
                'is_overdue': is_overdue,
                'overdue_days': overdue_days,
                'accrued_fine': float(accrued_fine),
                'fine_settled': fine_settled,
                'fine_status': fine_status,
                'fine_paid': fine_paid,
            })

        # 3. Borrowing History (Recent Returned Books)
        history_qs = LibraryTransaction.objects.filter(
            member=member,
            returned_on__isnull=False
        ).select_related('book').prefetch_related('fines').order_by('-returned_on')[:25]

        history = []
        for loan in history_qs:
            fine_rec = loan.fines.first()
            fine_amt = float(fine_rec.fine_amount or 0) if fine_rec else 0.0
            fine_paid = float(fine_rec.paid_amount or 0) if fine_rec else 0.0
            fine_status = fine_rec.status if fine_rec else 'NONE'
            history.append({
                'id': loan.id,
                'book_title': loan.book.title,
                'book_acc_no': loan.book.acc_no,
                'author': loan.book.author,
                'issued_on': str(loan.issued_on),
                'due_on': str(loan.due_on),
                'returned_on': str(loan.returned_on),
                'status': loan.status,
                'fine_amount': fine_amt,
                'fine_paid': fine_paid,
                'fine_status': fine_status,
            })

        # 4. Overdue Fines Ledger
        fines_qs = LibraryFine.objects.filter(member=member).select_related('book').order_by('-created_at')[:25]
        fines = [LibraryFineSerializer(f).data for f in fines_qs]

        pending_fines_sum = sum(
            float(f.get('balance_amount', 0)) for f in fines if f.get('status') in ['PENDING', 'PARTIAL']
        )
        total_fines_paid = sum(
            float(f.get('paid_amount', 0)) for f in fines
        )

        # 5. Book Reservations Queue
        res_qs = LibraryReservation.objects.filter(
            member=member
        ).select_related('book').order_by('-reserved_on')[:15]
        reservations = [LibraryReservationSerializer(r).data for r in res_qs]

        active_res_count = LibraryReservation.objects.filter(
            member=member,
            status__in=['PENDING', 'AVAILABLE']
        ).count()

        total_borrowed_lifetime = LibraryTransaction.objects.filter(member=member).count()

        # If there are fine records in the ledger, use pending_fines_sum directly (which is 0 when all are paid)
        # If there are no fine records at all, use total_overdue_fines
        effective_pending_fine = pending_fines_sum if len(fines) > 0 else float(total_overdue_fines)

        kpis = {
            'currently_borrowed': len(active_loans),
            'overdue_loans': overdue_count,
            'unsettled_overdues': sum(1 for l in active_loans if l.get('is_overdue') and not l.get('fine_settled')),
            'total_borrowed_lifetime': total_borrowed_lifetime,
            'pending_fines_amount': effective_pending_fine,
            'total_fines_paid': total_fines_paid,
            'active_reservations': active_res_count,
        }

        return self._success('My library data retrieved successfully', {
            'member': member_info,
            'kpis': kpis,
            'active_loans': active_loans,
            'history': history,
            'fines': fines,
            'reservations': reservations,
        })


class LibraryNotificationViewSet(LibraryViewSetMixin, viewsets.ViewSet):
    """Dispatches daily 9:00 AM overdue notifications for library borrowers."""

    def send_overdue_notifications(self, request):
        today = timezone.localdate()
        
        # Dynamic fine rate from request parameter or default 1.00
        rate_param = request.data.get('fine_per_day') or request.query_params.get('fine_per_day')
        try:
            fine_rate = Decimal(str(rate_param)) if rate_param is not None else Decimal('1.00')
        except Exception:
            fine_rate = Decimal('1.00')

        overdue_loans = LibraryTransaction.objects.filter(
            returned_on__isnull=True,
            due_on__lt=today
        ).select_related('member', 'member__student', 'member__user', 'book')

        notified_users = 0
        skipped_already_notified = 0
        skipped_no_due = 0
        total_overdue_fine_amount = Decimal('0.00')

        from leave.models import Notification

        for loan in overdue_loans:
            days = (today - loan.due_on).days
            if days <= 0:
                continue

            fine_amt = Decimal(str(days)) * fine_rate

            # Check existing fine record
            fine_rec = loan.fines.first()
            if fine_rec:
                # If fine record exists and was already paid in full, do NOT send notification!
                if fine_rec.status == 'PAID':
                    skipped_no_due += 1
                    continue
                
                # Check balance
                paid = fine_rec.paid_amount or Decimal('0.00')
                balance = max(Decimal('0.00'), fine_amt - paid)
                if balance <= Decimal('0.00'):
                    skipped_no_due += 1
                    continue

                if fine_rec.status == 'PENDING':
                    fine_rec.overdue_days = days
                    fine_rec.fine_rate_per_day = fine_rate
                    fine_rec.fine_amount = fine_amt
                    fine_rec.save()
            else:
                balance = fine_amt
                fine_rec = LibraryFine.objects.create(
                    transaction=loan,
                    member=loan.member,
                    book=loan.book,
                    due_on=loan.due_on,
                    overdue_days=days,
                    fine_rate_per_day=fine_rate,
                    fine_amount=fine_amt,
                    status='PENDING',
                    created_by=self._tracking_user(),
                    updated_by=self._tracking_user(),
                )

            total_overdue_fine_amount += balance

            # Determine user account
            target_user = None
            if loan.member.user:
                target_user = loan.member.user
            elif loan.member.student:
                stu = loan.member.student
                target_user = User.objects.filter(
                    Q(username=stu.roll_number) | Q(username=stu.register_number)
                ).first()

            if not target_user:
                continue

            # Prevent duplicate notifications on the same day for the same loan
            already_notified_today = Notification.objects.filter(
                user=target_user,
                created_at__date=today,
                title__icontains='Overdue Library Book',
                message__icontains=loan.book.acc_no or loan.book.title[:20]
            ).exists()

            if already_notified_today:
                skipped_already_notified += 1
                continue

            # Create in-app morning notification with exact dynamic amount
            Notification.objects.create(
                user=target_user,
                title=f'Overdue Library Book: {loan.book.title[:50]}',
                message=(
                    f'Your borrowed book "{loan.book.title}" (Acc: {loan.book.acc_no}) was due on {loan.due_on} '
                    f'and is now {days} day(s) overdue. Current pending fine due: ₹{balance:.2f} ({days} days @ ₹{fine_rate}/day). '
                    f'Please return or renew it at the library desk today.'
                ),
                notification_type='GENERAL',
            )
            notified_users += 1

        if notified_users == 0 and skipped_no_due > 0 and skipped_already_notified == 0:
            msg = 'All borrowers with overdue checkouts have already cleared their dues. No notifications sent.'
        else:
            msg = f'Overdue check completed. Notified {notified_users} borrower(s) (Skipped {skipped_no_due} with zero due, {skipped_already_notified} already notified today).'

        return self._success(
            msg,
            {
                'total_overdue_loans': overdue_loans.count(),
                'notified_users': notified_users,
                'skipped_no_due': skipped_no_due,
                'skipped_already_notified': skipped_already_notified,
                'total_overdue_fines': float(total_overdue_fine_amount),
                'check_date': str(today),
            }
        )

