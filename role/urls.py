from django.urls import path
from .views import RoleViewSet

urlpatterns = [
    path('create', RoleViewSet.as_view({'post': 'create'}), name='role-create'),
    path('list', RoleViewSet.as_view({'get': 'list'}), name='role-list'),
    path('list/<int:pk>', RoleViewSet.as_view({'get': 'retrieve'}), name='role-detail'),
    path('edit/<int:pk>', RoleViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='role-edit'),
    path('remove/<int:pk>', RoleViewSet.as_view({'delete': 'destroy'}), name='role-remove'),
]
