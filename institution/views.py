from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import Program, Department, AcademicYear, Batch, Regulation, Semester, Section, CollegeHeader, ExamType, Exam, Quota, FeesStructure
from .serializers import ProgramSerializer, DepartmentSerializer, AcademicYearSerializer, BatchSerializer, RegulationSerializer, SemesterSerializer, SectionSerializer, CollegeHeaderSerializer, ExamTypeSerializer, ExamSerializer, QuotaSerializer, FeesStructureSerializer
from users.permissions import IsAdminUser
from .permissions import (
    ProgramPermission, DepartmentPermission, AcademicYearPermission,
    BatchPermission, RegulationPermission, SemesterPermission,
    SectionPermission, CollegeHeaderPermission, ExamTypePermission,
    ExamPermission, QuotaPermission, FeesStructurePermission
)


# ─── Shared Mixin ────────────────────────────────────────────────────────────

class AdminWriteMixin:
    """Provides standard exception handling and user auditing for creation and updates."""

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": f"{self.model_label} not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)


# ─── Program ─────────────────────────────────────────────────────────────────

class ProgramViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Program.objects.all().order_by('id')
    serializer_class = ProgramSerializer
    permission_classes = [ProgramPermission]
    model_label = "Program"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Programs listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Program retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Program created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Program updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Program deleted successfully"}, status=status.HTTP_200_OK)


# ─── Department ──────────────────────────────────────────────────────────────

class DepartmentViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all().order_by('id')
    serializer_class = DepartmentSerializer
    permission_classes = [DepartmentPermission]
    model_label = "Department"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Departments listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Department retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Department created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Department updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Department deleted successfully"}, status=status.HTTP_200_OK)


# ─── Academic Year ───────────────────────────────────────────────────────────

class AcademicYearViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = AcademicYear.objects.all().order_by('id')
    serializer_class = AcademicYearSerializer
    permission_classes = [AcademicYearPermission]
    model_label = "Academic year"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Academic years listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Academic year retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Academic year created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Academic year updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Academic year deleted successfully"}, status=status.HTTP_200_OK)


# ─── Batch ───────────────────────────────────────────────────────────────────

class BatchViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Batch.objects.all().order_by('id')
    serializer_class = BatchSerializer
    permission_classes = [BatchPermission]
    model_label = "Batch"

    def get_queryset(self):
        # Filtering (department_id, is_active, etc.) is handled automatically
        # by the global DynamicFilterBackend — no manual filtering needed here.
        return super().get_queryset()


    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Batches listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Batch retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Batch created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Batch updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Batch deleted successfully"}, status=status.HTTP_200_OK)


# ─── Regulation ───────────────────────────────────────────────────

class RegulationViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Regulation.objects.all().order_by('id')
    serializer_class = RegulationSerializer
    permission_classes = [RegulationPermission]
    model_label = "Regulation"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Regulations listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Regulation retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Regulation created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Regulation updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Regulation deleted successfully"}, status=status.HTTP_200_OK)


# ─── Semester ───────────────────────────────────────────────────

class SemesterViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Semester.objects.all().order_by('id')
    serializer_class = SemesterSerializer
    permission_classes = [SemesterPermission]
    model_label = "Semester"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Semesters listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Semester retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Semester created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Semester updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Semester deleted successfully"}, status=status.HTTP_200_OK)


# ─── Section ───────────────────────────────────────────────────────

class SectionViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Section.objects.all().order_by('id')
    serializer_class = SectionSerializer
    permission_classes = [SectionPermission]
    model_label = "Section"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Sections listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Section retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        from django.db import transaction
        data = request.data
        department_id = data.get('department_id')
        sections_data = data.get('sections')

        if not department_id:
            return Response({"code": 400, "message": "department_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dept = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return Response({"code": 404, "message": "Department not found."}, status=status.HTTP_404_NOT_FOUND)

        if not isinstance(sections_data, list):
            sections_list = [sections_data] if sections_data else []
        else:
            sections_list = sections_data

        sections_list = [str(s).strip().upper() for s in sections_list if str(s).strip()]

        if not sections_list:
            return Response({"code": 400, "message": "At least one section letter must be provided."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user if request.user and request.user.is_authenticated else None

        with transaction.atomic():
            existing_sections = Section.objects.filter(department=dept)
            existing_names = {s.sections.upper(): s for s in existing_sections}

            # Delete sections no longer selected
            for name, inst in list(existing_names.items()):
                if name not in sections_list:
                    inst.delete()

            # Create new ones
            for name in sections_list:
                if name not in existing_names:
                    Section.objects.create(
                        department=dept,
                        sections=name,
                        created_by=user,
                        updated_by=user
                    )

            updated_sections = Section.objects.filter(department=dept).order_by('sections')
            serializer = self.get_serializer(updated_sections, many=True)

        return Response({
            "code": 201,
            "message": "Sections created successfully",
            "data": serializer.data[0] if serializer.data else None
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        from django.db import transaction
        data = request.data
        department_id = data.get('department_id')
        sections_data = data.get('sections')

        if not department_id:
            instance = self.get_object()
            dept = instance.department
        else:
            try:
                dept = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return Response({"code": 404, "message": "Department not found."}, status=status.HTTP_404_NOT_FOUND)

        if not isinstance(sections_data, list):
            sections_list = [sections_data] if sections_data else []
        else:
            sections_list = sections_data

        sections_list = [str(s).strip().upper() for s in sections_list if str(s).strip()]

        if not sections_list:
            return Response({"code": 400, "message": "At least one section letter must be provided."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user if request.user and request.user.is_authenticated else None

        with transaction.atomic():
            existing_sections = Section.objects.filter(department=dept)
            existing_names = {s.sections.upper(): s for s in existing_sections}

            # Delete sections no longer selected
            for name, inst in list(existing_names.items()):
                if name not in sections_list:
                    inst.delete()

            # Create new ones
            for name in sections_list:
                if name not in existing_names:
                    Section.objects.create(
                        department=dept,
                        sections=name,
                        created_by=user,
                        updated_by=user
                    )

            updated_sections = Section.objects.filter(department=dept).order_by('sections')
            serializer = self.get_serializer(updated_sections, many=True)

        return Response({
            "code": 200,
            "message": "Sections updated successfully",
            "data": serializer.data[0] if serializer.data else None
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        Section.objects.filter(department=instance.department).delete()
        return Response({"code": 200, "message": "Sections deleted successfully"}, status=status.HTTP_200_OK)


# ─── College Header ────────────────────────────────────────────────

class CollegeHeaderViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = CollegeHeader.objects.all().order_by('id')
    serializer_class = CollegeHeaderSerializer
    permission_classes = [CollegeHeaderPermission]
    model_label = "College Header"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "College Headers listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "College Header retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "College Header created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "College Header updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "College Header deleted successfully"}, status=status.HTTP_200_OK)


# ─── Exam Type ─────────────────────────────────────────────────────

class ExamTypeViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = ExamType.objects.all().order_by('id')
    serializer_class = ExamTypeSerializer
    permission_classes = [ExamTypePermission]
    model_label = "Exam Type"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam Types listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam Type retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Exam Type created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam Type updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam Type deleted successfully"}, status=status.HTTP_200_OK)


# ─── Exam ──────────────────────────────────────────────────────────

class ExamViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Exam.objects.all().order_by('id')
    serializer_class = ExamSerializer
    permission_classes = [ExamPermission]
    model_label = "Exam"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exams listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Exam created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Exam deleted successfully"}, status=status.HTTP_200_OK)


# ─── Quota ──────────────────────────────────────────────────────────

class QuotaViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Quota.objects.all().order_by('id')
    serializer_class = QuotaSerializer
    permission_classes = [QuotaPermission]
    model_label = "Quota"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Quotas listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Quota retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Quota created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Quota updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Quota deleted successfully"}, status=status.HTTP_200_OK)


# ─── Fees Structure ──────────────────────────────────────────

class FeesStructureViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FeesStructure.objects.all().order_by('id')
    serializer_class = FeesStructureSerializer
    permission_classes = [FeesStructurePermission]
    model_label = "Fees Structure"

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('department_id'):
            qs = qs.filter(department_id=params['department_id'])
        if params.get('batch_id'):
            qs = qs.filter(batch_id=params['batch_id'])
        if params.get('quota_id'):
            qs = qs.filter(quota_id=params['quota_id'])
        return qs

    def list(self, request, *args, **kwargs):
        # Support bypassing pagination when pagination=false is passed
        pagination = request.query_params.get('pagination', 'true').lower()
        if pagination == 'false':
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response({"code": 200, "message": "Fees structures listed successfully", "data": serializer.data}, status=status.HTTP_200_OK)

        # Retrieve filtered queryset
        queryset = self.filter_queryset(self.get_queryset())

        # Group by unique department and batch combinations to define batch pages
        distinct_batches = queryset.values('department_id', 'batch_id').distinct().order_by('department_id', 'batch_id')

        # Paginate the unique batch pairs
        page = self.paginate_queryset(distinct_batches)
        if page is not None:
            from django.db.models import Q
            filter_q = Q()
            for item in page:
                filter_q |= Q(department_id=item['department_id'], batch_id=item['batch_id'])

            if filter_q:
                page_queryset = queryset.filter(filter_q).order_by('department_id', 'batch_id', 'quota_id')
            else:
                page_queryset = queryset.none()

            serializer = self.get_serializer(page_queryset, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({"code": 200, "message": "Fees structures listed successfully", "data": paginated_response.data}, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({"code": 200, "message": "Fees structures listed successfully", "data": serializer.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Fees structure retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        data = request.data

        # ── Structured bulk upsert: { department_id, fees: [...] }
        if isinstance(data, dict) and 'fees' in data and isinstance(data['fees'], list):
            department_id    = data.get('department_id')
            fees_list        = data['fees']

            user        = request.user if request.user and request.user.is_authenticated else None
            results     = []
            created_cnt = 0
            updated_cnt = 0

            for entry in fees_list:
                # Flatten: merge shared top-level ids into each fee entry
                item = {
                    'department_id':    department_id,
                    'batch_id':         entry.get('batch_id'),
                    'quota_id':         entry.get('quota_id'),
                    'fees':             entry.get('fees'),
                }

                try:
                    instance = FeesStructure.objects.get(
                        department_id=department_id,
                        batch_id=entry.get('batch_id'),
                        quota_id=entry.get('quota_id'),
                    )
                    # Record exists → update fees
                    serializer = self.get_serializer(instance, data=item)
                    serializer.is_valid(raise_exception=True)
                    serializer.save(updated_by=user)
                    updated_cnt += 1

                except FeesStructure.DoesNotExist:
                    # Record does not exist → create
                    serializer = self.get_serializer(data=item)
                    serializer.is_valid(raise_exception=True)
                    serializer.save(created_by=user, updated_by=user)
                    created_cnt += 1

                results.append(serializer.data)

            parts = []
            if created_cnt:
                parts.append(f"{created_cnt} created")
            if updated_cnt:
                parts.append(f"{updated_cnt} updated")
            msg = "Fees structures saved: " + ", ".join(parts) if parts else "No changes made"

            return Response(
                {"code": 200, "message": msg, "data": results},
                status=status.HTTP_200_OK,
            )

        # ── Single object create ─────────────────────────────────────────────
        else:
            response = super().create(request, *args, **kwargs)
            return Response({"code": 201, "message": "Fees structure created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Fees structure updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Fees structure deleted successfully"}, status=status.HTTP_200_OK)





