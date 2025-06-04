from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.humanize.templatetags.humanize import naturaltime
from .models import GameRoom, Game
from django.db import models
from django.db.models import Count
import random
from django.shortcuts import render, get_object_or_404
from .game_logic import initialize_game
from django.views.decorators.cache import cache_page
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


@login_required
def game_room(request, room_id):
    room = get_object_or_404(GameRoom, id=room_id)
    game = get_object_or_404(Game, room=room)
    
    return render(request, 'game/game_room.html', {
        'room': room,
        'game': game
    })


@cache_page(5)
def list_games(request):
    try:
        games = GameRoom.objects.annotate(
            players_count=Count('players')
        ).filter(
            is_active=False
        ).values('id', 'name', 'players_count', 'max_players', 'created_at')[:50]
        
        
        games_data = []
        for game in games:
            game_data = {
                'id': game['id'],
                'name': game['name'],
                'players': game['players_count'],
                'max_players': game['max_players'],
                'created_ago': naturaltime(game['created_at']),
                'status': 'waiting'
            }
            games_data.append(game_data)
        
        return JsonResponse({
            'success': True,
            'games': games_data,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке списка игр: {str(e)}", exc_info=True)
        cache_key = 'fallback_games_list'
        fallback_data = cache.get(cache_key, {'games': [], 'cached': True})
        return JsonResponse({
            'success': False,
            'games': fallback_data['games'],
            'error': 'Ошибка загрузки. Показаны кешированные данные.',
            'cached': fallback_data['cached']
        }, status=200)

@login_required
def lobby_view(request):
    return render(request, 'lobby/lobby.html')

@login_required
def create_game(request):
    if request.method == 'POST':
        # Проверяем, нет ли у пользователя уже активной игры
        if GameRoom.objects.filter(players=request.user, is_active=False).exists():
            return JsonResponse({
                'success': False,
                'error': 'Вы уже находитесь в игре'
            })
        
        # Создаем новую игровую комнату
        game_room = GameRoom.objects.create(
            name=f"Игра {request.user.username}",
            max_players=2,
            created_by=request.user
        )
        game_room.players.add(request.user)
        
        # Инициализируем саму игру
        game = Game.objects.create(
            room=game_room,
            current_turn=request.user,
            status='waiting'
        )
        game.players.add(request.user)
        
        # Инициализируем игровую логику
        initialize_game(game)
        
        return JsonResponse({
            'success': True,
            'room_id': game_room.id,
            'game_id': game.id,
            'redirect_url': f'/game/{game.id}/'
        })
    return JsonResponse({'error': 'Invalid method'}, status=400)

@login_required
def start_game(request, room_id):
    """Запуск игры, когда набралось достаточно игроков"""
    try:
        game_room = GameRoom.objects.get(id=room_id)
        if game_room.players.count() >= game_room.max_players:
            game = Game.objects.get(room=game_room)
            game.status = 'active'
            game.save()
            return JsonResponse({'success': True})
        return JsonResponse({
            'success': False,
            'error': 'Недостаточно игроков'
        })
    except GameRoom.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Комната не найдена'
        }, status=404)

@login_required
def find_game(request):
    if request.method == 'POST':
        # Ищем случайную доступную игру
        available_games = GameRoom.objects.annotate(
            players_count=Count('players')
        ).filter(
            players_count__lt=models.F('max_players'),
            is_active=False
        ).exclude(players=request.user)
        
        if available_games.exists():
            game = random.choice(available_games)
            game.players.add(request.user)
            return JsonResponse({
                'success': True,
                'room_id': game.id
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Нет доступных игр'
            })
    return JsonResponse({'error': 'Invalid method'}, status=400)

@login_required
def join_game(request, game_id):
    if request.method == 'POST':
        try:
            game = GameRoom.objects.annotate(
                players_count=Count('players')
            ).get(id=game_id)
            
            if game.players_count >= game.max_players:
                return JsonResponse({
                    'success': False,
                    'error': 'Комната заполнена'
                })
            
            if request.user in game.players.all():
                return JsonResponse({
                    'success': False,
                    'error': 'Вы уже в этой игре'
                })
            
            game.players.add(request.user)
            return JsonResponse({'success': True})
            
        except GameRoom.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Игра не найдена'
            }, status=404)
    return JsonResponse({'error': 'Invalid method'}, status=400)

def list_games(request):
    games = GameRoom.objects.annotate(
        players_count=Count('players')
    ).filter(
        is_active=False
    ).values('id', 'name', 'players_count', 'max_players')
    
    return JsonResponse({
        'games': list(games)
    })