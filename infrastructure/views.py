from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Block, Floor, Hall
from .serializers import BlockSerializer, FloorSerializer, HallSerializer


class BlockViewSet(viewsets.ModelViewSet):
    queryset = Block.objects.all().order_by('block_code')
    serializer_class = BlockSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('true', '1', 'yes'))
        return qs


class FloorViewSet(viewsets.ModelViewSet):
    queryset = Floor.objects.select_related('block').all().order_by('block__block_code', 'floor_order')
    serializer_class = FloorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        block_id = self.request.query_params.get('block_id')
        is_active = self.request.query_params.get('is_active')
        if block_id:
            qs = qs.filter(block_id=block_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('true', '1', 'yes'))
        return qs


class HallViewSet(viewsets.ModelViewSet):
    queryset = Hall.objects.select_related('floor__block').all().order_by('floor__block__block_code', 'floor__floor_order', 'hall_no')
    serializer_class = HallSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        block_id = self.request.query_params.get('block_id')
        floor_id = self.request.query_params.get('floor_id')
        is_active = self.request.query_params.get('is_active')
        if block_id:
            qs = qs.filter(floor__block_id=block_id)
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('true', '1', 'yes'))
        return qs
