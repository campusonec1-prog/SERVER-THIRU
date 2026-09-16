from django.urls import path
from .views import AssetViewSet

urlpatterns = [
    path('list', AssetViewSet.as_view({'get': 'list'}), name='asset-list'),
    path('create', AssetViewSet.as_view({'post': 'create'}), name='asset-create'),
    path('get/<int:pk>', AssetViewSet.as_view({'get': 'retrieve'}), name='asset-detail'),
    path('detail/<int:pk>', AssetViewSet.as_view({'get': 'retrieve'}), name='asset-detail-alias'),
    path('edit/<int:pk>', AssetViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='asset-edit'),
    path('remove/<int:pk>', AssetViewSet.as_view({'delete': 'destroy'}), name='asset-remove'),
]
