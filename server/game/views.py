from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.urls import reverse
from django.db import transaction, models
from django.db.models import Count
from django.contrib import messages
from django.forms import Form, IntegerField, CharField

from .models import GameRoom, PlayerActivity
from players.models import Player
from .game_logic import DurakGame
import logging

logger = logging.getLogger(__name__)

class CreateRoomForm(Form):
    name = CharField(max_length=50, label="Название комнаты (необязательно)", required=False)
    max_players = IntegerField(min_value=2, max_value=4, label="Количество игроков")
    bet_amount = IntegerField(min_value=0, label="Ставка")

@login_required
def lobby_view(request):
    rooms = GameRoom.objects.filter(status=GameRoom.STATUS_WAITING)\
                            .annotate(players_count=Count('players'))\
                            .filter(players_count__lt=models.F('max_players'))\
                            .exclude(players=request.user)\
                            .order_by('-created_at')[:20] # Показать последние 20

    context = {
        'rooms': rooms,
        'user_balance': request.user.cash, # request.user - это ваш players.models.Player
    }
    return render(request, 'game/lobby.html', context)

@login_required
def create_room(request):
    """
    Создание новой игровой комнаты.
    GET-запрос: отображает форму.
    POST-запрос: обрабатывает форму и создает комнату.
    """
    if request.method == 'POST':
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            max_players = form.cleaned_data['max_players']
            bet_amount = form.cleaned_data['bet_amount']
            name = form.cleaned_data.get('name')
            if not name: # Если имя не указано, генерируем по умолчанию
                name = f"Игра {request.user.username}"

            # Проверка баланса пользователя
            if bet_amount > request.user.cash:
                messages.error(request, 'Недостаточно средств на счете для такой ставки.')
                # Возвращаем на ту же страницу с ошибкой
                return render(request, 'game/create_room.html', {
                    'form': form,
                    'max_players_range': range(2, 5), # Для удобства в шаблоне
                    'max_bet': request.user.cash,
                })

            # Проверка, не участвует ли игрок уже в другой активной или ожидающей комнате
            if GameRoom.objects.filter(players=request.user, status__in=[GameRoom.STATUS_WAITING, GameRoom.STATUS_PLAYING]).exists():
                messages.error(request, 'Вы уже находитесь в другой игре или ожидаете ее начала.')
                return redirect('game:lobby') # Редирект в лобби

            try:
                with transaction.atomic(): # Используем транзакцию для атомарности операций
                    # Создаем комнату
                    room = GameRoom.objects.create(
                        name=name,
                        creator=request.user,
                        max_players=max_players,
                        bet_amount=bet_amount,
                        status=GameRoom.STATUS_WAITING # Начальный статус
                    )
                    # Добавляем создателя в список игроков комнаты
                    room.players.add(request.user)
                    
                    # Обновляем current_room у игрока
                    request.user.current_room = room
                    
                    # Списываем ставку с баланса игрока
                    if bet_amount > 0:
                        request.user.cash -= bet_amount
                    
                    request.user.save(update_fields=['cash', 'current_room']) # Сохраняем только измененные поля
                    
                    # Создаем запись об активности игрока в этой комнате
                    PlayerActivity.objects.create(
                        player=request.user,
                        room=room,
                        is_active=True
                    )
                    
                    messages.success(request, f'Комната "{room.name}" успешно создана!')
                    return redirect('game:game_room', room_id=room.id) # Перенаправляем в комнату
            except Exception as e:
                logger.error(f"Ошибка при создании комнаты пользователем {request.user.username}: {e}")
                messages.error(request, "Произошла ошибка при создании комнаты. Попробуйте позже.")
                # Остаемся на странице создания или редиректим в лобби
                return render(request, 'game/create_room.html', {
                    'form': form, # Возвращаем форму с введенными данными
                    'max_players_range': range(2, 5),
                    'max_bet': request.user.cash,
                })
        else:
            # Форма невалидна, отображаем ошибки на странице
            messages.error(request, "Пожалуйста, исправьте ошибки в форме.")
    else: # GET-запрос
        form = CreateRoomForm()

    context = {
        'form': form,
        'max_players_range': range(2, 5), # Для генерации <select> или ползунка
        'max_bet': request.user.cash,
    }
    return render(request, 'game/create_room.html', context)


@login_required
@transaction.atomic # Используем транзакцию, т.к. меняем баланс и состояние комнаты
def join_game(request, game_id):
    """
    Присоединение к существующей игровой комнате.
    Ожидается POST-запрос (например, от кнопки в списке лобби).
    Возвращает JSON для обработки через AJAX или редиректит.
    """
    if request.method != 'POST':
        # Если это не POST, можно вернуть ошибку или редиректить
        messages.error(request, "Неверный метод запроса для присоединения к игре.")
        return redirect('game:lobby')

    room = get_object_or_404(GameRoom, id=game_id)
    user = request.user # request.user это уже экземпляр вашей модели Player

    # Проверки перед присоединением
    if room.status != GameRoom.STATUS_WAITING:
        messages.error(request, 'Игра уже началась или завершена.')
        return redirect('game:lobby') # или JsonResponse, если это чистый AJAX endpoint
        
    if user in room.players.all():
        messages.info(request, 'Вы уже находитесь в этой комнате.')
        return redirect('game:game_room', room_id=room.id)
        
    if room.players.count() >= room.max_players:
        messages.error(request, 'Комната заполнена.')
        return redirect('game:lobby')
        
    if room.bet_amount > user.cash:
        messages.error(request, 'Недостаточно средств для входа в эту комнату.')
        return redirect('game:lobby')
    
    try:
        # Добавляем игрока в комнату
        room.players.add(user)
        user.current_room = room
        
        # Списываем ставку
        if room.bet_amount > 0:
            user.cash -= room.bet_amount
        user.save(update_fields=['cash', 'current_room'])
        
        # Обновляем активность
        PlayerActivity.objects.update_or_create(
            player=user, room=room,
            defaults={'is_active': True, 'last_ping': timezone.now()}
        )
        
        messages.success(request, f'Вы успешно присоединились к комнате "{room.name}"!')
        
        # Автоматический старт игры при заполнении комнаты
        game_started_auto = False
        if room.players.count() >= room.max_players: # Используем >= на случай, если вдруг больше игроков
            if room.start_game(): # Метод start_game в модели GameRoom должен вернуть True/False
                game_started_auto = True
                messages.info(request, "Комната заполнена, игра начинается!")
            else:
                messages.error(request, "Не удалось автоматически начать игру, хотя комната заполнена.")
        
        # Если это был AJAX запрос, можно вернуть JsonResponse
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Вы успешно присоединились к игре!',
                'redirect_url': reverse('game:game_room', args=[room.id]),
                'game_started': game_started_auto
            })
        
        return redirect('game:game_room', room_id=room.id)
        
    except Exception as e:
        logger.error(f"Ошибка при присоединении пользователя {user.username} к комнате {room.id}: {str(e)}")
        messages.error(request, "Произошла ошибка при присоединении к комнате.")
        return redirect('game:lobby')


@login_required
def game_room(request, room_id):
    """
    Представление игровой комнаты. Здесь будет основная логика отображения игры
    и взаимодействия через WebSockets.
    """
    try:
        # Используем select_related/prefetch_related для оптимизации запросов к связанным моделям
        room = GameRoom.objects.select_related('creator').prefetch_related('players').get(id=room_id)
    except GameRoom.DoesNotExist:
        raise Http404("Игровая комната не найдена.") # Или редирект с сообщением
    
    user = request.user
    if user not in room.players.all():
        messages.error(request, "Вы не являетесь участником этой игры.")
        return redirect('game:lobby')
    
    # Обновляем активность игрока
    PlayerActivity.objects.update_or_create(
        player=user, room=room,
        defaults={'is_active': True, 'last_ping': timezone.now()}
    )
    
    game_instance_logic = None
    game_state_for_template = None

    # Инициализируем или загружаем DurakGame.
    # Конструктор DurakGame сам заботится о создании/загрузке Game из БД.
    try:
        game_instance_logic = DurakGame(room)
        if game_instance_logic:
            game_state_for_template = game_instance_logic.get_game_state(for_player_user_obj=request.user)
    except Exception as e:
        logger.error(f"Ошибка при инициализации DurakGame для комнаты {room.id}: {e}")
        messages.error(request, "Произошла ошибка при загрузке состояния игры.")

    context = {
        'room': room,
        'game_state': game_state_for_template, # Состояние игры для первоначальной отрисовки
        'is_creator': user == room.creator,
        'user_id_json': user.id, # Передаем ID пользователя для JavaScript
        'room_id_json': str(room.id), # Передаем ID комнаты (UUID или int) как строку
    }
    return render(request, 'game/game_room.html', context)


@login_required
@require_POST # Это действие должно быть POST-запросом
def start_game(request, room_id):
    """
    Ручной запуск игры создателем комнаты. (Обычно AJAX)
    """
    room = get_object_or_404(GameRoom, id=room_id)
    if request.user != room.creator:
        return JsonResponse({'success': False, 'error': 'Только создатель может начать игру.'}, status=403)
    
    if room.status != GameRoom.STATUS_WAITING:
        return JsonResponse({'success': False, 'error': 'Игра уже начата или завершена.'})
    
    if room.players.count() < 2: # Минимальное количество игроков
        return JsonResponse({'success': False, 'error': 'Недостаточно игроков (минимум 2).'})
    
    if room.start_game(): # Метод в модели GameRoom
        # Здесь можно отправить сигнал или WebSocket сообщение о старте игры
        return JsonResponse({'success': True, 'message': 'Игра успешно начата!'})
    else:
        return JsonResponse({'success': False, 'error': 'Не удалось начать игру.'})


@login_required
@require_POST # Безопаснее делать такие действия через POST
@transaction.atomic
def leave_room(request, room_id):
    """
    Выход игрока из комнаты. (Обычно AJAX)
    """
    room = get_object_or_404(GameRoom, id=room_id)
    user = request.user
    
    if user not in room.players.all():
        return JsonResponse({'success': False, 'error': 'Вы не в этой комнате.'}, status=403)
    
    try:
        # Если игра еще не началась, и были ставки, можно вернуть ставку
        returned_bet = False
        if room.status == GameRoom.STATUS_WAITING and room.bet_amount > 0:
            user.cash += room.bet_amount
            user.save(update_fields=['cash'])
            returned_bet = True
        
        room.players.remove(user) # Удаляем игрока из списка игроков комнаты
        if user.current_room == room: # Если текущая комната игрока - эта
            user.current_room = None
            user.save(update_fields=['current_room'])

        PlayerActivity.objects.filter(player=user, room=room).delete()
        
        message = "Вы покинули комнату."
        if returned_bet:
            message += " Ваша ставка возвращена."

        # Если создатель покидает комнату, которая ожидает, игра отменяется
        if user == room.creator and room.status == GameRoom.STATUS_WAITING:
            room.cancel_game() # Метод в модели GameRoom, который меняет статус и возвращает ставки всем
            # Оповестить остальных игроков через WebSocket, что комната отменена
            return JsonResponse({'success': True, 'room_canceled': True, 'message': 'Комната отменена, так как создатель вышел.'})

        # Если после выхода комната (ожидающая) стала пустой, отменяем ее
        if room.status == GameRoom.STATUS_WAITING and room.players.count() == 0:
            room.cancel_game()

        if room.status == GameRoom.STATUS_PLAYING:
            pass
            
        return JsonResponse({'success': True, 'message': message})
    
    except Exception as e:
        logger.error(f"Ошибка при выходе пользователя {user.username} из комнаты {room.id}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Ошибка сервера при выходе из комнаты.'}, status=500)


@login_required
@require_POST # Завершение игры - изменяющее состояние действие
@transaction.atomic
def end_game(request, room_id):
    """
    Принудительное завершение игры (например, администратором или по каким-то условиям).
    Обычно логика завершения игры (определение победителя) находится в DurakGame.
    Это view может быть для административных целей или если игра "зависла".
    """
    room = get_object_or_404(GameRoom, id=room_id)
    
    # Проверка прав (например, только создатель или админ)
    if not (request.user == room.creator or request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'У вас нет прав для завершения этой игры.'}, status=403)
    
    if room.status != GameRoom.STATUS_PLAYING:
        return JsonResponse({'success': False, 'error': 'Игра не находится в активном состоянии для завершения.'}, status=400)
    
    winner_id = request.POST.get('winner_id') # Предполагаем, что ID победителя передается
    winner = None
    if winner_id:
        try:
            winner = room.players.get(id=winner_id)
        except Player.DoesNotExist: # Player из players.models
            return JsonResponse({'success': False, 'error': 'Указанный победитель не найден в этой комнате.'}, status=400)
    
    try:
        room.end_game(winner=winner) # Метод в модели GameRoom, который обновляет балансы, статус и т.д.
        # Оповестить игроков через WebSocket о завершении игры
        return JsonResponse({
            'success': True,
            'message': f'Игра в комнате "{room.name}" завершена.',
            'winner_username': winner.username if winner else "Ничья или победитель не указан"
        })
    except Exception as e:
        logger.error(f"Ошибка при завершении игры {room.id} пользователем {request.user.username}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Внутренняя ошибка сервера при завершении игры.'}, status=500)


@login_required
def game_status(request, room_id):
    """
    Получение текущего состояния игры (обычно AJAX-запрос для обновления информации
    на странице game_room, если не используются WebSockets для всего).
    """
    try:
        room = GameRoom.objects.select_related('creator').prefetch_related('players__profile').get(id=room_id)
    except GameRoom.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Комната не найдена.'}, status=404)

    if request.user not in room.players.all():
        return JsonResponse({'success': False, 'error': 'Вы не участник этой игры.'}, status=403)
    
    game_state_data = None
    try:
        if room.status == GameRoom.STATUS_PLAYING or room.status == GameRoom.STATUS_FINISHED:
            # Для активной или завершенной игры, состояние берется из DurakGame
            game_logic = DurakGame(room) # Конструктор загрузит или инициализирует состояние
            game_state_data = game_logic.get_game_state(for_player_user_obj=request.user)
        else: # Для ожидающей комнаты, можно сформировать упрощенное состояние
            game_state_data = {
                'room_id': str(room.id),
                'status': room.status,
                'players': [{'id': p.id, 'username': p.username, 'is_creator': p == room.creator} for p in room.players.all()],
                'max_players': room.max_players,
                'bet_amount': room.bet_amount,
                'is_creator': request.user == room.creator,
            }
    except Exception as e:
        logger.error(f"Ошибка при получении статуса игры для комнаты {room.id}: {e}")
        return JsonResponse({'success': False, 'error': 'Ошибка при получении состояния игры.'}, status=500)
            
    return JsonResponse({'success': True, 'game_state': game_state_data})


@login_required
@require_POST # Ping обычно не должен менять состояние, но POST безопаснее если есть side-effects
def ping(request, room_id):
    """
    Обновление времени последней активности пользователя в комнате.
    Вызывается периодически со стороны клиента (AJAX).
    """
    try:
        room = GameRoom.objects.get(id=room_id)
    except GameRoom.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Комната не найдена'}, status=404)

    if request.user not in room.players.all():
        return JsonResponse({'success': False, 'error': 'Вы не участник этой комнаты.'}) 
    
    activity, created = PlayerActivity.objects.update_or_create(
        player=request.user,
        room=room,
        defaults={'is_active': True, 'last_ping': timezone.now()}
    )

    return JsonResponse({'success': True, 'message': 'Ping successful'})