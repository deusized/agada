from django.contrib.auth.forms import UserCreationForm
from .models import Player

class PlayerRegistrationForm(UserCreationForm):
    class Meta:
        model = Player
        fields = ('username', 'password1', 'password2')