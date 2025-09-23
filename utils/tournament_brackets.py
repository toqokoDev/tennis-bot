"""
Модуль для генерации турнирных сеток
Поддерживает олимпийскую систему и круговую систему
"""

import math
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class Player:
    """Класс для представления игрока в турнире"""
    id: str
    name: str
    photo_url: str = None
    initial: str = None


@dataclass
class Match:
    """Класс для представления матча в турнире"""
    id: str
    round: int
    match_number: int
    player1: Player = None
    player2: Player = None
    winner: Player = None
    score: str = None
    is_bye: bool = False


class TournamentBracket:
    """Базовый класс для турнирных сеток"""
    
    def __init__(self, players: List[Player], tournament_type: str):
        self.players = players
        self.tournament_type = tournament_type
        self.matches: List[Match] = []
        self.rounds: List[List[Match]] = []
        
    def generate_bracket(self) -> Dict[str, Any]:
        """Генерирует турнирную сетку"""
        raise NotImplementedError


class OlympicBracket(TournamentBracket):
    """Класс для олимпийской системы (на выбывание)"""
    
    def __init__(self, players: List[Player]):
        super().__init__(players, "Олимпийская система")
        self.generate_bracket()
    
    def generate_bracket(self) -> Dict[str, Any]:
        """Генерирует сетку олимпийской системы"""
        if len(self.players) < 2:
            return {"rounds": [], "total_rounds": 0}
        
        # Добавляем пустых игроков до степени двойки
        players_count = len(self.players)
        bracket_size = 2 ** math.ceil(math.log2(players_count))
        
        # Создаем список игроков с пустыми слотами
        bracket_players = self.players.copy()
        while len(bracket_players) < bracket_size:
            bracket_players.append(Player(id="bye", name="BYE", initial="BYE"))
        
        # Определяем количество раундов
        total_rounds = int(math.log2(bracket_size))
        
        # Генерируем матчи для каждого раунда
        current_players = bracket_players.copy()
        
        for round_num in range(total_rounds):
            round_matches = []
            next_round_players = []
            
            for i in range(0, len(current_players), 2):
                player1 = current_players[i]
                player2 = current_players[i + 1] if i + 1 < len(current_players) else None
                
                match_id = f"round_{round_num}_match_{i//2}"
                match = Match(
                    id=match_id,
                    round=round_num,
                    match_number=i//2,
                    player1=player1,
                    player2=player2,
                    is_bye=(player1.id == "bye" or (player2 and player2.id == "bye"))
                )
                
                round_matches.append(match)
                
                # Определяем победителя для следующего раунда
                if player1.id == "bye" and player2:
                    next_round_players.append(player2)
                elif player2 and player2.id == "bye":
                    next_round_players.append(player1)
                elif player1.id != "bye" and player2 and player2.id != "bye":
                    # Оба игрока реальные - добавляем пустого игрока для следующего раунда
                    next_round_players.append(Player(id="pending", name="TBD", initial="TBD"))
            
            self.rounds.append(round_matches)
            self.matches.extend(round_matches)
            current_players = next_round_players
        
        return {
            "rounds": self.rounds,
            "total_rounds": total_rounds,
            "bracket_size": bracket_size,
            "type": "Олимпийская система"
        }


class RoundRobinBracket(TournamentBracket):
    """Класс для круговой системы"""
    
    def __init__(self, players: List[Player]):
        super().__init__(players, "Круговая")
        self.generate_bracket()
    
    def generate_bracket(self) -> Dict[str, Any]:
        """Генерирует сетку круговой системы"""
        if len(self.players) < 2:
            return {"rounds": [], "total_rounds": 0}
        
        players_count = len(self.players)
        
        # Для круговой системы каждый играет с каждым
        # Количество матчей = n * (n-1) / 2
        total_matches = players_count * (players_count - 1) // 2
        
        # Разбиваем матчи на раунды (каждый игрок играет максимум один матч за раунд)
        rounds = []
        used_pairs = set()
        
        round_num = 0
        while len(used_pairs) < total_matches:
            round_matches = []
            round_players = set()
            
            # Создаем матчи для текущего раунда
            for i, player1 in enumerate(self.players):
                if player1.id in round_players:
                    continue
                    
                for j, player2 in enumerate(self.players[i+1:], i+1):
                    if player2.id in round_players:
                        continue
                    
                    pair_key = tuple(sorted([player1.id, player2.id]))
                    if pair_key not in used_pairs:
                        match_id = f"round_{round_num}_match_{len(round_matches)}"
                        match = Match(
                            id=match_id,
                            round=round_num,
                            match_number=len(round_matches),
                            player1=player1,
                            player2=player2
                        )
                        
                        round_matches.append(match)
                        used_pairs.add(pair_key)
                        round_players.add(player1.id)
                        round_players.add(player2.id)
                        break
            
            if round_matches:
                rounds.append(round_matches)
                self.matches.extend(round_matches)
                round_num += 1
        
        self.rounds = rounds
        
        return {
            "rounds": rounds,
            "total_rounds": len(rounds),
            "total_matches": total_matches,
            "type": "Круговая"
        }


def create_tournament_bracket(players: List[Player], tournament_type: str) -> TournamentBracket:
    """Создает турнирную сетку в зависимости от типа турнира"""
    if tournament_type == "Олимпийская система":
        return OlympicBracket(players)
    elif tournament_type == "Круговая":
        return RoundRobinBracket(players)
    else:
        raise ValueError(f"Неизвестный тип турнира: {tournament_type}")


def format_bracket_text(bracket: TournamentBracket) -> str:
    """Форматирует турнирную сетку в текстовом виде"""
    result = f"🏆 Турнирная сетка ({bracket.tournament_type})\n\n"
    
    for round_num, round_matches in enumerate(bracket.rounds):
        result += f"📋 Раунд {round_num + 1}:\n"
        
        for match in round_matches:
            if match.is_bye:
                if match.player1.id == "bye":
                    result += f"  🆓 {match.player2.name} (автоматически в следующий раунд)\n"
                else:
                    result += f"  🆓 {match.player1.name} (автоматически в следующий раунд)\n"
            else:
                player1_name = match.player1.name if match.player1 else "TBD"
                player2_name = match.player2.name if match.player2 else "TBD"
                
                if match.winner:
                    winner_name = match.winner.name
                    if match.winner == match.player1:
                        result += f"  🥇 {player1_name} vs {player2_name} → {winner_name} {match.score or ''}\n"
                    else:
                        result += f"  🥇 {player2_name} vs {player1_name} → {winner_name} {match.score or ''}\n"
                else:
                    result += f"  ⚔️ {player1_name} vs {player2_name}\n"
        
        result += "\n"
    
    return result


def get_player_initial(player: Player) -> str:
    """Получает инициалы игрока"""
    if player.initial:
        return player.initial
    
    if player.name and len(player.name) > 0:
        words = player.name.split()
        if len(words) >= 2:
            return f"{words[0][0].upper()}{words[1][0].upper()}"
        else:
            return player.name[0].upper()
    
    return "??"
