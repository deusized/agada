import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from asgiref.sync import sync_to_async
from .models import GameRoom, PlayerActivity

class GameRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
            
        # Добавляем игрока в активные
        await self.update_player_activity(True)
        
        await self.channel_layer.group_add(
            f"game_{self.room_id}",
            self.channel_name
        )
        await self.accept()
        
        # Отправляем обновленное количество игроков
        await self.send_player_count()

    async def disconnect(self, close_code):
        # Помечаем игрока как неактивного
        await self.update_player_activity(False)
        await self.send_player_count()
        
        # Проверяем нужно ли удалить комнату
        await self.check_room_activity()
        
        await self.channel_layer.group_discard(
            f"game_{self.room_id}",
            self.channel_name
        )

    async def receive(self, text_data):
        # Обновляем время активности при любом сообщении
        await self.update_player_activity(True)
        
        data = json.loads(text_data)
        # ... обработка игровых событий ...

    @sync_to_async
    def update_player_activity(self, is_active):
        room = GameRoom.objects.get(id=self.room_id)
        PlayerActivity.objects.update_or_create(
            player=self.user,
            room=room,
            defaults={'is_active': is_active}
        )
        room.save()  # Обновляет last_activity

    @sync_to_async
    def send_player_count(self):
        room = GameRoom.objects.get(id=self.room_id)
        self.channel_layer.group_send(
            f"game_{self.room_id}",
            {
                'type': 'player_count',
                'count': room.active_players
            }
        )

    @sync_to_async
    def check_room_activity(self):
        room = GameRoom.objects.get(id=self.room_id)
        if room.active_players == 0 and (timezone.now() - room.last_activity).total_seconds() > 10:
            room.delete()

    async def player_count(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_count',
            'count': event['count']
        }))

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