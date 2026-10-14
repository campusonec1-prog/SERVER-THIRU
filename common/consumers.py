import json
import logging
import urllib.parse
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.core.cache import cache

logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user_rooms(token_str):
    """
    Decodes JWT token, checks cache first (<1ms), and resolves user id, role, and department.
    Returns a list of targeted room names (e.g. ['user_12', 'role_admin', 'dept_3']).
    """
    if not token_str:
        return []
    try:
        token = AccessToken(token_str)
        user_id = token.get('user_id')
        if not user_id:
            return []

        # Check cache first for 10,000+ concurrency (<1ms)
        cache_key = f'ws_user_meta_{user_id}'
        cached_rooms = cache.get(cache_key)
        if cached_rooms:
            return cached_rooms

        from users.models import User
        user = User.objects.filter(id=user_id).select_related('role').first()
        if not user:
            return []

        rooms = [f'user_{user.id}']
        role_name = (getattr(user.role, 'role_name', '') or '').lower().replace(' ', '_').strip()
        if role_name:
            rooms.append(f'role_{role_name}')

        # Check if student has department
        dept_id = None
        try:
            from student.models import Student
            st = Student.objects.filter(user_id=user.id).only('department_id').first()
            if st and st.department_id:
                dept_id = st.department_id
        except Exception:
            pass

        if dept_id:
            rooms.append(f'dept_{dept_id}')

        cache.set(cache_key, rooms, timeout=300)
        return rooms
    except Exception as e:
        logger.debug(f"WS auth token decode error: {e}")
        return []


class RealTimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.joined_groups = set()
        self.default_group = 'realtime_updates'
        await self.channel_layer.group_add(self.default_group, self.channel_name)
        self.joined_groups.add(self.default_group)

        # Parse token from query string if provided (?token=...)
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        params = urllib.parse.parse_qs(query_string)
        token = params.get('token', [None])[0]
        if token:
            rooms = await get_user_rooms(token)
            for room in rooms:
                await self.channel_layer.group_add(room, self.channel_name)
                self.joined_groups.add(room)

        await self.accept()

    async def disconnect(self, close_code):
        for room in list(self.joined_groups):
            try:
                await self.channel_layer.group_discard(room, self.channel_name)
            except Exception:
                pass
        self.joined_groups.clear()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if not isinstance(data, dict):
                return
            msg_type = data.get('type')
            if msg_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            elif msg_type == 'authenticate':
                token = data.get('token')
                if token:
                    rooms = await get_user_rooms(token)
                    for room in rooms:
                        if room not in self.joined_groups:
                            await self.channel_layer.group_add(room, self.channel_name)
                            self.joined_groups.add(room)
                    await self.send(text_data=json.dumps({
                        'type': 'authenticated',
                        'rooms': list(self.joined_groups)
                    }))
            elif msg_type == 'subscribe_task':
                task_id = data.get('task_id')
                if task_id:
                    task_room = f'task_{task_id}'
                    await self.channel_layer.group_add(task_room, self.channel_name)
                    self.joined_groups.add(task_room)
                    await self.send(text_data=json.dumps({
                        'type': 'task_subscribed',
                        'task_id': task_id
                    }))
            elif msg_type == 'unsubscribe_task':
                task_id = data.get('task_id')
                if task_id:
                    task_room = f'task_{task_id}'
                    await self.channel_layer.group_discard(task_room, self.channel_name)
                    self.joined_groups.discard(task_room)
        except Exception as e:
            logger.debug(f"WS receive error: {e}")

    async def broadcast_update(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def presence_message(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def user_status(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def task_progress(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))


class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.presence_group = 'presence'
        self.realtime_group = 'realtime_updates'
        self.joined_groups = {self.presence_group, self.realtime_group}

        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.channel_layer.group_add(self.realtime_group, self.channel_name)

        # Parse token if present
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        params = urllib.parse.parse_qs(query_string)
        token = params.get('token', [None])[0]
        if token:
            rooms = await get_user_rooms(token)
            for room in rooms:
                await self.channel_layer.group_add(room, self.channel_name)
                self.joined_groups.add(room)

        await self.accept()

    async def disconnect(self, close_code):
        for room in list(self.joined_groups):
            try:
                await self.channel_layer.group_discard(room, self.channel_name)
            except Exception:
                pass
        self.joined_groups.clear()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if isinstance(data, dict):
                msg_type = data.get('type') or data.get('event')
                if msg_type in ('ping', 'heartbeat'):
                    await self.send(text_data=json.dumps({
                        'type': 'pong',
                        'status': 'online',
                        'timestamp': data.get('timestamp')
                    }))
                elif msg_type == 'get_presence':
                    await self.send(text_data=json.dumps({
                        'type': 'presence_ack',
                        'status': 'connected'
                    }))
                elif msg_type == 'authenticate':
                    token = data.get('token')
                    if token:
                        rooms = await get_user_rooms(token)
                        for room in rooms:
                            if room not in self.joined_groups:
                                await self.channel_layer.group_add(room, self.channel_name)
                                self.joined_groups.add(room)
                        await self.send(text_data=json.dumps({
                            'type': 'authenticated',
                            'rooms': list(self.joined_groups)
                        }))
        except Exception:
            pass

    async def presence_message(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def broadcast_update(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def user_status(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def task_progress(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))
