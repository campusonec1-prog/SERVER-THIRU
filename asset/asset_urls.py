from django.urls import path
from .views import AssetViewSet

urlpatterns = [
    path('list', AssetViewSet.as_view({'get': 'list'}), name='asset-list'),
    path('create', AssetViewSet.as_view({'post': 'create'}), name='asset-create'),
    path('bulk-import', AssetViewSet.as_view({'post': 'bulk_import'}), name='asset-bulk-import'),
    path('tracking-report', AssetViewSet.as_view({'get': 'tracking_report'}), name='asset-tracking-report'),
    path('tracking-report/pdf', AssetViewSet.as_view({'get': 'export_tracking_report_pdf'}), name='asset-tracking-report-pdf'),
    path('get/<int:pk>', AssetViewSet.as_view({'get': 'retrieve'}), name='asset-detail'),
    path('detail/<int:pk>', AssetViewSet.as_view({'get': 'retrieve'}), name='asset-detail-alias'),
    path('edit/<int:pk>', AssetViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='asset-edit'),
    path('remove/<int:pk>', AssetViewSet.as_view({'delete': 'destroy'}), name='asset-remove'),
]
