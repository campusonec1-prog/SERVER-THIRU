from django.urls import path, re_path
from .views import (
    DriverViewSet,
    BusViewSet,
    TransportRouteViewSet,
    RouteStopViewSet
)

urlpatterns = [
    # Driver Endpoints
    re_path(r'^drivers/create/?$', DriverViewSet.as_view({'post': 'create'}), name='driver-create'),
    re_path(r'^drivers/list/?$', DriverViewSet.as_view({'get': 'list'}), name='driver-list'),
    re_path(r'^drivers/detail/(?P<pk>\d+)/?$', DriverViewSet.as_view({'get': 'retrieve'}), name='driver-detail'),
    re_path(r'^drivers/edit/(?P<pk>\d+)/?$', DriverViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='driver-edit'),
    re_path(r'^drivers/remove/(?P<pk>\d+)/?$', DriverViewSet.as_view({'delete': 'destroy'}), name='driver-remove'),

    # Bus Endpoints
    re_path(r'^buses/create/?$', BusViewSet.as_view({'post': 'create'}), name='bus-create'),
    re_path(r'^buses/list/?$', BusViewSet.as_view({'get': 'list'}), name='bus-list'),
    re_path(r'^buses/detail/(?P<pk>\d+)/?$', BusViewSet.as_view({'get': 'retrieve'}), name='bus-detail'),
    re_path(r'^buses/edit/(?P<pk>\d+)/?$', BusViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='bus-edit'),
    re_path(r'^buses/remove/(?P<pk>\d+)/?$', BusViewSet.as_view({'delete': 'destroy'}), name='bus-remove'),

    # Route Endpoints
    re_path(r'^routes/create/?$', TransportRouteViewSet.as_view({'post': 'create'}), name='route-create'),
    re_path(r'^routes/list/?$', TransportRouteViewSet.as_view({'get': 'list'}), name='route-list'),
    re_path(r'^routes/detail/(?P<pk>\d+)/?$', TransportRouteViewSet.as_view({'get': 'retrieve'}), name='route-detail'),
    re_path(r'^routes/edit/(?P<pk>\d+)/?$', TransportRouteViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='route-edit'),
    re_path(r'^routes/remove/(?P<pk>\d+)/?$', TransportRouteViewSet.as_view({'delete': 'destroy'}), name='route-remove'),

    # Route Stop Endpoints
    re_path(r'^stops/create/?$', RouteStopViewSet.as_view({'post': 'create'}), name='stop-create'),
    re_path(r'^stops/list/?$', RouteStopViewSet.as_view({'get': 'list'}), name='stop-list'),
    re_path(r'^stops/detail/(?P<pk>\d+)/?$', RouteStopViewSet.as_view({'get': 'retrieve'}), name='stop-detail'),
    re_path(r'^stops/edit/(?P<pk>\d+)/?$', RouteStopViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='stop-edit'),
    re_path(r'^stops/remove/(?P<pk>\d+)/?$', RouteStopViewSet.as_view({'delete': 'destroy'}), name='stop-remove'),
]

