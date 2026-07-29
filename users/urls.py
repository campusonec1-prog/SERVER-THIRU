from django.urls import path
from .views import UserViewSet

urlpatterns = [
    path('create', UserViewSet.as_view({'post': 'create'}), name='user-create'),
    path('list', UserViewSet.as_view({'get': 'list'}), name='user-list'),
    path('list/<int:pk>', UserViewSet.as_view({'get': 'retrieve'}), name='user-detail'),
    path('edit/<int:pk>', UserViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='user-edit'),
    path('remove/<int:pk>', UserViewSet.as_view({'delete': 'destroy'}), name='user-remove'),
]
