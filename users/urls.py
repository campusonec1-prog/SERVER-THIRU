from django.urls import path
from .views import UserViewSet, UserDetailsViewSet

urlpatterns = [
    path('create', UserViewSet.as_view({'post': 'create'}), name='user-create'),
    path('list', UserViewSet.as_view({'get': 'list'}), name='user-list'),
    path('list/<int:pk>', UserViewSet.as_view({'get': 'retrieve'}), name='user-detail'),
    path('edit/<int:pk>', UserViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='user-edit'),
    path('remove/<int:pk>', UserViewSet.as_view({'delete': 'destroy'}), name='user-remove'),
    path('login', UserViewSet.as_view({'post': 'login'}), name='user-login'),

    # User Details endpoints
    path('details/create', UserDetailsViewSet.as_view({'post': 'create'}), name='user-details-create'),
    path('details/list', UserDetailsViewSet.as_view({'get': 'list'}), name='user-details-list'),
    path('details/get/<int:pk>', UserDetailsViewSet.as_view({'get': 'retrieve'}), name='user-details-detail'),
    path('details/edit/<int:pk>', UserDetailsViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='user-details-edit'),
    path('details/remove/<int:pk>', UserDetailsViewSet.as_view({'delete': 'destroy'}), name='user-details-remove'),
]

