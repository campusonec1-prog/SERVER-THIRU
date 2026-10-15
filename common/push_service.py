import logging
import os
from django.conf import settings

logger = logging.getLogger('push_notifications')

_firebase_app = None

def get_firebase_app():
    """
    Lazily initialize Firebase Admin SDK.
    Looks for service account credentials file in:
      1. settings.FIREBASE_SERVICE_ACCOUNT_PATH
      2. Environment variable FIREBASE_CREDENTIALS
      3. Base directory: firebase-service-account.json
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Already initialized
        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            return _firebase_app

        # 1. Option: Credentials passed directly via environment variable JSON string (cloud/PaaS/Docker)
        raw_json = getattr(settings, 'FIREBASE_CREDENTIALS_JSON', None) or os.environ.get('FIREBASE_CREDENTIALS_JSON')
        if raw_json:
            import json
            cred_dict = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            cred = credentials.Certificate(cred_dict)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase Admin SDK initialized from FIREBASE_CREDENTIALS_JSON environment variable.")
            return _firebase_app

        # 2. Option: Credentials file path (VPS / dedicated server / local file)
        cred_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH', None)
        if not cred_path:
            cred_path = os.environ.get('FIREBASE_CREDENTIALS')
        if not cred_path:
            default_path = os.path.join(settings.BASE_DIR, 'firebase-service-account.json')
            if os.path.exists(default_path):
                cred_path = default_path

        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info(f"[FCM] Firebase Admin SDK initialized with credentials from: {cred_path}")
            return _firebase_app
        else:
            logger.warning("[FCM] No firebase-service-account.json or credentials found. Push notifications will run in mock/log mode.")
            return None
    except Exception as e:
        logger.error(f"[FCM] Error initializing Firebase Admin: {e}")
        return None


def register_device(user, token, device_type='android'):
    """
    Registers or updates an active FCM device token for a user.
    """
    from users.models import DeviceToken
    if not user or not token:
        return None
    
    device, created = DeviceToken.objects.update_or_create(
        user=user,
        token=token.strip(),
        defaults={
            'device_type': device_type.lower(),
            'is_active': True
        }
    )
    active_count = DeviceToken.objects.filter(user=user, is_active=True).count()
    print(f"\n[FCM DEVICE TOKEN] User '{user.username}' {'registered new' if created else 'updated'} {device_type} token: {token[:20]}... (Active Devices: {active_count})", flush=True)
    logger.info(f"[FCM] Device token {'registered' if created else 'updated'} for user {user.username} ({device_type})")
    return device


def unregister_device(user, token):
    """
    Deactivates a device token upon logout.
    """
    from users.models import DeviceToken
    if not user or not token:
        return 0
    updated = DeviceToken.objects.filter(user=user, token=token.strip()).update(is_active=False)
    print(f"\n[FCM DEVICE TOKEN] User '{user.username}' deactivated token: {token[:20]}...", flush=True)
    logger.info(f"[FCM] Device token deactivated for user {user.username}")
    return updated


def send_push_notification(user, title, body, data=None):
    """
    Sends a native push notification to all active devices of a given user.
    Handles invalid/unregistered tokens cleanly by marking them inactive.
    """
    from users.models import DeviceToken

    if not user:
        return {'success': 0, 'failure': 0}

    tokens = list(DeviceToken.objects.filter(user=user, is_active=True).values_list('token', flat=True))

    # Ensure all data values are strings (required by FCM data payload)
    fcm_data = {
        'title': str(title) if title else 'IMS TEC Alert',
        'body': str(body) if body else '',
    }
    if data and isinstance(data, dict):
        for k, v in data.items():
            fcm_data[str(k)] = str(v) if v is not None else ''

    print(f"\n{'='*70}", flush=True)
    print(f"[PUSH NOTIFICATION DISPATCH]", flush=True)
    print(f"  Target User : {getattr(user, 'username', user)} (ID: {getattr(user, 'id', 'N/A')})", flush=True)
    print(f"  Title       : {title}", flush=True)
    print(f"  Body        : {body}", flush=True)
    print(f"  Payload     : {fcm_data}", flush=True)
    print(f"  Active Tokens : {len(tokens)} token(s) registered in DB", flush=True)

    if not tokens:
        print(f"  [STATUS]    SKIPPED: Target user has 0 active registered devices.", flush=True)
        print(f"              (User must open Android app and tap Allow Notifications)", flush=True)
        print(f"{'='*70}\n", flush=True)
        logger.debug(f"[FCM] User {getattr(user, 'username', user)} has no active device tokens registered.")
        return {'success': 0, 'failure': 0}

    app = get_firebase_app()
    if not app:
        print(f"  [STATUS]    MOCK MODE: Firebase credentials not initialized on server.", flush=True)
        print(f"              Ensure 'firebase-service-account.json' is present on the server.", flush=True)
        print(f"{'='*70}\n", flush=True)
        logger.info(f"[FCM Mock] Push to {user.username}: Title='{title}' | Body='{body}' | Data={fcm_data} | Tokens={len(tokens)}")
        return {'success': len(tokens), 'failure': 0, 'mock': True}

    try:
        from firebase_admin import messaging

        android_notification = messaging.AndroidNotification(
            channel_id='ims_tec_notifications',
            color='#4f46e5',
            sound='default',
            default_sound=True,
            default_vibrate_timings=True,
            priority='high',
            visibility='public',
        )

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=fcm_data,
            android=messaging.AndroidConfig(
                priority='high',
                notification=android_notification,
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=title, body=body),
                        sound='default',
                        badge=1,
                    )
                )
            )
        )

        # Use send_each_for_multicast (supported in firebase-admin 6.2+ & 7.0+)
        if hasattr(messaging, 'send_each_for_multicast'):
            response = messaging.send_each_for_multicast(message)
        else:
            response = messaging.send_multicast(message)

        print(f"  [FCM GOOGLE RESPONSE]", flush=True)
        print(f"    Success Deliveries : {response.success_count}", flush=True)
        print(f"    Failed Deliveries  : {response.failure_count}", flush=True)

        # Deactivate stale or unregistered tokens
        if response.failure_count > 0:
            stale_tokens = []
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    err_code = getattr(resp.exception, 'code', str(resp.exception))
                    print(f"    Token[{idx}] Error : {err_code}", flush=True)
                    if 'registration-token-not-registered' in err_code or 'invalid-argument' in err_code:
                        stale_tokens.append(tokens[idx])
            if stale_tokens:
                DeviceToken.objects.filter(token__in=stale_tokens).update(is_active=False)
                print(f"    Cleaned up {len(stale_tokens)} stale token(s) from DB.", flush=True)
                logger.info(f"[FCM] Deactivated {len(stale_tokens)} stale device tokens.")

        print(f"{'='*70}\n", flush=True)
        logger.info(f"[FCM] Sent to {user.username}: {response.success_count} success, {response.failure_count} failures")

        return {
            'success': response.success_count,
            'failure': response.failure_count
        }
    except Exception as e:
        print(f"  [FCM ERROR] Exception: {e}", flush=True)
        print(f"{'='*70}\n", flush=True)
        logger.error(f"[FCM] Exception sending multicast push: {e}")
        return {'success': 0, 'failure': len(tokens), 'error': str(e)}


def send_push_notification_for_inbox_notification(notification_instance):
    """
    Helper to bridge Django's leave/inbox Notification instance to native push.
    Dispatches deep-link route based on notification_type.
    """
    if not notification_instance or not notification_instance.user:
        return None

    ntype = notification_instance.notification_type or 'GENERAL'
    print(f"\n[FCM INBOX TRIGGER] Notification #{notification_instance.id} ({ntype}) -> User '{notification_instance.user.username}'", flush=True)
    
    # Determine the target frontend deep link route
    route = '/dashboard'
    if ntype in ['SUBSTITUTION_REQUEST', 'SUBSTITUTION_RESPONSE', 'LEAVE_STATUS', 'LEAVE_APPROVAL_REQUEST']:
        route = '/faculty/leave'
    elif ntype == 'HOSTEL_LEAVE':
        route = '/student/portal'
    elif ntype == 'GENERAL':
        route = '/admin/announcements'

    data_payload = {
        'notification_id': str(notification_instance.id),
        'notification_type': str(ntype),
        'related_leave_id': str(notification_instance.related_leave_id or ''),
        'related_substitution_id': str(notification_instance.related_substitution_id or ''),
        'route': route,
    }

    return send_push_notification(
        user=notification_instance.user,
        title=notification_instance.title or 'IMS TEC Alert',
        body=notification_instance.message or '',
        data=data_payload
    )
