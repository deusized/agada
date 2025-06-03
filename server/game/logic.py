import random

class DurakGame:
    def __init__(self, players):
        self.players = players
        self.deck = self.generate_deck()
        self.trump_suit = self.select_trump()
        self.table = []
        self.current_attacker = None
        self.current_defender = None

    def generate_deck(self):
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return [{'suit': s, 'rank': r} for s in suits for r in ranks]

    def select_trump(self):
        return random.choice(['hearts', 'diamonds', 'clubs', 'spades'])

    def deal_cards(self):
        for player in self.players:
            while len(player.hand) < 6 and self.deck:
                player.hand.append(self.deck.pop())