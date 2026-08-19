from rest_framework import serializers
from .models import StudentStatus, Student
from institution.models import Department, Section, Batch, Quota
from users.models import User
from dynamic_forms.models import ApplicationUser


def apply_default_error_messages(fields):
    for field_name, field in fields.items():
        friendly_name = field_name.replace('_', ' ').capitalize()
        field.error_messages['required'] = f"{friendly_name} is required."
        field.error_messages['blank'] = f"{friendly_name} cannot be empty."
        field.error_messages['null'] = f"{friendly_name} cannot be null."


class StudentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentStatus
        fields = ['id', 'status_name', 'is_active', 'created_at', 'updated_at', 'created_by', 'updated_by']
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'status_name': {
                'required': True,
                'error_messages': {'unique': 'This student status already exists.'}
            },
            'is_active': {'required': False, 'default': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_status_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Status name cannot be empty.")
        qs = StudentStatus.objects.filter(status_name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This student status already exists.")
        return value.strip()


class StudentSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        error_messages={'does_not_exist': 'Department does not exist.'}
    )
    section_id = serializers.PrimaryKeyRelatedField(
        source='section',
        queryset=Section.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Section does not exist.'}
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source='batch',
        queryset=Batch.objects.all(),
        error_messages={'does_not_exist': 'Batch does not exist.'}
    )
    user_id = serializers.PrimaryKeyRelatedField(
        source='user',
        queryset=ApplicationUser.objects.all(),
        error_messages={'does_not_exist': 'Application user does not exist.'}
    )
    status_id = serializers.PrimaryKeyRelatedField(
        source='status',
        queryset=StudentStatus.objects.all(),
        error_messages={'does_not_exist': 'Student status does not exist.'}
    )
    quota_id = serializers.PrimaryKeyRelatedField(
        source='quota',
        queryset=Quota.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'Quota does not exist.'}
    )

    class Meta:
        model = Student
        fields = [
            'id', 'roll_number', 'register_number', 'department_id',
            'section_id', 'batch_id', 'user_id', 'lab_batch', 'status_id',
            'quota_id', 'is_hostler', 'is_day_scholar', 'is_bus', 'bus_from', 'bus_to',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
        extra_kwargs = {
            'roll_number': {
                'required': False,
                'allow_null': True,
                'allow_blank': True,
                'error_messages': {'unique': 'This roll number already exists.'}
            },
            'register_number': {
                'required': False,
                'allow_null': True,
                'allow_blank': True,
                'error_messages': {'unique': 'This register number already exists.'}
            },
            'department_id': {'required': True},
            'batch_id': {'required': True},
            'user_id': {
                'required': True,
                'error_messages': {'unique': 'This user is already assigned to a student.'}
            },
            'status_id': {'required': True},
            'lab_batch': {'required': False, 'allow_null': True, 'allow_blank': True},
            'is_hostler': {'required': False},
            'is_day_scholar': {'required': False},
            'is_bus': {'required': False},
            'bus_from': {'required': False, 'allow_null': True, 'allow_blank': True},
            'bus_to': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)

    def validate_user_id(self, value):
        if not value:
            raise serializers.ValidationError("Application user is required.")
        qs = Student.objects.filter(user=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This user is already assigned to a student.")
        return value

    def validate_roll_number(self, value):
        if value is None or not str(value).strip():
            return None
        val_str = str(value).strip()
        qs = Student.objects.filter(roll_number__iexact=val_str)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This roll number already exists.")
        return val_str

    def validate_register_number(self, value):
        if value is None or not str(value).strip():
            return None
        val_str = str(value).strip()
        qs = Student.objects.filter(register_number__iexact=val_str)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This register number already exists.")
        return val_str

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['student_name'] = instance.user.name if instance.user else None
        ret['student_email'] = instance.user.email if instance.user else None
        
        photo_url = ""
        app_no = ""
        if instance.user:
            # Safely query the candidate's first application to access form_data photo and application_no
            app = instance.user.applications.first()
            if app:
                app_no = app.application_no
                if app.form_data and isinstance(app.form_data, dict):
                    fd = app.form_data
                    photo_url = fd.get('photo', '')
                    if not photo_url:
                        for key, val in fd.items():
                            if isinstance(val, dict) and val.get('photo'):
                                photo_url = val.get('photo')
                                break
        ret['student_photo'] = photo_url
        ret['application_no'] = app_no

        ret['department_name'] = instance.department.department_name if instance.department else None
        ret['program_name'] = instance.department.program.program_name if (instance.department and instance.department.program) else None
        ret['batch_name'] = instance.batch.batch if instance.batch else None
        
        sec_str = ""
        if instance.section:
            if isinstance(instance.section.sections, list):
                sec_str = ", ".join(instance.section.sections)
            else:
                sec_str = str(instance.section.sections)
        ret['section_name'] = sec_str
        
        ret['status_name'] = instance.status.status_name if instance.status else None
        ret['quota_name'] = instance.quota.quota_name if instance.quota else None

        # Dynamically fetch matching FeesStructure based on department, batch, and quota
        from institution.models import FeesStructure
        total_fees = 0.0
        if instance.department and instance.batch and instance.quota:
            fs = FeesStructure.objects.filter(
                department=instance.department,
                batch=instance.batch,
                quota=instance.quota
            ).first()
            if fs:
                total_fees = float(fs.fees)
        ret['total_fees'] = total_fees

        # Populate StudentFees details if created
        fees_payment = getattr(instance, 'fees_payment', None)
        if fees_payment:
            ret['fees_payment_id'] = fees_payment.id
            ret['fees_paid'] = float(fees_payment.paid_amount)
            ret['fees_balance'] = float(fees_payment.balance_amount)
            ret['payment_mode'] = fees_payment.payment_mode
            ret['aadhaar_number'] = fees_payment.aadhaar_number
            ret['emis_number'] = fees_payment.emis_number
            ret['umis_number'] = fees_payment.umis_number
            ret['remarks'] = fees_payment.remarks
            ret['certificates_surrendered'] = fees_payment.certificates_surrendered
            ret['qualification'] = fees_payment.qualification
            ret['community'] = fees_payment.community
            ret['marks_maths'] = fees_payment.marks_maths
            ret['marks_physics'] = fees_payment.marks_physics
            ret['marks_chemistry'] = fees_payment.marks_chemistry
            ret['marks_total'] = fees_payment.marks_total
            ret['marks_percentage'] = float(fees_payment.marks_percentage) if fees_payment.marks_percentage else None
            ret['mode_of_admission'] = fees_payment.mode_of_admission
            ret['books_fees_total'] = float(fees_payment.books_fees_total)
            ret['books_fees_paid'] = float(fees_payment.books_fees_paid)
            ret['due_date'] = fees_payment.due_date.isoformat() if fees_payment.due_date else None
            ret['recommendation_id'] = fees_payment.recommendation_id
            ret['recommendation_name'] = fees_payment.recommendation.name if fees_payment.recommendation else ''
        else:
            ret['fees_payment_id'] = None
            ret['fees_paid'] = 0.0
            ret['fees_balance'] = total_fees
            ret['payment_mode'] = 'Cash'
            ret['aadhaar_number'] = ''
            ret['emis_number'] = ''
            ret['umis_number'] = ''
            ret['remarks'] = ''
            ret['certificates_surrendered'] = {}
            ret['qualification'] = ''
            ret['community'] = ''
            ret['marks_maths'] = None
            ret['marks_physics'] = None
            ret['marks_chemistry'] = None
            ret['marks_total'] = None
            ret['marks_percentage'] = None
            ret['mode_of_admission'] = 'I Sem'
            ret['books_fees_total'] = 0.0
            ret['books_fees_paid'] = 0.0
            ret['due_date'] = None
            ret['recommendation_id'] = None
            ret['recommendation_name'] = ''

        return ret


from .models import Marks
from institution.models import Exam
from subject.models import Subject

class MarksSerializer(serializers.ModelSerializer):
    student_id = serializers.PrimaryKeyRelatedField(
        source='student',
        queryset=Student.objects.all(),
        error_messages={'does_not_exist': 'Student does not exist.'}
    )
    exam_id = serializers.PrimaryKeyRelatedField(
        source='exam',
        queryset=Exam.objects.all(),
        error_messages={'does_not_exist': 'Exam does not exist.'}
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject',
        queryset=Subject.objects.all(),
        error_messages={'does_not_exist': 'Subject does not exist.'}
    )

    class Meta:
        model = Marks
        fields = [
            'id', 'student_id', 'exam_id', 'subject_id', 'marks_obtained',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)


from .models import CounsellingReport
from institution.models import Semester

class CounsellingReportSerializer(serializers.ModelSerializer):
    student_id = serializers.PrimaryKeyRelatedField(
        source='student',
        queryset=Student.objects.all(),
        error_messages={'does_not_exist': 'Student does not exist.'}
    )
    semester_id = serializers.PrimaryKeyRelatedField(
        source='semester',
        queryset=Semester.objects.all(),
        error_messages={'does_not_exist': 'Semester does not exist.'}
    )

    class Meta:
        model = CounsellingReport
        fields = [
            'id', 'student_id', 'semester_id', 'report_date', 'remarks',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)


from .models import StudentFees

class StudentFeesSerializer(serializers.ModelSerializer):
    student_id = serializers.PrimaryKeyRelatedField(
        source='student',
        queryset=Student.objects.all(),
        error_messages={'does_not_exist': 'Student does not exist.'}
    )

    class Meta:
        model = StudentFees
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)




