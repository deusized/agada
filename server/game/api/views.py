from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['POST'])
def check_balance(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    
    return Response({
        'cash': request.user.cash
    })

@api_view(['POST'])
def create_lobby(request):
    # Логика создания лобби
    return Response({'room_id': new_room.id})