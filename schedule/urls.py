from django.urls import path
from .views import DayViewSet, PeriodViewSet, SessionViewSet

urlpatterns = [
    path('days/list', DayViewSet.as_view({'get': 'list'}), name='day-list'),
    path('days/create', DayViewSet.as_view({'post': 'create'}), name='day-create'),
    path('days/get/<int:pk>', DayViewSet.as_view({'get': 'retrieve'}), name='day-detail'),
    path('days/edit/<int:pk>', DayViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='day-edit'),
    path('days/remove/<int:pk>', DayViewSet.as_view({'delete': 'destroy'}), name='day-remove'),

    # Period endpoints
    path('periods/list', PeriodViewSet.as_view({'get': 'list'}), name='period-list'),
    path('periods/create', PeriodViewSet.as_view({'post': 'create'}), name='period-create'),
    path('periods/get/<int:pk>', PeriodViewSet.as_view({'get': 'retrieve'}), name='period-detail'),
    path('periods/edit/<int:pk>', PeriodViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='period-edit'),
    path('periods/remove/<int:pk>', PeriodViewSet.as_view({'delete': 'destroy'}), name='period-remove'),

    # Session endpoints
    path('sessions/list', SessionViewSet.as_view({'get': 'list'}), name='session-list'),
    path('sessions/create', SessionViewSet.as_view({'post': 'create'}), name='session-create'),
    path('sessions/get/<int:pk>', SessionViewSet.as_view({'get': 'retrieve'}), name='session-detail'),
    path('sessions/edit/<int:pk>', SessionViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='session-edit'),
    path('sessions/remove/<int:pk>', SessionViewSet.as_view({'delete': 'destroy'}), name='session-remove'),
]
