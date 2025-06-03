from django.contrib.auth.models import AbstractUser
from django.db import models

class Player(AbstractUser):
    cash = models.IntegerField(default=1000)
    
    def __str__(self):
        return self.username