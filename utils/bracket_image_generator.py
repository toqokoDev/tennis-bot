import io
import os
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Tuple, Optional
from utils.tournament_brackets import TournamentBracket, Player, Match


class BracketImageGenerator:
    """Класс для генерации изображений турнирных сеток"""
    
    def __init__(self):
        self.cell_width = 200
        self.cell_height = 60
        self.round_spacing = 50
        self.match_spacing = 80
        self.font_size = 16
        self.title_font_size = 24
        
        # Цвета
        self.bg_color = (255, 255, 255)  # Белый фон
        self.cell_color = (240, 240, 240)  # Серый фон ячейки
        self.border_color = (0, 0, 0)  # Черная граница
        self.text_color = (0, 0, 0)  # Черный текст
        self.winner_color = (0, 150, 0)  # Зеленый для победителя
        self.bye_color = (150, 150, 150)  # Серый для BYE
        
        # Попытка загрузить шрифт
        try:
            self.font = ImageFont.truetype("arial.ttf", self.font_size)
            self.title_font = ImageFont.truetype("arial.ttf", self.title_font_size)
        except:
            try:
                self.font = ImageFont.load_default()
                self.title_font = ImageFont.load_default()
            except:
                self.font = None
                self.title_font = None
    
    def load_user_photo(self, photo_path: str) -> Optional[Image.Image]:
        """Загружает фото пользователя из локального файла"""
        try:
            if not photo_path:
                return None
            
            # Проверяем существование файла
            if not os.path.exists(photo_path):
                return None
            
            image = Image.open(photo_path)
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')
            return image
        except Exception as e:
            print(f"Ошибка загрузки фото: {e}")
        return None
    
    def create_player_avatar(self, player: Player, size: int = 40) -> Image.Image:
        """Создает аватар игрока"""
        avatar = Image.new('RGB', (size, size), self.cell_color)
        draw = ImageDraw.Draw(avatar)
        
        # Пытаемся загрузить фото пользователя
        if player.photo_url:
            user_photo = self.load_user_photo(player.photo_url)
            if user_photo:
                # Изменяем размер фото
                user_photo = user_photo.resize((size, size), Image.Resampling.LANCZOS)
                avatar.paste(user_photo)
            else:
                # Если фото не загрузилось, создаем круг с инициалами
                self._draw_circle_with_initials(draw, player, size)
        else:
            # Создаем круг с инициалами
            self._draw_circle_with_initials(draw, player, size)
        
        return avatar
    
    def _draw_circle_with_initials(self, draw: ImageDraw.Draw, player: Player, size: int):
        """Рисует круг с инициалами игрока"""
        # Рисуем круг
        margin = 2
        draw.ellipse([margin, margin, size-margin, size-margin], 
                    fill=(100, 150, 200), outline=self.border_color, width=2)
        
        # Получаем инициалы
        initials = self._get_player_initials(player)
        
        # Рисуем инициалы
        if self.font:
            bbox = draw.textbbox((0, 0), initials, font=self.font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (size - text_width) // 2
            y = (size - text_height) // 2
            
            draw.text((x, y), initials, fill=(255, 255, 255), font=self.font)
    
    def _get_player_initials(self, player: Player) -> str:
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
    
    def draw_match_cell(self, draw: ImageDraw.Draw, x: int, y: int, match: Match) -> None:
        """Рисует ячейку матча"""
        # Определяем цвета
        if match.is_bye:
            cell_color = self.bye_color
            text_color = (255, 255, 255)
        elif match.winner:
            cell_color = self.winner_color
            text_color = (255, 255, 255)
        else:
            cell_color = self.cell_color
            text_color = self.text_color
        
        # Рисуем прямоугольник
        draw.rectangle([x, y, x + self.cell_width, y + self.cell_height], 
                      fill=cell_color, outline=self.border_color, width=2)
        
        # Рисуем игроков
        if match.player1 and match.player1.id != "bye":
            # Аватар игрока 1
            avatar1 = self.create_player_avatar(match.player1, 30)
            draw.bitmap((x + 5, y + 5), avatar1.convert('1'))
            
            # Имя игрока 1
            player1_name = match.player1.name[:15]  # Ограничиваем длину
            if self.font:
                draw.text((x + 40, y + 5), player1_name, fill=text_color, font=self.font)
        
        if match.player2 and match.player2.id != "bye":
            # Аватар игрока 2
            avatar2 = self.create_player_avatar(match.player2, 30)
            draw.bitmap((x + 5, y + 30), avatar2.convert('1'))
            
            # Имя игрока 2
            player2_name = match.player2.name[:15]  # Ограничиваем длину
            if self.font:
                draw.text((x + 40, y + 30), player2_name, fill=text_color, font=self.font)
        
        # Рисуем счет если есть
        if match.score and self.font:
            draw.text((x + 150, y + 20), match.score, fill=text_color, font=self.font)
    
    def generate_olympic_bracket_image(self, bracket: TournamentBracket) -> Image.Image:
        """Генерирует изображение сетки олимпийской системы"""
        if not bracket.rounds:
            return self._create_empty_bracket_image("Нет участников")
        
        # Вычисляем размеры изображения
        max_matches_in_round = max(len(round) for round in bracket.rounds)
        image_width = len(bracket.rounds) * (self.cell_width + self.round_spacing) + 100
        image_height = max_matches_in_round * (self.cell_height + self.match_spacing) + 100
        
        # Создаем изображение
        image = Image.new('RGB', (image_width, image_height), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        # Рисуем заголовок
        title = f"🏆 Турнирная сетка ({bracket.tournament_type})"
        if self.title_font:
            draw.text((20, 20), title, fill=self.text_color, font=self.title_font)
        
        # Рисуем раунды
        for round_num, round_matches in enumerate(bracket.rounds):
            round_x = 20 + round_num * (self.cell_width + self.round_spacing)
            
            # Заголовок раунда
            round_title = f"Раунд {round_num + 1}"
            if self.font:
                draw.text((round_x, 60), round_title, fill=self.text_color, font=self.font)
            
            # Рисуем матчи раунда
            for match_num, match in enumerate(round_matches):
                match_y = 90 + match_num * (self.cell_height + self.match_spacing)
                self.draw_match_cell(draw, round_x, match_y, match)
        
        return image
    
    def generate_round_robin_image(self, bracket: TournamentBracket) -> Image.Image:
        """Генерирует изображение сетки круговой системы"""
        if not bracket.rounds:
            return self._create_empty_bracket_image("Нет участников")
        
        # Вычисляем размеры изображения
        max_matches_in_round = max(len(round) for round in bracket.rounds)
        image_width = len(bracket.rounds) * (self.cell_width + self.round_spacing) + 100
        image_height = max_matches_in_round * (self.cell_height + self.match_spacing) + 100
        
        # Создаем изображение
        image = Image.new('RGB', (image_width, image_height), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        # Рисуем заголовок
        title = f"🏆 Турнирная сетка ({bracket.tournament_type})"
        if self.title_font:
            draw.text((20, 20), title, fill=self.text_color, font=self.title_font)
        
        # Рисуем раунды
        for round_num, round_matches in enumerate(bracket.rounds):
            round_x = 20 + round_num * (self.cell_width + self.round_spacing)
            
            # Заголовок раунда
            round_title = f"Раунд {round_num + 1}"
            if self.font:
                draw.text((round_x, 60), round_title, fill=self.text_color, font=self.font)
            
            # Рисуем матчи раунда
            for match_num, match in enumerate(round_matches):
                match_y = 90 + match_num * (self.cell_height + self.match_spacing)
                self.draw_match_cell(draw, round_x, match_y, match)
        
        return image
    
    def _create_empty_bracket_image(self, message: str) -> Image.Image:
        """Создает пустое изображение с сообщением"""
        image = Image.new('RGB', (400, 200), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        if self.title_font:
            draw.text((50, 100), message, fill=self.text_color, font=self.title_font)
        
        return image
    
    def generate_bracket_image(self, bracket: TournamentBracket) -> Image.Image:
        """Генерирует изображение турнирной сетки в зависимости от типа"""
        if bracket.tournament_type == "Олимпийская система":
            return self.generate_olympic_bracket_image(bracket)
        elif bracket.tournament_type == "Круговая":
            return self.generate_round_robin_image(bracket)
        else:
            return self._create_empty_bracket_image("Неизвестный тип турнира")


def create_bracket_image(bracket: TournamentBracket) -> Image.Image:
    """Создает изображение турнирной сетки"""
    generator = BracketImageGenerator()
    return generator.generate_bracket_image(bracket)


def save_bracket_image(bracket: TournamentBracket, filepath: str) -> bool:
    """Сохраняет изображение турнирной сетки в файл"""
    try:
        image = create_bracket_image(bracket)
        image.save(filepath, 'PNG')
        return True
    except Exception as e:
        print(f"Ошибка сохранения изображения: {e}")
        return False
