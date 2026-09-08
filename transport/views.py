import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from .models import Driver, Bus, TransportRoute, RouteStop
from .serializers import (
    DriverSerializer,
    BusSerializer,
    TransportRouteSerializer,
    RouteStopSerializer
)

logger = logging.getLogger(__name__)


def broadcast_event(model_name, event_name, payload):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': model_name,
                        'event': event_name,
                        'payload': payload
                    }
                }
            )
    except Exception:
        pass


def extract_validation_message(exc):
    errors = exc.detail
    if isinstance(errors, dict):
        first_key = next(iter(errors))
        val = errors[first_key]
        if isinstance(val, list):
            return f"{first_key}: {val[0]}"
        return f"{first_key}: {val}"
    elif isinstance(errors, list):
        return str(errors[0])
    return str(errors)


class BaseTransportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Requested item not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            return Response({
                "code": 400,
                "message": extract_validation_message(exc)
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Deleted successfully."
        }, status=status.HTTP_200_OK)


class DriverViewSet(BaseTransportViewSet):
    queryset = Driver.objects.all().order_by('-id')
    serializer_class = DriverSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')

        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == 'true'))
        if search:
            qs = qs.filter(driver_name__icontains=search) | qs.filter(license_number__icontains=search) | qs.filter(phone_number__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('Driver', 'driver_created', DriverSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('Driver', 'driver_updated', DriverSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('Driver', 'driver_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Drivers listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Driver retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Driver profile created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Driver profile updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Driver deleted successfully."
        }, status=status.HTTP_200_OK)


class BusViewSet(BaseTransportViewSet):
    queryset = Bus.objects.all().order_by('-id')
    serializer_class = BusSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        fuel_type = self.request.query_params.get('fuel_type')
        driver_id = self.request.query_params.get('driver_id')
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')

        if status_param:
            qs = qs.filter(status__iexact=status_param)
        if fuel_type:
            qs = qs.filter(fuel_type__iexact=fuel_type)
        if driver_id:
            qs = qs.filter(driver_id=driver_id)
        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == 'true'))
        if search:
            qs = qs.filter(bus_number__icontains=search) | qs.filter(registration_number__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('Bus', 'bus_created', BusSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('Bus', 'bus_updated', BusSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('Bus', 'bus_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Buses listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Bus retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Bus created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Bus updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Bus deleted successfully."
        }, status=status.HTTP_200_OK)


class TransportRouteViewSet(BaseTransportViewSet):
    queryset = TransportRoute.objects.all().order_by('-id')
    serializer_class = TransportRouteSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        bus_id = self.request.query_params.get('bus_id')
        search = self.request.query_params.get('search')

        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == 'true'))
        if bus_id:
            qs = qs.filter(bus_id=bus_id)
        if search:
            qs = qs.filter(route_name__icontains=search) | qs.filter(start_location__icontains=search) | qs.filter(end_location__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('TransportRoute', 'route_created', TransportRouteSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('TransportRoute', 'route_updated', TransportRouteSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('TransportRoute', 'route_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Routes listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Transport route created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Transport route updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Transport route deleted successfully."
        }, status=status.HTTP_200_OK)


class RouteStopViewSet(BaseTransportViewSet):
    queryset = RouteStop.objects.all().order_by('route', 'stop_order')
    serializer_class = RouteStopSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        route_id = self.request.query_params.get('route_id')
        search = self.request.query_params.get('search')

        if route_id:
            qs = qs.filter(route_id=route_id)
        if search:
            qs = qs.filter(stop_name__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('RouteStop', 'stop_created', RouteStopSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('RouteStop', 'stop_updated', RouteStopSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('RouteStop', 'stop_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stops listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stop retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Route stop created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stop updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stop deleted successfully."
        }, status=status.HTTP_200_OK)
