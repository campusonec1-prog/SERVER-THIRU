from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from common.serializers import TrackingModelSerializerMixin
from student.models import Student

from .models import LibraryBook, LibraryMember, LibraryTransaction, LibraryFine, LibraryReservation


class LibraryBookQuickSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibraryBook
        fields = [
            'id', 'call_no', 'acc_no', 'title', 'author', 'isbn',
            'status', 'total_copies', 'available_copies', 'shelf_location',
            'department', 'is_active',
        ]


class LibraryMemberQuickSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    borrower_name = serializers.SerializerMethodField()
    borrower_role = serializers.SerializerMethodField()
    roll_number = serializers.SerializerMethodField()
    register_number = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()

    class Meta:
        model = LibraryMember
        fields = [
            'id', 'member_type', 'membership_number', 'student', 'user',
            'student_name', 'borrower_name', 'borrower_role',
            'roll_number', 'register_number', 'department_name', 'is_active',
        ]

    def get_student_name(self, obj):
        return obj.borrower_name

    def get_borrower_name(self, obj):
        return obj.borrower_name

    def get_borrower_role(self, obj):
        return obj.borrower_role

    def get_roll_number(self, obj):
        if obj.student:
            return obj.student.roll_number or ''
        if obj.user:
            return obj.user.username or ''
        return ''

    def get_register_number(self, obj):
        if obj.student:
            return obj.student.register_number or ''
        return ''

    def get_department_name(self, obj):
        if obj.student and obj.student.department:
            return obj.student.department.department_name
        return ''


class LibraryBookSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    issued_copies = serializers.SerializerMethodField()
    next_due_on = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = LibraryBook
        fields = [
            'id', 'call_no', 'acc_no', 'title', 'author', 'author1', 'author2', 'author3',
            'language', 'subject', 'sub_header', 'isbn', 'category', 'publisher', 'shelf_location',
            'price', 'date_of_purchase', 'location', 'status', 'max_times_issued',
            'pub_id', 'ven_id', 'department', 'pages', 'year_of_pub', 'curr_name',
            'remarks', 'catalog_details', 'total_copies', 'available_copies',
            'issued_copies', 'next_due_on', 'is_available', 'is_active', 'created_at', 'updated_at',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = ['available_copies', 'issued_copies', 'next_due_on', 'is_available', 'created_at', 'updated_at']
        extra_kwargs = {
            'total_copies': {'required': False, 'default': 1},
        }

    def get_issued_copies(self, obj):
        return obj.total_copies - obj.available_copies

    def get_is_available(self, obj):
        return obj.available_copies > 0

    def get_next_due_on(self, obj):
        if obj.available_copies < 1:
            if hasattr(obj, '_prefetched_objects_cache') and 'transactions' in obj._prefetched_objects_cache:
                for loan in obj.transactions.all():
                    if not loan.returned_on:
                        return str(loan.due_on)
            else:
                due = obj.transactions.filter(returned_on__isnull=True).order_by('due_on').values_list('due_on', flat=True).first()
                if due:
                    return str(due)
        return None

    def create(self, validated_data):
        validated_data['available_copies'] = validated_data['total_copies']
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'total_copies' in validated_data:
            issued = instance.total_copies - instance.available_copies
            total = validated_data['total_copies']
            if total < issued:
                raise serializers.ValidationError({'total_copies': 'Total copies cannot be less than currently issued copies.'})
            validated_data['available_copies'] = total - issued
        return super().update(instance, validated_data)


class LibraryMemberSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    borrower_name = serializers.SerializerMethodField()
    borrower_role = serializers.SerializerMethodField()
    roll_number = serializers.SerializerMethodField()
    register_number = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    batch_name = serializers.SerializerMethodField()
    section_name = serializers.SerializerMethodField()

    class Meta:
        model = LibraryMember
        fields = [
            'id', 'member_type', 'membership_number', 'student', 'user',
            'student_name', 'borrower_name', 'borrower_role',
            'roll_number', 'register_number', 'department_name', 'batch_name', 'section_name',
            'joined_on', 'is_active', 'created_at', 'updated_at',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = ['membership_number', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        return obj.borrower_name

    def get_borrower_name(self, obj):
        return obj.borrower_name

    def get_borrower_role(self, obj):
        return obj.borrower_role

    def get_roll_number(self, obj):
        if obj.student:
            return obj.student.roll_number or ''
        if obj.user:
            return obj.user.username or ''
        return ''

    def get_register_number(self, obj):
        if obj.student:
            return obj.student.register_number or ''
        return ''

    def get_department_name(self, obj):
        if obj.student and obj.student.department:
            return obj.student.department.department_name
        return ''

    def get_batch_name(self, obj):
        if obj.student and obj.student.batch:
            return getattr(obj.student.batch, 'batch', '')
        return ''

    def get_section_name(self, obj):
        if obj.student and obj.student.section:
            return getattr(obj.student.section, 'sections', '')
        return ''

    def validate(self, attrs):
        student = attrs.get('student')
        user = attrs.get('user')
        if not student and not user and self.instance is None:
            raise serializers.ValidationError('Either a student or a staff user must be selected.')

        instance_id = getattr(self.instance, 'id', None)
        if student:
            q = LibraryMember.objects.filter(student=student)
            if instance_id:
                q = q.exclude(id=instance_id)
            if q.exists():
                raise serializers.ValidationError({'student': 'This student already has a library unique code.'})
        if user:
            q = LibraryMember.objects.filter(user=user)
            if instance_id:
                q = q.exclude(id=instance_id)
            if q.exists():
                raise serializers.ValidationError({'user': 'This user/staff already has a library unique code.'})
        return attrs

    def create(self, validated_data):
        student = validated_data.get('student')
        user = validated_data.get('user')

        if student:
            validated_data['member_type'] = 'STUDENT'
            if not validated_data.get('membership_number'):
                validated_data['membership_number'] = LibraryMember.generate_code_for_student(student)
        elif user:
            validated_data['member_type'] = 'STAFF'
            if not validated_data.get('membership_number'):
                validated_data['membership_number'] = LibraryMember.generate_code_for_user(user)

        return super().create(validated_data)


class LibraryTransactionSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    book_acc_no = serializers.CharField(source='book.acc_no', read_only=True)
    book_call_no = serializers.CharField(source='book.call_no', read_only=True)
    book_author = serializers.CharField(source='book.author', read_only=True)
    member_number = serializers.CharField(source='member.membership_number', read_only=True)
    student_name = serializers.SerializerMethodField()
    borrower_name = serializers.SerializerMethodField()
    borrower_role = serializers.SerializerMethodField()
    roll_number = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    overdue_days = serializers.SerializerMethodField()
    fine_amount = serializers.SerializerMethodField()

    class Meta:
        model = LibraryTransaction
        fields = [
            'id', 'book', 'book_title', 'book_acc_no', 'book_call_no', 'book_author',
            'member', 'member_number', 'student_name', 'borrower_name', 'borrower_role',
            'roll_number', 'department_name',
            'issued_on', 'due_on', 'returned_on', 'renewal_count',
            'status', 'is_overdue', 'overdue_days', 'fine_amount', 'notes', 'history', 'created_at', 'updated_at',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        extra_kwargs = {
            'due_on': {'required': False},
        }
        read_only_fields = ['status', 'renewal_count', 'is_overdue', 'overdue_days', 'fine_amount', 'history', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        return obj.member.borrower_name if obj.member else ''

    def get_borrower_name(self, obj):
        return obj.member.borrower_name if obj.member else ''

    def get_borrower_role(self, obj):
        return obj.member.borrower_role if obj.member else ''

    def get_roll_number(self, obj):
        if not obj.member:
            return ''
        if obj.member.student:
            return obj.member.student.roll_number or ''
        if obj.member.user:
            return obj.member.user.username or ''
        return ''

    def get_department_name(self, obj):
        if obj.member and obj.member.student and obj.member.student.department:
            return obj.member.student.department.department_name
        return ''

    def get_is_overdue(self, obj):
        return obj.status == 'OVERDUE' or (obj.status != 'RETURNED' and obj.due_on and obj.due_on < timezone.localdate())

    def get_overdue_days(self, obj):
        today = timezone.localdate()
        if obj.status != 'RETURNED' and obj.due_on and obj.due_on < today:
            return (today - obj.due_on).days
        elif obj.returned_on and obj.due_on and obj.returned_on > obj.due_on:
            return (obj.returned_on - obj.due_on).days
        return 0

    def get_fine_amount(self, obj):
        fine_rec = obj.fines.filter(status__in=['PENDING', 'PARTIAL']).first() or obj.fines.first()
        if fine_rec:
            return float(max(Decimal('0.00'), (fine_rec.fine_amount or Decimal('0.00')) - (fine_rec.paid_amount or Decimal('0.00'))))
        days = self.get_overdue_days(obj)
        fine_rate = 1.0
        if self.context and 'fine_per_day' in self.context:
            try:
                fine_rate = float(self.context['fine_per_day'])
            except (ValueError, TypeError):
                fine_rate = 1.0
        return round(days * fine_rate, 2)

    def validate(self, attrs):
        if self.instance is None:
            book = attrs.get('book')
            member = attrs.get('member')
            if book and book.available_copies < 1:
                raise serializers.ValidationError({'book': 'No available copies for this book.'})
            if member and not member.is_active:
                raise serializers.ValidationError({'member': 'This library membership is inactive.'})
            if member and LibraryTransaction.objects.filter(member=member, book=book, returned_on__isnull=True).exists():
                raise serializers.ValidationError('This book is already issued to the selected member.')
        if attrs.get('returned_on') and self.instance and self.instance.returned_on:
            raise serializers.ValidationError({'returned_on': 'This book has already been returned.'})
        return attrs


class StudentLookupSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='user.name', read_only=True)
    program_id = serializers.IntegerField(source='department.program_id', read_only=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    batch_name = serializers.CharField(source='batch.batch', read_only=True)
    section_name = serializers.CharField(source='section.sections', read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'roll_number', 'register_number', 'student_name', 'program_id', 'department_name', 'batch_name', 'section_name']


class LibraryFineSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    member_number = serializers.CharField(source='member.membership_number', read_only=True)
    student_name = serializers.SerializerMethodField()
    borrower_name = serializers.SerializerMethodField()
    borrower_role = serializers.SerializerMethodField()
    roll_number = serializers.SerializerMethodField()
    register_number = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    book_title = serializers.CharField(source='book.title', read_only=True)
    book_acc_no = serializers.CharField(source='book.acc_no', read_only=True, default='')
    book_call_no = serializers.CharField(source='book.call_no', read_only=True, default='')
    balance_amount = serializers.SerializerMethodField()

    class Meta:
        model = LibraryFine
        fields = [
            'id', 'transaction', 'member', 'member_number', 'student_name',
            'borrower_name', 'borrower_role',
            'roll_number', 'register_number', 'department_name',
            'book', 'book_title', 'book_acc_no', 'book_call_no',
            'due_on', 'returned_on', 'overdue_days', 'fine_rate_per_day',
            'fine_amount', 'paid_amount', 'balance_amount',
            'status', 'paid_on', 'receipt_no', 'remarks',
            'created_at', 'updated_at',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = ['balance_amount', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        return obj.member.borrower_name if obj.member else ''

    def get_borrower_name(self, obj):
        return obj.member.borrower_name if obj.member else ''

    def get_borrower_role(self, obj):
        return obj.member.borrower_role if obj.member else ''

    def get_roll_number(self, obj):
        if not obj.member:
            return ''
        if obj.member.student:
            return obj.member.student.roll_number or ''
        if obj.member.user:
            return obj.member.user.username or ''
        return ''

    def get_register_number(self, obj):
        if obj.member and obj.member.student:
            return obj.member.student.register_number or ''
        return ''

    def get_department_name(self, obj):
        if obj.member and obj.member.student and obj.member.student.department:
            return obj.member.student.department.department_name
        return ''

    def get_balance_amount(self, obj):
        fine = obj.fine_amount or 0
        paid = obj.paid_amount or 0
        balance = fine - paid
        return max(0.0, float(balance))


class LibraryReservationSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    borrower_name = serializers.SerializerMethodField()
    borrower_role = serializers.SerializerMethodField()
    borrower_code = serializers.SerializerMethodField()
    book_acc_no = serializers.CharField(source='book.acc_no', read_only=True)
    author = serializers.CharField(source='book.author', read_only=True)
    shelf_location = serializers.CharField(source='book.shelf_location', read_only=True)
    available_copies = serializers.IntegerField(source='book.available_copies', read_only=True)

    class Meta:
        model = LibraryReservation
        fields = [
            'id', 'book', 'book_title', 'book_acc_no', 'author', 'shelf_location',
            'available_copies', 'member', 'borrower_code', 'borrower_name',
            'borrower_role', 'status', 'queue_position', 'reserved_on',
            'notified_on', 'available_until', 'notes', 'created_at', 'updated_at',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = ['queue_position', 'reserved_on', 'notified_on', 'created_at', 'updated_at']

    def get_borrower_name(self, obj):
        return obj.member.borrower_name if obj.member else ''

    def get_borrower_role(self, obj):
        return obj.member.borrower_role if obj.member else ''

    def get_borrower_code(self, obj):
        return obj.member.borrower_code if obj.member else ''

