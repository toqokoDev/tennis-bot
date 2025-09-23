"""
Модуль для управления турнирами и автоматического старта
"""

import logging
import math
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.tournament_brackets import create_tournament_bracket, Player, Match
from services.storage import storage
from config.tournament_config import MIN_PARTICIPANTS

logger = logging.getLogger(__name__)


class TournamentManager:
    """Класс для управления турнирами"""
    
    def __init__(self):
        self.storage = storage
    
    async def check_tournament_readiness(self, tournament_id: str) -> bool:
        """Проверяет, готов ли турнир к старту"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        
        if not tournament_data:
            return False
        
        participants = tournament_data.get('participants', {})
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
        
        return len(participants) >= min_participants
    
    async def start_tournament(self, tournament_id: str) -> bool:
        """Запускает турнир и проводит жеребьевку"""
        try:
            tournaments = await self.storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            
            if not tournament_data:
                logger.error(f"Турнир {tournament_id} не найден")
                return False
            
            participants = tournament_data.get('participants', {})
            tournament_type = tournament_data.get('type', 'Олимпийская система')
            
            # Проводим жеребьевку
            matches = self._conduct_draw(participants, tournament_type, tournament_id)
            
            # Обновляем статус турнира
            tournament_data['status'] = 'started'
            tournament_data['started_at'] = datetime.now().isoformat()
            tournament_data['matches'] = matches
            tournament_data['current_round'] = 0
            
            tournaments[tournament_id] = tournament_data
            await self.storage.save_tournaments(tournaments)
            
            logger.info(f"Турнир {tournament_id} успешно запущен с {len(matches)} матчами")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска турнира {tournament_id}: {e}")
            return False
    
    def _conduct_draw(self, participants: Dict[str, Any], tournament_type: str, tournament_id: str) -> List[Dict[str, Any]]:
        """Проводит жеребьевку для турнира"""
        import random
        
        matches = []
        participant_ids = list(participants.keys())
        
        if tournament_type == "Олимпийская система":
            # Олимпийская система - случайная жеребьевка
            random.shuffle(participant_ids)
            
            # Добавляем BYE если нужно
            bracket_size = 2 ** math.ceil(math.log2(len(participant_ids)))
            while len(participant_ids) < bracket_size:
                participant_ids.append("BYE")
            
            # Создаем матчи первого раунда
            for i in range(0, len(participant_ids), 2):
                player1_id = participant_ids[i]
                player2_id = participant_ids[i + 1] if i + 1 < len(participant_ids) else None
                
                match_data = {
                    'id': f"{tournament_id}_round_0_match_{i//2}",
                    'tournament_id': tournament_id,
                    'round': 0,
                    'match_number': i // 2,
                    'player1_id': player1_id if player1_id != "BYE" else None,
                    'player2_id': player2_id if player2_id != "BYE" else None,
                    'player1_name': participants[player1_id]['name'] if player1_id != "BYE" else "BYE",
                    'player2_name': participants[player2_id]['name'] if player2_id != "BYE" else "BYE",
                    'winner_id': None,
                    'score': None,
                    'status': 'pending',
                    'is_bye': player1_id == "BYE" or player2_id == "BYE",
                    'created_at': datetime.now().isoformat()
                }
                matches.append(match_data)
                
        elif tournament_type == "Круговая":
            # Круговая система - каждый с каждым
            random.shuffle(participant_ids)
            
            for i, player1_id in enumerate(participant_ids):
                for j, player2_id in enumerate(participant_ids[i+1:], i+1):
                    match_data = {
                        'id': f"{tournament_id}_round_0_match_{len(matches)}",
                        'tournament_id': tournament_id,
                        'round': 0,
                        'match_number': len(matches),
                        'player1_id': player1_id,
                        'player2_id': player2_id,
                        'player1_name': participants[player1_id]['name'],
                        'player2_name': participants[player2_id]['name'],
                        'winner_id': None,
                        'score': None,
                        'status': 'pending',
                        'is_bye': False,
                        'created_at': datetime.now().isoformat()
                    }
                    matches.append(match_data)
        
        return matches
    
    async def get_tournament_matches(self, tournament_id: str) -> List[Dict[str, Any]]:
        """Получает матчи турнира"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        return tournament_data.get('matches', [])
    
    async def get_current_round_matches(self, tournament_id: str) -> List[Dict[str, Any]]:
        """Получает матчи текущего раунда"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        current_round = tournament_data.get('current_round', 0)
        matches = tournament_data.get('matches', [])
        
        return [match for match in matches if match['round'] == current_round]
    
    async def get_available_opponents(self, tournament_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Получает доступных соперников для пользователя в турнире"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        matches = tournament_data.get('matches', [])
        
        print(f"DEBUG: tournament_id={tournament_id}, user_id={user_id}")
        print(f"DEBUG: tournament_type={tournament_type}")
        print(f"DEBUG: matches count={len(matches)}")
        
        available_opponents = []
        
        if tournament_type == "Олимпийская система":
            # В олимпийской системе ищем матч с этим пользователем
            for match in matches:
                print(f"DEBUG: match={match}")
                if match['status'] == 'pending' and not match.get('is_bye', False):
                    if match['player1_id'] == user_id:
                        # Пользователь играет против player2
                        opponent_data = {
                            'user_id': match['player2_id'],
                            'name': match['player2_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent1: {opponent_data}")
                    elif match['player2_id'] == user_id:
                        # Пользователь играет против player1
                        opponent_data = {
                            'user_id': match['player1_id'],
                            'name': match['player1_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent2: {opponent_data}")
                        
        elif tournament_type == "Круговая":
            # В круговой системе ищем все незавершенные матчи с этим пользователем
            for match in matches:
                print(f"DEBUG: match={match}")
                if match['status'] == 'pending' and not match.get('is_bye', False):
                    if match['player1_id'] == user_id:
                        opponent_data = {
                            'user_id': match['player2_id'],
                            'name': match['player2_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent1: {opponent_data}")
                    elif match['player2_id'] == user_id:
                        opponent_data = {
                            'user_id': match['player1_id'],
                            'name': match['player1_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent2: {opponent_data}")
        
        print(f"DEBUG: available_opponents={available_opponents}")
        return available_opponents
    
    async def update_match_result(self, match_id: str, winner_id: str, score: str) -> bool:
        """Обновляет результат матча"""
        try:
            tournaments = await self.storage.load_tournaments()
            
            # Находим турнир и матч
            for tournament_id, tournament_data in tournaments.items():
                matches = tournament_data.get('matches', [])
                for match in matches:
                    if match['id'] == match_id:
                        match['winner_id'] = winner_id
                        match['score'] = score
                        match['status'] = 'completed'
                        match['completed_at'] = datetime.now().isoformat()
                        
                        # Сохраняем изменения
                        tournaments[tournament_id] = tournament_data
                        await self.storage.save_tournaments(tournaments)
                        
                        logger.info(f"Результат матча {match_id} обновлен: {winner_id} победил со счетом {score}")
                        return True
            
            logger.error(f"Матч {match_id} не найден")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка обновления результата матча {match_id}: {e}")
            return False
    
    async def advance_tournament_round(self, tournament_id: str) -> bool:
        """Переводит турнир на следующий раунд"""
        try:
            tournaments = await self.storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            
            if not tournament_data:
                return False
            
            current_round = tournament_data.get('current_round', 0)
            matches = tournament_data.get('matches', [])
            
            # Проверяем, завершены ли все матчи текущего раунда
            current_round_matches = [match for match in matches if match['round'] == current_round]
            completed_matches = [match for match in current_round_matches if match['status'] == 'completed']
            
            if len(completed_matches) == len(current_round_matches):
                # Переходим к следующему раунду
                tournament_data['current_round'] = current_round + 1
                tournaments[tournament_id] = tournament_data
                await self.storage.save_tournaments(tournaments)
                
                logger.info(f"Турнир {tournament_id} переведен на раунд {current_round + 1}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка перевода турнира {tournament_id} на следующий раунд: {e}")
            return False
    
    async def get_tournament_standings(self, tournament_id: str) -> Dict[str, Any]:
        """Получает таблицу результатов турнира"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        participants = tournament_data.get('participants', {})
        matches = tournament_data.get('matches', [])
        
        standings = {}
        
        # Инициализируем статистику для каждого участника
        for user_id in participants.keys():
            standings[user_id] = {
                'name': participants[user_id].get('name', 'Неизвестно'),
                'matches_played': 0,
                'matches_won': 0,
                'matches_lost': 0,
                'points': 0
            }
        
        # Подсчитываем результаты
        for match in matches:
            if match['status'] == 'completed' and not match['is_bye']:
                player1_id = match['player1_id']
                player2_id = match['player2_id']
                winner_id = match['winner_id']
                
                if player1_id in standings:
                    standings[player1_id]['matches_played'] += 1
                    if winner_id == player1_id:
                        standings[player1_id]['matches_won'] += 1
                        standings[player1_id]['points'] += 1
                    else:
                        standings[player1_id]['matches_lost'] += 1
                
                if player2_id in standings:
                    standings[player2_id]['matches_played'] += 1
                    if winner_id == player2_id:
                        standings[player2_id]['matches_won'] += 1
                        standings[player2_id]['points'] += 1
                    else:
                        standings[player2_id]['matches_lost'] += 1
        
        return standings


# Глобальный экземпляр менеджера турниров
tournament_manager = TournamentManager()
