from django.http import Http404
from django.db import IntegrityError, models
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend

from common.pagination import CustomPageNumberPagination
from .models import AssetCategory, Asset
from .serializers import AssetCategorySerializer, AssetSerializer
from .permissions import AssetCategoryPermission, AssetPermission


class AssetCategoryViewSet(viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all().order_by('-created_at')
    serializer_class = AssetCategorySerializer
    permission_classes = [AssetCategoryPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'description']
    filterset_fields = ['is_active']

    def get_queryset(self):
        qs = super().get_queryset()
        is_active_param = self.request.query_params.get('is_active', None)
        if is_active_param is not None and is_active_param != '':
            val = is_active_param.lower()
            if val in ['true', '1']:
                qs = qs.filter(is_active=True)
            elif val in ['false', '0']:
                qs = qs.filter(is_active=False)
        return qs

    def handle_exception(self, exc):
        if isinstance(exc, models.ProtectedError):
            return Response({
                "code": 400,
                "message": "Cannot delete asset category because assets are associated with it."
            }, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset category not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, IntegrityError):
            return Response({
                "code": 400,
                "message": "An asset category with this name already exists.",
                "errors": {"name": ["An asset category with this name already exists."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset categories retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset category retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Asset category created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset category updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset category deleted successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch', 'post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        category = self.get_object()
        is_active = request.data.get('is_active', not category.is_active)
        if isinstance(is_active, str):
            is_active = is_active.lower() in ['true', '1']
        
        category.is_active = bool(is_active)
        category.save()

        action_msg = "activated" if category.is_active else "deactivated"
        serializer = self.get_serializer(category)
        return Response({
            "code": 200,
            "message": f"Asset category {action_msg} successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.select_related('category').all().order_by('-created_at')
    serializer_class = AssetSerializer
    permission_classes = [AssetPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset_code',
        'asset_name',
        'brand',
        'model_number',
        'serial_number',
        'vendor_name',
        'location'
    ]
    filterset_fields = ['category', 'status', 'condition']

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, IntegrityError):
            err_str = str(exc).lower()
            if 'asset_code' in err_str:
                msg = "An asset with this asset code already exists."
                err_dict = {"asset_code": [msg]}
            elif 'serial_number' in err_str:
                msg = "An asset with this serial number already exists."
                err_dict = {"serial_number": [msg]}
            else:
                msg = "Database integrity violation."
                err_dict = {}

            return Response({
                "code": 400,
                "message": msg,
                "errors": err_dict
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Assets retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Asset created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset deleted successfully."
        }, status=status.HTTP_200_OK)
