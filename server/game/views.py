from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import GameRoom, Game
from .serializers import GameRoomSerializer, GameSerializer
from players.models import Player
from django.shortcuts import render, redirect

def lobby_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    rooms = GameRoom.objects.filter(is_active=False)
    return render(request, 'lobby/lobby.html', {'game_rooms': rooms})

def game_view(request, room_id):
    if not request.user.is_authenticated:
        return redirect('login')
    
    return render(request, 'game/game.html', {'room_id': room_id})


class GameRoomViewSet(viewsets.ModelViewSet):
    queryset = GameRoom.objects.all()
    serializer_class = GameRoomSerializer

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        room = self.get_object()
        player = Player.objects.get(user=request.user)
        
        if room.current_players >= room.max_players:
            return Response({'error': 'Комната заполнена'}, status=status.HTTP_400_BAD_REQUEST)
        
        room.current_players += 1
        room.save()
        
        if room.current_players == room.max_players:
            game = Game.objects.create(room=room)
            game.players.set([player])
            game.save()
            room.is_active = True
            room.save()
            
            # Инициализация игры (раздача карт, определение козыря и т.д.)
            self.initialize_game(game)
            
            return Response(GameSerializer(game).data, status=status.HTTP_200_OK)
        
        return Response(GameRoomSerializer(room).data, status=status.HTTP_200_OK)

    def initialize_game(self, game):
        # Логика инициализации игры
        pass