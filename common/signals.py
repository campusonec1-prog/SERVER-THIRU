from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Models that send high-volume bursts or perform bulk database operations where individual
# row-by-row signals could cause performance degradation. These models broadcast summary events
# from their respective bulk service/view endpoints instead.
EXCLUDED_SIGNAL_MODELS = {
    'StudentAttendance',       # Broadcasted in batches via attendance_views
    'Marks',                   # Broadcasted in batches via marks_views
    'AssessmentOption',        # Child options within question/quiz
    'AssessmentQuestion',      # Questions handled within quiz/assessment
    'LMSAssessmentQuestionItem'
}

def _send_realtime_broadcast(data):
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': data
                }
            )
    except Exception:
        pass


@receiver(post_save)
def broadcast_post_save(sender, instance, created, **kwargs):
    # Skip django internal models, sessions, contenttypes, authtoken
    if sender.__module__.startswith('django.'):
        return
    if sender.__module__.startswith('rest_framework.'):
        return

    model_name = sender.__name__
    if model_name in EXCLUDED_SIGNAL_MODELS:
        return

    data = {
        'id': getattr(instance, 'pk', None),
        'model': model_name,
        'event': 'create' if created else 'update'
    }

    # Include lightweight metadata for immediate UI matching without heavy payloads
    if hasattr(instance, 'status') and instance.status is not None:
        try:
            data['status'] = str(getattr(instance.status, 'status_name', instance.status))
        except Exception:
            pass

    if hasattr(instance, 'application_number') and instance.application_number:
        data['application_number'] = str(instance.application_number)

    if hasattr(instance, 'user_id') and instance.user_id:
        data['user_id'] = instance.user_id

    transaction.on_commit(lambda: _send_realtime_broadcast(data))


@receiver(post_delete)
def broadcast_post_delete(sender, instance, **kwargs):
    if sender.__module__.startswith('django.'):
        return
    if sender.__module__.startswith('rest_framework.'):
        return

    model_name = sender.__name__
    if model_name in EXCLUDED_SIGNAL_MODELS:
        return

    data = {
        'id': getattr(instance, 'pk', None),
        'model': model_name,
        'event': 'delete'
    }

    transaction.on_commit(lambda: _send_realtime_broadcast(data))


