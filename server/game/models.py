from django.db import models
from django.conf import settings  # Импортируем настройки Django

class GameRoom(models.Model):
    name = models.CharField(max_length=100)
    max_players = models.IntegerField(default=2)
    current_players = models.IntegerField(default=0)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Правильный способ ссылаться на пользовательскую модель
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Используем AUTH_USER_MODEL из настроек
        on_delete=models.CASCADE,
        related_name='created_rooms'
    )
    
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='game_rooms'
    )
    
    def __str__(self):
        return f"{self.name} ({self.current_players}/{self.max_players})"

class Game(models.Model):
    room = models.OneToOneField(GameRoom, on_delete=models.CASCADE)
    players = models.ManyToManyField(settings.AUTH_USER_MODEL)
    current_turn = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='current_turn'
    )
    trump_suit = models.CharField(max_length=10, blank=True)
    deck = models.JSONField(default=list)
    discard_pile = models.JSONField(default=list)
    status = models.CharField(max_length=20, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Game in {self.room.name}"