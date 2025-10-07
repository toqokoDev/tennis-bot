import os
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

from config.paths import GAMES_PHOTOS_DIR, BASE_DIR
from .models import Player, Match, TournamentBracket


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
        self.name_font_size = 14
        self.title_font_size = 14
        self.subtitle_font_size = 18
        self.score_font_size = 13
        
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
            self.name_font = ImageFont.truetype("arial.ttf", self.name_font_size)
            self.name_bold_font = ImageFont.truetype("arialbd.ttf", self.name_font_size)
            self.title_font = ImageFont.truetype("arialbd.ttf", self.title_font_size)
            self.subtitle_font = ImageFont.truetype("arialbd.ttf", self.subtitle_font_size)
            self.score_font = ImageFont.truetype("arial.ttf", self.score_font_size)
        except Exception:
            # Пытаемся DejaVuSans (обычно доступен в Pillow)
            try:
                self.font = ImageFont.truetype("DejaVuSans.ttf", self.font_size)
                self.bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.font_size)
                self.name_font = ImageFont.truetype("DejaVuSans.ttf", self.name_font_size)
                self.name_bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.name_font_size)
                self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.title_font_size)
                self.subtitle_font = ImageFont.truetype("DejaVuSans.ttf", self.subtitle_font_size)
                self.score_font = ImageFont.truetype("DejaVuSans.ttf", self.score_font_size)
            except Exception:
                # Последний фолбэк — дефолтный, но он может не поддерживать кириллицу
                try:
                    self.font = ImageFont.load_default()
                    self.bold_font = ImageFont.load_default()
                    self.name_font = ImageFont.load_default()
                    self.name_bold_font = ImageFont.load_default()
                    self.title_font = ImageFont.load_default()
                    self.subtitle_font = ImageFont.load_default()
                    self.score_font = ImageFont.load_default()
                except Exception:
                    self.font = None
                    self.bold_font = None
                    self.name_font = None
                    self.name_bold_font = None
                    self.title_font = None
                    self.subtitle_font = None
                    self.score_font = None

    @staticmethod
    def _sanitize_title(text: str) -> str:
        """Удаляет эмодзи и связанные служебные символы из строки заголовка."""
        try:
            import re
            emoji_pattern = re.compile(
                "[\U0001F600-\U0001F64F"  # emoticons
                "\U0001F300-\U0001F5FF"  # symbols & pictographs
                "\U0001F680-\U0001F6FF"  # transport & map symbols
                "\U0001F1E6-\U0001F1FF"  # flags
                "\U00002700-\U000027BF"  # dingbats
                "\U0001F900-\U0001F9FF"  # supplemental symbols
                "\U00002600-\U000026FF"  # misc symbols
                "]+",
                flags=re.UNICODE,
            )
            cleaned = emoji_pattern.sub("", str(text or ""))
            # variation selectors + ZWJ
            cleaned = cleaned.replace("\u200d", "").replace("\ufe0f", "")
            return cleaned
        except Exception:
            return "".join(ch for ch in str(text or "") if ord(ch) <= 0xFFFF)

    def create_player_avatar(self, player: Player, size: int = 24) -> Image.Image:
        """Создает квадратный аватар игрока"""
        # Пробуем загрузить пользовательское фото, если имеется
        try:
            if getattr(player, 'photo_url', None):
                raw_path = str(player.photo_url)
                abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(BASE_DIR, raw_path)
                if os.path.exists(abs_path):
                    img = Image.open(abs_path)
                    img = img.convert('RGBA')
                    w, h = img.size
                    side = min(w, h)
                    left = (w - side) // 2
                    top = (h - side) // 2
                    img = img.crop((left, top, left + side, top + side))
                    try:
                        resample = Image.Resampling.LANCZOS  # Pillow>=9
                    except Exception:
                        resample = Image.LANCZOS
                    img = img.resize((size, size), resample)
                    return img
        except Exception:
            # Игнорируем и используем заглушку
            pass

        # Заглушка: цветной квадрат с инициалами
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        color = (100, 150, 200)
        draw.rectangle([0, 0, size, size], fill=color)
        initials = self._get_player_initials(player)
        if self.font:
            try:
                bbox = draw.textbbox((0, 0), initials, font=self.font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (size - text_width) // 2
                y = (size - text_height) // 2
                draw.text((x, y), initials, fill=(255, 255, 255), font=self.font)
            except Exception:
                pass
        return avatar
    
    def _is_free_slot(self, player: Optional[Player]) -> bool:
        """Определяет, является ли слот свободным местом (плейсхолдер).

        Считаем свободным, если:
        - игрок отсутствует
        - id начинается с 'empty_'
        - имя равно 'Свободное место'
        """
        if player is None:
            return True
        try:
            if isinstance(getattr(player, 'id', None), str) and player.id.startswith('empty_'):
                return True
        except Exception:
            pass
        try:
            if (getattr(player, 'name', None) or '').strip().lower() == 'свободное место':
                return True
        except Exception:
            pass
        return False

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

    def _get_short_name(self, player: Player) -> str:
        """Получает короткое имя в формате 'И. Фамилия'"""
        name_parts = player.name.split()
        if len(name_parts) >= 2:
            # Берем первую букву имени и фамилию
            return f"{name_parts[0][0]}. {name_parts[1]}"
        elif len(name_parts) == 1:
            return name_parts[0]
        else:
            return player.name
    
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
        
        # Счёт матча больше не рисуем над ячейкой — он выводится под подписью победителя на коннекторе

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
        

    def _draw_player_in_cell(self, draw: ImageDraw.Draw, player: Player, x: int, y: int, width: int, height: int, 
                           is_winner: bool, is_special: bool = False):
        """Рисует информацию об игроке в ячейке"""
        # Если это свободный слот — ничего не рисуем
        if self._is_free_slot(player):
            return
        # Аватар
        avatar_size = 30
        avatar = self.create_player_avatar(player, avatar_size)
        if avatar:
            draw._image.paste(avatar, (x + 5, y + (height - avatar_size) // 2), avatar)
        
        # Имя игрока
        name_x = x + 5 + avatar_size + 6
        name_y = y
        
        # Для победителя используем жирный шрифт, для остальных обычный
        font = self.name_bold_font if is_winner else self.name_font
        color = self.winner_color if is_winner else self.text_color
        
        if font:
            display_name = player.name[:22] + "..." if len(player.name) > 22 else player.name
            try:
                bbox = draw.textbbox((0, 0), display_name, font=font)
                text_h = bbox[3] - bbox[1]
                name_y = y + (height - text_h) // 2
            except Exception:
                name_y = y + (height - self.name_font_size) // 2
            draw.text((name_x, name_y), display_name, fill=color, font=font)
            
    
    def draw_connectors(self, draw: ImageDraw.Draw, round_positions: List[List[Tuple[int, int]]], 
                       rounds_matches: List[List[Match]], is_mini_tournament: bool = False, tournament_name: str = ""):
        """Рисует соединительные линии между раундами и победителя над стрелочками в формате 'И. Фамилия'"""
        connector_color = self.connector_color
        
        # Больше не рисуем наконечник — только тонкая линия до следующего соединения

        # Обрабатываем все раунды, включая последний (для отображения финального победителя)
        for round_num in range(len(round_positions)):
            current_round = round_positions[round_num]
            
            # Проверяем, есть ли следующий раунд
            has_next_round = (round_num + 1) < len(round_positions)
            next_round = round_positions[round_num + 1] if has_next_round else []
            
            # Если это последний раунд (финал) и нет следующего, рисуем линию победителя вправо
            if not has_next_round and current_round:
                for match_num, (match_x, match_y) in enumerate(current_round):
                    match_center_y = match_y + self.cell_height // 2
                    
                    # Рисуем горизонтальную линию вправо от финального матча
                    # Для мини-турниров в раунде > 0: от точки схождения входящих линий
                    # Для остальных случаев: от правого края ячейки
                    if is_mini_tournament and round_num > 0:
                        # В мини-турнирах финал без ячейки - линии сходятся в match_x - 10
                        line_start_x = match_x - 10
                    elif round_num == 0:
                        # Если есть ячейка - от правого края
                        line_start_x = match_x + self.cell_width
                    else:
                        # Резервный случай
                        line_start_x = match_x
                    
                    line_length = 120
                    draw.line([line_start_x, match_center_y, 
                              line_start_x + line_length, match_center_y], 
                             fill=connector_color, width=1)
                    
                    # Победитель финала над линией
                    try:
                        if round_num < len(rounds_matches):
                            final_match = rounds_matches[round_num][match_num] if match_num < len(rounds_matches[round_num]) else None
                            if final_match and getattr(final_match, 'winner', None) and self.font:
                                winner_name = self._get_short_name(final_match.winner)
                                bbox = draw.textbbox((0, 0), winner_name, font=self.font)
                                text_w = bbox[2] - bbox[0]
                                text_h = bbox[3] - bbox[1]
                                label_x = line_start_x + (line_length - text_w) // 2
                                label_y = match_center_y - text_h - 6
                                draw.text((label_x, label_y), winner_name, fill=self.text_color, font=self.font)
                                
                                # Счёт под подписью
                                if getattr(final_match, 'score', None) and self.score_font:
                                    try:
                                        score_text = str(final_match.score)
                                        sb = draw.textbbox((0, 0), score_text, font=self.score_font)
                                        sw = sb[2] - sb[0]
                                        sx = label_x + (text_w - sw) // 2
                                        sy = label_y + text_h + 10
                                        draw.text((sx, sy), score_text, fill=self.text_color, font=self.score_font)
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    
                    # Рисуем название турнира справа от финальной линии для мини-турниров
                    if is_mini_tournament and tournament_name:
                        if self.title_font:
                            try:
                                # Подпись справа от линии победителя
                                label_x = line_start_x + line_length + 20
                                label_y = match_center_y - 10
                                draw.text((label_x, label_y), tournament_name, 
                                         fill=self.text_color, font=self.title_font)
                            except Exception:
                                pass
                continue
            
            for match_num in range(len(next_round)):
                # Позиция матча в следующем раунде
                next_x, next_y = next_round[match_num]
                next_center_y = next_y + self.cell_height // 2
                
                # Определяем, есть ли ячейка в следующем раунде (только первый раунд)
                next_has_cell = (round_num + 1) == 0
                
                # Прокладываем мостик внутри узла следующего раунда, чтобы линии были
                if next_has_cell:
                    try:
                        # продолжаем короткий заход (до next_x-1) вправо до начала выхода (next_x + cell_width)
                        draw.line([next_x - 1, next_center_y, next_x + self.cell_width, next_center_y],
                                  fill=connector_color, width=1)
                    except Exception:
                        pass

                # Позиции соответствующих матчей в текущем раунде
                prev_match1_idx = match_num * 2
                prev_match2_idx = match_num * 2 + 1
                
                # Определяем, есть ли ячейка в текущем раунде (только первый раунд)
                current_has_cell = round_num == 0
                
                if prev_match1_idx < len(current_round):
                    prev_x, prev_y = current_round[prev_match1_idx]
                    prev_center_y = prev_y + self.cell_height // 2
                    
                    # Точка начала линии зависит от того, есть ли в текущем раунде ячейка
                    line_start_x = prev_x + (self.cell_width if current_has_cell else 0)
                    
                    # Горизонтальная линия от предыдущего матча
                    draw.line([line_start_x, prev_center_y, 
                              next_x - 10, prev_center_y], 
                             fill=connector_color, width=1)
                    
                    # Вертикальная линия
                    draw.line([next_x - 10, prev_center_y, 
                              next_x - 10, next_center_y], 
                             fill=connector_color, width=1)
                    # Тонкий заход в следующий матч без стрелки
                    try:
                        draw.line([next_x - 10, next_center_y, next_x - 1, next_center_y], fill=connector_color, width=1)
                    except Exception:
                        pass
                    
                    # Подпись победителя на линии предыдущего матча 1 в формате 'И. Фамилия'
                    try:
                        match_obj = None
                        if round_num < len(rounds_matches):
                            cur_round_matches = rounds_matches[round_num]
                            if prev_match1_idx < len(cur_round_matches):
                                match_obj = cur_round_matches[prev_match1_idx]
                        if match_obj and getattr(match_obj, 'winner', None) and self.font:
                            winner_name = self._get_short_name(match_obj.winner)
                            bbox = draw.textbbox((0, 0), winner_name, font=self.font)
                            text_w = bbox[2] - bbox[0]
                            text_h = bbox[3] - bbox[1]
                            # Центруем по горизонтальному отрезку
                            seg_left = line_start_x
                            seg_right = next_x - 10
                            label_x = max(seg_left + 4, min((seg_left + seg_right - text_w) // 2, seg_right - 2 - text_w))
                            label_y = prev_center_y - text_h - 6
                            draw.text((label_x, label_y), winner_name, fill=self.text_color, font=self.font)
                            # Счёт под подписью победителя (центрируем под текстом имени)
                            if getattr(match_obj, 'score', None) and self.score_font:
                                try:
                                    score_text = str(match_obj.score)
                                    sb = draw.textbbox((0, 0), score_text, font=self.score_font)
                                    sw = sb[2] - sb[0]
                                    sx = label_x + (text_w - sw) // 2
                                    sy = label_y + text_h + 10
                                    draw.text((sx, sy), score_text, fill=self.text_color, font=self.score_font)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                
                if prev_match2_idx < len(current_round):
                    prev_x, prev_y = current_round[prev_match2_idx]
                    prev_center_y = prev_y + self.cell_height // 2
                    
                    # Точка начала линии зависит от того, есть ли в текущем раунде ячейка
                    line_start_x = prev_x + (self.cell_width if current_has_cell else 0)
                    
                    # Горизонтальная линия от предыдущего матча
                    draw.line([line_start_x, prev_center_y, 
                              next_x - 10, prev_center_y], 
                             fill=connector_color, width=1)
                    
                    # Вертикальная линия
                    draw.line([next_x - 10, prev_center_y, 
                              next_x - 10, next_center_y], 
                             fill=connector_color, width=1)
                    # Тонкий заход в следующий матч без стрелки
                    try:
                        draw.line([next_x - 10, next_center_y, next_x - 1, next_center_y], fill=connector_color, width=1)
                    except Exception:
                        pass
                    
                    # Подпись победителя на линии предыдущего матча 2 в формате 'И. Фамилия'
                    try:
                        match_obj = None
                        if round_num < len(rounds_matches):
                            cur_round_matches = rounds_matches[round_num]
                            if prev_match2_idx < len(cur_round_matches):
                                match_obj = cur_round_matches[prev_match2_idx]
                        if match_obj and getattr(match_obj, 'winner', None) and self.font:
                            winner_name = self._get_short_name(match_obj.winner)
                            bbox = draw.textbbox((0, 0), winner_name, font=self.font)
                            text_w = bbox[2] - bbox[0]
                            text_h = bbox[3] - bbox[1]
                            seg_left = line_start_x
                            seg_right = next_x - 10
                            label_x = max(seg_left + 4, min((seg_left + seg_right - text_w) // 2, seg_right - 2 - text_w))
                            label_y = prev_center_y - text_h - 6
                            draw.text((label_x, label_y), winner_name, fill=self.text_color, font=self.font)
                            # Счёт под подписью победителя (центрируем под текстом имени)
                            if getattr(match_obj, 'score', None) and self.score_font:
                                try:
                                    score_text = str(match_obj.score)
                                    sb = draw.textbbox((0, 0), score_text, font=self.score_font)
                                    sw = sb[2] - sb[0]
                                    sx = label_x + (text_w - sw) // 2
                                    sy = label_y + text_h + 10
                                    draw.text((sx, sy), score_text, fill=self.text_color, font=self.score_font)
                                except Exception:
                                    pass
                    except Exception:
                        pass
    
    def generate_olympic_bracket_image(self, bracket: TournamentBracket, photo_paths: Optional[list[str]] = None) -> Image.Image:
        """Генерирует изображение сетки олимпийской системы"""
        try:
            # Вычисляем размеры для основной сетки
            main_bracket_width, main_bracket_height = self.calculate_bracket_dimensions(bracket)
            
            # Вычисляем размеры для мини-турниров
            mini_tournaments_height = 0
            mini_tournaments_width = 0
            mini_tournaments_spacing = 80  # Отступ слева от основной сетки до мини-турниров
            
            if bracket.additional_tournaments:
                for i, mini_tournament in enumerate(bracket.additional_tournaments):
                    mini_width, mini_height = self.calculate_bracket_dimensions(mini_tournament)
                    mini_tournaments_height += mini_height
                    # Добавляем отступ только между турнирами (не после последнего)
                    if i < len(bracket.additional_tournaments) - 1:
                        # Учитываем увеличенный отступ после мини-турнира за 5-6 места
                        spacing = 100 if (i == 0 and '5' in mini_tournament.name) else 60
                        mini_tournaments_height += spacing
                    mini_tournaments_width = max(mini_tournaments_width, mini_width)
            
            # Общие размеры изображения
            # Ширина: левый отступ (50) + основная сетка + отступ до мини-турниров + мини-турниры + правый отступ (50)
            if mini_tournaments_width > 0:
                total_width = 50 + main_bracket_width + mini_tournaments_spacing + mini_tournaments_width + 50
            else:
                total_width = 50 + main_bracket_width + 50
            
            # Минимальная ширина
            total_width = max(total_width, 1200)
            
            has_photos = bool(photo_paths)
            # Базовый нижний отступ без фото (для заголовка и небольшого поля)
            base_bottom_padding = 80
            photos_height = 380 if has_photos else 0
            
            # Высота: заголовок (100) + max(основная сетка, мини-турниры) + фото + нижний отступ
            content_height = max(main_bracket_height, mini_tournaments_height)
            total_height = 100 + content_height + photos_height + base_bottom_padding
            
            # Создаем изображение
            image = Image.new('RGB', (total_width, total_height), self.bg_color)
            draw = ImageDraw.Draw(image)
            
            # Заголовок турнира
            title = self._sanitize_title(bracket.name)
            if self.title_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.title_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text(((total_width - title_width) // 2, 20), title, 
                             fill=self.text_color, font=self.title_font)
                except:
                    pass
            
            # Рисуем основную сетку
            main_bracket_y = 100
            round_positions = self._draw_bracket_grid(draw, bracket, 50, main_bracket_y, main_bracket_width, main_bracket_height)
            
            # Рисуем соединительные линии для основной сетки
            self.draw_connectors(draw, round_positions, bracket.rounds)
            
            # Рисуем мини-турниры справа от основной сетки
            current_y = main_bracket_y
            if bracket.additional_tournaments:
                for i, mini_tournament in enumerate(bracket.additional_tournaments):
                    tournament_x = main_bracket_width + mini_tournaments_spacing
                    tournament_y = current_y
                    
                    # Рисуем сетку мини-турнира
                    mini_round_positions = self._draw_mini_tournament_grid(draw, mini_tournament, tournament_x, tournament_y)
                    
                    # Рисуем соединительные линии для мини-турнира
                    self.draw_connectors(draw, mini_round_positions, mini_tournament.rounds, 
                                        is_mini_tournament=True, tournament_name=mini_tournament.name)
                    
                    # Увеличенный отступ после мини-турнира за 5-6 места
                    if i == 0 and '5' in mini_tournament.name:
                        current_y += self.calculate_bracket_dimensions(mini_tournament)[1] + 100
                    else:
                        current_y += self.calculate_bracket_dimensions(mini_tournament)[1] + 60
            
            # Рисуем область для фото игр внизу только если есть фото
            if has_photos:
                # Позиция фото: начало контента (100) + высота контента + небольшой отступ
                photos_y = 100 + content_height + 20
                photos_area_height = photos_height - 40  # Оставляем место для отступов
                self._draw_game_photos_area(draw, 50, photos_y, total_width - 100, photos_area_height, photo_paths or [])
            
            return image
            
        except Exception as e:
            print(f"Ошибка генерации олимпийской сетки: {e}")
            return self._create_error_image(str(e))
    
    def _draw_bracket_grid(self, draw: ImageDraw.Draw, bracket: TournamentBracket, start_x: int, start_y: int, width: int, height: int) -> List[List[Tuple[int, int]]]:
        """Рисует основную сетку турнира и возвращает позиции матчей"""
        round_positions = []
        current_x = start_x
        
        for round_num, round_matches in enumerate(bracket.rounds):
            if not round_matches:
                continue
            
            # Для первого раунда используем полный промежуток с ячейкой
            # Для остальных раундов используем только spacing без ширины ячейки
            if round_num == 0:
                round_x = current_x
                current_x += self.cell_width + self.round_spacing
            else:
                round_x = current_x
                current_x += self.round_spacing
            
            # Заголовок раунда
            round_title = self._get_round_title(round_num, len(bracket.rounds))
            if self.font:
                try:
                    title_bbox = draw.textbbox((0, 0), round_title, font=self.bold_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    # Центрируем заголовок:
                    # - для первого раунда - над центром ячейки
                    # - для остальных - над областью соединительных линий
                    if round_num == 0:
                        title_x = round_x + (self.cell_width - title_width) // 2
                    else:
                        # Для остальных раундов центрируем над областью spacing
                        title_x = round_x + (self.round_spacing - title_width) // 2
                    draw.text((title_x, start_y - 40), 
                        round_title, fill=self.round_title_color, font=self.bold_font)
                except:
                    pass
            
            # Позиции матчей в раунде
            match_positions = []
            
            for match_num, match in enumerate(round_matches):
                match_y = self._calculate_match_y(round_num, match_num, round_matches, round_positions, start_y, height)
                match_positions.append((round_x, match_y))
                # Рисуем полноценные ячейки только в первом раунде; далее — только линии и подписи
                if round_num == 0:
                    self.draw_match_cell(draw, round_x, match_y, match, round_num)
            
            round_positions.append(match_positions)
        
        return round_positions
    
    def _draw_mini_tournament_grid(self, draw: ImageDraw.Draw, tournament: TournamentBracket, start_x: int, start_y: int) -> List[List[Tuple[int, int]]]:
        """Рисует сетку мини-турнира"""
        round_positions = []
        current_x = start_x
        
        for round_num, round_matches in enumerate(tournament.rounds):
            if not round_matches:
                continue
            
            # Для первого раунда используем полный промежуток с ячейкой
            # Для остальных раундов используем только минимальный spacing без ячейки
            mini_spacing = 80  # Увеличенный отступ для соединительных линий и подписей
            if round_num == 0:
                round_x = current_x
                current_x += self.cell_width + mini_spacing
            else:
                round_x = current_x
                current_x += mini_spacing
            
            # Убираем заголовки раундов для мини-турниров (Финал/Полуфинал) - они избыточны
            
            # Позиции матчей в раунде
            match_positions = []
            tournament_height = self.calculate_bracket_dimensions(tournament)[1]
            
            for match_num, match in enumerate(round_matches):
                match_y = self._calculate_match_y(round_num, match_num, round_matches, round_positions, start_y, tournament_height)
                match_positions.append((round_x, match_y))
                # Рисуем ячейки только для первого раунда, далее только линии
                if round_num == 0:
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
            
            # Проверяем, что предыдущий раунд существует
            if round_num - 1 < len(round_positions) and round_positions[round_num - 1]:
                prev_round = round_positions[round_num - 1]
                if (prev_match1_idx < len(prev_round) and 
                    prev_match2_idx < len(prev_round)):
                    y1 = prev_round[prev_match1_idx][1] + self.cell_height // 2
                    y2 = prev_round[prev_match2_idx][1] + self.cell_height // 2
                    return (y1 + y2) // 2 - self.cell_height // 2
            
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
                    thumb_h = height - 60
                    thumb_w = thumb_h * 4 // 3
                    padding = 15
                    visible = photo_paths[:8]  # Увеличили количество видимых фото
                    total_w = len(visible) * thumb_w + (len(visible) - 1) * padding
                    start_x = x + (width - total_w) // 2
                    cur_x = start_x
                    for p in visible:
                        try:
                            img = PILImage.open(p)
                            img = img.convert('RGB')
                            img_thumb = img.copy()
                            img_thumb.thumbnail((thumb_w, thumb_h))
                            draw._image.paste(img_thumb, (cur_x, y + 45))
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
            
            # Ширина: первый раунд с ячейкой, остальные только spacing
            # Первый раунд: cell_width + round_spacing
            # Остальные раунды: round_spacing каждый
            num_rounds = len(bracket.rounds)
            if num_rounds > 0:
                width = self.cell_width + self.round_spacing  # Первый раунд
                if num_rounds > 1:
                    width += (num_rounds - 1) * self.round_spacing  # Остальные раунды
                width += 200  # Дополнительное место для финальной линии и подписи победителя (увеличено для длинных имен)
            else:
                width = 400
            
            # Высота: учитываем максимальное количество матчей + дополнительное пространство для подписей
            max_matches = max(len(round_matches) for round_matches in bracket.rounds)
            # Добавляем дополнительные 40 пикселей сверху и снизу для подписей победителей и счета
            height = (max_matches * (self.cell_height + self.match_spacing) + 80)
            
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
