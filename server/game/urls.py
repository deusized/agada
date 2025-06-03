from django.urls import path
from . import views
from .api import views as api_views

urlpatterns = [
    path('lobby/', views.lobby_view, name='lobby'),
    path('game/<int:room_id>/', views.game_view, name='game'),
    path('balance/', api_views.check_balance, name='check-balance'),
    path('create-lobby/', api_views.create_lobby, name='create-lobby'),
]