from django.db import models
from django.utils import timezone
from players.models import Player
from django.conf import settings

class GameRoom(models.Model):
    GAME_TYPE_CHOICES = (
        ('classic', 'Классический дурак'),
        ('transfer', 'Переводной дурак'),
    )

    game_type = models.CharField(
        max_length=20,
        choices=GAME_TYPE_CHOICES,
        default='classic'
    )
    
    last_activity = models.DateTimeField(auto_now=True)  # Время последней активности
    
    @property
    def active_players(self):
        """Возвращает количество активных игроков"""
        return self.playeractivity_set.filter(is_active=True).count()

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]

    name = models.CharField(max_length=100)
    max_players = models.IntegerField(default=2)
    game_type = models.CharField(max_length=20, choices=GAME_TYPE_CHOICES, default='classic')
    current_players = models.IntegerField(default=0)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Правильный способ ссылаться на пользовательскую модель
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_rooms'
    )
    
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='game_rooms'
    )
    
    def __str__(self):
        return f"{self.name} ({self.current_players}/{self.max_players})"


class PlayerActivity(models.Model):
    """Модель для отслеживания активности игроков"""
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('player', 'room')


class Game(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Ожидание игроков'),
        ('active', 'В процессе'),
        ('finished', 'Завершена')
    ]
    
    room = models.OneToOneField(GameRoom, on_delete=models.CASCADE)
    players = models.ManyToManyField(Player)
    current_turn = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, related_name='current_turns')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    trump_suit = models.CharField(max_length=10, blank=True)
    deck = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Игра в {self.room.name}"