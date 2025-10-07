from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Player:
    id: str
    name: str
    photo_url: Optional[str] = None
    initial: Optional[str] = None


@dataclass
class Match:
    player1: Optional[Player]
    player2: Optional[Player]
    winner: Optional[Player] = None
    score: Optional[str] = None
    is_bye: bool = False
    match_number: int = 0
    is_placement: bool = False  # Флаг для игр за места


@dataclass
class TournamentBracket:
    players: List[Player]
    matches: List[Match]
    rounds: List[List[Match]]
    placement_matches: List[Match] = None  # Игры за места
    additional_tournaments: List['TournamentBracket'] = None  # Дополнительные мини-турниры
    tournament_type: str = "Олимпийская система"
    name: str = "Турнир"


__all__ = ["Player", "Match", "TournamentBracket"]
