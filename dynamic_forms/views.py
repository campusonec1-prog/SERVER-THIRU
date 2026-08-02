from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import FormModule, FormField
from .serializers import FormModuleSerializer, FormFieldSerializer
from users.permissions import IsAdminUser


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


class FormModuleViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FormModule.objects.all().order_by('display_order', 'id')
    serializer_class = FormModuleSerializer
    model_label = "Form Module"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Modules listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Form Module created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module deleted successfully"}, status=status.HTTP_200_OK)


class FormFieldViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FormField.objects.all().order_by('display_order', 'id')
    serializer_class = FormFieldSerializer
    model_label = "Form Field"

    def list(self, request, *args, **kwargs):
        # Allow filtering by form_module_id
        module_id = request.query_params.get('form_module_id')
        if module_id:
            self.queryset = self.queryset.filter(form_module_id=module_id)
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Fields listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Form Field created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field deleted successfully"}, status=status.HTTP_200_OK)
