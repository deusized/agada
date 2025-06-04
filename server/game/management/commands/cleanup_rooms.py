from django.core.management.base import BaseCommand
from django.utils import timezone
from game.models import GameRoom
import time

class Command(BaseCommand):
    help = 'Cleans up inactive game rooms'
    
    def handle(self, *args, **options):
        while True:
            # Удаляем комнаты без активности более 10 секунд
            inactive_rooms = GameRoom.objects.filter(
                last_activity__lt=timezone.now() - timezone.timedelta(seconds=10),
                playeractivity__is_active=False
            ).distinct()
            
            count = inactive_rooms.count()
            inactive_rooms.delete()
            
            self.stdout.write(f'Deleted {count} inactive rooms')
            time.sleep(5)  # Проверяем каждые 5 секунд