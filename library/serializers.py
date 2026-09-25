from django.utils import timezone
from rest_framework import serializers

from student.models import Student

from .models import LibraryBook, LibraryMember, LibraryTransaction


class LibraryBookSerializer(serializers.ModelSerializer):
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
        ]
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
            active_loan = obj.transactions.filter(returned_on__isnull=True).order_by('due_on').first()
            if active_loan and active_loan.due_on:
                return str(active_loan.due_on)
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


class LibraryMemberSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.application.candidate.name', read_only=True, default='')
    roll_number = serializers.CharField(source='student.roll_number', read_only=True)
    register_number = serializers.CharField(source='student.register_number', read_only=True)
    department_name = serializers.CharField(source='student.department.department_name', read_only=True)
    batch_name = serializers.CharField(source='student.batch.batch', read_only=True)
    section_name = serializers.CharField(source='student.section.sections', read_only=True)

    class Meta:
        model = LibraryMember
        fields = [
            'id', 'student', 'student_name', 'roll_number', 'register_number',
            'department_name', 'batch_name', 'section_name',
            'membership_number', 'joined_on', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['membership_number', 'created_at', 'updated_at']

    def validate_student(self, value):
        instance_id = getattr(self.instance, 'id', None)
        query = LibraryMember.objects.filter(student=value)
        if instance_id:
            query = query.exclude(id=instance_id)
        if query.exists():
            raise serializers.ValidationError('This student already has a library membership.')
        return value

    def create(self, validated_data):
        student = validated_data['student']
        register_number = ''.join(char for char in str(student.register_number or '') if char.isdigit())
        if len(register_number) < 5:
            raise serializers.ValidationError({'student': 'The student must have a register number with at least 5 digits.'})

        joined_on = validated_data.get('joined_on') or timezone.localdate()
        membership_number = f'{joined_on.strftime("%y%m")}{register_number[-5:]}'
        if LibraryMember.objects.filter(membership_number=membership_number).exists():
            raise serializers.ValidationError({'student': f'Membership number {membership_number} already exists.'})

        validated_data['membership_number'] = membership_number
        return super().create(validated_data)


class LibraryTransactionSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    member_number = serializers.CharField(source='member.membership_number', read_only=True)
    student_name = serializers.CharField(source='member.student.application.candidate.name', read_only=True, default='')
    roll_number = serializers.CharField(source='member.student.roll_number', read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = LibraryTransaction
        fields = [
            'id', 'book', 'book_title', 'member', 'member_number', 'student_name',
            'roll_number', 'issued_on', 'due_on', 'returned_on', 'renewal_count',
            'status', 'is_overdue', 'notes', 'history', 'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'due_on': {'required': False},
        }
        read_only_fields = ['status', 'renewal_count', 'is_overdue', 'history', 'created_at', 'updated_at']

    def get_is_overdue(self, obj):
        return obj.status == 'OVERDUE' or (obj.status != 'RETURNED' and obj.due_on < timezone.localdate())

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
