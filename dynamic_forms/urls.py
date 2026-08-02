from django.urls import path
from .views import FormModuleViewSet, FormFieldViewSet

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
]
