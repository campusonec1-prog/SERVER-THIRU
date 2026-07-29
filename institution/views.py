from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import Program, Department, AcademicYear, Batch, Regulation, Semester, Section
from .serializers import ProgramSerializer, DepartmentSerializer, AcademicYearSerializer, BatchSerializer, RegulationSerializer, SemesterSerializer, SectionSerializer
from users.permissions import IsAdminUser


# ─── Shared Mixin ────────────────────────────────────────────────────────────

class AdminWriteMixin:
    """Restrict create/update/delete to Admin users; list/retrieve are public."""

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return []

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
    model_label = "Batch"

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
    model_label = "Section"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Sections listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Section retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Section created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Section updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Section deleted successfully"}, status=status.HTTP_200_OK)

