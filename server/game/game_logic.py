from __future__ import annotations

import random
import os
from django.conf import settings
from django.db import transaction
from .models import Game, GameRoom
from django.contrib.auth import get_user_model
import typing

User = get_user_model()

class DurakGame:
    def __init__(self, room: GameRoom):
        self.room = room
        self.game_model_instance = None # Экземпляр модели game.models.Game
        self.players = list(room.players.all().order_by('id')) # User объекты, упорядочены для консистентности индексов
        
        # player_hands_data это {player_id_str: [card_dict1, card_dict2, ...]}
        self.player_hands_data = {} 
        self.deck = []
        self.trump_suit = None
        self.trump_card_revealed = None # Карта, показывающая козырь (если есть на столе)
        self.table = [] # [{ 'attack_card': card, 'defense_card': card_or_none, 'attacker_id': id }, ...]
        
        # Индексы указывают на позиции в self.players
        self.attacker_index = 0 
        self.defender_index = 1 % len(self.players) if len(self.players) > 0 else 0
        
        self._load_or_initialize_game_state()

    def _generate_deck(self):
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [{'rank': rank, 'suit': suit, 'id': f"{rank}-{suit}"} for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    def _load_or_initialize_game_state(self):
        try:
            self.game_model_instance = Game.objects.get(room=self.room)
            # Загружаем состояние из модели
            self.deck = list(self.game_model_instance.deck) # Убедимся, что это изменяемый список
            self.trump_suit = self.game_model_instance.trump_suit
            self.table = list(self.game_model_instance.table) # Убедимся, что это изменяемый список
            self.player_hands_data = dict(self.game_model_instance.player_hands) # Убедимся, что это изменяемый dict
            self.trump_card_revealed = self.game_model_instance.trump_card_revealed # Загружаем открытый козырь

            # Определяем current_player_index (атакующего)
            if self.game_model_instance.current_turn:
                try:
                    # self.players уже отсортирован, ищем по id
                    current_turn_user_id = self.game_model_instance.current_turn.id
                    self.attacker_index = next(i for i, p in enumerate(self.players) if p.id == current_turn_user_id)
                except (StopIteration, AttributeError): # Игрок не найден или current_turn is None
                    self._set_initial_attacker_defender()
            else:
                self._set_initial_attacker_defender()
            
            self.defender_index = (self.attacker_index + 1) % len(self.players) if self.players else 0

            # Убедимся, что для всех активных игроков есть запись в player_hands_data
            for player_user in self.players:
                if str(player_user.id) not in self.player_hands_data:
                    self.player_hands_data[str(player_user.id)] = []

        except Game.DoesNotExist:
            # Новая игра, инициализируем состояние
            self.deck = self._generate_deck()
            self.player_hands_data = {str(p.id): [] for p in self.players}
            self._initialize_hands_and_trump() # Раздача и определение козыря
            self._set_initial_attacker_defender() # Определяем первого атакующего
            
            # Сохраняем начальное состояние игры в БД
            self.game_model_instance = Game.objects.create(
                room=self.room,
                status='active',
                # Остальные поля будут установлены в save_game_state
            )
            self.save_game_state()

    def _set_initial_attacker_defender(self):
        # Логика определения первого атакующего (например, с младшим козырем)
        # Пока что: первый игрок в списке self.players (отсортирован по ID)
        # или тот, у кого наименьший козырь (если реализовать)
        if not self.players: return
        
        # Простой вариант: первый по ID
        self.attacker_index = 0
        # Продвинутый вариант: поиск младшего козыря
        min_trump_holder_idx = -1
        min_trump_value = 100 # Больше любого значения карты

        if self.trump_suit:
            for idx, player_user in enumerate(self.players):
                player_hand = self._get_player_hand(player_user)
                for card in player_hand:
                    if card['suit'] == self.trump_suit:
                        card_val = self.card_value(card['rank'])
                        if card_val < min_trump_value:
                            min_trump_value = card_val
                            min_trump_holder_idx = idx
        
        if min_trump_holder_idx != -1:
            self.attacker_index = min_trump_holder_idx
        else:
            self.attacker_index = 0

        self.defender_index = (self.attacker_index + 1) % len(self.players) if self.players else 0


    def _initialize_hands_and_trump(self):
        """Раздача карт и определение козыря для новой игры."""
        if not self.players or not self.deck:
            return

        for _ in range(6):
            for player_user in self.players:
                if self.deck:
                    card = self.deck.pop(0)
                    self.player_hands_data.setdefault(str(player_user.id), []).append(card)
        
        if self.deck:
            self.trump_card_revealed = self.deck[0]
            self.trump_suit = self.trump_card_revealed['suit']
        elif self.player_hands_data:
             pass
        else:
            self.trump_suit = None
            self.trump_card_revealed = None


    def _get_player_hand(self, player_user_obj):
        return self.player_hands_data.get(str(player_user_obj.id), [])

    def _remove_card_from_hand(self, player_user_obj, card_index_in_hand: int):
        hand = self._get_player_hand(player_user_obj)
        if 0 <= card_index_in_hand < len(hand):
            removed_card = hand.pop(card_index_in_hand)
            self.player_hands_data[str(player_user_obj.id)] = hand # Обновляем, т.к. pop изменяет
            return removed_card
        return None
    
    def _add_cards_to_hand(self, player_user_obj, cards_to_add: list):
        hand = self._get_player_hand(player_user_obj)
        hand.extend(cards_to_add)
        self.player_hands_data[str(player_user_obj.id)] = hand


    def card_value(self, rank_str):
        values = {'6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        return values.get(rank_str.upper(), 0)

    def _can_beat(self, attack_card, defense_card, trump_suit):
        if defense_card['suit'] == attack_card['suit']:
            return self.card_value(defense_card['rank']) > self.card_value(attack_card['rank'])
        elif defense_card['suit'] == trump_suit and attack_card['suit'] != trump_suit:
            return True
        return False

    def attack(self, attacking_player_user: typing.Any, card_indices: list[int]):
        if not self.players or attacking_player_user != self.players[self.attacker_index]:
            return {'success': False, 'message': "Сейчас не ваш ход для атаки."}

        if not card_indices:
            return {'success': False, 'message': "Нужно выбрать карты для атаки."}

        attacker_hand = list(self._get_player_hand(attacking_player_user)) # Копия
        cards_to_play_objects = []
        # Проверяем индексы и собираем объекты карт
        for idx in sorted(card_indices, reverse=True): # Удаляем с конца, чтобы не сбить индексы
            if 0 <= idx < len(attacker_hand):
                cards_to_play_objects.insert(0, attacker_hand[idx]) # Сохраняем порядок выбора
            else:
                return {'success': False, 'message': f"Неверный индекс карты: {idx}."}
        
        if not cards_to_play_objects:
            return {'success': False, 'message': "Не выбрано ни одной валидной карты."}

        defender_user = self.players[self.defender_index]
        defender_hand_count = len(self._get_player_hand(defender_user))
        
        # Правила атаки/подкидывания
        unbeaten_attack_cards_on_table = [pair['attack_card'] for pair in self.table if not pair.get('defense_card')]
        
        if not self.table or not unbeaten_attack_cards_on_table: # Первая атака в раунде
            if not all(c['rank'] == cards_to_play_objects[0]['rank'] for c in cards_to_play_objects):
                return {'success': False, 'message': "Для первой атаки все карты должны быть одного ранга."}
            if len(cards_to_play_objects) > defender_hand_count:
                 return {'success': False, 'message': f"Нельзя атаковать большим количеством карт ({len(cards_to_play_objects)}), чем есть у защищающегося ({defender_hand_count})."}
            if len(cards_to_play_objects) > 6: # Максимум 6 карт на стол за раунд
                 return {'success': False, 'message': "Нельзя атаковать более чем 6 картами за раунд."}
        else: # Подкидывание
            if len(self.table) + len(cards_to_play_objects) > 6:
                return {'success': False, 'message': "Слишком много карт на столе (максимум 6)."}
            
            allowed_ranks_for_throw_in = set(c['rank'] for c in unbeaten_attack_cards_on_table)
            # Также можно подкидывать ранги отбитых карт в этом же раунде
            for pair in self.table:
                if pair.get('defense_card'): # Если карта отбита
                    allowed_ranks_for_throw_in.add(pair['attack_card']['rank'])
                    allowed_ranks_for_throw_in.add(pair['defense_card']['rank'])
            
            if not all(c['rank'] in allowed_ranks_for_throw_in for c in cards_to_play_objects):
                return {'success': False, 'message': "Карты для подкидывания должны совпадать по рангу с картами на столе."}
            
            # Нельзя подкинуть больше карт, чем останется у защищающегося после текущих не отбитых атак
            # И не больше, чем было у него в начале раунда.
            # И не больше 6 карт всего на столе.
            max_throw_in = defender_hand_count - len(unbeaten_attack_cards_on_table)
            if len(cards_to_play_objects) > max_throw_in and max_throw_in >=0 : # Если max_throw_in <0, значит уже нельзя подкидывать
                 return {'success': False, 'message': f"Нельзя подкинуть больше карт ({len(cards_to_play_objects)}), чем может отбить защищающийся ({max_throw_in})."}


        # Если все проверки пройдены, играем карты
        for card_obj_to_play in cards_to_play_objects:
            # Ищем карту в реальной руке по id (или rank/suit, если id нет), чтобы получить правильный индекс
            actual_hand = self._get_player_hand(attacking_player_user)
            try:
                card_idx_to_remove = actual_hand.index(card_obj_to_play) # Ищем точный объект карты
                removed_card = self._remove_card_from_hand(attacking_player_user, card_idx_to_remove)
                if removed_card:
                    self.table.append({'attack_card': removed_card, 'defense_card': None, 'attacker_id': attacking_player_user.id})
                else: # Не должно произойти
                    return {'success': False, 'message': "Внутренняя ошибка: не удалось удалить карту из руки."}
            except ValueError: # Карта не найдена (не должно произойти, если cards_to_play_objects из копии руки)
                 return {'success': False, 'message': "Внутренняя ошибка: карта для хода не найдена в руке."}
        
        self.save_game_state()
        return {'success': True, 'message': "Атака совершена."}


    def defend(self, defending_player_user: typing.Any, attack_card_table_index: int, defense_card_hand_index: int):
        if not self.players or defending_player_user != self.players[self.defender_index]:
            return {'success': False, 'message': "Сейчас не ваш ход для защиты."}
        
        if not (0 <= attack_card_table_index < len(self.table)):
            return {'success': False, 'message': "Неверный индекс атакующей карты на столе."}

        table_pair = self.table[attack_card_table_index]
        if table_pair.get('defense_card'):
            return {'success': False, 'message': "Эта карта уже отбита."}

        attack_card = table_pair['attack_card']
        
        defender_hand = self._get_player_hand(defending_player_user)
        if not (0 <= defense_card_hand_index < len(defender_hand)):
            return {'success': False, 'message': "Неверный индекс карты в руке для защиты."}
        
        defense_card_obj = defender_hand[defense_card_hand_index]

        if self._can_beat(attack_card, defense_card_obj, self.trump_suit):
            removed_defense_card = self._remove_card_from_hand(defending_player_user, defense_card_hand_index)
            if removed_defense_card: # Должен быть равен defense_card_obj
                table_pair['defense_card'] = removed_defense_card
                table_pair['defender_id'] = defending_player_user.id
                self.save_game_state()
                return {'success': True, 'message': "Карта отбита."}
            else: # Не должно случиться
                 return {'success': False, 'message': "Внутренняя ошибка при удалении карты защиты."}
        else:
            return {'success': False, 'message': "Этой картой нельзя отбиться."}

    def _deal_cards_after_round(self):
        # Порядок добора: сначала атакующий, потом подкидывавшие (по порядку), потом защищавшийся (если отбился).
        # Это упрощенная версия, просто по кругу, начиная с атакующего.
        # Нужна более сложная логика отслеживания, кто подкидывал.
        
        # Собираем всех, кто участвовал в раунде и нуждается в доборе
        players_to_deal = []
        # Атакующий
        attacker_user = self.players[self.attacker_index]
        if len(self._get_player_hand(attacker_user)) < 6:
            players_to_deal.append(attacker_user)
        
        # Уникальные ID подкидывавших (не включая основного атакующего)
        thrower_ids = set()
        for pair in self.table:
            if pair.get('attacker_id') and pair['attacker_id'] != attacker_user.id:
                thrower_ids.add(pair['attacker_id'])
        
        for pid in thrower_ids:
            try:
                thrower_user = User.objects.get(id=pid)
                if len(self._get_player_hand(thrower_user)) < 6 and thrower_user not in players_to_deal:
                    players_to_deal.append(thrower_user)
            except User.DoesNotExist:
                pass

        defender_user = self.players[self.defender_index]
        all_defended_in_table = all(p.get('defense_card') for p in self.table) if self.table else True
        if all_defended_in_table and len(self._get_player_hand(defender_user)) < 6 and defender_user not in players_to_deal:
            players_to_deal.append(defender_user)

        for player_user_to_deal in players_to_deal:
            hand = self._get_player_hand(player_user_to_deal)
            while len(hand) < 6 and self.deck:
                card = self.deck.pop(0)
                hand.append(card)
            self.player_hands_data[str(player_user_to_deal.id)] = hand
        
        if self.trump_card_revealed and self.trump_card_revealed not in self.deck:
            taken_into_hand = False
            for hand_cards in self.player_hands_data.values():
                if self.trump_card_revealed in hand_cards:
                    taken_into_hand = True
                    break
            if taken_into_hand:
                if not self.deck:
                    self.trump_card_revealed = None


    def take_cards_action(self, taking_player_user: typing.Any):
        if not self.players or taking_player_user != self.players[self.defender_index]:
            return {'success': False, 'message': "Только защищающийся игрок может взять карты."}
        
        if not self.table: # Нечего брать
             return {'success': False, 'message': "Нет карт на столе, чтобы взять."}

        cards_to_take_from_table = []
        for pair in self.table:
            cards_to_take_from_table.append(pair['attack_card'])
            if pair.get('defense_card'): # Если была попытка отбиться, но игрок все равно берет
                cards_to_take_from_table.append(pair['defense_card'])
        
        self._add_cards_to_hand(taking_player_user, cards_to_take_from_table)
        
        self.table = []
        self._deal_cards_after_round()
        
        self.attacker_index = (self.defender_index + 1) % len(self.players)
        self.defender_index = (self.attacker_index + 1) % len(self.players)
        
        game_end_result = self._check_game_over_conditions()
        if game_end_result:
            self.save_game_state(game_over_result=game_end_result)
            return {**game_end_result, 'message': game_end_result.get('message', "Игра завершена.")}

        self.save_game_state()
        return {'success': True, 'message': "Карты взяты."}

    def pass_or_bito_action(self, acting_player_user: typing.Any):
        all_cards_on_table_defended = True
        has_unbeaten_cards = False
        if not self.table:
            return {'success': False, 'message': "Стол пуст, действие 'пас/бито' не применимо."}

        for pair in self.table:
            if not pair.get('defense_card'):
                all_cards_on_table_defended = False
                has_unbeaten_cards = True
                break
        if all_cards_on_table_defended:
            self.table = []
            self._deal_cards_after_round()

            game_end_result = self._check_game_over_conditions()
            if game_end_result:
                self.save_game_state(game_over_result=game_end_result)
                return {**game_end_result, 'message': game_end_result.get('message', "Бито! Игра завершена.")}

            self.attacker_index = self.defender_index
            self.defender_index = (self.attacker_index + 1) % len(self.players)
            
            self.save_game_state()
            return {'success': True, 'action_type': 'bito', 'message': "Бито! Раунд завершен."}
        elif has_unbeaten_cards:
            self.save_game_state()
            return {'success': True, 'action_type': 'attacker_passed', 'message': "Атакующий спасовал. Защищающийся должен действовать или другие могут подкинуть."}
        
        return {'success': False, 'message': "Не удалось определить действие 'пас/бито'."} # Не должно сюда дойти


    def _check_game_over_conditions(self):
        if not self.deck:
            players_with_cards_count = 0
            last_player_with_cards = None
            winners = []

            for player_user in self.players:
                if self._get_player_hand(player_user):
                    players_with_cards_count += 1
                    last_player_with_cards = player_user
                else:
                    if not self.room.winner or self.room.winner != player_user :
                         pass

            if players_with_cards_count == 0:
                return {'game_over': True, 'is_draw': True, 'winner': None, 'loser': None, 'message': "Игра окончена! Ничья."}
            
            if players_with_cards_count == 1:
                loser = last_player_with_cards
                winner = self.room.winner if self.room.winner and self.room.winner != loser else None
                
                if not winner and len(self.players) == 2:
                    winner = next(p for p in self.players if p != loser)

                return {'game_over': True, 'is_draw': False, 'winner': winner, 'loser': loser, 'message': f"Игра окончена! Проигравший: {loser.username}."}
            

        if self.deck:
            for player_user in self.players:
                if not self._get_player_hand(player_user) and not self.room.winner:
                    pass 
        return None

    def get_game_state(self, for_player_user_obj: typing.Any = None):

        game_status = self.game_model_instance.status if self.game_model_instance else self.room.status
        winner_username = self.room.winner.username if self.room.winner else None
        
        game_over_info = self._check_game_over_conditions()
        if game_over_info and game_over_info['game_over']:
            game_status = GameRoom.STATUS_FINISHED
            if game_over_info.get('winner'):
                winner_username = game_over_info['winner'].username
            elif game_over_info.get('is_draw'):
                 winner_username = "Ничья"
        
        state = {
            'room_id': str(self.room.id),
            'players': [],
            'attacker_username': self.players[self.attacker_index].username if self.players else "N/A",
            'defender_username': self.players[self.defender_index].username if self.players else "N/A",
            'trump_suit': self.trump_suit,
            'trump_card_revealed': self.trump_card_revealed,
            'deck_count': len(self.deck),
            'table': self.table, 
            'status': game_status,
            'winner': winner_username,
            'is_game_over': game_over_info['game_over'] if game_over_info else False,
            'game_over_message': game_over_info.get('message') if game_over_info else None,
        }

        for idx, player_user_loop in enumerate(self.players):
            player_id_str = str(player_user_loop.id)
            hand_cards = self._get_player_hand(player_user_loop)
            player_data = {
                'id': player_user_loop.id,
                'username': player_user_loop.username,
                'card_count': len(hand_cards),
                'is_attacker': idx == self.attacker_index,
                'is_defender': idx == self.defender_index,
                'is_current_player_for_state': player_user_loop == for_player_user_obj,
            }

            if player_user_loop == for_player_user_obj or game_status == GameRoom.STATUS_FINISHED:
                player_data['cards'] = []
                for card_idx_in_hand, card_in_hand in enumerate(hand_cards):
                     player_data['cards'].append({
                        'rank': card_in_hand['rank'],
                        'suit': card_in_hand['suit'],
                        'id': card_in_hand.get('id', f"{card_in_hand['rank']}-{card_in_hand['suit']}"),
                        'image_url': self._get_card_image_url(card_in_hand),
                    })
            state['players'].append(player_data)

        for table_pair in state['table']:
            if table_pair.get('attack_card'):
                table_pair['attack_card']['image_url'] = self._get_card_image_url(table_pair['attack_card'])
            if table_pair.get('defense_card'):
                table_pair['defense_card']['image_url'] = self._get_card_image_url(table_pair['defense_card'])
        
        if state['trump_card_revealed']:
            state['trump_card_revealed']['image_url'] = self._get_card_image_url(state['trump_card_revealed'])

        return state

    def _get_card_image_url(self, card_dict):
        if not card_dict or not card_dict.get('suit') or not card_dict.get('rank'):
            return os.path.join(settings.STATIC_URL, 'cards/back.png')
        
        suit = card_dict['suit'].lower()
        rank = card_dict['rank'].upper()
        return f"{settings.STATIC_URL}cards/{suit}/{rank}.png"


    def save_game_state(self, game_over_result=None):
        if not self.game_model_instance:
            return 

        with transaction.atomic():
            game = self.game_model_instance

            current_attacker_user = self.players[self.attacker_index] if self.players and 0 <= self.attacker_index < len(self.players) else None
            game.current_turn = current_attacker_user
            game.trump_suit = self.trump_suit
            game.trump_card_revealed = self.trump_card_revealed
            game.deck = self.deck
            game.table = self.table
            game.player_hands = self.player_hands_data

            is_game_really_over = game_over_result and game_over_result.get('game_over', False)

            if is_game_really_over:
                game.status = 'finished'
                self.room.status = GameRoom.STATUS_FINISHED
                winner_obj = game_over_result.get('winner')
                loser_obj = game_over_result.get('loser')
                is_draw = game_over_result.get('is_draw', False)

                if winner_obj and not self.room.winner :
                    self.room.winner = winner_obj
                
                self.room.end_game(winner=winner_obj, loser=loser_obj, is_draw=is_draw)
            else:
                game.status = 'active'
                self.room.status = GameRoom.STATUS_PLAYING
            
            game.save()