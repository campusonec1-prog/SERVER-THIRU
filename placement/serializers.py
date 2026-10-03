import re
from rest_framework import serializers
from common.serializers import TrackingModelSerializerMixin
from institution.models import Department, Batch
from .models import (
    PlacementCompany,
    PlacementDrive,
    PlacementDriveEligibility,
    StudentPlacementTracking,
    IndustryChoices,
    DriveTypeChoices,
    DriveStatusChoices,
    AttendanceStatusChoices,
    PlacementOutcomeChoices
)


class PlacementCompanyBriefSerializer(serializers.ModelSerializer):
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)

    class Meta:
        model = PlacementCompany
        fields = [
            'id',
            'company_name',
            'industry',
            'industry_display',
            'company_website',
            'city',
            'state',
            'is_active',
        ]


class PlacementCompanySerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)

    class Meta:
        model = PlacementCompany
        fields = [
            'id',
            'company_name',
            'industry',
            'industry_display',
            'company_website',
            'description',
            'contact_person_name',
            'contact_email',
            'contact_phone_number',
            'address',
            'city',
            'state',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'industry_display']
        extra_kwargs = {
            'contact_person_name': {'required': False, 'allow_null': True, 'allow_blank': True},
            'contact_email': {'required': False, 'allow_null': True, 'allow_blank': True},
            'contact_phone_number': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def validate_company_name(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Company name is required.")
        return val

    def validate_contact_phone_number(self, value):
        if not value:
            return value
        val = value.strip()
        if not val:
            return ""
        cleaned = re.sub(r'[\s\-\(\)\+]', '', val)
        if not cleaned.isdigit() or len(cleaned) < 7 or len(cleaned) > 15:
            raise serializers.ValidationError("Please provide a valid contact phone number (7-15 digits).")
        return val

    def validate_contact_email(self, value):
        if not value:
            return value
        return value.strip().lower()

    def validate_company_website(self, value):
        if value:
            val = value.strip()
            if val and not (val.startswith('http://') or val.startswith('https://')):
                val = f"https://{val}"
            return val
        return value


class PlacementDriveSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    company_details = PlacementCompanyBriefSerializer(source='company', read_only=True)
    drive_type_display = serializers.CharField(source='get_drive_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PlacementDrive
        fields = [
            'id',
            'company',
            'company_details',
            'job_role',
            'drive_type',
            'drive_type_display',
            'job_description',
            'location',
            'ctc',
            'no_of_rounds',
            'rounds',
            'application_start_date',
            'application_end_date',
            'drive_date',
            'document_url',
            'document_name',
            'status',
            'status_display',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
            'drive_type_display',
            'status_display',
            'company_details'
        ]

    def validate(self, attrs):
        start_date = attrs.get('application_start_date') or (self.instance.application_start_date if self.instance else None)
        end_date = attrs.get('application_end_date') or (self.instance.application_end_date if self.instance else None)
        drive_date = attrs.get('drive_date') or (self.instance.drive_date if self.instance else None)

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({
                "application_end_date": "Application end date cannot be earlier than application start date."
            })

        if drive_date and start_date and drive_date < start_date:
            raise serializers.ValidationError({
                "drive_date": "Drive date cannot be earlier than application start date."
            })

        # Process rounds JSON
        rounds_val = attrs.get('rounds')
        if rounds_val is not None:
            if isinstance(rounds_val, str):
                import json
                try:
                    rounds_val = json.loads(rounds_val)
                    attrs['rounds'] = rounds_val
                except Exception:
                    pass
            if isinstance(rounds_val, list):
                cleaned_rounds = [
                    r.strip() if isinstance(r, str) else r
                    for r in rounds_val
                    if r is not None and (not isinstance(r, str) or r.strip())
                ]
                attrs['rounds'] = cleaned_rounds
                if 'no_of_rounds' not in attrs or attrs.get('no_of_rounds') is None:
                    attrs['no_of_rounds'] = len(cleaned_rounds)

        return attrs


class PlacementDriveEligibilitySerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    drive_details = PlacementDriveSerializer(source='drive', read_only=True)
    department_details = serializers.SerializerMethodField(read_only=True)
    batch_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PlacementDriveEligibility
        fields = [
            'id',
            'drive',
            'drive_details',
            'minimum_cgpa',
            'max_backlogs',
            'departments',
            'department_details',
            'batches',
            'batch_details',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
            'drive_details',
            'department_details',
            'batch_details'
        ]

    def get_department_details(self, obj):
        return [
            {
                'id': dept.id,
                'department_name': dept.department_name,
                'department_code': dept.department_code,
                'short_name': dept.short_name,
            }
            for dept in obj.departments.all()
        ]

    def get_batch_details(self, obj):
        return [
            {
                'id': batch.id,
                'batch': batch.batch,
                'department_id': batch.department_id,
                'department_name': batch.department.department_name if batch.department else None,
            }
            for batch in obj.batches.select_related('department').all()
        ]

    def validate_minimum_cgpa(self, value):
        if value < 0 or value > 10:
            raise serializers.ValidationError("Minimum CGPA must be between 0.00 and 10.00.")
        return value

    def validate_max_backlogs(self, value):
        if value < 0:
            raise serializers.ValidationError("Max backlogs cannot be negative.")
        return value


class StudentPlacementTrackingSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    student_details = serializers.SerializerMethodField(read_only=True)
    drive_details = PlacementDriveSerializer(source='drive', read_only=True)
    attendance_status_display = serializers.CharField(source='get_attendance_status_display', read_only=True)
    final_status_display = serializers.CharField(source='get_final_status_display', read_only=True)

    class Meta:
        model = StudentPlacementTracking
        fields = [
            'id',
            'student',
            'student_details',
            'drive',
            'drive_details',
            'attendance_status',
            'attendance_status_display',
            'cleared_rounds',
            'final_status',
            'final_status_display',
            'remarks',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
            'student_details',
            'drive_details',
            'attendance_status_display',
            'final_status_display'
        ]

    def get_student_details(self, obj):
        if not obj.student:
            return None
        st = obj.student
        app = st.application
        cand = app.candidate if app else None
        name = cand.name if cand else None
        if not name and app and app.form_data:
            fd = app.form_data
            pd = fd.get('personal_details', {}) if isinstance(fd, dict) else {}
            name = pd.get('candidate_name') or pd.get('name') or (fd.get('name') if isinstance(fd, dict) else None)

        return {
            'id': st.id,
            'name': name or f"Student #{st.id}",
            'roll_number': st.roll_number,
            'register_number': st.register_number,
            'email': cand.email if cand else None,
            'department_name': st.department.department_name if st.department else None,
            'batch_name': st.batch.batch if st.batch else None,
        }

    def validate(self, attrs):
        rounds_val = attrs.get('cleared_rounds')
        if rounds_val is not None:
            if isinstance(rounds_val, str):
                import json
                try:
                    rounds_val = json.loads(rounds_val)
                    attrs['cleared_rounds'] = rounds_val
                except Exception:
                    pass
            if not isinstance(rounds_val, list):
                attrs['cleared_rounds'] = []
        return attrs

