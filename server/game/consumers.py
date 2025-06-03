import json
from channels.generic.websocket import AsyncWebsocketConsumer

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'game_{self.room_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'join':
            await self.handle_join(data)
        elif action == 'play_card':
            await self.handle_play_card(data)
        # ... другие действия

    async def handle_join(self, data):
        # Логика присоединения к игре
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_message',
                'message': {
                    'action': 'player_joined',
                    'player': data['player']
                }
            }
        )

    async def game_message(self, event):
        await self.send(text_data=json.dumps(event['message']))