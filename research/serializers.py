from rest_framework import serializers
from .models import FacultyResearchProject
from users.models import UserDetails
from users.serializers import UserDetailsSerializer
from institution.models import Department
from institution.serializers import DepartmentSerializer


class FacultyResearchProjectSerializer(serializers.ModelSerializer):
    principal_investigator_detail = serializers.SerializerMethodField(read_only=True)
    co_investigators_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FacultyResearchProject
        fields = [
            'id',
            'project_title',
            'project_code',
            'principal_investigator',
            'principal_investigator_detail',
            'co_investigators',
            'co_investigators_detail',
            'external_co_investigators',
            'research_area',
            'project_type',
            'funding_agency',
            'sanctioned_amount',
            'project_start_date',
            'project_end_date',
            'status',
            'description',
            'objectives',
            'outcomes',
            'site_name',
            'reference_url',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_principal_investigator_detail(self, obj):
        if not obj.principal_investigator:
            return None
        pi = obj.principal_investigator
        return {
            'id': pi.id,
            'faculty_code': pi.faculty_code,
            'name': pi.user.name if pi.user else '',
            'mail': pi.user.mail if pi.user else '',
            'designation': pi.designation,
            'qualification': pi.qualification,
            'department_name': pi.department.department_name if pi.department else ''
        }

    def get_co_investigators_detail(self, obj):
        result = []
        for co in obj.co_investigators.select_related('user', 'department').all():
            result.append({
                'id': co.id,
                'faculty_code': co.faculty_code,
                'name': co.user.name if co.user else '',
                'mail': co.user.mail if co.user else '',
                'designation': co.designation,
                'qualification': co.qualification,
                'department_name': co.department.department_name if co.department else ''
            })
        return result

    def validate_project_title(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Project title is required.")
        return value.strip()

    def validate_project_start_date(self, value):
        if not value:
            raise serializers.ValidationError("Project start date is required.")
        return value

    def validate_sanctioned_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Sanctioned amount cannot be negative.")
        return value

    def validate_status(self, value):
        valid_statuses = [choice[0] for choice in FacultyResearchProject.STATUS_CHOICES]
        if value not in valid_statuses:
            raise serializers.ValidationError("Invalid project status.")
        return value

    def validate_project_type(self, value):
        valid_types = [choice[0] for choice in FacultyResearchProject.PROJECT_TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError("Invalid project type.")
        return value

    def validate(self, attrs):
        # 1. Project Title check
        title = attrs.get('project_title') or (self.instance.project_title if self.instance else None)
        if not title or not str(title).strip():
            raise serializers.ValidationError({"project_title": "Project title is required."})

        # 2. Principal Investigator check
        pi = attrs.get('principal_investigator') or (self.instance.principal_investigator if self.instance else None)
        if not pi:
            raise serializers.ValidationError({"principal_investigator": "Principal investigator not found."})

        # 3. Dates validation
        start_date = attrs.get('project_start_date') or (self.instance.project_start_date if self.instance else None)
        end_date = attrs.get('project_end_date') if 'project_end_date' in attrs else (self.instance.project_end_date if self.instance else None)
        
        if not start_date:
            raise serializers.ValidationError({"project_start_date": "Project start date is required."})

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"project_end_date": "Project end date cannot be before the start date."})

        # 4. Sanctioned Amount validation
        sanctioned = attrs.get('sanctioned_amount') if 'sanctioned_amount' in attrs else (self.instance.sanctioned_amount if self.instance else None)
        if sanctioned is not None and sanctioned < 0:
            raise serializers.ValidationError({"sanctioned_amount": "Sanctioned amount cannot be negative."})

        # 5. Funding agency requirement check
        project_type = attrs.get('project_type') or (self.instance.project_type if self.instance else None)
        funding_agency = attrs.get('funding_agency') if 'funding_agency' in attrs else (self.instance.funding_agency if self.instance else None)

        if project_type in ['Funded', 'Industry Sponsored', 'Consultancy']:
            if not funding_agency or not str(funding_agency).strip():
                raise serializers.ValidationError({"funding_agency": f"Funding agency is required for {project_type.lower()} projects."})

        # 6. Co-investigators validation (PI cannot be co-investigator)
        co_investigators = attrs.get('co_investigators')
        if co_investigators is not None:
            co_ids = [co.id if hasattr(co, 'id') else co for co in co_investigators]
            pi_id = pi.id if hasattr(pi, 'id') else pi
            if pi_id in co_ids:
                raise serializers.ValidationError({"co_investigators": "Principal investigator cannot also be a co-investigator."})

        # 7. Status transition check (Cancelled project cannot be directly updated to Completed)
        if self.instance and self.instance.status == 'Cancelled':
            new_status = attrs.get('status', self.instance.status)
            if new_status == 'Completed':
                raise serializers.ValidationError({"status": "Cancelled projects cannot be changed to completed."})

        return attrs
