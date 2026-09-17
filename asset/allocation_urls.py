from django.urls import path
from .views import AssetAllocationViewSet

urlpatterns = [
    path('list', AssetAllocationViewSet.as_view({'get': 'list'}), name='asset-allocation-list'),
    path('assign', AssetAllocationViewSet.as_view({'post': 'assign_asset'}), name='asset-allocation-assign'),
    path('return', AssetAllocationViewSet.as_view({'post': 'return_asset', 'patch': 'return_asset'}), name='asset-allocation-return'),
    path('return/<int:pk>', AssetAllocationViewSet.as_view({'post': 'return_asset_by_id', 'patch': 'return_asset_by_id'}), name='asset-allocation-return-by-id'),
    path('get/<int:pk>', AssetAllocationViewSet.as_view({'get': 'retrieve'}), name='asset-allocation-detail'),
    path('detail/<int:pk>', AssetAllocationViewSet.as_view({'get': 'retrieve'}), name='asset-allocation-detail-alias'),
    path('history/<int:asset_id>', AssetAllocationViewSet.as_view({'get': 'asset_history'}), name='asset-allocation-history'),
]
