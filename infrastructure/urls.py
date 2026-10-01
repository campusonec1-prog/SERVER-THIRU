from django.urls import path
from .views import BlockViewSet, FloorViewSet, HallViewSet

urlpatterns = [
    # Blocks
    path('blocks/list', BlockViewSet.as_view({'get': 'list'}), name='infra-block-list'),
    path('blocks/create', BlockViewSet.as_view({'post': 'create'}), name='infra-block-create'),
    path('blocks/get/<int:pk>', BlockViewSet.as_view({'get': 'retrieve'}), name='infra-block-detail'),
    path('blocks/edit/<int:pk>', BlockViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='infra-block-edit'),
    path('blocks/remove/<int:pk>', BlockViewSet.as_view({'delete': 'destroy'}), name='infra-block-remove'),

    # Floors
    path('floors/list', FloorViewSet.as_view({'get': 'list'}), name='infra-floor-list'),
    path('floors/create', FloorViewSet.as_view({'post': 'create'}), name='infra-floor-create'),
    path('floors/get/<int:pk>', FloorViewSet.as_view({'get': 'retrieve'}), name='infra-floor-detail'),
    path('floors/edit/<int:pk>', FloorViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='infra-floor-edit'),
    path('floors/remove/<int:pk>', FloorViewSet.as_view({'delete': 'destroy'}), name='infra-floor-remove'),

    # Halls
    path('halls/list', HallViewSet.as_view({'get': 'list'}), name='infra-hall-list'),
    path('halls/create', HallViewSet.as_view({'post': 'create'}), name='infra-hall-create'),
    path('halls/get/<int:pk>', HallViewSet.as_view({'get': 'retrieve'}), name='infra-hall-detail'),
    path('halls/edit/<int:pk>', HallViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='infra-hall-edit'),
    path('halls/remove/<int:pk>', HallViewSet.as_view({'delete': 'destroy'}), name='infra-hall-remove'),
]
