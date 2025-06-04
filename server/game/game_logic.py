def initialize_game(game):
    """Инициализация игрового состояния"""
    # 1. Создаём колоду
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    ranks = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [{'suit': s, 'rank': r} for s in suits for r in ranks]
    
    # 2. Перемешиваем
    import random
    random.shuffle(deck)
    
    # 3. Выбираем козырь
    trump_card = deck[-1]
    game.trump_suit = trump_card['suit']
    
    # 4. Сохраняем колоду
    game.deck = deck
    game.save()
    
    # 5. Раздаём карты (первые 6 каждому игроку)
    for player in game.players.all():
        player_cards = []
        for _ in range(6):
            if deck:
                player_cards.append(deck.pop())
        # Здесь нужно сохранить карты игрока (реализуйте в вашей модели)