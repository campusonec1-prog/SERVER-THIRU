from django.urls import path
from .views import AssetMaintenanceViewSet

urlpatterns = [
    path('list', AssetMaintenanceViewSet.as_view({'get': 'list'}), name='asset-maintenance-list'),
    path('create', AssetMaintenanceViewSet.as_view({'post': 'create'}), name='asset-maintenance-create'),
    path('get/<int:pk>', AssetMaintenanceViewSet.as_view({'get': 'retrieve'}), name='asset-maintenance-detail'),
    path('detail/<int:pk>', AssetMaintenanceViewSet.as_view({'get': 'retrieve'}), name='asset-maintenance-detail-alias'),
    path('edit/<int:pk>', AssetMaintenanceViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='asset-maintenance-edit'),
    path('start/<int:pk>', AssetMaintenanceViewSet.as_view({'post': 'start_maintenance'}), name='asset-maintenance-start'),
    path('complete/<int:pk>', AssetMaintenanceViewSet.as_view({'post': 'complete_maintenance'}), name='asset-maintenance-complete'),
    path('cancel/<int:pk>', AssetMaintenanceViewSet.as_view({'post': 'cancel_maintenance'}), name='asset-maintenance-cancel'),
    path('history/<int:asset_id>', AssetMaintenanceViewSet.as_view({'get': 'asset_maintenance_history'}), name='asset-maintenance-history'),
]
