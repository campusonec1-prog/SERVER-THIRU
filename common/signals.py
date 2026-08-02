from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@receiver(post_save)
def broadcast_post_save(sender, instance, created, **kwargs):
    # Skip django internal models
    if sender.__module__.startswith('django.'):
        return

    channel_layer = get_channel_layer()
    if channel_layer:
        model_name = sender.__name__
        event_type = 'create' if created else 'update'
        
        data = {
            'id': instance.pk,
            'model': model_name,
            'event': event_type
        }
        
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': data
                }
            )
        except Exception:
            pass

@receiver(post_delete)
def broadcast_post_delete(sender, instance, **kwargs):
    if sender.__module__.startswith('django.'):
        return

    channel_layer = get_channel_layer()
    if channel_layer:
        model_name = sender.__name__
        
        data = {
            'id': instance.pk,
            'model': model_name,
            'event': 'delete'
        }
        
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': data
                }
            )
        except Exception:
            pass
