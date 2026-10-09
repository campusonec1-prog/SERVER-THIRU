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
