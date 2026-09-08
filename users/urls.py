from django.urls import path, re_path
from .views import UserViewSet, UserDetailsViewSet

urlpatterns = [
    re_path(r'^create/?$', UserViewSet.as_view({'post': 'create'}), name='user-create'),
    re_path(r'^list/?$', UserViewSet.as_view({'get': 'list'}), name='user-list'),
    re_path(r'^list/(?P<pk>\d+)/?$', UserViewSet.as_view({'get': 'retrieve'}), name='user-detail'),
    re_path(r'^edit/(?P<pk>\d+)/?$', UserViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='user-edit'),
    re_path(r'^remove/(?P<pk>\d+)/?$', UserViewSet.as_view({'delete': 'destroy'}), name='user-remove'),
    re_path(r'^login/?$', UserViewSet.as_view({'post': 'login'}), name='user-login'),
    re_path(r'^bulk-import/?$', UserViewSet.as_view({'post': 'bulk_import'}), name='user-bulk-import'),

    # User Details endpoints
    re_path(r'^details/create/?$', UserDetailsViewSet.as_view({'post': 'create'}), name='user-details-create'),
    re_path(r'^details/list/?$', UserDetailsViewSet.as_view({'get': 'list'}), name='user-details-list'),
    re_path(r'^details/get/(?P<pk>\d+)/?$', UserDetailsViewSet.as_view({'get': 'retrieve'}), name='user-details-detail'),
    re_path(r'^details/edit/(?P<pk>\d+)/?$', UserDetailsViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='user-details-edit'),
    re_path(r'^details/remove/(?P<pk>\d+)/?$', UserDetailsViewSet.as_view({'delete': 'destroy'}), name='user-details-remove'),
]


