import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

class RealTimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'realtime_updates'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if isinstance(data, dict) and data.get('type') == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
        except Exception:
            pass

    async def broadcast_update(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def presence_message(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))

    async def user_status(self, event):
        data = event.get('data', event)
        await self.send(text_data=json.dumps(data))


class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.presence_group = 'presence'
        self.realtime_group = 'realtime_updates'
        await self.channel_layer.group_add(
            self.presence_group,
            self.channel_name
        )
        await self.channel_layer.group_add(
            self.realtime_group,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.presence_group,
            self.channel_name
        )
        await self.channel_layer.group_discard(
            self.realtime_group,
            self.channel_name
        )

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


