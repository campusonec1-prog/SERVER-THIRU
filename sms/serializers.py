from rest_framework import serializers
from .models import SMSLog


class SMSLogSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)

    class Meta:
        model = SMSLog
        fields = [
            'id',
            'student',
            'student_name',
            'register_number',
            'recipient_type',
            'phone_number',
            'sms_type',
            'template_id',
            'message',
            'sent_date',
            'status',
            'gateway_response',
            'response_id',
            'error_message',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']


class FullDayAbsenteeStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    register_number = serializers.CharField(allow_blank=True, allow_null=True)
    roll_number = serializers.CharField(allow_blank=True, allow_null=True)
    department_id = serializers.IntegerField(allow_null=True)
    department_name = serializers.CharField(allow_blank=True, allow_null=True)
    batch_id = serializers.IntegerField(allow_null=True)
    batch_name = serializers.CharField(allow_blank=True, allow_null=True)
    section_id = serializers.IntegerField(allow_null=True)
    section_name = serializers.CharField(allow_blank=True, allow_null=True)
    student_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_name = serializers.CharField(allow_blank=True, allow_null=True)
    absent_periods_count = serializers.IntegerField(default=0)
    total_periods_count = serializers.IntegerField(default=0)
    sms_status = serializers.CharField(default='NOT_SENT')
    sms_sent_at = serializers.DateTimeField(allow_null=True, required=False)
    sms_log_id = serializers.IntegerField(allow_null=True, required=False)
    sms_response = serializers.JSONField(allow_null=True, required=False)


class SendFullDayAbsentSMSRequestSerializer(serializers.Serializer):
    date = serializers.DateField(required=True)
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=False
    )
    recipient_type = serializers.ChoiceField(
        choices=['PARENT', 'STUDENT', 'BOTH'],
        default='PARENT',
        required=False
    )


class AfternoonAbsenteeStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    register_number = serializers.CharField(allow_blank=True, allow_null=True)
    roll_number = serializers.CharField(allow_blank=True, allow_null=True)
    department_id = serializers.IntegerField(allow_null=True)
    department_name = serializers.CharField(allow_blank=True, allow_null=True)
    batch_id = serializers.IntegerField(allow_null=True)
    batch_name = serializers.CharField(allow_blank=True, allow_null=True)
    section_id = serializers.IntegerField(allow_null=True)
    section_name = serializers.CharField(allow_blank=True, allow_null=True)
    student_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_name = serializers.CharField(allow_blank=True, allow_null=True)
    an_period_no = serializers.IntegerField(default=5)
    fn_status = serializers.CharField(default='P')
    sms_status = serializers.CharField(default='NOT_SENT')
    sms_sent_at = serializers.DateTimeField(allow_null=True, required=False)
    sms_log_id = serializers.IntegerField(allow_null=True, required=False)
    sms_response = serializers.JSONField(allow_null=True, required=False)


class SendAfternoonAbsentSMSRequestSerializer(serializers.Serializer):
    date = serializers.DateField(required=True)
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=False
    )
    recipient_type = serializers.ChoiceField(
        choices=['PARENT', 'STUDENT', 'BOTH'],
        default='PARENT',
        required=False
    )


class FeesPendingStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    register_number = serializers.CharField(allow_blank=True, allow_null=True)
    roll_number = serializers.CharField(allow_blank=True, allow_null=True)
    department_id = serializers.IntegerField(allow_null=True)
    department_name = serializers.CharField(allow_blank=True, allow_null=True)
    department_code = serializers.CharField(allow_blank=True, allow_null=True)
    batch_id = serializers.IntegerField(allow_null=True)
    batch_name = serializers.CharField(allow_blank=True, allow_null=True)
    section_id = serializers.IntegerField(allow_null=True)
    section_name = serializers.CharField(allow_blank=True, allow_null=True)
    year_of_study = serializers.IntegerField(default=1)
    semesters = serializers.ListField(child=serializers.IntegerField(), required=False)
    semesters_label = serializers.CharField(allow_blank=True, allow_null=True)
    quota = serializers.CharField(allow_blank=True, allow_null=True)
    total_fee = serializers.FloatField(default=0.0)
    paid_fee = serializers.FloatField(default=0.0)
    concession_fee = serializers.FloatField(default=0.0)
    balance_fee = serializers.FloatField(default=0.0)
    student_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_name = serializers.CharField(allow_blank=True, allow_null=True)
    sms_status = serializers.CharField(default='NOT_SENT')
    sms_sent_at = serializers.DateTimeField(allow_null=True, required=False)
    sms_log_id = serializers.IntegerField(allow_null=True, required=False)
    sms_response = serializers.JSONField(allow_null=True, required=False)
    message_preview = serializers.CharField(allow_blank=True, allow_null=True)


class SendFeesPendingSMSItemSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(required=True)
    amount = serializers.FloatField(required=False, allow_null=True)


class SendFeesPendingSMSRequestSerializer(serializers.Serializer):
    academic_year = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    students = serializers.ListField(
        child=SendFeesPendingSMSItemSerializer(),
        required=False,
        allow_empty=True
    )
    recipient_type = serializers.ChoiceField(
        choices=['PARENT', 'STUDENT', 'BOTH'],
        default='PARENT',
        required=False
    )
    force = serializers.BooleanField(default=False, required=False)

    def validate(self, data):
        student_ids = data.get('student_ids') or []
        students = data.get('students') or []
        if not student_ids and not students:
            raise serializers.ValidationError("Either student_ids or students list must be provided.")
        return data


class MarksStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    student_name = serializers.CharField(allow_blank=True, allow_null=True)
    register_number = serializers.CharField(allow_blank=True, allow_null=True)
    roll_number = serializers.CharField(allow_blank=True, allow_null=True)
    program_id = serializers.IntegerField(allow_null=True, required=False)
    program_name = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    department_id = serializers.IntegerField(allow_null=True)
    department_name = serializers.CharField(allow_blank=True, allow_null=True)
    department_code = serializers.CharField(allow_blank=True, allow_null=True)
    batch_id = serializers.IntegerField(allow_null=True)
    batch_name = serializers.CharField(allow_blank=True, allow_null=True)
    section_id = serializers.IntegerField(allow_null=True)
    section_name = serializers.CharField(allow_blank=True, allow_null=True)
    semester_id = serializers.IntegerField(allow_null=True, required=False)
    semester_name = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    exam_id = serializers.IntegerField(allow_null=True)
    exam_name = serializers.CharField(allow_blank=True, allow_null=True)
    subject_marks = serializers.ListField(child=serializers.DictField(), default=list)
    marks_part_1 = serializers.CharField(allow_blank=True, allow_null=True)
    marks_part_2 = serializers.CharField(allow_blank=True, allow_null=True)
    total_marks = serializers.CharField(allow_blank=True, allow_null=True)
    rank = serializers.IntegerField(default=1)
    student_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_mobile = serializers.CharField(allow_blank=True, allow_null=True)
    parent_name = serializers.CharField(allow_blank=True, allow_null=True)
    sms_status = serializers.CharField(default='NOT_SENT')
    sms_sent_at = serializers.DateTimeField(allow_null=True, required=False)
    sms_log_id = serializers.IntegerField(allow_null=True, required=False)
    sms_response = serializers.JSONField(allow_null=True, required=False)
    message_preview = serializers.CharField(allow_blank=True, allow_null=True)


class SendMarksSMSItemSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(required=True)
    exam_name = serializers.CharField(required=False, allow_blank=True)
    roll_no = serializers.CharField(required=False, allow_blank=True)
    subject_marks = serializers.ListField(child=serializers.DictField(), required=False)
    total_marks = serializers.CharField(required=False, allow_blank=True)
    rank = serializers.IntegerField(required=False, allow_null=True)


class SendMarksSMSRequestSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField(required=True)
    semester_id = serializers.IntegerField(required=False, allow_null=True)
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    students = serializers.ListField(
        child=SendMarksSMSItemSerializer(),
        required=False,
        allow_empty=True
    )
    recipient_type = serializers.ChoiceField(
        choices=['PARENT', 'STUDENT', 'BOTH'],
        default='PARENT',
        required=False
    )
    force = serializers.BooleanField(default=False, required=False)

    def validate(self, data):
        student_ids = data.get('student_ids') or []
        students = data.get('students') or []
        if not student_ids and not students:
            raise serializers.ValidationError("Either student_ids or students list must be provided.")
        return data

