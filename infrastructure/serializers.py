from rest_framework import serializers
from common.serializers import TrackingModelSerializerMixin
from .models import Block, Floor, Hall


class BlockSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Block
        fields = ['id', 'block_code', 'block_name', 'is_active', 'created_at', 'updated_at'] + TrackingModelSerializerMixin.TRACKING_FIELDS


class FloorSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    block_code = serializers.CharField(source='block.block_code', read_only=True)
    block_name = serializers.CharField(source='block.block_name', read_only=True)

    class Meta:
        model = Floor
        fields = [
            'id', 'block', 'block_code', 'block_name', 'floor_name',
            'is_active', 'created_at', 'updated_at'
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS


class HallSerializer(TrackingModelSerializerMixin, serializers.ModelSerializer):
    floor_name = serializers.CharField(source='floor.floor_name', read_only=True)
    block_code = serializers.CharField(source='floor.block.block_code', read_only=True)
    block_name = serializers.CharField(source='floor.block.block_name', read_only=True)
    block_id = serializers.IntegerField(source='floor.block.id', read_only=True)

    class Meta:
        model = Hall
        fields = [
            'id', 'floor', 'floor_name', 'block_id', 'block_code', 'block_name',
            'hall_no', 'hall_name', 'is_active',
            'created_at', 'updated_at'
        ] + TrackingModelSerializerMixin.TRACKING_FIELDS
