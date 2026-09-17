from django.urls import path
from .views import AssetTransferViewSet

urlpatterns = [
    path('list', AssetTransferViewSet.as_view({'get': 'list'}), name='asset-transfer-list'),
    path('transfer', AssetTransferViewSet.as_view({'post': 'transfer_asset'}), name='asset-transfer-create'),
    path('get/<int:pk>', AssetTransferViewSet.as_view({'get': 'retrieve'}), name='asset-transfer-detail'),
    path('detail/<int:pk>', AssetTransferViewSet.as_view({'get': 'retrieve'}), name='asset-transfer-detail-alias'),
    path('history/<int:asset_id>', AssetTransferViewSet.as_view({'get': 'asset_transfer_history'}), name='asset-transfer-history'),
]
