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


def send_targeted_broadcast(group_name, data):
    """
    Sends WebSocket message to a targeted room (e.g. 'user_12', 'task_123', 'dept_3', or 'role_admin').
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            event_type = 'task_progress' if data.get('type') in ('import_progress', 'sms_progress') else 'broadcast_update'
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': event_type,
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

    # Dispatch native mobile push notification for inbox notifications (Leave, Substitutions, etc.)
    if model_name == 'Notification' and created:
        try:
            from common.push_service import send_push_notification_for_inbox_notification
            transaction.on_commit(lambda: send_push_notification_for_inbox_notification(instance))
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[PushNotification Trigger Error] {e}")


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


