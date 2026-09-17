from django.http import Http404
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from common.pagination import CustomPageNumberPagination
from .models import AssetCategory, Asset, AssetAllocation, AssetStatus, AssetTransfer
from .serializers import AssetCategorySerializer, AssetSerializer, AssetAllocationSerializer, AssetTransferSerializer
from .permissions import AssetCategoryPermission, AssetPermission, AssetAllocationPermission, AssetTransferPermission
from users.models import User
from institution.models import Department


def broadcast_custom_ws_event(event_name, data):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': 'AssetAllocation',
                        'event': event_name,
                        'data': data
                    }
                }
            )
        except Exception:
            pass


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


class AssetAllocationViewSet(viewsets.ModelViewSet):
    queryset = AssetAllocation.objects.select_related(
        'asset', 'asset__category', 'assigned_to', 'department'
    ).all().order_by('-assigned_date')
    serializer_class = AssetAllocationSerializer
    permission_classes = [AssetAllocationPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset__asset_code',
        'asset__asset_name',
        'asset__serial_number',
        'location',
        'asset__location',
        'assigned_to__name',
        'assigned_to__username',
        'department__department_name',
        'department__department_code',
    ]
    filterset_fields = ['department', 'asset', 'assigned_to']

    def get_queryset(self):
        qs = super().get_queryset()
        is_current_param = self.request.query_params.get('is_current', None)
        if is_current_param is not None and is_current_param != '' and is_current_param.lower() != 'all':
            val = is_current_param.lower()
            if val in ['true', '1']:
                qs = qs.filter(is_current=True)
            elif val in ['false', '0']:
                qs = qs.filter(is_current=False)
        return qs

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset allocation record not found."
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
                "message": "Asset is already assigned.",
                "errors": {
                    "asset": ["This asset already has an active allocation."]
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset allocations retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset allocation retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='assign')
    def assign_asset(self, request):
        asset_id = request.data.get('asset')
        if not asset_id:
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"asset": ["Asset is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # 1. Status validation
        if asset.status != AssetStatus.AVAILABLE:
            status_labels = {
                AssetStatus.ASSIGNED: "assigned",
                AssetStatus.MAINTENANCE: "under maintenance",
                AssetStatus.DAMAGED: "damaged",
                AssetStatus.LOST: "lost",
                AssetStatus.DISPOSED: "disposed",
            }
            label = status_labels.get(asset.status, asset.get_status_display().lower())
            return Response({
                "code": 400,
                "message": f"Asset cannot be assigned because it is currently {label}."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Check active allocation
        if AssetAllocation.objects.filter(asset=asset, is_current=True).exists():
            return Response({
                "code": 400,
                "message": "Asset is already assigned.",
                "errors": {
                    "asset": ["This asset already has an active allocation."]
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            allocation = serializer.save(is_current=True)
            asset.status = AssetStatus.ASSIGNED
            location_input = request.data.get('location')
            if location_input is not None:
                asset.location = str(location_input).strip() or None
                asset.save(update_fields=['status', 'location', 'updated_at'])
            else:
                asset.save(update_fields=['status', 'updated_at'])

        broadcast_custom_ws_event('asset_assigned', serializer.data)

        return Response({
            "code": 201,
            "message": "Asset assigned successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post', 'patch'], url_path='return')
    def return_asset(self, request):
        allocation_id = request.data.get('allocation_id') or request.data.get('id')
        asset_id = request.data.get('asset_id') or request.data.get('asset')

        allocation = None
        if allocation_id:
            allocation = AssetAllocation.objects.filter(pk=allocation_id, is_current=True).first()
        elif asset_id:
            allocation = AssetAllocation.objects.filter(asset_id=asset_id, is_current=True).first()

        if not allocation:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            allocation.is_current = False
            allocation.returned_date = timezone.now()
            allocation.save(update_fields=['is_current', 'returned_date'])

            asset = allocation.asset
            asset.status = AssetStatus.AVAILABLE
            asset.save(update_fields=['status', 'updated_at'])

        result_serializer = self.get_serializer(allocation)
        broadcast_custom_ws_event('asset_returned', result_serializer.data)

        return Response({
            "code": 200,
            "message": "Asset returned successfully.",
            "data": result_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post', 'patch'], url_path='return-by-id')
    def return_asset_by_id(self, request, pk=None):
        allocation = AssetAllocation.objects.filter(pk=pk, is_current=True).first()
        if not allocation:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            allocation.is_current = False
            allocation.returned_date = timezone.now()
            allocation.save(update_fields=['is_current', 'returned_date'])

            asset = allocation.asset
            asset.status = AssetStatus.AVAILABLE
            asset.save(update_fields=['status', 'updated_at'])

        result_serializer = self.get_serializer(allocation)
        broadcast_custom_ws_event('asset_returned', result_serializer.data)

        return Response({
            "code": 200,
            "message": "Asset returned successfully.",
            "data": result_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='history/(?P<asset_id>\\d+)')
    def asset_history(self, request, asset_id=None):
        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        allocations = self.get_queryset().filter(asset_id=asset_id)
        page = self.paginate_queryset(allocations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Asset allocation history retrieved successfully.",
                "data": paginated_res.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(allocations, many=True)
        return Response({
            "code": 200,
            "message": "Asset allocation history retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AssetTransferViewSet(viewsets.ModelViewSet):
    queryset = AssetTransfer.objects.select_related(
        'asset', 'from_user', 'to_user', 'from_department', 'to_department'
    ).all().order_by('-transfer_date')
    serializer_class = AssetTransferSerializer
    permission_classes = [AssetTransferPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset__asset_code',
        'asset__asset_name',
        'asset__serial_number',
        'from_user__name',
        'from_user__username',
        'to_user__name',
        'to_user__username',
        'from_department__department_name',
        'from_department__department_code',
        'to_department__department_name',
        'to_department__department_code',
        'from_location',
        'to_location'
    ]
    filterset_fields = ['asset', 'from_department', 'to_department', 'from_user', 'to_user']

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset transfer record not found."
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

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset transfers retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset transfer retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer_asset(self, request):
        asset_id = request.data.get('asset')
        if not asset_id:
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"asset": ["Asset is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # 1. Validate asset status
        if asset.status == AssetStatus.AVAILABLE:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is currently available."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.MAINTENANCE:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is under maintenance."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.DAMAGED:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is damaged."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.LOST:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is lost."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.DISPOSED:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it has been disposed."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status != AssetStatus.ASSIGNED:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Find active allocation
        active_alloc = AssetAllocation.objects.filter(asset=asset, is_current=True).first()
        if not active_alloc:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        from_user = active_alloc.assigned_to
        from_department = active_alloc.department
        from_location = asset.location

        to_user_id = request.data.get('to_user') or None
        to_dept_id = request.data.get('to_department') or None
        to_location = request.data.get('to_location') or None
        remarks = request.data.get('remarks') or None

        if not to_user_id and not to_dept_id and not to_location:
            return Response({
                "code": 400,
                "message": "Destination user, department, or location is required.",
                "errors": {"to_user": ["Must select a destination User or Department or Location."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Check if destination is different from current source assignment
        curr_user_id = from_user.id if from_user else None
        curr_dept_id = from_department.id if from_department else None
        curr_loc = (from_location or '').strip()
        new_loc = (to_location or '').strip()

        target_user_id = int(to_user_id) if to_user_id else None
        target_dept_id = int(to_dept_id) if to_dept_id else None

        if target_user_id == curr_user_id and target_dept_id == curr_dept_id and (not new_loc or new_loc == curr_loc):
            return Response({
                "code": 400,
                "message": "Destination must be different from the current assignment.",
                "errors": {"to_user": ["Destination must be different from the current assignment."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()

        with transaction.atomic():
            transfer = AssetTransfer.objects.create(
                asset=asset,
                from_user=from_user,
                to_user_id=target_user_id,
                from_department=from_department,
                to_department_id=target_dept_id,
                from_location=from_location,
                to_location=new_loc or None,
                remarks=remarks.strip() if remarks else None,
            )

            active_alloc.is_current = False
            active_alloc.returned_date = now
            active_alloc.save(update_fields=['is_current', 'returned_date'])

            AssetAllocation.objects.create(
                asset=asset,
                assigned_to_id=target_user_id,
                department_id=target_dept_id,
                location=new_loc or from_location or None,
                assigned_date=now,
                is_current=True,
                remarks=f"Transferred from previous allocation" + (f": {remarks}" if remarks else ""),
            )

            if new_loc:
                asset.location = new_loc
                asset.save(update_fields=['location', 'updated_at'])

        serializer = self.get_serializer(transfer)
        broadcast_custom_ws_event('asset_transferred', serializer.data)

        return Response({
            "code": 201,
            "message": "Asset transferred successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='history/(?P<asset_id>\\d+)')
    def asset_transfer_history(self, request, asset_id=None):
        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        transfers = self.get_queryset().filter(asset_id=asset_id)
        page = self.paginate_queryset(transfers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Asset transfer history retrieved successfully.",
                "data": paginated_res.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(transfers, many=True)
        return Response({
            "code": 200,
            "message": "Asset transfer history retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

