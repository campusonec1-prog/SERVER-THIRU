from django.db import models
from common.models import TrackingModel

class Block(TrackingModel):
    """Master table for building blocks (A-Block, B-Block, etc.)"""
    block_code = models.CharField(max_length=20, unique=True)
    block_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'blocks'
        ordering = ['block_code']

    def __str__(self):
        return f"{self.block_code} - {self.block_name}"


class Floor(TrackingModel):
    """Master table for floors within a block."""
    block = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        db_column='block_id',
        related_name='floors'
    )
    floor_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'floors'
        ordering = ['block', 'floor_name']
        unique_together = ('block', 'floor_name')

    def __str__(self):
        return f"{self.block.block_code} / {self.floor_name}"


class Hall(TrackingModel):
    """Master table for halls. General infrastructure model."""
    floor = models.ForeignKey(
        Floor,
        on_delete=models.CASCADE,
        db_column='floor_id',
        related_name='halls'
    )
    hall_no = models.CharField(max_length=50)
    hall_name = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'halls'
        ordering = ['floor', 'hall_no']
        unique_together = ('floor', 'hall_no')

    @property
    def block(self):
        return self.floor.block

    def __str__(self):
        return f"{self.floor.block.block_code} / {self.floor.floor_name} / {self.hall_no}"
