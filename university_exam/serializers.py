from rest_framework import serializers
from .models import (
    ExamAttendanceImport, UniversityExamSchedule,
    UniversityExamAttendance, ExamHallAllocation, ExamSeatAllocation,
    UniversityExamHall, ExamHallDate
)
from common.serializers import TrackingModelSerializerMixin


class UniversityExamHallSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    hall_no = serializers.CharField(source='hall.hall_no', read_only=True)
    hall_name = serializers.CharField(source='hall.hall_name', read_only=True)
    floor_name = serializers.CharField(source='hall.floor.floor_name', read_only=True)
    block_code = serializers.CharField(source='hall.floor.block.block_code', read_only=True)

    class Meta:
        model = UniversityExamHall
        fields = [
            'id', 'hall', 'hall_no', 'hall_name', 'floor_name', 'block_code',
            'min_capacity', 'max_capacity', 'total_seats', 'rows_count', 'columns_count',
            'is_active', 'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]

    def validate(self, attrs):
        # Handle instance updates where attrs might be partial
        min_cap = attrs.get('min_capacity', getattr(self.instance, 'min_capacity', 25))
        max_cap = attrs.get('max_capacity', getattr(self.instance, 'max_capacity', 27))
        total = attrs.get('total_seats', getattr(self.instance, 'total_seats', 0))

        errors = {}
        if min_cap < 25:
            errors['min_capacity'] = "Minimum capacity must be at least 25."
        if max_cap > 27:
            errors['max_capacity'] = "Maximum capacity cannot exceed 27."
        if min_cap > max_cap:
            errors['min_capacity'] = "Minimum capacity cannot exceed maximum capacity."
        if total < min_cap:
            errors['total_seats'] = "Total seats must be greater than or equal to min capacity."
            
        if errors:
            raise serializers.ValidationError(errors)
            
        return attrs


class ExamHallDateSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    hall_no = serializers.CharField(source='exam_hall.hall.hall_no', read_only=True)

    class Meta:
        model = ExamHallDate
        fields = [
            'id', 'exam_hall', 'hall_no', 'exam_date', 'session', 'is_available', 'notes',
            'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]


class ExamAttendanceImportSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    branch_code = serializers.CharField(source='department.department_code', read_only=True)
    branch_name = serializers.CharField(source='department.department_name', read_only=True)
    register_no = serializers.CharField(source='student.register_number', read_only=True)
    student_name = serializers.SerializerMethodField()
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)

    class Meta:
        model = ExamAttendanceImport
        fields = [
            'id', 'department', 'student', 'subject', 'exam_date', 'session',
            'answer_book_no', 'qp_code', 'source_file', 'source_page',
            'import_status', 'error_message', 'branch_code', 'branch_name',
            'register_no', 'student_name', 'subject_code', 'subject_name',
            'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]

    def get_student_name(self, obj):
        if obj.student and obj.student.application:
            return obj.student.application.form_data.get('personal_info', {}).get('full_name', '')
        return ''


class UniversityExamScheduleSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_code = serializers.CharField(source='department.department_code', read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    student_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = UniversityExamSchedule
        fields = [
            'id', 'department', 'department_name', 'department_code',
            'subject', 'subject_code', 'subject_name',
            'exam_date', 'session', 'qp_code', 'exam_type',
            'seating_strategy', 'status', 'student_count',
            'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]


class UniversityExamAttendanceSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    register_number = serializers.CharField(source='student.register_number', read_only=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    subject_code = serializers.CharField(source='exam_schedule.subject.subject_code', read_only=True)

    class Meta:
        model = UniversityExamAttendance
        fields = [
            'id', 'exam_schedule', 'student', 'student_name', 'register_number',
            'department', 'department_name', 'subject_code',
            'attendance_status', 'answer_book_no', 'qp_code', 'attendance_marked_at',
            'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]

    def get_student_name(self, obj):
        try:
            return obj.student.application.candidate.name
        except Exception:
            return obj.student.roll_number or str(obj.student.id)


class ExamHallAllocationSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    hall_no = serializers.CharField(source='exam_hall.hall.hall_no', read_only=True)
    hall_name = serializers.CharField(source='exam_hall.hall.hall_name', read_only=True)
    block_code = serializers.CharField(source='exam_hall.hall.floor.block.block_code', read_only=True)
    floor_name = serializers.CharField(source='exam_hall.hall.floor.floor_name', read_only=True)
    exam_date = serializers.DateField(source='exam_schedule.exam_date', read_only=True)
    session = serializers.CharField(source='exam_schedule.session', read_only=True)

    class Meta:
        model = ExamHallAllocation
        fields = [
            'id', 'exam_schedule', 'exam_date', 'session',
            'exam_hall', 'hall_no', 'hall_name', 'block_code', 'floor_name',
            'allocation_order', 'planned_capacity', 'allocated_students', 'status',
            'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]


class ExamSeatAllocationSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    register_number = serializers.CharField(source='student.register_number', read_only=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_code = serializers.CharField(source='department.department_code', read_only=True)
    department_short_name = serializers.CharField(source='department.short_name', read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    subject_name = serializers.CharField(source='subject.subject_name', read_only=True)
    hall_no = serializers.CharField(source='hall_allocation.exam_hall.hall.hall_no', read_only=True)
    block_code = serializers.CharField(source='hall_allocation.exam_hall.hall.floor.block.block_code', read_only=True)
    floor_name = serializers.CharField(source='hall_allocation.exam_hall.hall.floor.floor_name', read_only=True)
    answer_book_no = serializers.SerializerMethodField()

    class Meta:
        model = ExamSeatAllocation
        fields = [
            'id', 'exam_schedule', 'hall_allocation',
            'hall_no', 'block_code', 'floor_name',
            'student', 'student_name', 'register_number',
            'seat_number', 'row_number', 'column_number',
            'department', 'department_name', 'department_code', 'department_short_name',
            'subject', 'subject_code', 'subject_name',
            'allocation_status', 'answer_book_no',
            'created_at', 'updated_at',
            *TrackingModelSerializerMixin.TRACKING_FIELDS,
        ]

    def get_answer_book_no(self, obj):
        try:
            from .models import UniversityExamAttendance
            att = UniversityExamAttendance.objects.get(
                exam_schedule=obj.exam_schedule,
                student=obj.student
            )
            return att.answer_book_no
        except Exception:
            return None

    def get_student_name(self, obj):
        try:
            return obj.student.application.candidate.name
        except Exception:
            return obj.student.roll_number or str(obj.student.id)
