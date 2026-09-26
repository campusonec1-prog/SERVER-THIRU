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
        data = event['data']
        await self.send(text_data=json.dumps(data))

