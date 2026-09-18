from django.urls import path
from .views import AssetDisposalViewSet

urlpatterns = [
    path('list', AssetDisposalViewSet.as_view({'get': 'list'}), name='asset-disposal-list'),
    path('create', AssetDisposalViewSet.as_view({'post': 'create'}), name='asset-disposal-create'),
    path('get/<int:pk>', AssetDisposalViewSet.as_view({'get': 'retrieve'}), name='asset-disposal-detail'),
    path('detail/<int:pk>', AssetDisposalViewSet.as_view({'get': 'retrieve'}), name='asset-disposal-detail-alias'),
    path('update/<int:pk>', AssetDisposalViewSet.as_view({'put': 'update_request', 'patch': 'update_request'}), name='asset-disposal-update'),
    path('approve/<int:pk>', AssetDisposalViewSet.as_view({'post': 'approve'}), name='asset-disposal-approve'),
    path('reject/<int:pk>', AssetDisposalViewSet.as_view({'post': 'reject'}), name='asset-disposal-reject'),
    path('cancel/<int:pk>', AssetDisposalViewSet.as_view({'post': 'cancel'}), name='asset-disposal-cancel'),
    path('complete/<int:pk>', AssetDisposalViewSet.as_view({'post': 'complete'}), name='asset-disposal-complete'),
    path('history/<int:asset_id>', AssetDisposalViewSet.as_view({'get': 'history'}), name='asset-disposal-history'),
]
