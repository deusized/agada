from django.db import models, transaction
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

class GameRoom(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_PLAYING = 'playing'
    STATUS_FINISHED = 'finished'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_WAITING, 'Ожидание игроков'),
        (STATUS_PLAYING, 'Игра идет'),
        (STATUS_FINISHED, 'Завершена'),
        (STATUS_CANCELLED, 'Отменена')
    ]

    name = models.CharField(max_length=100, blank=True, help_text="Название комнаты, если не указано, генерируется.")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_rooms'
    )
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='joined_game_rooms',
        blank=True
    )
    max_players = models.PositiveSmallIntegerField(default=2, help_text="От 2 до 4 игроков")
    bet_amount = models.PositiveIntegerField(default=0, help_text="Ставка для входа в игру")
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='won_game_rooms'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Игровая комната"
        verbose_name_plural = "Игровые комнаты"

    def __str__(self):
        return f"{self.name or f'Комната #{self.id}'} ({self.get_status_display()})"

    def get_absolute_url(self):
        return reverse('game:game_room', args=[str(self.id)])

    @property
    def current_players_count(self):
        return self.players.count()

    @property
    def is_full(self):
        return self.players.count() >= self.max_players

    def save(self, *args, **kwargs):
        if not self.name and self.creator:
            self.name = f"Игра {self.creator.username} (Ставка: {self.bet_amount})"
        super().save(*args, **kwargs)

    def start_game(self):
        """Начинает игру, если условия соблюдены."""
        if self.players.count() >= 2 and self.status == self.STATUS_WAITING and self.players.count() <= self.max_players :
            self.status = self.STATUS_PLAYING
            self.save(update_fields=['status'])
            return True
        return False

    def end_game(self, winner=None, loser=None, is_draw=False):
        """Завершает игру, обновляет статусы и балансы."""
        if self.status == self.STATUS_FINISHED:
            return

        with transaction.atomic():
            self.status = self.STATUS_FINISHED
            self.winner = winner
            self.save(update_fields=['status', 'winner'])

            all_players_in_room = list(self.players.all())

            if not is_draw and winner and self.bet_amount > 0:
                total_pot = self.bet_amount * len(all_players_in_room)
                winner.cash += total_pot
                winner.games_won += 1
                winner.save(update_fields=['cash', 'games_won'])
                
            elif is_draw and self.bet_amount > 0:
                for player_obj in all_players_in_room:
                    player_obj.cash += self.bet_amount
                    player_obj.save(update_fields=['cash'])
            
            for player_obj in all_players_in_room:
                player_obj.games_played += 1
                if player_obj.current_room == self:
                    player_obj.current_room = None
                player_obj.save(update_fields=['games_played', 'current_room'])

    def cancel_game(self):
        """Отменяет ожидающую игру и возвращает ставки."""
        if self.status == self.STATUS_WAITING:
            with transaction.atomic():
                self.status = self.STATUS_CANCELLED
                self.save(update_fields=['status'])
                
                if self.bet_amount > 0:
                    for player_obj in self.players.all():
                        player_obj.cash += self.bet_amount
                        if player_obj.current_room == self:
                            player_obj.current_room = None
                        player_obj.save(update_fields=['cash', 'current_room'])
                
                self.players.clear()

    def clean_up_inactive_waiting_room(self, timeout_seconds=300): # Например, 5 минут
        """Удаляет/отменяет ОЖИДАЮЩУЮ комнату, если в ней давно нет активных игроков."""
        if self.status == self.STATUS_WAITING:
            recent_activity_exists = PlayerActivity.objects.filter(
                room=self,
                last_ping__gte=timezone.now() - timezone.timedelta(seconds=timeout_seconds)
            ).exists()

            if not recent_activity_exists and self.players.count() > 0:
                self.cancel_game()
                return True
            elif self.players.count() == 0 and (timezone.now() - self.created_at).total_seconds() > timeout_seconds:
                self.delete()
                return True
        return False


class Game(models.Model):
    """
    Модель для хранения текущего состояния конкретной игровой партии.
    Создается, когда GameRoom переходит в статус 'playing'.
    """
    room = models.OneToOneField(
        GameRoom,
        on_delete=models.CASCADE,
        related_name='game_instance'
    )
    current_turn = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_game_turns'
    )
    status = models.CharField(
        max_length=20,
        choices=GameRoom.STATUS_CHOICES,
        default=GameRoom.STATUS_WAITING
    )
    trump_suit = models.CharField(max_length=10, blank=True, null=True, help_text="Козырная масть (hearts, spades, etc.)")
    trump_card_revealed = models.JSONField(null=True, blank=True, help_text="Карта, которая показывает козырь (если есть 'под колодой')")
    deck = models.JSONField(default=list, help_text="Список карт в колоде")
    table = models.JSONField(default=list, help_text="Список карт на столе (атака/защита)")
    player_hands = models.JSONField(default=dict, help_text="Словарь {player_id: [карты]} для рук игроков")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Состояние игры"
        verbose_name_plural = "Состояния игр"

    def __str__(self):
        return f"Игра для комнаты #{self.room.id} ({self.get_status_display()})"


class PlayerActivity(models.Model):
    """
    Отслеживание активности игрока в комнате (для WebSockets, определения неактивных и т.д.)
    """
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, help_text="Находится ли игрок сейчас активно на странице комнаты")
    last_ping = models.DateTimeField(auto_now_add=True, help_text="Время последней активности/пинга")

    class Meta:
        unique_together = ('player', 'room')
        ordering = ['-last_ping']
        verbose_name = "Активность игрока"
        verbose_name_plural = "Активности игроков"

    def save(self, *args, **kwargs):
        if self.is_active:
            self.last_ping = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.player.username} в комнате {self.room.name} (Активен: {self.is_active})"