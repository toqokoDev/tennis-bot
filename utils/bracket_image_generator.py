import io
import os
import math
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from config.paths import GAMES_PHOTOS_DIR


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


class BracketImageGenerator:
    """Класс для генерации изображений турнирных сеток в стиле tennis-play.com"""
    
    def __init__(self):
        # Основные размеры
        self.cell_width = 280
        self.cell_height = 60
        self.round_spacing = 100
        self.match_spacing = 20
        self.vertical_margin = 30
        self.font_size = 12
        self.title_font_size = 20
        self.subtitle_font_size = 14
        self.score_font_size = 11
        
        # Цветовая схема как на tennis-play.com
        self.bg_color = (255, 255, 255)  # Белый фон
        self.cell_color = (255, 255, 255)  # Белый фон ячейки
        self.cell_border_color = (209, 213, 219)  # Серый бордер
        self.text_color = (31, 41, 55)  # Темно-серый текст
        self.secondary_text_color = (107, 114, 128)  # Серый текст
        self.winner_color = (31, 41, 55)  # Темный для победителя (жирный)
        self.winner_bg_color = (220, 252, 231)  # Светло-зеленый фон победителя
        self.connector_color = (156, 163, 175)  # Цвет соединительных линий
        self.round_title_color = (59, 130, 246)  # Синий для заголовков раундов
        self.placement_color = (139, 69, 19)  # Коричневый для игр за мест
        self.mini_tournament_color = (101, 163, 13)  # Зеленый для мини-турниров (не использовать для оформления)
        
        # Загрузка шрифтов с Unicode-фолбэком
        try:
            self.font = ImageFont.truetype("arial.ttf", self.font_size)
            self.bold_font = ImageFont.truetype("arialbd.ttf", self.font_size)
            self.title_font = ImageFont.truetype("arialbd.ttf", self.title_font_size)
            self.subtitle_font = ImageFont.truetype("arialbd.ttf", self.subtitle_font_size)
            self.score_font = ImageFont.truetype("arial.ttf", self.score_font_size)
        except Exception:
            # Пытаемся DejaVuSans (обычно доступен в Pillow)
            try:
                self.font = ImageFont.truetype("DejaVuSans.ttf", self.font_size)
                self.bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.font_size)
                self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.title_font_size)
                self.subtitle_font = ImageFont.truetype("DejaVuSans.ttf", self.subtitle_font_size)
                self.score_font = ImageFont.truetype("DejaVuSans.ttf", self.score_font_size)
            except Exception:
                # Последний фолбэк — дефолтный, но он может не поддерживать кириллицу
                try:
                    self.font = ImageFont.load_default()
                    self.bold_font = ImageFont.load_default()
                    self.title_font = ImageFont.load_default()
                    self.subtitle_font = ImageFont.load_default()
                    self.score_font = ImageFont.load_default()
                except Exception:
                    self.font = None
                    self.bold_font = None
                    self.title_font = None
                    self.subtitle_font = None
                    self.score_font = None
    
    def create_player_avatar(self, player: Player, size: int = 24) -> Image.Image:
        """Создает квадратный аватар игрока"""
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        
        # Если фото нет, создаем простой квадрат с цветом
        color = (100, 150, 200)
        draw.rectangle([0, 0, size, size], fill=color)
        
        # Инициалы
        initials = self._get_player_initials(player)
        if self.font:
            try:
                bbox = draw.textbbox((0, 0), initials, font=self.font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (size - text_width) // 2
                y = (size - text_height) // 2
                draw.text((x, y), initials, fill=(255, 255, 255), font=self.font)
            except:
                pass
        
        return avatar
    
    def _get_player_initials(self, player: Player) -> str:
        """Получает инициалы игрока"""
        if player.initial:
            return player.initial
        
        name_parts = player.name.split()
        if len(name_parts) >= 2:
            return f"{name_parts[0][0]}{name_parts[1][0]}".upper()
        elif len(name_parts) == 1:
            return name_parts[0][0].upper()
        else:
            return "??"
    
    def draw_match_cell(self, draw: ImageDraw.Draw, x: int, y: int, match: Match, round_num: int = 0, 
                       is_placement: bool = False, is_mini_tournament: bool = False) -> None:
        """Рисует ячейку матча в стиле tennis-play.com"""
        if not match:
            return
        
        # Цвета для разных типов матчей
        if is_mini_tournament:
            # Для мини-турниров не используем зеленый цвет границ
            border_color = self.cell_border_color
        elif is_placement:
            border_color = self.placement_color
        else:
            border_color = self.cell_border_color
        
        # Фон ячейки
        draw.rectangle([x, y, x + self.cell_width, y + self.cell_height], 
                      fill=self.cell_color, outline=border_color, width=1)
        
        # Информация о матче
        player1 = match.player1
        player2 = match.player2
        
        # Рисуем игроков
        player_height = self.cell_height // 2
        player_y = y
        
        # Игрок 1
        if player1:
            self._draw_player_in_cell(draw, player1, x, player_y, self.cell_width, player_height, 
                                    match.winner == player1, is_placement or is_mini_tournament)
        
        # Разделительная линия
        draw.line([x, y + player_height, x + self.cell_width, y + player_height], 
                 fill=border_color, width=1)
        
        # Игрок 2
        if player2:
            self._draw_player_in_cell(draw, player2, x, y + player_height, self.cell_width, player_height, 
                                    match.winner == player2, is_placement or is_mini_tournament)
        
        # Рисуем счет над разделительной линией внутри ячейки (без фона)
        if match.score and self.score_font:
            try:
                # Центрируем относительно ширины ячейки
                score_text = str(match.score)
                bbox = draw.textbbox((0, 0), score_text, font=self.score_font)
                text_w = bbox[2] - bbox[0]
                score_x = x + (self.cell_width - text_w) // 2
                score_y = y + (self.cell_height // 2) - 18
                draw.text((score_x, score_y), score_text, fill=self.text_color, font=self.score_font)
            except:
                pass
    
    def _draw_player_in_cell(self, draw: ImageDraw.Draw, player: Player, x: int, y: int, width: int, height: int, 
                           is_winner: bool, is_special: bool = False):
        """Рисует информацию об игроке в ячейке"""
        # Аватар
        avatar_size = 20
        avatar = self.create_player_avatar(player, avatar_size)
        if avatar:
            draw._image.paste(avatar, (x + 5, y + (height - avatar_size) // 2), avatar)
        
        # Имя игрока
        name_x = x + 30
        name_y = y + (height - 12) // 2
        
        # Для победителя используем жирный шрифт, для остальных обычный
        font = self.bold_font if is_winner else self.font
        color = self.winner_color if is_winner else self.text_color
        
        if font:
            display_name = player.name[:15] + "..." if len(player.name) > 15 else player.name
            draw.text((name_x, name_y), display_name, fill=color, font=font)
            
    
    def draw_connectors(self, draw: ImageDraw.Draw, round_positions: List[List[Tuple[int, int]]], 
                       is_mini_tournament: bool = False):
        """Рисует соединительные линии между раундами"""
        connector_color = self.connector_color
        
        for round_num in range(len(round_positions) - 1):
            current_round = round_positions[round_num]
            next_round = round_positions[round_num + 1]
            
            for match_num in range(len(next_round)):
                # Позиция матча в следующем раунде
                next_x, next_y = next_round[match_num]
                next_center_y = next_y + self.cell_height // 2
                
                # Позиции соответствующих матчей в текущем раунде
                prev_match1_idx = match_num * 2
                prev_match2_idx = match_num * 2 + 1
                
                if prev_match1_idx < len(current_round):
                    prev_x, prev_y = current_round[prev_match1_idx]
                    prev_center_y = prev_y + self.cell_height // 2
                    
                    # Горизонтальная линия от предыдущего матча
                    draw.line([prev_x + self.cell_width, prev_center_y, 
                              next_x - 10, prev_center_y], 
                             fill=connector_color, width=1)
                    
                    # Вертикальная линия
                    draw.line([next_x - 10, prev_center_y, 
                              next_x - 10, next_center_y], 
                             fill=connector_color, width=1)
                
                if prev_match2_idx < len(current_round):
                    prev_x, prev_y = current_round[prev_match2_idx]
                    prev_center_y = prev_y + self.cell_height // 2
                    
                    # Горизонтальная линия от предыдущего матча
                    draw.line([prev_x + self.cell_width, prev_center_y, 
                              next_x - 10, prev_center_y], 
                             fill=connector_color, width=1)
                    
                    # Вертикальная линия
                    draw.line([next_x - 10, prev_center_y, 
                              next_x - 10, next_center_y], 
                             fill=connector_color, width=1)
    
    def generate_olympic_bracket_image(self, bracket: TournamentBracket, photo_paths: Optional[list[str]] = None) -> Image.Image:
        """Генерирует изображение сетки олимпийской системы"""
        try:
            # Вычисляем размеры для основной сетки
            main_bracket_width, main_bracket_height = self.calculate_bracket_dimensions(bracket)
            
            # Вычисляем размеры для мини-турниров
            mini_tournaments_height = 0
            mini_tournaments_width = 0
            
            if bracket.additional_tournaments:
                for mini_tournament in bracket.additional_tournaments:
                    mini_width, mini_height = self.calculate_bracket_dimensions(mini_tournament)
                    mini_tournaments_height += mini_height + 100  # + отступ между турнирами
                    mini_tournaments_width = max(mini_tournaments_width, mini_width)
            
            # Общие размеры изображения
            total_width = max(main_bracket_width + mini_tournaments_width + 100, 1200)
            total_height = main_bracket_height + mini_tournaments_height + 200  # + место для фото
            
            # Создаем изображение
            image = Image.new('RGB', (total_width, total_height), self.bg_color)
            draw = ImageDraw.Draw(image)
            
            # Заголовок турнира
            title = bracket.name
            if self.title_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.title_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text(((total_width - title_width) // 2, 20), title, 
                             fill=self.text_color, font=self.title_font)
                except:
                    pass
            
            # Рисуем основную сетку
            main_bracket_y = 80
            round_positions = self._draw_bracket_grid(draw, bracket, 50, main_bracket_y, main_bracket_width, main_bracket_height)
            
            # Рисуем соединительные линии для основной сетки
            self.draw_connectors(draw, round_positions)
            
            # Рисуем мини-турниры справа от основной сетки
            current_y = main_bracket_y
            if bracket.additional_tournaments:
                for i, mini_tournament in enumerate(bracket.additional_tournaments):
                    tournament_x = main_bracket_width + 100
                    tournament_y = current_y
                    
                    # Заголовок мини-турнира — общий цвет
                    if self.subtitle_font:
                        try:
                            title_bbox = draw.textbbox((0, 0), mini_tournament.name, font=self.subtitle_font)
                            title_width = title_bbox[2] - title_bbox[0]
                            draw.text((tournament_x + (mini_tournaments_width - title_width) // 2, tournament_y - 30), 
                                     mini_tournament.name, fill=self.round_title_color, font=self.subtitle_font)
                        except:
                            pass
                    
                    # Рисуем сетку мини-турнира
                    mini_round_positions = self._draw_mini_tournament_grid(draw, mini_tournament, tournament_x, tournament_y)
                    
                    # Рисуем соединительные линии для мини-турнира
                    self.draw_connectors(draw, mini_round_positions, is_mini_tournament=True)
                    
                    current_y += self.calculate_bracket_dimensions(mini_tournament)[1] + 100
            
            # Рисуем область для фото игр внизу
            photos_y = total_height - 150
            self._draw_game_photos_area(draw, 50, photos_y, total_width - 100, 120, photo_paths or [])
            
            return image
            
        except Exception as e:
            print(f"Ошибка генерации олимпийской сетки: {e}")
            return self._create_error_image(str(e))
    
    def _draw_bracket_grid(self, draw: ImageDraw.Draw, bracket: TournamentBracket, start_x: int, start_y: int, width: int, height: int) -> List[List[Tuple[int, int]]]:
        """Рисует основную сетку турнира и возвращает позиции матчей"""
        round_positions = []
        
        for round_num, round_matches in enumerate(bracket.rounds):
            if not round_matches:
                continue
                
            round_x = start_x + round_num * (self.cell_width + self.round_spacing)
            
            # Заголовок раунда
            round_title = self._get_round_title(round_num, len(bracket.rounds))
            if self.font:
                try:
                    title_bbox = draw.textbbox((0, 0), round_title, font=self.bold_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text((round_x + (self.cell_width - title_width) // 2, start_y - 30), 
                             round_title, fill=self.round_title_color, font=self.bold_font)
                except:
                    pass
            
            # Позиции матчей в раунде
            match_positions = []
            
            for match_num, match in enumerate(round_matches):
                match_y = self._calculate_match_y(round_num, match_num, round_matches, round_positions, start_y, height)
                match_positions.append((round_x, match_y))
                self.draw_match_cell(draw, round_x, match_y, match, round_num)
            
            round_positions.append(match_positions)
        
        return round_positions
    
    def _draw_mini_tournament_grid(self, draw: ImageDraw.Draw, tournament: TournamentBracket, start_x: int, start_y: int) -> List[List[Tuple[int, int]]]:
        """Рисует сетку мини-турнира"""
        round_positions = []
        
        for round_num, round_matches in enumerate(tournament.rounds):
            if not round_matches:
                continue
                
            round_x = start_x + round_num * (self.cell_width + self.round_spacing - 20)  # Более компактно
            
            # Заголовок раунда для мини-турнира
            round_title = self._get_round_title(round_num, len(tournament.rounds))
            if self.font:
                try:
                    title_bbox = draw.textbbox((0, 0), round_title, font=self.font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text((round_x + (self.cell_width - title_width) // 2, start_y - 20), 
                             round_title, fill=self.round_title_color, font=self.font)
                except:
                    pass
            
            # Позиции матчей в раунде
            match_positions = []
            tournament_height = self.calculate_bracket_dimensions(tournament)[1]
            
            for match_num, match in enumerate(round_matches):
                match_y = self._calculate_match_y(round_num, match_num, round_matches, round_positions, start_y, tournament_height)
                match_positions.append((round_x, match_y))
                self.draw_match_cell(draw, round_x, match_y, match, round_num, is_mini_tournament=True)
            
            round_positions.append(match_positions)
        
        return round_positions
    
    def _get_round_title(self, round_num: int, total_rounds: int) -> str:
        """Возвращает заголовок для раунда"""
        if round_num == total_rounds - 1:
            return "Финал"
        elif round_num == total_rounds - 2:
            return "Полуфинал"
        elif round_num == total_rounds - 3:
            return "Четвертьфинал"
        else:
            return f"Раунд {round_num + 1}"
    
    def _calculate_match_y(self, round_num: int, match_num: int, round_matches: List[Match], 
                          round_positions: List[List[Tuple[int, int]]], start_y: int, total_height: int) -> int:
        """Вычисляет Y-позицию для матча"""
        if round_num == 0:
            # Первый раунд - равномерное распределение
            total_matches = len(round_matches)
            return (start_y + match_num * (self.cell_height + self.match_spacing) + 
                    (total_height - start_y - total_matches * (self.cell_height + self.match_spacing)) // 2)
        else:
            # Последующие раунды - позиционируем между матчами предыдущего раунда
            prev_match1_idx = match_num * 2
            prev_match2_idx = match_num * 2 + 1
            
            if (prev_match1_idx < len(round_positions[round_num - 1]) and 
                prev_match2_idx < len(round_positions[round_num - 1])):
                y1 = round_positions[round_num - 1][prev_match1_idx][1] + self.cell_height // 2
                y2 = round_positions[round_num - 1][prev_match2_idx][1] + self.cell_height // 2
                return (y1 + y2) // 2 - self.cell_height // 2
            else:
                # Fallback равномерное распределение
                total_matches = len(round_matches)
                return (start_y + match_num * (self.cell_height + self.match_spacing) + 
                        (total_height - start_y - total_matches * (self.cell_height + self.match_spacing)) // 2)
    
    def _draw_game_photos_area(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int, photo_paths: list[str]):
        """Рисует область для фото игр внизу по всей ширине"""
        try:
            # Заголовок области
            title = "Фото с игр турнира"
            if self.subtitle_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.subtitle_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text((x + (width - title_width) // 2, y + 10), 
                             title, fill=self.text_color, font=self.subtitle_font)
                except:
                    pass
            
            # Рамка области по всей ширине
            draw.rectangle([x, y + 30, x + width, y + height - 10], 
                          fill=(250, 250, 250), outline=self.cell_border_color, width=2)
            
            # Если есть фото — рисуем миниатюры, иначе заглушку
            if photo_paths:
                try:
                    from PIL import Image as PILImage
                    thumb_h = height - 50
                    thumb_w = thumb_h * 4 // 3
                    padding = 10
                    visible = photo_paths[:6]
                    total_w = len(visible) * thumb_w + (len(visible) - 1) * padding
                    start_x = x + (width - total_w) // 2
                    cur_x = start_x
                    for p in visible:
                        try:
                            img = PILImage.open(p)
                            img = img.convert('RGB')
                            img_thumb = img.copy()
                            img_thumb.thumbnail((thumb_w, thumb_h))
                            draw._image.paste(img_thumb, (cur_x, y + 40))
                        except Exception:
                            pass
                        cur_x += thumb_w + padding
                except Exception:
                    pass
            else:
                if self.font:
                    text = "Здесь будут размещены фотографии с турнирных игр"
                    text_bbox = draw.textbbox((0, 0), text, font=self.font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_x = x + (width - text_width) // 2
                    text_y = y + (height - 10) // 2
                    draw.text((text_x, text_y), text, fill=self.secondary_text_color, font=self.font)
                
        except Exception as e:
            print(f"Ошибка отрисовки области для фото: {e}")
    
    def calculate_bracket_dimensions(self, bracket: TournamentBracket) -> Tuple[int, int]:
        """Вычисляет размеры для сетки"""
        try:
            if not bracket.rounds:
                return (400, 200)
            
            # Ширина: учитываем все раунды + отступы
            width = (len(bracket.rounds) * (self.cell_width + self.round_spacing) + 50)
            
            # Высота: учитываем максимальное количество матчей
            max_matches = max(len(round_matches) for round_matches in bracket.rounds)
            height = (max_matches * (self.cell_height + self.match_spacing) + 50)
            
            return (width, height)
            
        except:
            return (400, 200)
    
    def _create_error_image(self, message: str) -> Image.Image:
        """Создает изображение с сообщением об ошибке"""
        image = Image.new('RGB', (600, 300), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        if self.title_font:
            draw.text((50, 50), "Ошибка генерации сетки", fill=(255, 0, 0), font=self.title_font)
        
        if self.font:
            draw.text((50, 100), message, fill=self.text_color, font=self.font)
        
        return image


def create_tournament_from_data() -> TournamentBracket:
    """Создает турнирную сетку на основе данных из примера"""
    # Создаем игроков
    players = [
        Player("1", "Шкирдов Виталий"),
        Player("2", "Максим Кочкин"),
        Player("3", "Александр Нефедов"),
        Player("4", "Шкирдов Сергей"),
        Player("5", "Дмитрий"),
        Player("6", "Сергей Шуваев"),
        Player("7", "Артем Логвинов"),
        Player("8", "Дмитрий Мельников")
    ]
    
    # Основная сетка - 1-ый круг
    round1_matches = [
        Match(players[0], players[1], players[1], "2-6, 1-6"),
        Match(players[2], players[3], players[3], "1-0"),
        Match(players[4], players[5], players[5], "1-7-4"),
        Match(players[6], players[7], players[6], "6-6")
    ]
    
    # Полуфинал
    round2_matches = [
        Match(players[1], players[3], players[1], "6-6"),
        Match(players[5], players[6], players[6], "6-5-6")
    ]
    
    # Финал
    round3_matches = [
        Match(players[1], players[6], players[1], "6-6")
    ]
    
    # Создаем мини-турниры для игр за места
    
    # Турнир за 3-4 места (проигравшие в полуфинале)
    tournament_3_4 = TournamentBracket(
        players=[players[3], players[5]],
        matches=[],
        rounds=[[Match(players[3], players[5], players[3], "6-6")]],
        name="Игра за 3-е место"
    )
    
    # Турнир за 5-8 места (проигравшие в первом круге)
    tournament_5_8 = TournamentBracket(
        players=[players[0], players[2], players[4], players[7]],
        matches=[],
        rounds=[
            [
                Match(players[0], players[2], players[0], "6-1"),
                Match(players[4], players[7], players[4], "6-0")
            ],
            [
                Match(players[0], players[4], players[0], "6-3")
            ]
        ],
        name="За 5-8 места"
    )
    
    main_bracket = TournamentBracket(
        players=players,
        matches=round1_matches + round2_matches + round3_matches,
        rounds=[round1_matches, round2_matches, round3_matches],
        additional_tournaments=[tournament_3_4, tournament_5_8],
        name="Турнир уровни 3.5-4.5 №16",
        tournament_type="Олимпийская система"
    )
    
    return main_bracket


def create_bracket_image(bracket: TournamentBracket) -> Image.Image:
    """Создает изображение турнирной сетки"""
    generator = BracketImageGenerator()
    return generator.generate_olympic_bracket_image(bracket)


def save_bracket_image(bracket: TournamentBracket, filepath: str) -> bool:
    """Сохраняет изображение турнирной сетки в файл"""
    try:
        image = create_bracket_image(bracket)
        image.save(filepath, 'PNG', quality=95)
        return True
    except Exception as e:
        print(f"Ошибка сохранения изображения: {e}")
        return False


def main():
    """Пример использования"""
    # Создаем тестовые данные
    bracket = create_tournament_from_data()
    
    # Генерируем изображение
    image = create_bracket_image(bracket)
    
    # Сохраняем в файл
    image.save("tournament_bracket.png", "PNG")
    print("Изображение турнирной сетки сохранено как 'tournament_bracket.png'")


if __name__ == "__main__":
    main()
    
# ===== Дополнительные вспомогательные функции для интеграции с обработчиками бота =====

def _normalize_players(players_input: List[Any]) -> List[Player]:
    """Преобразует входные объекты игроков к локальному датаклассу Player."""
    normalized: List[Player] = []
    for p in players_input:
        # поддерживаем объекты с атрибутами и словари
        try:
            pid = getattr(p, 'id', None) or p.get('id')
            name = getattr(p, 'name', None) or p.get('name')
            photo_url = getattr(p, 'photo_url', None) or p.get('photo_url')
            initial = getattr(p, 'initial', None) or p.get('initial')
        except AttributeError:
            pid = getattr(p, 'id', None)
            name = getattr(p, 'name', None)
            photo_url = getattr(p, 'photo_url', None)
            initial = getattr(p, 'initial', None)
        normalized.append(Player(id=str(pid), name=str(name or 'Игрок'), photo_url=photo_url, initial=initial))
    return normalized

def _build_olympic_rounds_from_players(players: List[Player]) -> TournamentBracket:
    """Строит структуру раундов для олимпийской сетки из упорядоченного списка игроков."""
    try:
        num_players = len(players)
        if num_players < 2:
            return TournamentBracket(players=players, matches=[], rounds=[[]], name="Турнир", tournament_type="Олимпийская система")

        # Доводим до степени двойки, заполняя пустыми слотами
        bracket_size = 1
        while bracket_size < num_players:
            bracket_size *= 2

        padded_players: List[Optional[Player]] = players[:]
        while len(padded_players) < bracket_size:
            padded_players.append(Player(id=f"empty_{len(padded_players)}", name="Свободное место"))

        # Раунды
        rounds: List[List[Match]] = []
        current_round: List[Match] = []

        # Первый раунд из упорядоченного списка
        for i in range(0, bracket_size, 2):
            p1 = padded_players[i]
            p2 = padded_players[i + 1] if i + 1 < len(padded_players) else None
            current_round.append(Match(player1=p1, player2=p2, match_number=(i // 2)))
        rounds.append(current_round)

        # Остальные раунды (пустые участники TBD)
        matches_in_round = len(current_round)
        while matches_in_round > 1:
            next_round: List[Match] = []
            for m in range(matches_in_round // 2):
                next_round.append(Match(player1=None, player2=None, match_number=m))
            rounds.append(next_round)
            matches_in_round = len(next_round)

        bracket = TournamentBracket(
            players=players,
            matches=[m for rnd in rounds for m in rnd],
            rounds=rounds,
            name="Турнир",
            tournament_type="Олимпийская система",
        )
        return bracket
    except Exception as e:
        print(f"Ошибка построения структуры олимпийской сетки: {e}")
        return TournamentBracket(players=players, matches=[], rounds=[[]], name="Турнир", tournament_type="Олимпийская система")

def _build_olympic_rounds_from_tournament(tournament_data: Dict[str, Any], players_fallback: List[Player]) -> TournamentBracket:
    """Строит структуру раундов из состояния турнира: participants + matches.

    - Если есть matches: используем их для заполнения раундов, победителей и счетов
    - Если матчей нет: возвращаем структуру из игроков
    - Если следующих раундов нет, но есть победители предыдущего, создаем плейсхолдеры с победителями
    """
    try:
        matches_raw: List[Dict[str, Any]] = tournament_data.get('matches', []) or []
        participants_map: Dict[str, Dict[str, Any]] = tournament_data.get('participants', {}) or {}
        # Карта id -> Player
        id_to_player: Dict[str, Player] = {}
        for pid, pdata in participants_map.items():
            name = str(pdata.get('name') or pid)
            id_to_player[str(pid)] = Player(id=str(pid), name=name)
        for p in players_fallback:
            if p.id not in id_to_player:
                id_to_player[p.id] = p

        if not matches_raw:
            return _build_olympic_rounds_from_players(list(id_to_player.values()))

        # Группируем матчи по раундам
        from collections import defaultdict
        round_to_matches: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        max_round = 0
        for m in matches_raw:
            rnd = int(m.get('round', 0))
            round_to_matches[rnd].append(m)
            max_round = max(max_round, rnd)

        # Сортируем внутри раундов по match_number
        for rnd in round_to_matches:
            round_to_matches[rnd] = sorted(round_to_matches[rnd], key=lambda x: int(x.get('match_number', 0)))

        # Создаем структуру раундов
        rounds: List[List[Match]] = []
        for rnd in range(0, max_round + 1):
            current_round_matches = []
            raw_list = round_to_matches.get(rnd, [])
            for raw in raw_list:
                p1_id = raw.get('player1_id')
                p2_id = raw.get('player2_id')
                p1 = id_to_player.get(str(p1_id)) if p1_id else None
                p2 = id_to_player.get(str(p2_id)) if p2_id else None
                score = raw.get('score')
                winner_id = raw.get('winner_id')
                winner = id_to_player.get(str(winner_id)) if winner_id else None
                is_bye = bool(raw.get('is_bye'))
                mm = Match(player1=p1, player2=p2, winner=winner, score=score, is_bye=is_bye, match_number=int(raw.get('match_number', 0)))
                current_round_matches.append(mm)
            rounds.append(current_round_matches)

        # Если следующих раундов нет, но есть победители предыдущего — создадим каркас следующего раунда
        def winners_of_round(rmatches: List[Match]) -> List[Optional[Player]]:
            ws: List[Optional[Player]] = []
            for m in rmatches:
                if m.is_bye and (m.player1 or m.player2):
                    ws.append(m.player1 or m.player2)
                elif m.winner:
                    ws.append(m.winner)
                else:
                    ws.append(None)
            return ws

        # Добавляем последующие раунды каркасом, пока больше одного претендента
        current_round = rounds[0] if rounds else []
        while current_round:
            ws = winners_of_round(current_round)
            if len(ws) <= 1:
                break
            next_round_size = (len(ws) + 1) // 2
            next_round: List[Match] = []
            for i in range(0, len(ws), 2):
                p1w = ws[i] if i < len(ws) else None
                p2w = ws[i + 1] if i + 1 < len(ws) else None
                next_round.append(Match(player1=p1w, player2=p2w, match_number=len(next_round)))
            # Если уже существует следующий раунд, не дублируем
            if len(rounds) <= rounds.index(current_round) + 1:
                rounds.append(next_round)
            current_round = next_round

        # Соберем плоский список матчей
        flat_matches = [m for rnd in rounds for m in rnd]

        bracket = TournamentBracket(
            players=list(id_to_player.values()),
            matches=flat_matches,
            rounds=rounds,
            name=tournament_data.get('name', 'Турнир'),
            tournament_type='Олимпийская система'
        )
        return bracket
    except Exception as e:
        print(f"Ошибка построения сетки из состояния турнира: {e}")
        return _build_olympic_rounds_from_players(players_fallback)

def create_simple_text_image_bytes(text: str, title: str = "Информация") -> bytes:
    """Создает простое изображение с заголовком и текстом и возвращает его как bytes (PNG)."""
    image = Image.new('RGB', (1000, 500), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    # Загружаем шрифты с учетом Unicode
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 20)
        text_font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
            text_font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except Exception:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()

    # Заголовок
    try:
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        draw.text(((1000 - (title_bbox[2] - title_bbox[0])) // 2, 20), title, fill=(31, 41, 55), font=title_font)
    except Exception:
        try:
            draw.text((20, 20), title, fill=(31, 41, 55), font=title_font)
        except Exception:
            # В крайнем случае удаляем не-ASCII символы
            safe_title = title.encode('ascii', 'ignore').decode('ascii')
            draw.text((20, 20), safe_title, fill=(31, 41, 55), font=title_font)

    # Текст с переносами строк
    y = 70
    for line in str(text or "").splitlines() or [""]:
        try:
            draw.text((30, y), line, fill=(31, 41, 55), font=text_font)
        except Exception:
            safe_line = str(line).encode('ascii', 'ignore').decode('ascii')
            draw.text((30, y), safe_line, fill=(31, 41, 55), font=text_font)
        y += 22

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()

def build_tournament_bracket_image_bytes(tournament_data: Dict[str, Any], players_input: List[Any], completed_games: Optional[List[Dict[str, Any]]] = None):
    """Строит изображение турнирной сетки в байтах и текстовое представление.

    - Для типа "Олимпийская система" — рисует сетку BracketImageGenerator
    - Для остальных типов возвращает простое изображение-заглушку (круговая отрисовывается в другом модуле)
    """
    try:
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        name = tournament_data.get('name', 'Турнир')
        players = _normalize_players(players_input)

        if tournament_type == 'Олимпийская система':
            # Строим сетку по фактическим матчам, если они есть, чтобы отображались пары, счет и победители
            bracket_struct = _build_olympic_rounds_from_tournament(tournament_data, players)
            bracket_struct.name = name
            # Собираем пути до фото игр этого турнира
            photo_paths: list[str] = []
            try:
                
                if completed_games:
                    for g in completed_games:
                        fn = g.get('media_filename')
                        if fn:
                            photo_paths.append(f"{GAMES_PHOTOS_DIR}/{fn}")
            except Exception:
                pass
            generator = BracketImageGenerator()
            image = generator.generate_olympic_bracket_image(bracket_struct, photo_paths)
            buf = io.BytesIO()
            image.save(buf, format='PNG')
            buf.seek(0)

            # Текстовое краткое описание пар первого круга
            lines = [f"{name}", "", "Первый круг:"]
            if bracket_struct.rounds:
                for m in bracket_struct.rounds[0]:
                    p1 = m.player1.name if m.player1 else 'TBD'
                    p2 = m.player2.name if m.player2 else 'TBD'
                    lines.append(f"- {p1} vs {p2}")
            text = "\n".join(lines)
            return buf.getvalue(), text
        else:
            # Для круговой таблицы используем отдельный генератор с фото
            from utils.round_robin_image_generator import build_round_robin_table
            table_players = [{"id": getattr(p, 'id', None) or p.get('id'), "name": getattr(p, 'name', None) or p.get('name')} for p in players_input]
            # Собираем фото путей
            photo_paths: list[str] = []
            try:
                if completed_games:
                    for g in completed_games:
                        fn = g.get('media_filename')
                        if fn:
                            photo_paths.append(f"{GAMES_PHOTOS_DIR}/{fn}")
            except Exception:
                pass
            # Генератор round robin сейчас не принимает фото, но мы расширили _draw_game_photos_area, так что передадим позже при интеграции
            # Возвращаем совместимо: старый вызов без фото (фото выводятся placeholders)
            image_bytes = build_round_robin_table(table_players, completed_games, name)
            return image_bytes, name
    except Exception as e:
        print(f"Ошибка сборки изображения турнирной сетки: {e}")
        fallback = "Не удалось сгенерировать изображение"
        return create_simple_text_image_bytes(fallback, tournament_data.get('name', 'Турнир')), fallback