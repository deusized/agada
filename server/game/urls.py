from django.urls import path
from . import views

urlpatterns = [
    path('', views.lobby_view, name='lobby'),
    path('create/', views.create_game, name='create_game'),
    path('find/', views.find_game, name='find-game'),
    path('join/<int:game_id>/', views.join_game, name='join-game'),
    path('<int:room_id>/', views.game_room, name='game_room'),
    path('start/<int:room_id>/', views.start_game, name='start_game'),
    path('list/', views.list_games, name='list-games'),
]