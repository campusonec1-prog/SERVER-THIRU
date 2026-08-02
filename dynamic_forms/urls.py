from django.urls import path
from .views import (
    FormModuleViewSet, FormFieldViewSet, ApplicationViewSet, 
    ApplicationStatusViewSet, ApplicationUserViewSet, ApplicationUserLoginView
)

urlpatterns = [
    # Form Module endpoints
    path('modules/list', FormModuleViewSet.as_view({'get': 'list'}), name='module-list'),
    path('modules/create', FormModuleViewSet.as_view({'post': 'create'}), name='module-create'),
    path('modules/get/<int:pk>', FormModuleViewSet.as_view({'get': 'retrieve'}), name='module-detail'),
    path('modules/edit/<int:pk>', FormModuleViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='module-edit'),
    path('modules/remove/<int:pk>', FormModuleViewSet.as_view({'delete': 'destroy'}), name='module-remove'),

    # Form Field endpoints
    path('fields/list', FormFieldViewSet.as_view({'get': 'list'}), name='field-list'),
    path('fields/create', FormFieldViewSet.as_view({'post': 'create'}), name='field-create'),
    path('fields/get/<int:pk>', FormFieldViewSet.as_view({'get': 'retrieve'}), name='field-detail'),
    path('fields/edit/<int:pk>', FormFieldViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='field-edit'),
    path('fields/remove/<int:pk>', FormFieldViewSet.as_view({'delete': 'destroy'}), name='field-remove'),

    # Application endpoints
    path('applications/list', ApplicationViewSet.as_view({'get': 'list'}), name='application-list'),
    path('applications/create', ApplicationViewSet.as_view({'post': 'create'}), name='application-create'),
    path('applications/get/<int:pk>', ApplicationViewSet.as_view({'get': 'retrieve'}), name='application-detail'),
    path('applications/edit/<int:pk>', ApplicationViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='application-edit'),
    path('applications/remove/<int:pk>', ApplicationViewSet.as_view({'delete': 'destroy'}), name='application-remove'),

    # Application Status endpoints
    path('statuses/list', ApplicationStatusViewSet.as_view({'get': 'list'}), name='status-list'),
    path('statuses/create', ApplicationStatusViewSet.as_view({'post': 'create'}), name='status-create'),
    path('statuses/get/<int:pk>', ApplicationStatusViewSet.as_view({'get': 'retrieve'}), name='status-detail'),
    path('statuses/edit/<int:pk>', ApplicationStatusViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='status-edit'),
    path('statuses/remove/<int:pk>', ApplicationStatusViewSet.as_view({'delete': 'destroy'}), name='status-remove'),

    # Application User (Candidate) endpoints
    path('users/list', ApplicationUserViewSet.as_view({'get': 'list'}), name='app-user-list'),
    path('users/create', ApplicationUserViewSet.as_view({'post': 'create'}), name='app-user-create'),
    path('users/login', ApplicationUserLoginView.as_view(), name='app-user-login'),
    path('users/get/<int:pk>', ApplicationUserViewSet.as_view({'get': 'retrieve'}), name='app-user-detail'),
    path('users/edit/<int:pk>', ApplicationUserViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='app-user-edit'),
    path('users/remove/<int:pk>', ApplicationUserViewSet.as_view({'delete': 'destroy'}), name='app-user-remove'),
]
