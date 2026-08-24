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
        
        # Resolve student name with fallback to application and form_data
        name_val = instance.user.name if instance.user else None
        app_no = ""
        photo_url = ""
        
        if instance.user:
            app = instance.user.applications.first()
            if app:
                app_no = app.application_no
                if not name_val:
                    name_val = app.candidate_name
                if app.form_data and isinstance(app.form_data, dict):
                    fd = app.form_data
                    if not name_val:
                        pd = fd.get('personal_details', {})
                        if isinstance(pd, dict):
                            name_val = pd.get('candidate_name') or pd.get('name')
                        if not name_val:
                            name_val = fd.get('candidate_name') or fd.get('name')
                    fd = app.form_data
                    photo_url = fd.get('photo', '')
                    if not photo_url:
                        # Check inside certificates list
                        certs = fd.get('certificates') or []
                        if isinstance(certs, dict) and 'certificates' in certs:
                            certs = certs['certificates']
                        if isinstance(certs, list):
                            for c in certs:
                                if c and isinstance(c, dict) and c.get('certificate_type') == 'Passport Size Photo':
                                    doc_val = c.get('document')
                                    if isinstance(doc_val, str) and doc_val.startswith('http'):
                                        photo_url = doc_val
                                    elif isinstance(doc_val, dict) and isinstance(doc_val.get('url'), str):
                                        photo_url = doc_val.get('url')
                                    break
                    if not photo_url:
                        for key, val in fd.items():
                            if isinstance(val, dict) and val.get('photo'):
                                photo_url = val.get('photo')
                                break
        ret['student_name'] = name_val or "Unknown"
        ret['student_email'] = instance.user.email if instance.user else None
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

        # ── Admission slip fields (StudentAdmissionSlip) ────────────────
        admission_slip = getattr(instance, 'admission_slip', None)
        if admission_slip:
            ret['admission_slip_id'] = admission_slip.id
            ret['aadhaar_number'] = admission_slip.aadhaar_number
            ret['emis_number'] = admission_slip.emis_number
            ret['umis_number'] = admission_slip.umis_number
            ret['qualification'] = admission_slip.qualification
            ret['community'] = admission_slip.community
            ret['marks_maths'] = admission_slip.marks_maths
            ret['marks_physics'] = admission_slip.marks_physics
            ret['marks_chemistry'] = admission_slip.marks_chemistry
            ret['marks_total'] = admission_slip.marks_total
            ret['marks_percentage'] = float(admission_slip.marks_percentage) if admission_slip.marks_percentage else None
            ret['mode_of_admission'] = admission_slip.mode_of_admission
            ret['certificates_surrendered'] = admission_slip.certificates_surrendered
            ret['recommendation_id'] = admission_slip.recommendation_id
            ret['recommendation_name'] = admission_slip.recommendation.name if admission_slip.recommendation else ''
        else:
            ret['admission_slip_id'] = None
            ret['aadhaar_number'] = ''
            ret['emis_number'] = ''
            ret['umis_number'] = ''
            ret['qualification'] = ''
            ret['community'] = ''
            ret['marks_maths'] = None
            ret['marks_physics'] = None
            ret['marks_chemistry'] = None
            ret['marks_total'] = None
            ret['marks_percentage'] = None
            ret['mode_of_admission'] = 'I Sem'
            ret['certificates_surrendered'] = {}
            ret['recommendation_id'] = None
            ret['recommendation_name'] = ''

        # ── Fees fields (StudentFees) ───────────────────────────────────
        fees_payment = getattr(instance, 'fees_payment', None)
        if fees_payment:
            ret['fees_payment_id'] = fees_payment.id
            ret['fees_paid'] = float(fees_payment.paid_amount)
            ret['fees_balance'] = float(fees_payment.balance_amount)
            ret['payment_mode'] = fees_payment.payment_mode
            ret['books_fees_total'] = float(fees_payment.books_fees_total)
            ret['books_fees_paid'] = float(fees_payment.books_fees_paid)
            ret['due_date'] = fees_payment.due_date.isoformat() if fees_payment.due_date else None
            ret['remarks'] = fees_payment.remarks
        else:
            ret['fees_payment_id'] = None
            ret['fees_paid'] = 0.0
            ret['fees_balance'] = total_fees
            ret['payment_mode'] = 'Cash'
            ret['books_fees_total'] = 0.0
            ret['books_fees_paid'] = 0.0
            ret['due_date'] = None
            ret['remarks'] = ''

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

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        student = instance.student
        if student:
            ret['student_roll'] = student.roll_number
            ret['student_register'] = student.register_number
            if student.user:
                ret['student_name'] = student.user.name
            else:
                ret['student_name'] = "Unknown"
                
            ret['department_id'] = student.department.id if student.department else None
            ret['department_name'] = student.department.department_name if student.department else ""
            
            ret['batch_id'] = student.batch.id if student.batch else None
            ret['batch_name'] = student.batch.batch if student.batch else ""
            
            ret['section_id'] = student.section.id if student.section else None
            sec_str = ""
            if student.section:
                if isinstance(student.section.sections, list):
                    sec_str = ", ".join(student.section.sections)
                else:
                    sec_str = str(student.section.sections)
            ret['section_name'] = sec_str
            
        exam = instance.exam
        if exam:
            ret['exam_name'] = exam.exam_name
            
        subject = instance.subject
        if subject:
            ret['subject_name'] = subject.subject_name
            ret['subject_code'] = subject.subject_code
            ret['semester_id'] = subject.semester.id if subject.semester else None
            
        return ret

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


from .models import StudentFees, StudentAdmissionSlip

class StudentAdmissionSlipSerializer(serializers.ModelSerializer):
    student_id = serializers.PrimaryKeyRelatedField(
        source='student',
        queryset=Student.objects.all(),
        error_messages={'does_not_exist': 'Student does not exist.'}
    )
    recommendation_id = serializers.PrimaryKeyRelatedField(
        source='recommendation',
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
        error_messages={'does_not_exist': 'User does not exist.'}
    )

    class Meta:
        model = StudentAdmissionSlip
        fields = [
            'id', 'student_id',
            'aadhaar_number', 'emis_number', 'umis_number',
            'qualification', 'community',
            'marks_maths', 'marks_physics', 'marks_chemistry', 'marks_total', 'marks_percentage',
            'mode_of_admission', 'certificates_surrendered', 'recommendation_id',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def validate(self, attrs):
        student = attrs.get('student')
        if not student and self.instance:
            student = self.instance.student

        if student:
            is_pg = (student.department.program.program_level == 'PG') if (student.department and student.department.program) else False
            
            emis = attrs.get('emis_number')
            if emis is None and self.instance:
                emis = self.instance.emis_number
            
            umis = attrs.get('umis_number')
            if umis is None and self.instance:
                umis = self.instance.umis_number

            if not emis or str(emis).strip() == '':
                raise serializers.ValidationError({"emis_number": "EMIS Number is required."})

            if is_pg:
                if not umis or str(umis).strip() == '':
                    raise serializers.ValidationError({"umis_number": "UMIS Number is required."})

        return attrs

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)


class StudentFeesSerializer(serializers.ModelSerializer):
    student_id = serializers.PrimaryKeyRelatedField(
        source='student',
        queryset=Student.objects.all(),
        error_messages={'does_not_exist': 'Student does not exist.'}
    )

    class Meta:
        model = StudentFees
        fields = [
            'id', 'student_id',
            'total_fees', 'paid_amount', 'balance_amount', 'payment_mode',
            'books_fees_total', 'books_fees_paid', 'due_date', 'remarks',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_default_error_messages(self.fields)
