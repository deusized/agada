from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from models import GameRoom
from django.contrib.auth import get_user_model

User = get_user_model()

@api_view(['POST'])
def create_lobby(request):
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Требуется авторизация'}, 
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        # Создаем новую комнату
        new_room = GameRoom.objects.create(
            name=f"Лобби {request.user.username}",
            max_players=2,  # Для игры в дурака обычно 2 игрока
            created_by=request.user
        )
        
        # Добавляем создателя в комнату
        new_room.players.add(request.user)
        new_room.current_players = 1
        new_room.save()

        return Response({
            'success': True,
            'room_id': new_room.id,
            'message': 'Лобби успешно создано'
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['POST'])
def check_balance(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    
    return Response({
        'cash': request.user.cash
    })
