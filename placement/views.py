from django.db.models import Count, Q
from django.http import Http404
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, NotAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from common.pagination import CustomPageNumberPagination
from common.r2 import upload_file_to_r2
from .models import (
    PlacementCompany,
    PlacementDrive,
    PlacementDriveEligibility,
    IndustryChoices,
    DriveTypeChoices,
    DriveStatusChoices
)
from .serializers import (
    PlacementCompanySerializer,
    PlacementDriveSerializer,
    PlacementDriveEligibilitySerializer
)
from .permissions import PlacementCompanyPermission


def broadcast_placement_event(model_name, event_name, data):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': model_name,
                        'event': event_name,
                        'data': data
                    }
                }
            )
        except Exception:
            pass


class PlacementCompanyViewSet(viewsets.ModelViewSet):
    queryset = PlacementCompany.objects.select_related('created_by', 'updated_by').all().order_by('-created_at')
    serializer_class = PlacementCompanySerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'company_name',
        'contact_person_name',
        'contact_email',
        'contact_phone_number',
        'city',
        'state',
        'industry',
        'description'
    ]

    filterset_fields = [
        'industry',
        'is_active',
        'city',
        'state'
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('PlacementCompany', 'create', {'id': instance.id, 'company_name': instance.company_name})

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('PlacementCompany', 'update', {'id': instance.id, 'company_name': instance.company_name})

    def perform_destroy(self, instance):
        inst_id = instance.id
        inst_name = instance.company_name
        instance.delete()
        broadcast_placement_event('PlacementCompany', 'delete', {'id': inst_id, 'company_name': inst_name})

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement companies retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement company details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement company created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement company updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement company deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        company = self.get_object()
        company.is_active = not company.is_active
        user = request.user if request.user and request.user.is_authenticated else None
        company.updated_by = user
        company.save()
        
        serializer = self.get_serializer(company)
        broadcast_placement_event('PlacementCompany', 'update', {
            'id': company.id,
            'company_name': company.company_name,
            'is_active': company.is_active
        })
        
        return Response({
            "code": 200,
            "message": f"Company marked as {'active' if company.is_active else 'inactive'} successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='industry-choices')
    def industry_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in IndustryChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Industry choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary-stats')
    def summary_stats(self, request):
        total = PlacementCompany.objects.count()
        active = PlacementCompany.objects.filter(is_active=True).count()
        inactive = total - active
        
        industry_counts = (
            PlacementCompany.objects.values('industry')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        
        industry_dict = dict(IndustryChoices.choices)
        top_industries = [
            {
                "industry": item['industry'],
                "label": industry_dict.get(item['industry'], item['industry']),
                "count": item['count']
            }
            for item in industry_counts
        ]

        return Response({
            "code": 200,
            "message": "Placement stats retrieved successfully",
            "data": {
                "total_companies": total,
                "active_companies": active,
                "inactive_companies": inactive,
                "top_industries": top_industries
            }
        }, status=status.HTTP_200_OK)


class PlacementDriveViewSet(viewsets.ModelViewSet):
    queryset = PlacementDrive.objects.select_related('company', 'created_by', 'updated_by').all().order_by('-application_start_date', '-created_at')
    serializer_class = PlacementDriveSerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'job_role',
        'company__company_name',
        'location',
        'ctc',
        'job_description',
    ]

    filterset_fields = [
        'company',
        'drive_type',
        'status',
        'location',
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('PlacementDrive', 'create', {
            'id': instance.id,
            'job_role': instance.job_role,
            'company_name': instance.company.company_name
        })

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('PlacementDrive', 'update', {
            'id': instance.id,
            'job_role': instance.job_role,
            'company_name': instance.company.company_name
        })

    def perform_destroy(self, instance):
        inst_id = instance.id
        role_name = instance.job_role
        instance.delete()
        broadcast_placement_event('PlacementDrive', 'delete', {'id': inst_id, 'job_role': role_name})

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drives retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement drive created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        drive = self.get_object()
        new_status = request.data.get('status')
        if not new_status or new_status not in DriveStatusChoices.values:
            return Response({
                "code": 400,
                "message": f"Invalid status. Choose from: {list(DriveStatusChoices.values)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        drive.status = new_status
        user = request.user if request.user and request.user.is_authenticated else None
        drive.updated_by = user
        drive.save()

        serializer = self.get_serializer(drive)
        broadcast_placement_event('PlacementDrive', 'update', {
            'id': drive.id,
            'job_role': drive.job_role,
            'status': drive.status
        })

        return Response({
            "code": 200,
            "message": f"Placement drive status updated to {drive.get_status_display()}",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='type-choices')
    def type_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in DriveTypeChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Drive type choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='status-choices')
    def status_choices(self, request):
        choices = [
            {"value": choice[0], "label": choice[1]}
            for choice in DriveStatusChoices.choices
        ]
        return Response({
            "code": 200,
            "message": "Drive status choices retrieved successfully",
            "data": choices
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary-stats')
    def summary_stats(self, request):
        total = PlacementDrive.objects.count()
        reg_open = PlacementDrive.objects.filter(status=DriveStatusChoices.REGISTRATION_OPEN).count()
        upcoming = PlacementDrive.objects.filter(status=DriveStatusChoices.UPCOMING).count()
        in_progress = PlacementDrive.objects.filter(status=DriveStatusChoices.IN_PROGRESS).count()
        completed = PlacementDrive.objects.filter(status=DriveStatusChoices.COMPLETED).count()

        return Response({
            "code": 200,
            "message": "Placement drive stats retrieved successfully",
            "data": {
                "total_drives": total,
                "registration_open": reg_open,
                "upcoming": upcoming,
                "in_progress": in_progress,
                "completed": completed
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='upload-document')
    def upload_document(self, request):
        file_obj = request.FILES.get('file') or request.FILES.get('document')
        if not file_obj:
            return Response({
                "code": 400,
                "message": "No document file provided for upload."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            file_url = upload_file_to_r2(file_obj, folder_name="placement_drives")
            return Response({
                "code": 200,
                "message": "Placement document uploaded successfully to Cloudflare R2.",
                "data": {
                    "document_name": file_obj.name,
                    "document_url": file_url
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Failed to upload document to Cloudflare R2: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PlacementDriveEligibilityViewSet(viewsets.ModelViewSet):
    queryset = PlacementDriveEligibility.objects.select_related(
        'drive',
        'drive__company',
        'created_by',
        'updated_by'
    ).prefetch_related(
        'departments',
        'batches',
        'batches__department'
    ).all().order_by('-created_at')
    serializer_class = PlacementDriveEligibilitySerializer
    permission_classes = [PlacementCompanyPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    search_fields = [
        'drive__job_role',
        'drive__company__company_name',
        'departments__department_name',
        'departments__department_code',
        'batches__batch',
    ]

    filterset_fields = [
        'drive',
        'departments',
        'batches',
    ]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_placement_event('PlacementDriveEligibility', 'create', {
            'id': instance.id,
            'drive_id': instance.drive_id,
            'job_role': instance.drive.job_role
        })

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_placement_event('PlacementDriveEligibility', 'update', {
            'id': instance.id,
            'drive_id': instance.drive_id,
            'job_role': instance.drive.job_role
        })

    def perform_destroy(self, instance):
        inst_id = instance.id
        drive_id = instance.drive_id
        role_name = instance.drive.job_role if instance.drive else 'Drive'
        instance.delete()
        broadcast_placement_event('PlacementDriveEligibility', 'delete', {
            'id': inst_id,
            'drive_id': drive_id,
            'job_role': role_name
        })

    def list(self, request, *args, **kwargs):
        # Support optional filter by ?drive_id=<id>
        drive_id = request.query_params.get('drive_id') or request.query_params.get('drive')
        if drive_id:
            self.queryset = self.queryset.filter(drive_id=drive_id)
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibilities retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibility details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Placement drive eligibility criteria created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibility criteria updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Placement drive eligibility criteria deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='by-drive/(?P<drive_id>[^/.]+)')
    def by_drive(self, request, drive_id=None):
        eligibility = self.queryset.filter(drive_id=drive_id).first()
        if not eligibility:
            return Response({
                "code": 200,
                "message": "No eligibility criteria found for this drive",
                "data": None
            }, status=status.HTTP_200_OK)
        serializer = self.get_serializer(eligibility)
        return Response({
            "code": 200,
            "message": "Drive eligibility retrieved successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

