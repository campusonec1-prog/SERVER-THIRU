from django.urls import path
from .views import AssetCategoryViewSet

urlpatterns = [
    path('list', AssetCategoryViewSet.as_view({'get': 'list'}), name='asset-category-list'),
    path('create', AssetCategoryViewSet.as_view({'post': 'create'}), name='asset-category-create'),
    path('get/<int:pk>', AssetCategoryViewSet.as_view({'get': 'retrieve'}), name='asset-category-detail'),
    path('detail/<int:pk>', AssetCategoryViewSet.as_view({'get': 'retrieve'}), name='asset-category-detail-alias'),
    path('edit/<int:pk>', AssetCategoryViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='asset-category-edit'),
    path('toggle-status/<int:pk>', AssetCategoryViewSet.as_view({'patch': 'toggle_status', 'post': 'toggle_status'}), name='asset-category-toggle-status'),
    path('remove/<int:pk>', AssetCategoryViewSet.as_view({'delete': 'destroy'}), name='asset-category-remove'),
]
