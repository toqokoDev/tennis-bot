import os
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

from config.paths import BASE_DIR
from .models import Player, Match, TournamentBracket


class BracketImageGenerator:
    
    def __init__(self):
        # Основные размеры
        self.cell_width = 700
        self.cell_height = 220
        self.round_spacing = 250
        self.match_spacing = 30
        self.vertical_margin = 30
        
        # Размеры шрифтов (увеличены в 2 раза)
        self.font_size = 44
        self.name_font_size = 44
        self.title_font_size = 44
        self.subtitle_font_size = 44
        self.score_font_size = 44
        
        # Параметры линий (для удобной настройки)
        self.line_width = 3  # Толщина соединительных линий
        self.cell_border_width = 5  # Толщина границ ячеек
        self.final_line_length = self.cell_width - 100  # Длина финальной линии победителя равна ширине ячейки
        self.final_line_width = 3  # Толщина финальной линии победителя (жирная)
        self.connector_offset = 30  # Расстояние от ячейки до точки схождения линий
        self.mini_spacing = 250  # Отступ между раундами в мини-турнирах
        self.mini_tournament_gap_large = 140  # Отступ между турниром за 5-6 место и турниром за 3 место
        self.mini_tournament_gap_normal = 40  # Обычный отступ между мини-турнирами
        self.mini_tournament_top_offset = 40  # Отступ сверху перед мини-турниром за 3 место
        
        # Отступы для подписей на линиях
        self.label_offset_above = 8  # Отступ имени победителя над линией
        self.label_offset_below = 12  # Отступ счета под именем победителя
        
        # Дополнительные пространства для расчета размеров
        self.final_area_padding = 0  # Без дополнительного места справа после финала
        self.vertical_labels_padding = 80  # Дополнительное пространство сверху и снизу для подписей
        
        # Цветовая схема как на tennis-play.com
        self.bg_color = (255, 255, 255)  # Белый фон
        self.cell_color = (255, 255, 255)  # Белый фон ячейки
        self.cell_border_color = (209, 213, 219)  # Серый бордер
        self.text_color = (31, 41, 55)  # Темно-серый текст
        self.secondary_text_color = (107, 114, 128)  # Серый текст
        self.winner_color = (31, 41, 55)  # Темный для победителя (жирный)
        self.winner_bg_color = (220, 252, 231)  # Светло-зеленый фон победителя
        self.connector_color = (156, 163, 175)  # Цвет соединительных линий
        self.round_title_color = (107, 114, 128)  # Серый для заголовков раундов
        self.placement_color = (139, 69, 19)  # Коричневый для игр за мест
        
        # Увеличенный отступ между подписью мини-сетки и первой ячейкой
        self.mini_title_spacing = 24

        # Загрузка шрифтов: сначала Circe, затем Arial/DejaVu, затем дефолт
        def _try_load_font(candidates, size):
            for path in candidates:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
            return None

        circe_regular_candidates = [
            "Circe-Regular.ttf",
            "Circe.ttf",
            os.path.join(BASE_DIR, "fonts", "Circe-Regular.ttf"),
            os.path.join(BASE_DIR, "fonts", "Circe.ttf"),
        ]
        circe_bold_candidates = [
            "Circe-Bold.ttf",
            os.path.join(BASE_DIR, "fonts", "Circe-Bold.ttf"),
        ]

        # Пытаемся Circe
        self.font = _try_load_font(circe_regular_candidates, self.font_size)
        self.bold_font = _try_load_font(circe_bold_candidates, self.font_size)
        self.name_font = _try_load_font(circe_regular_candidates, self.name_font_size)
        self.name_bold_font = _try_load_font(circe_bold_candidates, self.name_font_size)
        self.title_font = _try_load_font(circe_bold_candidates, self.title_font_size)
        self.subtitle_font = _try_load_font(circe_regular_candidates, self.subtitle_font_size)
        self.score_font = _try_load_font(circe_regular_candidates, self.score_font_size)

        # Фолбэк Arial
        if not self.font:
            try:
                self.font = ImageFont.truetype("arial.ttf", self.font_size)
            except Exception:
                self.font = None
        if not self.bold_font:
            try:
                self.bold_font = ImageFont.truetype("arialbd.ttf", self.font_size)
            except Exception:
                self.bold_font = None
        if not self.name_font:
            try:
                self.name_font = ImageFont.truetype("arial.ttf", self.name_font_size)
            except Exception:
                self.name_font = None
        if not self.name_bold_font:
            try:
                self.name_bold_font = ImageFont.truetype("arialbd.ttf", self.name_font_size)
            except Exception:
                self.name_bold_font = None
        if not self.title_font:
            try:
                self.title_font = ImageFont.truetype("arialbd.ttf", self.title_font_size)
            except Exception:
                self.title_font = None
        if not self.subtitle_font:
            try:
                self.subtitle_font = ImageFont.truetype("arial.ttf", self.subtitle_font_size)
            except Exception:
                self.subtitle_font = None
        if not self.score_font:
            try:
                self.score_font = ImageFont.truetype("arial.ttf", self.score_font_size)
            except Exception:
                self.score_font = None

        # Фолбэк DejaVuSans
        if not self.font:
            try:
                self.font = ImageFont.truetype("DejaVuSans.ttf", self.font_size)
            except Exception:
                self.font = None
        if not self.bold_font:
            try:
                self.bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.font_size)
            except Exception:
                self.bold_font = None
        if not self.name_font:
            try:
                self.name_font = ImageFont.truetype("DejaVuSans.ttf", self.name_font_size)
            except Exception:
                self.name_font = None
        if not self.name_bold_font:
            try:
                self.name_bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.name_font_size)
            except Exception:
                self.name_bold_font = None
        if not self.title_font:
            try:
                self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.title_font_size)
            except Exception:
                self.title_font = None
        if not self.subtitle_font:
            try:
                self.subtitle_font = ImageFont.truetype("DejaVuSans.ttf", self.subtitle_font_size)
            except Exception:
                self.subtitle_font = None
        if not self.score_font:
            try:
                self.score_font = ImageFont.truetype("DejaVuSans.ttf", self.score_font_size)
            except Exception:
                self.score_font = None

        # Последний фолбэк — дефолтный
        if not self.font:
            try:
                self.font = ImageFont.load_default()
            except Exception:
                self.font = None
        if not self.bold_font:
            try:
                self.bold_font = ImageFont.load_default()
            except Exception:
                self.bold_font = None
        if not self.name_font:
            try:
                self.name_font = ImageFont.load_default()
            except Exception:
                self.name_font = None
        if not self.name_bold_font:
            try:
                self.name_bold_font = ImageFont.load_default()
            except Exception:
                self.name_bold_font = None
        if not self.title_font:
            try:
                self.title_font = ImageFont.load_default()
            except Exception:
                self.title_font = None
        if not self.subtitle_font:
            try:
                self.subtitle_font = ImageFont.load_default()
            except Exception:
                self.subtitle_font = None
        if not self.score_font:
            try:
                self.score_font = ImageFont.load_default()
            except Exception:
                self.score_font = None

        # Нормализация отступов и длин линий относительно ширины ячейки
        # Чтобы горизонтальные соединительные линии были длиной ровно в ширину ячейки,
        # выбираем расстояние между раундами как (ширина ячейки + смещение коннектора)
        try:
            self.round_spacing = self.cell_width + self.connector_offset
            self.mini_spacing = self.cell_width + self.connector_offset
            self.final_line_length = self.cell_width - 100
        except Exception:
            pass

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

    def create_player_avatar(self, player: Optional[Player], size: int = 24) -> Image.Image:
        """Создает квадратный аватар игрока. Осветляет фото; инициалы рисует ТОЛЬКО если фото отсутствует."""
        img = None
        had_photo = False
        # Пробуем загрузить пользовательское фото, если имеется
        try:
            if player is not None and getattr(player, 'photo_url', None):
                raw_path = str(player.photo_url)
                abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(BASE_DIR, raw_path)
                if os.path.exists(abs_path):
                    src = Image.open(abs_path)
                    src = src.convert('RGBA')
                    w, h = src.size
                    side = min(w, h)
                    left = (w - side) // 2
                    top = (h - side) // 2
                    src = src.crop((left, top, left + side, top + side))
                    try:
                        resample = Image.Resampling.LANCZOS  # Pillow>=9
                    except Exception:
                        resample = Image.LANCZOS
                    img = src.resize((size, size), resample)
                    had_photo = True
        except Exception:
            img = None

        # Если фото нет — создаем светло-серый фон
        if img is None:
            img = Image.new('RGBA', (size, size), (229, 229, 229, 255))

        # Делаем изображение чуть светлее только для реальных фото
        if had_photo:
            try:
                overlay = Image.new('RGBA', (size, size), (255, 255, 255, 40))
                img = Image.alpha_composite(img, overlay)
            except Exception:
                pass

        # Рисуем инициалы по центру ТОЛЬКО если фото отсутствует
        if not had_photo:
            try:
                initials = self._get_player_initials(player) if player else ""
                if initials:
                    draw = ImageDraw.Draw(img)
                    # Выбираем доступный шрифт
                    font = self.name_bold_font or self.bold_font or self.font
                    bbox = draw.textbbox((0, 0), initials, font=font)
                    text_w = max(0, bbox[2] - bbox[0])
                    text_h = max(0, bbox[3] - bbox[1])
                    x = (size - text_w) // 2
                    y = (size - text_h) // 2
                    draw.text((x, y), initials, fill=(255, 255, 255), font=font)
            except Exception:
                pass

        return img
    
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
            return ""

    def _get_short_name(self, player: Player) -> str:
        """Получает полное имя и фамилию"""
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
                      fill=self.cell_color, outline=border_color, width=self.cell_border_width)
        
        # Счёт матча больше не рисуем над ячейкой — он выводится под подписью победителя на коннекторе

        # Информация о матче
        player1 = match.player1
        player2 = match.player2
        
        # Рисуем игроков
        player_height = self.cell_height // 2
        player_y = y
        
        # Игрок 1 (рисуем даже при отсутствии игрока — будет серый аватар)
        self._draw_player_in_cell(draw, player1, x, player_y, self.cell_width, player_height, 
                                  match.winner == player1 if player1 else False, is_placement or is_mini_tournament)
        
        # Разделительная линия
        draw.line([x, y + player_height, x + self.cell_width, y + player_height], 
                 fill=border_color, width=self.cell_border_width)
        
        # Игрок 2 (рисуем даже при отсутствии игрока — будет серый аватар)
        self._draw_player_in_cell(draw, player2, x, y + player_height, self.cell_width, player_height, 
                                  match.winner == player2 if player2 else False, is_placement or is_mini_tournament)

    def _draw_player_in_cell(self, draw: ImageDraw.Draw, player: Optional[Player], x: int, y: int, width: int, height: int, 
                           is_winner: bool, is_special: bool = False):
        """Рисует информацию об игроке в ячейке"""
        # Аватар: делаем крупнее и хорошо видимым (в пределах половины ячейки)
        is_free = self._is_free_slot(player)
        # Размер аватара ограничиваем высотой строки игрока
        avatar_size = max(60, min(height - 10, int(height * 0.8)))
        avatar = self.create_player_avatar(player if not is_free else None, avatar_size)
        if avatar:
            draw._image.paste(avatar, (x + 10, y + (height - avatar_size) // 2), avatar)
        name_x = x + 10 + avatar_size + 12
        name_y = y
        
        # Для победителя используем жирный шрифт, для остальных обычный
        font = self.name_bold_font if is_winner else self.name_font
        color = self.winner_color if is_winner else self.text_color
        
        if font and not is_free and player is not None:
            display_name = player.name
            try:
                bbox = draw.textbbox((0, 0), display_name, font=font)
                text_h = bbox[3] - bbox[1]
                name_y = y + (height - text_h) // 2
            except Exception:
                name_y = y + (height - self.name_font_size) // 2
            draw.text((name_x, name_y), display_name, fill=color, font=font)
    
    def draw_connectors(self, draw: ImageDraw.Draw, round_positions: List[List[Tuple[int, int]]], 
                       rounds_matches: List[List[Match]], is_mini_tournament: bool = False, tournament_name: str = ""):
        """Рисует соединительные линии между раундами и победителя над стрелочками (полное имя)"""
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
                    
                    line_length = self.final_line_length
                    draw.line([line_start_x, match_center_y, 
                              line_start_x + line_length, match_center_y], 
                             fill=connector_color, width=self.final_line_width)
                    
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
                                label_y = match_center_y - text_h - self.label_offset_above
                                draw.text((label_x, label_y), winner_name, fill=self.text_color, font=self.font)
                                
                                # Счёт под подписью
                                if getattr(final_match, 'score', None) and self.score_font:
                                    try:
                                        score_text = str(final_match.score)
                                        sb = draw.textbbox((0, 0), score_text, font=self.score_font)
                                        sw = sb[2] - sb[0]
                                        sx = label_x + (text_w - sw) // 2
                                        sy = label_y + text_h + self.label_offset_below
                                        draw.text((sx, sy), score_text, fill=self.text_color, font=self.score_font)
                                    except Exception:
                                        pass
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
                                  fill=connector_color, width=self.line_width)
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
                    
                    # Расстояние до точки схождения (больше для линий от ячеек, увеличено для полных имен и длинных линий)
                    connector_offset = self.connector_offset
                    
                    # Горизонтальная линия от предыдущего матча
                    draw.line([line_start_x, prev_center_y, 
                              next_x - connector_offset, prev_center_y], 
                             fill=connector_color, width=self.line_width)
                    
                    # Вертикальная линия
                    draw.line([next_x - connector_offset, prev_center_y, 
                              next_x - connector_offset, next_center_y], 
                             fill=connector_color, width=self.line_width)
                    # Тонкий заход в следующий матч без стрелки
                    try:
                        draw.line([next_x - connector_offset, next_center_y, next_x - 1, next_center_y], fill=connector_color, width=self.line_width)
                    except Exception:
                        pass
                    
                    # Подпись победителя на линии предыдущего матча 1 (полное имя)
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
                            seg_right = next_x - connector_offset
                            label_x = max(seg_left + 4, min((seg_left + seg_right - text_w) // 2, seg_right - 2 - text_w))
                            label_y = prev_center_y - text_h - self.label_offset_above
                            draw.text((label_x, label_y), winner_name, fill=self.text_color, font=self.font)
                            # Счёт под подписью победителя (центрируем под текстом имени)
                            if getattr(match_obj, 'score', None) and self.score_font:
                                try:
                                    score_text = str(match_obj.score)
                                    sb = draw.textbbox((0, 0), score_text, font=self.score_font)
                                    sw = sb[2] - sb[0]
                                    sx = label_x + (text_w - sw) // 2
                                    sy = label_y + text_h + self.label_offset_below
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
                    
                    # Расстояние до точки схождения (больше для линий от ячеек, увеличено для полных имен и длинных линий)
                    connector_offset = self.connector_offset
                    
                    # Горизонтальная линия от предыдущего матча
                    draw.line([line_start_x, prev_center_y, 
                              next_x - connector_offset, prev_center_y], 
                             fill=connector_color, width=self.line_width)
                    
                    # Вертикальная линия
                    draw.line([next_x - connector_offset, prev_center_y, 
                              next_x - connector_offset, next_center_y], 
                             fill=connector_color, width=self.line_width)
                    # Тонкий заход в следующий матч без стрелки
                    try:
                        draw.line([next_x - connector_offset, next_center_y, next_x - 1, next_center_y], fill=connector_color, width=self.line_width)
                    except Exception:
                        pass
                    
                    # Подпись победителя на линии предыдущего матча 2 (полное имя)
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
                            seg_right = next_x - connector_offset
                            label_x = max(seg_left + 4, min((seg_left + seg_right - text_w) // 2, seg_right - 2 - text_w))
                            label_y = prev_center_y - text_h - self.label_offset_above
                            draw.text((label_x, label_y), winner_name, fill=self.text_color, font=self.font)
                            # Счёт под подписью победителя (центрируем под текстом имени)
                            if getattr(match_obj, 'score', None) and self.score_font:
                                try:
                                    score_text = str(match_obj.score)
                                    sb = draw.textbbox((0, 0), score_text, font=self.score_font)
                                    sw = sb[2] - sb[0]
                                    sx = label_x + (text_w - sw) // 2
                                    sy = label_y + text_h + self.label_offset_below
                                    draw.text((sx, sy), score_text, fill=self.text_color, font=self.score_font)
                                except Exception:
                                    pass
                    except Exception:
                        pass
    
    def generate_olympic_bracket_image(self, bracket: TournamentBracket, photo_paths: Optional[list[str]] = None) -> Image.Image:
        """Генерирует изображение сетки олимпийской системы"""
        try:
            # Автонастройка размеров ячеек и линий под текущие шрифты и тексты
            self._autosize_layout(bracket)
            
            # Внешние отступы изображения
            margin = 20
            title_gap = 50  # Увеличенный интервал от названия турнира до подписей туров
            # Вычисляем размеры для основной сетки
            main_bracket_width, main_bracket_height = self.calculate_bracket_dimensions(bracket)
            
            # Вычисляем размеры для мини-турниров (которые будут снизу)
            mini_tournaments_height = 0
            mini_tournaments_width = 0
            bottom_gap = 40  # Базовый зазор между основной сеткой и мини-сетками
            gap_between_main_and_minis = max(10, bottom_gap // 2)
            
            if bracket.additional_tournaments:
                for i, mini_tournament in enumerate(bracket.additional_tournaments):
                    # Добавляем отступ сверху перед турниром за 3 место
                    if '3' in mini_tournament.name and 'место' in mini_tournament.name:
                        mini_tournaments_height += self.mini_tournament_top_offset
                    
                    mini_width, mini_height = self.calculate_bracket_dimensions(mini_tournament, is_mini=True)
                    mini_tournaments_height += mini_height
                    # Добавляем отступ только между турнирами (не после последнего)
                    if i < len(bracket.additional_tournaments) - 1:
                        # Учитываем увеличенный отступ после мини-турнира за 5-6 места
                        spacing = self.mini_tournament_gap_large if (i == 0 and '5' in mini_tournament.name) else self.mini_tournament_gap_normal
                        mini_tournaments_height += spacing
                    mini_tournaments_width = max(mini_tournaments_width, mini_width)
            
            # Общие размеры изображения: ровно по контенту + 20px слева/справа
            content_width = max(main_bracket_width, mini_tournaments_width)
            total_width = margin * 2 + content_width

            # Нижний отступ отсутствует
            base_bottom_padding = 0

            # Высота: заголовок + основная сетка + (зазор + мини-сетки, если есть) + нижний отступ
            if mini_tournaments_height > 0:
                content_height = main_bracket_height + gap_between_main_and_minis + mini_tournaments_height
            else:
                content_height = main_bracket_height
            # Высота заголовка (для расчета вертикального отступа контента)
            # Временный draw для измерения, фактический рисуем ниже
            title = self._sanitize_title(bracket.name)
            tmp_img = Image.new('RGB', (1, 1), self.bg_color)
            tmp_draw = ImageDraw.Draw(tmp_img)
            title_h = 0
            if self.font:
                try:
                    tb = tmp_draw.textbbox((0, 0), title, font=self.font)
                    title_h = max(0, tb[3] - tb[1])
                except Exception:
                    title_h = 0
            total_height = margin + title_h + title_gap + content_height + margin
            
            # Создаем изображение
            image = Image.new('RGB', (total_width, total_height), self.bg_color)
            draw = ImageDraw.Draw(image)
            
            # Заголовок турнира (черный, без жирного)
            title = self._sanitize_title(bracket.name)
            if self.title_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.title_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text(((total_width - title_width) // 2, margin), title, 
                             fill=(0, 0, 0), font=self.title_font)
                except Exception:
                    pass
            
            # Рисуем основную сетку
            main_bracket_y = margin + title_h + title_gap
            round_positions = self._draw_bracket_grid(draw, bracket, margin, main_bracket_y, main_bracket_width, main_bracket_height)
            
            # Рисуем соединительные линии для основной сетки
            self.draw_connectors(draw, round_positions, bracket.rounds)
            
            # Рисуем мини-турниры снизу от основной сетки с переупорядочиванием: 3-е место, 5-е, 7-е
            current_y = main_bracket_y + main_bracket_height + gap_between_main_and_minis
            if bracket.additional_tournaments:
                # Сортировка: сначала содержащие '3 место', потом '5', затем '7'
                def _order_key(t):
                    name = (t.name or '').lower()
                    if '3' in name and 'мест' in name:
                        return 0
                    if '5' in name and 'мест' in name:
                        return 1
                    if '7' in name and 'мест' in name:
                        return 2
                    return 3
                sorted_minis = sorted(bracket.additional_tournaments, key=_order_key)
                for i, mini_tournament in enumerate(sorted_minis):
                    tournament_x = margin
                    tournament_y = current_y
                    mini_round_positions = self._draw_mini_tournament_grid(draw, mini_tournament, tournament_x, tournament_y)
                    self.draw_connectors(draw, mini_round_positions, mini_tournament.rounds, 
                                        is_mini_tournament=True, tournament_name=mini_tournament.name)
                    mini_w, mini_h = self.calculate_bracket_dimensions(mini_tournament, is_mini=True)
                    current_y += mini_h + 10
            
            # Блок фотографий отключен по требованиям
            
            return image
            
        except Exception as e:
            print(f"Ошибка генерации олимпийской сетки: {e}")
            return self._create_error_image(str(e))

    def _text_size(self, text: str, font: Optional[ImageFont.ImageFont]) -> tuple[int, int]:
        """Безопасно измеряет размер текста для заданного шрифта."""
        try:
            if not font:
                return (0, 0)
            # Используем временное изображение для расчёта bbox
            dummy = Image.new('RGB', (1, 1))
            d = ImageDraw.Draw(dummy)
            bbox = d.textbbox((0, 0), str(text or ''), font=font)
            return (max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1]))
        except Exception:
            return (0, 0)

    def _collect_all_player_names(self, bracket: TournamentBracket) -> list[str]:
        names: list[str] = []
        try:
            for rnd in (bracket.rounds or []):
                for m in (rnd or []):
                    if getattr(m, 'player1', None) and getattr(m.player1, 'name', None):
                        names.append(m.player1.name)
                    if getattr(m, 'player2', None) and getattr(m.player2, 'name', None):
                        names.append(m.player2.name)
            for mini in (bracket.additional_tournaments or []):
                for rnd in (mini.rounds or []):
                    for m in (rnd or []):
                        if getattr(m, 'player1', None) and getattr(m.player1, 'name', None):
                            names.append(m.player1.name)
                        if getattr(m, 'player2', None) and getattr(m.player2, 'name', None):
                            names.append(m.player2.name)
        except Exception:
            pass
        # Фолбэк, чтобы не получить пустой набор
        if not names:
            names = ["Игрок"]
        return names

    def _autosize_layout(self, bracket: TournamentBracket) -> None:
        """Подгоняет размеры ячеек и расстояния между раундами под размеры шрифтов и текстов."""
        try:
            names = self._collect_all_player_names(bracket)
            # Максимальная ширина имени в ячейке
            max_name_w = 0
            name_h = 0
            for n in names:
                w, h = self._text_size(n, self.name_font)
                if w > max_name_w:
                    max_name_w = w
                if h > name_h:
                    name_h = h

            # Максимальная ширина подписи победителя на линиях (используется self.font)
            max_label_w = 0
            label_h = 0
            for n in names:
                w, h = self._text_size(n, self.font)
                if w > max_label_w:
                    max_label_w = w
                if h > label_h:
                    label_h = h

            # Параметры отступов
            horizontal_padding = 20  # внутри ячейки
            vertical_padding = max(10, self.font_size // 4)

            # Новая ширина ячейки: левый отступ + имя + правый отступ
            new_cell_width = horizontal_padding + max_name_w + horizontal_padding
            # Минимальное ограничение, чтобы не было слишком узко
            self.cell_width = max(self.cell_width, new_cell_width)

            # Новая высота ячейки: два ряда текста (два игрока) c вертикальными отступами
            # и минимальная высота под аватар (делаем аватар крупнее и читаемым)
            row_height = max(name_h + vertical_padding * 2, int(self.name_font_size * 1.2))
            new_cell_height = max(row_height * 2, int(self.name_font_size * 3))
            self.cell_height = max(self.cell_height, new_cell_height)

            # Сегмент горизонтальной линии коннектора должен умещать полную подпись победителя
            segment_len_required = max(self.cell_width, max_label_w + 16)
            self.final_line_length = segment_len_required
            self.round_spacing = segment_len_required + self.connector_offset
            self.mini_spacing = segment_len_required + self.connector_offset

            # Вертикальные отступы между матчами уменьшаем, но не меньше 6
            self.match_spacing = max(6, min(self.match_spacing, vertical_padding * 2))

            # Подписи над/под линиями – увеличим вертикальные поля для читаемости
            self.label_offset_above = max(self.label_offset_above, 6)
            self.label_offset_below = max(self.label_offset_below, 8)
            self.vertical_labels_padding = max(self.vertical_labels_padding, label_h * 3)
        except Exception:
            # В случае ошибки не рушим процесс
            pass
    
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
            
            # Заголовок раунда - для финала рисуем позже над точкой схождения линий
            is_final = round_num == len(bracket.rounds) - 1
            round_title = self._get_round_title(round_num, len(bracket.rounds))
            if self.font and not is_final:
                try:
                    title_bbox = draw.textbbox((0, 0), round_title, font=self.font)
                    title_width = title_bbox[2] - title_bbox[0]
                    if round_num == 0:
                        title_x = round_x + (self.cell_width - title_width) // 2
                    else:
                        title_x = round_x + (self.round_spacing - title_width) // 2
                    draw.text((title_x, start_y - 10), 
                        round_title, fill=self.round_title_color, font=self.font)
                except Exception:
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
            
            # Рисуем заголовок "Финал" посередине линии на той же высоте, что и другие туры
            if is_final and self.font and match_positions and round_num > 0 and len(round_positions) > 0:
                try:
                    title_bbox = draw.textbbox((0, 0), round_title, font=self.font)
                    title_width = title_bbox[2] - title_bbox[0]
                    # Позиция по горизонтали - посередине линии от предыдущего раунда до точки схождения
                    prev_round = round_positions[round_num - 1]
                    if prev_round:
                        # Начало линии (правый край предыдущих ячеек)
                        line_start_x = prev_round[0][0] + self.cell_width if round_num - 1 == 0 else prev_round[0][0]
                        # Конец линии (точка схождения)
                        line_end_x = round_x - self.connector_offset
                        # Центр линии
                        title_x = (line_start_x + line_end_x - title_width) // 2
                        # Позиция по вертикали - на той же высоте, что и другие туры
                        draw.text((title_x, start_y - 10), 
                            round_title, fill=self.round_title_color, font=self.font)
                except Exception:
                    pass
        
        return round_positions
    
    def _draw_mini_tournament_grid(self, draw: ImageDraw.Draw, tournament: TournamentBracket, start_x: int, start_y: int) -> List[List[Tuple[int, int]]]:
        """Рисует сетку мини-турнира"""
        round_positions = []
        current_x = start_x
        first_match_y = None
        
        for round_num, round_matches in enumerate(tournament.rounds):
            if not round_matches:
                continue
            
            # Для первого раунда используем полный промежуток с ячейкой
            # Отступ для соединительных линий и подписей (увеличен для полных имен и длинных линий)
            if round_num == 0:
                round_x = current_x
                current_x += self.cell_width + self.mini_spacing
            else:
                round_x = current_x
                current_x += self.mini_spacing

            # Позиции матчей в раунде
            match_positions = []
            tournament_height = self.calculate_bracket_dimensions(tournament)[1]
            
            for match_num, match in enumerate(round_matches):
                # Для мини-сеток start_y — это верх мини-блока; total_height — высота мини-блока
                match_y = self._calculate_match_y(round_num, match_num, round_matches, round_positions, start_y, tournament_height)
                match_positions.append((round_x, match_y))
                
                # Запоминаем Y-координату первой ячейки для привязки заголовка
                if first_match_y is None and round_num == 0 and match_num == 0:
                    first_match_y = match_y
                
                # Рисуем ячейки только для первого раунда, далее только линии
                if round_num == 0:
                    self.draw_match_cell(draw, round_x, match_y, match, round_num, is_mini_tournament=True)
            
            round_positions.append(match_positions)
        
        # Выводим название мини-турнира над первой ячейкой с увеличенным отступом
        tournament_title = tournament.name
        if self.bold_font and tournament_title and first_match_y is not None:
            try:
                title_bbox = draw.textbbox((0, 0), tournament_title, font=self.font)
                title_height = title_bbox[3] - title_bbox[1]
                title_x = start_x
                draw.text((title_x, first_match_y - title_height - self.mini_title_spacing),
                    tournament_title, fill=self.round_title_color, font=self.font)
            except Exception:
                pass
        
        return round_positions
    
    def _get_round_title(self, round_num: int, total_rounds: int) -> str:
        """Возвращает заголовок для раунда: "1-й круг", ..., последний — "Финал""" 
        if round_num == total_rounds - 1:
            return "Финал"
        # Нумерованные круги (1-й круг, 2-й круг, ...)
        return f"{round_num + 1}-й круг"
    
    def _calculate_match_y(self, round_num: int, match_num: int, round_matches: List[Match], 
                          round_positions: List[List[Tuple[int, int]]], start_y: int, total_height: int) -> int:
        """Вычисляет Y-позицию для матча"""
        if round_num == 0:
            # Первый раунд - равномерное распределение
            total_matches = len(round_matches)
            # total_height здесь трактуем как ВЫСОТУ области, а не абсолютную координату низа
            available_height = max(total_height, 0)
            offset_top = max((available_height - total_matches * (self.cell_height + self.match_spacing)) // 2, 0)
            return start_y + offset_top + match_num * (self.cell_height + self.match_spacing)
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
            
            # Fallback равномерное распределение в доступной области
            total_matches = len(round_matches)
            available_height = max(total_height, 0)
            offset_top = max((available_height - total_matches * (self.cell_height + self.match_spacing)) // 2, 0)
            return start_y + offset_top + match_num * (self.cell_height + self.match_spacing)
    
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
    
    def calculate_bracket_dimensions(self, bracket: TournamentBracket, is_mini: bool = False) -> Tuple[int, int]:
        """Вычисляет размеры для сетки"""
        try:
            if not bracket.rounds:
                return (400, 200)
            
            # Ширина: первый раунд с ячейкой, остальные только spacing
            # Корректная формула без лишнего правого отступа:
            # width = cell_width + (num_rounds - 1) * spacing + final_line_length
            num_rounds = len(bracket.rounds)
            if num_rounds > 0:
                spacing = self.mini_spacing if is_mini else self.round_spacing
                width = self.cell_width + max(0, num_rounds - 1) * spacing
                # Добавляем только длину финальной линии
                width += self.final_line_length
            else:
                width = 400
            
            # Высота: учитываем максимальное количество матчей + дополнительное пространство для подписей
            max_matches = max(len(round_matches) for round_matches in bracket.rounds)
            # Добавляем дополнительное пространство сверху и снизу для подписей победителей и счета
            height = (max_matches * (self.cell_height + self.match_spacing) + self.vertical_labels_padding)
            
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
