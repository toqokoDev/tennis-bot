import io
import os
import math
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Tuple, Optional
from utils.tournament_brackets import TournamentBracket, Player, Match
from config.paths import BASE_DIR, GAMES_PHOTOS_DIR


class BracketImageGenerator:
    """Класс для генерации изображений турнирных сеток с улучшенным отображением"""
    
    def __init__(self):
        # Основные размеры
        self.cell_width = 300
        self.cell_height = 80
        self.round_spacing = 120
        self.match_spacing = 40
        self.vertical_margin = 30
        self.font_size = 14
        self.title_font_size = 26
        self.subtitle_font_size = 18
        self.table_font_size = 12
        
        # Цветовая схема
        self.bg_color = (248, 250, 252)  # Светло-серый фон
        self.cell_color = (255, 255, 255)  # Белый фон ячейки
        self.cell_border_color = (209, 213, 219)  # Серый бордер
        self.text_color = (31, 41, 55)  # Темно-серый текст
        self.secondary_text_color = (107, 114, 128)  # Серый текст
        self.winner_color = (34, 197, 94)  # Зеленый для победителя
        self.winner_bg_color = (220, 252, 231)  # Светло-зеленый фон победителя
        self.bye_color = (156, 163, 175)  # Серый для BYE
        self.connector_color = (156, 163, 175)  # Цвет соединительных линий
        self.round_title_color = (59, 130, 246)  # Синий для заголовков раундов
        self.table_header_color = (59, 130, 246)  # Синий для заголовков таблицы
        self.table_row_color_even = (248, 250, 252)  # Четные строки таблицы
        self.table_row_color_odd = (255, 255, 255)  # Нечетные строки таблицы
        
        # Эффекты
        self.cell_shadow = True
        self.rounded_corners = True
        
        # Загрузка шрифтов
        try:
            self.font = ImageFont.truetype("arial.ttf", self.font_size)
            self.bold_font = ImageFont.truetype("arialbd.ttf", self.font_size)
            self.title_font = ImageFont.truetype("arialbd.ttf", self.title_font_size)
            self.subtitle_font = ImageFont.truetype("arialbd.ttf", self.subtitle_font_size)
            self.table_font = ImageFont.truetype("arial.ttf", self.table_font_size)
            self.table_bold_font = ImageFont.truetype("arialbd.ttf", self.table_font_size)
        except:
            try:
                self.font = ImageFont.load_default()
                self.bold_font = ImageFont.load_default()
                self.title_font = ImageFont.load_default()
                self.subtitle_font = ImageFont.load_default()
                self.table_font = ImageFont.load_default()
                self.table_bold_font = ImageFont.load_default()
            except:
                self.font = None
                self.bold_font = None
                self.title_font = None
                self.subtitle_font = None
                self.table_font = None
                self.table_bold_font = None
    
    def load_user_photo(self, photo_path: str) -> Optional[Image.Image]:
        """Загружает фото пользователя из локального файла"""
        try:
            if not photo_path:
                return None
            
            # Безопасное преобразование пути
            full_path = str(photo_path)
            try:
                if not os.path.isabs(photo_path) and BASE_DIR:
                    full_path = str((BASE_DIR / photo_path).resolve())
            except (TypeError, AttributeError):
                full_path = str(photo_path)
            
            # Проверяем существование файла
            if not os.path.exists(full_path):
                return None
            
            image = Image.open(full_path)
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')
            return image
        except Exception as e:
            print(f"Ошибка загрузки фото пользователя {photo_path}: {e}")
        return None

    def load_game_photo(self, media_filename: Optional[str], game_id: Optional[str] = None) -> Optional[Image.Image]:
        """Загружает фото игры по имени файла или game_id (ищет по маске)."""
        try:
            candidate_paths: List[str] = []
            
            if media_filename:
                try:
                    if GAMES_PHOTOS_DIR:
                        candidate_paths.append(str((GAMES_PHOTOS_DIR / str(media_filename)).resolve()))
                    else:
                        candidate_paths.append(str(media_filename))
                except (TypeError, AttributeError):
                    candidate_paths.append(str(media_filename))
            
            # Попытка по маске, если известен id
            if game_id and not media_filename and GAMES_PHOTOS_DIR:
                game_id_str = str(game_id)
                # пробуем common имена: <id>_photo.*
                for ext in ["jpg", "jpeg", "png"]:
                    candidate_paths.append(str((GAMES_PHOTOS_DIR / f"{game_id_str}_photo.{ext}").resolve()))
            
            for path in candidate_paths:
                if os.path.exists(path):
                    img = Image.open(path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    return img
        except Exception as e:
            print(f"Ошибка загрузки фото игры: {e}")
        return None
    
    def create_player_avatar(self, player: Player, size: int = 36) -> Image.Image:
        """Создает аватар игрока с улучшенным дизайном"""
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        
        # Пытаемся загрузить фото пользователя
        if player and hasattr(player, 'photo_url') and player.photo_url:
            user_photo = self.load_user_photo(str(player.photo_url))
            if user_photo:
                # Создаем круглую маску
                mask = Image.new('L', (size, size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse([0, 0, size, size], fill=255)
                
                # Изменяем размер фото и применяем маску
                user_photo = user_photo.resize((size, size), Image.Resampling.LANCZOS)
                avatar.paste(user_photo, (0, 0), mask)
            else:
                # Если фото не загрузилось, создаем круг с инициалами
                self._draw_circle_with_initials(draw, player, size)
        else:
            # Создаем круг с инициалами
            self._draw_circle_with_initials(draw, player, size)
        
        return avatar
    
    def _draw_circle_with_initials(self, draw: ImageDraw.Draw, player: Player, size: int):
        """Рисует круг с инициалами игрока с градиентом"""
        # Градиентный фон
        center = size // 2
        for r in range(center, 0, -1):
            alpha = int(200 * (r / center))
            color = (100, 150, 200, alpha)
            draw.ellipse([center - r, center - r, center + r, center + r], fill=color)
        
        # Белый бордер
        draw.ellipse([2, 2, size-2, size-2], outline=(255, 255, 255, 200), width=2)
        
        # Инициалы
        initials = self._get_player_initials(player)
        
        # Рисуем инициалы
        if self.font:
            try:
                bbox = draw.textbbox((0, 0), initials, font=self.bold_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = (size - text_width) // 2
                y = (size - text_height) // 2
                
                draw.text((x, y), initials, fill=(255, 255, 255, 255), font=self.bold_font)
            except:
                # Fallback если шрифт не работает
                draw.text((size//4, size//4), initials, fill=(255, 255, 255, 255))
    
    def _get_player_initials(self, player: Player) -> str:
        """Получает инициалы игрока"""
        if not player:
            return "??"
            
        if hasattr(player, 'initial') and player.initial:
            return str(player.initial)
        
        if hasattr(player, 'name') and player.name:
            name_str = str(player.name)
            if len(name_str) > 0:
                words = name_str.split()
                if len(words) >= 2:
                    return f"{words[0][0].upper()}{words[1][0].upper()}"
                else:
                    return name_str[0].upper()
        
        return "??"
    
    def _draw_rounded_rectangle(self, draw: ImageDraw.Draw, x1: int, y1: int, x2: int, y2: int, radius: int = 8, **kwargs):
        """Рисует прямоугольник со скругленными углами"""
        # Основной прямоугольник
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], **kwargs)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], **kwargs)
        
        # Углы
        draw.ellipse([x1, y1, x1 + radius*2, y1 + radius*2], **kwargs)
        draw.ellipse([x2 - radius*2, y1, x2, y1 + radius*2], **kwargs)
        draw.ellipse([x1, y2 - radius*2, x1 + radius*2, y2], **kwargs)
        draw.ellipse([x2 - radius*2, y2 - radius*2, x2, y2], **kwargs)
    
    def _draw_cell_shadow(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int, radius: int = 8):
        """Рисует тень для ячейки"""
        shadow_color = (0, 0, 0, 30)
        shadow_offset = 2
        
        for i in range(3):
            alpha = shadow_color[3] - i * 10
            if alpha <= 0:
                break
                
            shadow_x = x + shadow_offset + i
            shadow_y = y + shadow_offset + i
            
            self._draw_rounded_rectangle(
                draw, shadow_x, shadow_y, 
                shadow_x + width, shadow_y + height,
                radius, fill=(0, 0, 0, alpha)
            )
    
    def draw_match_cell(self, base_image: Image.Image, draw: ImageDraw.Draw, x: int, y: int, match: Match, round_num: int = 0) -> None:
        """Рисует улучшенную ячейку матча"""
        # Безопасная проверка матча
        if not match:
            return
            
        # Определяем цвета в зависимости от статуса матча
        if hasattr(match, 'is_bye') and match.is_bye:
            bg_color = (243, 244, 246)  # Серый фон для BYE
            border_color = self.bye_color
            text_color = self.secondary_text_color
        elif hasattr(match, 'winner') and match.winner:
            bg_color = self.winner_bg_color
            border_color = self.winner_color
            text_color = self.text_color
        else:
            bg_color = self.cell_color
            border_color = self.cell_border_color
            text_color = self.text_color
        
        # Рисуем тень
        if self.cell_shadow:
            self._draw_cell_shadow(draw, x, y, self.cell_width, self.cell_height)
        
        # Рисуем основной прямоугольник
        if self.rounded_corners:
            self._draw_rounded_rectangle(
                draw, x, y, x + self.cell_width, y + self.cell_height,
                radius=8, fill=bg_color, outline=border_color, width=2
            )
        else:
            draw.rectangle([x, y, x + self.cell_width, y + self.cell_height], 
                          fill=bg_color, outline=border_color, width=2)
        
        # Информация о матче (раунд и номер)
        match_info = f"R{round_num + 1} M{getattr(match, 'match_number', 0) + 1}"
        if self.font:
            try:
                info_bbox = draw.textbbox((0, 0), match_info, font=self.font)
                info_width = info_bbox[2] - info_bbox[0]
                draw.text((x + self.cell_width - info_width - 8, y + 8), match_info, 
                         fill=self.secondary_text_color, font=self.font)
            except:
                pass
        
        # Рисуем игроков
        player_elements = []
        
        player1 = getattr(match, 'player1', None)
        player2 = getattr(match, 'player2', None)
        
        if player1 and hasattr(player1, 'id') and str(player1.id) != "bye":
            if hasattr(player1, 'id') and str(player1.id).startswith("empty"):
                player_elements.append(("Свободное место", None, False))
            else:
                avatar1 = self.create_player_avatar(player1, 32)
                is_winner = hasattr(match, 'winner') and match.winner == player1
                player_elements.append((getattr(player1, 'name', 'Игрок 1'), avatar1, is_winner))
        
        if player2 and hasattr(player2, 'id') and str(player2.id) != "bye":
            if hasattr(player2, 'id') and str(player2.id).startswith("empty"):
                player_elements.append(("Свободное место", None, False))
            else:
                avatar2 = self.create_player_avatar(player2, 32)
                is_winner = hasattr(match, 'winner') and match.winner == player2
                player_elements.append((getattr(player2, 'name', 'Игрок 2'), avatar2, is_winner))
        
        # Распределяем игроков по вертикали
        player_height = 32
        total_height = len(player_elements) * player_height
        start_y = y + (self.cell_height - total_height) // 2
        
        for i, (name, avatar, is_winner) in enumerate(player_elements):
            player_y = start_y + i * player_height
            
            # Аватар
            if avatar:
                try:
                    base_image.paste(avatar, (x + 12, player_y), avatar)
                except Exception:
                    try:
                        base_image.paste(avatar, (x + 12, player_y))
                    except:
                        pass
            
            # Имя игрока
            name_str = str(name) if name else "Игрок"
            display_name = name_str[:18] + "..." if len(name_str) > 18 else name_str
            name_x = x + 52
            
            if self.font:
                try:
                    # Выделяем победителя жирным шрифтом
                    font = self.bold_font if is_winner else self.font
                    draw.text((name_x, player_y + 8), display_name, fill=text_color, font=font)
                except:
                    pass
        
        # Рисуем счет если есть
        score = getattr(match, 'score', None)
        if score and self.font:
            try:
                score_str = str(score)
                score_bbox = draw.textbbox((0, 0), score_str, font=self.bold_font)
                score_width = score_bbox[2] - score_bbox[0]
                draw.text((x + self.cell_width - score_width - 12, y + self.cell_height - 25), 
                         score_str, fill=text_color, font=self.bold_font)
            except:
                pass
    
    def generate_olympic_bracket_image(self, bracket: TournamentBracket) -> Image.Image:
        """Генерирует улучшенное изображение сетки олимпийской системы"""
        try:
            width, height = self.calculate_bracket_dimensions(bracket)
            
            # Создаем изображение с прозрачностью для тени
            image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            
            # Фон
            draw.rectangle([0, 0, width, height], fill=self.bg_color)
            
            # Заголовок
            tournament_type = getattr(bracket, 'tournament_type', 'Турнир')
            title = f"🏆 Турнирная сетка - {tournament_type}"
            
            if self.title_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.title_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text(((width - title_width) // 2, 25), title, 
                             fill=self.text_color, font=self.title_font)
                except:
                    pass
            
            if not hasattr(bracket, 'rounds') or not bracket.rounds:
                players = getattr(bracket, 'players', []) or []
                if players:
                    self._draw_players_list(draw, players, width, height)
                else:
                    self._draw_empty_state(draw, "Нет участников", width, height)
                return image.convert('RGB')
            
            # Рисуем раунды с соединительными линиями
            round_positions = []
            
            for round_num, round_matches in enumerate(bracket.rounds):
                if not round_matches:
                    continue
                    
                round_x = 50 + round_num * (self.cell_width + self.round_spacing)
                
                # Заголовок раунда
                round_title = f"Раунд {round_num + 1}"
                if self.font:
                    try:
                        title_bbox = draw.textbbox((0, 0), round_title, font=self.bold_font)
                        title_width = title_bbox[2] - title_bbox[0]
                        draw.text((round_x + (self.cell_width - title_width) // 2, 110), 
                                 round_title, fill=self.round_title_color, font=self.bold_font)
                    except:
                        pass
                
                # Позиции матчей в раунде
                match_positions = []
                
                for match_num, match in enumerate(round_matches):
                    # Вычисляем Y-позицию с учетом двоичного дерева
                    if round_num == 0:
                        # Первый раунд - равномерное распределение
                        total_first_round_matches = len(bracket.rounds[0])
                        match_y = (150 + match_num * (self.cell_height + self.match_spacing) + 
                                  (height - 150 - total_first_round_matches * (self.cell_height + self.match_spacing)) // 2)
                    else:
                        # Последующие раунды - позиционируем между матчами предыдущего раунда
                        prev_match1_idx = match_num * 2
                        prev_match2_idx = match_num * 2 + 1
                        
                        if (prev_match1_idx < len(round_positions[round_num - 1]) and 
                            prev_match2_idx < len(round_positions[round_num - 1])):
                            y1 = round_positions[round_num - 1][prev_match1_idx][1] + self.cell_height // 2
                            y2 = round_positions[round_num - 1][prev_match2_idx][1] + self.cell_height // 2
                            match_y = (y1 + y2) // 2 - self.cell_height // 2
                        else:
                            # Fallback равномерное распределение
                            total_matches = len(round_matches)
                            match_y = (150 + match_num * (self.cell_height + self.match_spacing) + 
                                      (height - 150 - total_matches * (self.cell_height + self.match_spacing)) // 2)
                    
                    match_positions.append((round_x, match_y))
                    self.draw_match_cell(image, draw, round_x, match_y, match, round_num)
                
                round_positions.append(match_positions)
            
            return image.convert('RGB')
            
        except Exception as e:
            print(f"Ошибка генерации олимпийской сетки: {e}")
            return self._create_empty_bracket_image(f"Ошибка: {str(e)}")
    
    def generate_round_robin_image(self, bracket: TournamentBracket) -> Image.Image:
        """Генерирует улучшенное изображение турнирной таблицы для круговой системы"""
        try:
            players = getattr(bracket, 'players', []) or []
            
            if not players:
                return self._create_empty_bracket_image("Нет участников")
            
            # Создаем изображение с достаточной шириной для таблицы
            width = 1000  # Уменьшено с 1200
            height = 600  # Уменьшено с 800
            
            image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            
            # Фон
            draw.rectangle([0, 0, width, height], fill=self.bg_color)
            
            # Заголовок
            tournament_name = getattr(bracket, 'name', 'Турнир уровня 1.5-2.5 Север №11')
            title = f"🏆 {tournament_name}"
            subtitle = "Круговая система | Мужчины"
            status = "ЗАВЕРШЁН"
            
            if self.title_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.title_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text(((width - title_width) // 2, 20), title, 
                             fill=self.text_color, font=self.title_font)
                except:
                    pass
            
            if self.subtitle_font:
                try:
                    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=self.subtitle_font)
                    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
                    draw.text(((width - subtitle_width) // 2, 55), subtitle, 
                             fill=self.secondary_text_color, font=self.subtitle_font)
                except:
                    pass
            
            # Статус турнира
            if self.bold_font:
                try:
                    status_bbox = draw.textbbox((0, 0), status, font=self.bold_font)
                    status_width = status_bbox[2] - status_bbox[0]
                    status_color = (34, 197, 94)  # Зеленый для завершенного
                    draw.text(((width - status_width) // 2, 85), status, 
                             fill=status_color, font=self.bold_font)
                except:
                    pass
            
            # Рисуем турнирную таблицу
            self._draw_tournament_table(draw, players, bracket, width, height)
            
            return image.convert('RGB')
            
        except Exception as e:
            print(f"Ошибка генерации круговой сетки: {e}")
            return self._create_empty_bracket_image(f"Ошибка: {str(e)}")
    
    def _draw_tournament_table(self, draw: ImageDraw.Draw, players: List[Player], bracket: TournamentBracket, width: int, height: int):
        """Рисует турнирную таблицу с результатами"""
        try:
            # Определяем размеры таблицы
            # Колонки: Место | Игрок | Игры | Победы | Очки
            col_widths = [60, 200, 80, 80, 80]  # Упрощенные колонки
            row_height = 35  # Уменьшена высота строк
            header_height = 40
            
            # Начальные координаты таблицы
            table_x = 50
            table_y = 120  # Сдвинуто выше
            table_width = sum(col_widths)
            
            # Заголовок таблицы
            headers = ["Место", "Игрок", "Игры", "Победы", "Очки"]
            
            # Рисуем заголовок таблицы
            self._draw_table_header(draw, headers, col_widths, table_x, table_y, table_width, header_height)
            
            # Рисуем строки с игроками
            current_y = table_y + header_height

            # Подготовим статистику для круговой таблицы на основе self.games
            def compute_round_robin_stats(all_players: List[Player], games: Optional[List[Dict[str, Any]]]):
                player_ids = [getattr(p, 'id', None) for p in all_players]
                results = {pid: {} for pid in player_ids if pid is not None}
                wins = {pid: 0 for pid in player_ids if pid is not None}
                games_played = {pid: 0 for pid in player_ids if pid is not None}
                points = {pid: 0 for pid in player_ids if pid is not None}
                tied_ids = set()

                if games:
                    for game in games:
                        try:
                            if game.get('status') != 'completed':
                                continue
                            game_players = game.get('players') or []
                            if len(game_players) < 2:
                                continue
                            
                            # Получаем ID игроков из структуры teams
                            teams = game.get('players', {})
                            if isinstance(teams, dict):
                                team1_players = teams.get('team1', [])
                                team2_players = teams.get('team2', [])
                                if len(team1_players) > 0 and len(team2_players) > 0:
                                    p1 = team1_players[0]
                                    p2 = team2_players[0]
                                else:
                                    continue
                            else:
                                continue
                                
                            if p1 not in results or p2 not in results:
                                continue
                            score = game.get('score', '')
                            if not score:
                                continue
                            sets = [s.strip() for s in str(score).split(',') if ':' in s]
                            p1_sets = 0
                            p2_sets = 0
                            for set_score in sets:
                                try:
                                    a, b = map(int, set_score.split(':'))
                                except Exception:
                                    continue
                                if a > b:
                                    p1_sets += 1
                                elif b > a:
                                    p2_sets += 1
                            # записываем двунаправленно
                            results[p1][p2] = {'sets_won': p1_sets, 'sets_lost': p2_sets}
                            results[p2][p1] = {'sets_won': p2_sets, 'sets_lost': p1_sets}
                            # победы
                            if p1_sets > p2_sets:
                                wins[p1] += 1
                            elif p2_sets > p1_sets:
                                wins[p2] += 1
                        except Exception as e:
                            print(f"Ошибка обработки игры: {e}")
                            continue

                # игры сыграно по количеству записанных соперников
                for pid in player_ids:
                    if pid is None:
                        continue
                    games_played[pid] = len(results.get(pid, {}))

                # очки для тай-брейка в группах по победам
                wins_groups = {}
                for pid in player_ids:
                    if pid is None:
                        continue
                    wins_groups.setdefault(wins.get(pid, 0), []).append(pid)
                for _, group in wins_groups.items():
                    if len(group) <= 1:
                        continue
                    tied_ids.update(group)
                    for pid in group:
                        total = 0
                        for opp in group:
                            if opp == pid:
                                continue
                            if opp in results.get(pid, {}):
                                r = results[pid][opp]
                                total += int(r.get('sets_won', 0)) - int(r.get('sets_lost', 0))
                        points[pid] = total

                # сортировка и места
                sorted_ids = sorted(
                    [pid for pid in player_ids if pid is not None],
                    key=lambda pid: (wins.get(pid, 0), points.get(pid, 0)),
                    reverse=True
                )
                places = {pid: idx + 1 for idx, pid in enumerate(sorted_ids)}

                return {
                    'wins': wins,
                    'games_played': games_played,
                    'points': points,
                    'tied_ids': tied_ids,
                    'places': places,
                }

            # Получаем игры из bracket или используем переданные
            games = getattr(bracket, 'games', None) or getattr(self, 'games', None)
            stats = compute_round_robin_stats(players, games)

            for i, player in enumerate(players):
                # Цвет фона строки (чередование)
                row_color = self.table_row_color_even if i % 2 == 0 else self.table_row_color_odd
                
                # Рисуем фон строки
                draw.rectangle([table_x, current_y, table_x + table_width, current_y + row_height], 
                              fill=row_color, outline=self.cell_border_color, width=1)
                
                # Получаем данные игрока
                pid = getattr(player, 'id', None)
                place = stats['places'].get(pid, i + 1)
                games_count = stats['games_played'].get(pid, 0)
                wins_count = stats['wins'].get(pid, 0)
                points_count = stats['points'].get(pid, 0)
                
                # Рисуем ячейки строки
                cell_x = table_x
                
                # Место
                self._draw_table_cell(draw, str(place), cell_x, current_y, col_widths[0], row_height, 
                                    is_bold=(place <= 3))
                cell_x += col_widths[0]
                
                # Игрок
                self._draw_player_cell(draw, player, cell_x, current_y, col_widths[1], row_height)
                cell_x += col_widths[1]
                
                # Игры
                self._draw_table_cell(draw, str(games_count), cell_x, current_y, col_widths[2], row_height)
                cell_x += col_widths[2]
                
                # Победы
                self._draw_table_cell(draw, str(wins_count), cell_x, current_y, col_widths[3], row_height)
                cell_x += col_widths[3]
                
                # Очки (только для игроков с равным количеством побед)
                points_display = str(points_count) if pid in stats['tied_ids'] else "-"
                self._draw_table_cell(draw, points_display, cell_x, current_y, col_widths[4], row_height)
                
                current_y += row_height
            
            # Подпись под таблицей
            footnote_y = current_y + 15
            footnote = "* В столбце 'Очки' показана общая разница в сетах между игроками с равным количеством побед."
            
            if self.table_font:
                draw.text((table_x, footnote_y), footnote, fill=self.secondary_text_color, font=self.table_font)
                
        except Exception as e:
            print(f"Ошибка отрисовки таблицы: {e}")
    
    def _draw_table_header(self, draw: ImageDraw.Draw, headers: List[str], col_widths: List[int], 
                          x: int, y: int, width: int, height: int):
        """Рисует заголовок таблицы"""
        # Фон заголовка
        draw.rectangle([x, y, x + width, y + height], 
                      fill=self.table_header_color, outline=self.cell_border_color, width=1)
        
        # Текст заголовков
        cell_x = x
        for header, col_width in zip(headers, col_widths):
            if self.table_bold_font:
                try:
                    bbox = draw.textbbox((0, 0), header, font=self.table_bold_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    text_x = cell_x + (col_width - text_width) // 2
                    text_y = y + (height - text_height) // 2
                    
                    draw.text((text_x, text_y), header, fill=(255, 255, 255), font=self.table_bold_font)
                except:
                    pass
            
            cell_x += col_width
    
    def _draw_player_cell(self, draw: ImageDraw.Draw, player: Player, x: int, y: int, width: int, height: int):
        """Рисует ячейку с информацией об игроке"""
        try:
            # Аватар
            avatar_size = 25  # Уменьшен размер аватара
            avatar = self.create_player_avatar(player, avatar_size)
            
            # Вставляем аватар
            if avatar:
                try:
                    draw._image.paste(avatar, (x + 5, y + (height - avatar_size) // 2), avatar)
                except:
                    draw._image.paste(avatar, (x + 5, y + (height - avatar_size) // 2))
            
            # Имя игрока
            player_name = getattr(player, 'name', 'Игрок')
            display_name = player_name[:18] + "..." if len(player_name) > 18 else player_name
            
            if self.table_bold_font:
                draw.text((x + 35, y + (height - 12) // 2), display_name, 
                         fill=self.text_color, font=self.table_bold_font)
                         
        except Exception as e:
            print(f"Ошибка отрисовки ячейки игрока: {e}")
    
    def _draw_table_cell(self, draw: ImageDraw.Draw, value: str, x: int, y: int, width: int, height: int, is_bold: bool = False):
        """Рисует обычную ячейку таблицы"""
        try:
            font = self.table_bold_font if is_bold else self.table_font
            
            if font:
                bbox = draw.textbbox((0, 0), value, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                text_x = x + (width - text_width) // 2
                text_y = y + (height - text_height) // 2
                
                color = self.winner_color if is_bold and value == "1" else self.text_color
                
                draw.text((text_x, text_y), value, fill=color, font=font)
        except:
            pass
    
    def calculate_bracket_dimensions(self, bracket: TournamentBracket) -> Tuple[int, int]:
        """Вычисляет оптимальные размеры для сетки"""
        try:
            if not hasattr(bracket, 'rounds') or not bracket.rounds:
                players = getattr(bracket, 'players', []) or []
                if players:
                    height = 150 + len(players) * (self.cell_height + self.match_spacing)
                    return (800, height)
                return (800, 400)
            
            # Вычисляем максимальное количество матчей в раунде
            max_matches = max(len(round_matches) for round_matches in bracket.rounds)
            
            # Ширина: учитываем все раунды + отступы
            width = (len(bracket.rounds) * (self.cell_width + self.round_spacing) + 100)
            
            # Высота: учитываем максимальное количество матчей + заголовки
            height = (150 + max_matches * (self.cell_height + self.match_spacing))
            
            return (width, height)
            
        except:
            return (800, 600)
    
    def _draw_players_list(self, draw: ImageDraw.Draw, players: List[Player], width: int, height: int):
        """Рисует список участников"""
        try:
            title = "Участники турнира"
            if self.subtitle_font:
                title_bbox = draw.textbbox((0, 0), title, font=self.subtitle_font)
                title_width = title_bbox[2] - title_bbox[0]
                draw.text(((width - title_width) // 2, 120), title, 
                         fill=self.text_color, font=self.subtitle_font)
            
            # Распределяем игроков по колонкам
            players_per_column = 8  # Уменьшено количество игроков в колонке
            num_columns = math.ceil(len(players) / players_per_column)
            column_width = width // max(1, num_columns)
            
            for i, player in enumerate(players):
                col = i // players_per_column
                row = i % players_per_column
                
                x = 50 + col * column_width
                y = 160 + row * 35  # Уменьшено расстояние между строками
                
                # Аватар
                avatar = self.create_player_avatar(player, 22)  # Уменьшен размер аватара
                if avatar:
                    try:
                        draw._image.paste(avatar, (x, y), avatar)
                    except:
                        draw._image.paste(avatar, (x, y))
                
                # Имя игрока
                player_name = getattr(player, 'name', 'Игрок')
                display_name = player_name[:18] + "..." if len(player_name) > 18 else player_name
                
                if self.font:
                    draw.text((x + 28, y + 4), display_name, fill=self.text_color, font=self.font)
                    
        except Exception as e:
            print(f"Ошибка отрисовки списка игроков: {e}")
    
    def _draw_empty_state(self, draw: ImageDraw.Draw, message: str, width: int, height: int):
        """Рисует состояние пустой сетки"""
        try:
            if self.title_font:
                bbox = draw.textbbox((0, 0), message, font=self.title_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = (width - text_width) // 2
                y = (height - text_height) // 2
                
                draw.text((x, y), message, fill=self.secondary_text_color, font=self.title_font)
        except:
            pass

    def append_games_sidebar(self, base_image: Image.Image, games: List[Dict[str, Any]]) -> Image.Image:
        """Добавляет справа колонку с завершенными играми и детальной информацией."""
        try:
            if not games:
                return base_image
            
            sidebar_width = 300  # Уменьшена ширина сайдбара
            margin = 15
            thumb_w, thumb_h = 270, 150  # Уменьшены размеры миниатюр
            header_h = 40
            gap = 15
            game_card_height = thumb_h + 60  # Уменьшена высота карточки
            
            # Вычисляем сколько игр поместится
            available_height = base_image.height - header_h - margin * 2
            max_items = max(1, available_height // game_card_height)
            games_to_show = games[:max_items]
            
            # Создаем новое изображение шире и переносим базовую сетку
            new_w = base_image.width + sidebar_width
            new_h = base_image.height
            out = Image.new('RGB', (new_w, new_h), self.bg_color)
            out.paste(base_image, (0, 0))
            draw = ImageDraw.Draw(out)
            
            # Заголовок с фоном
            x0 = base_image.width
            draw.rectangle([x0, 0, new_w, header_h], fill=self.table_header_color)
            title = "🎮 Последние игры"
            if self.subtitle_font:
                try:
                    title_bbox = draw.textbbox((0, 0), title, font=self.subtitle_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    draw.text((x0 + (sidebar_width - title_width) // 2, 10), title, 
                             fill=(255, 255, 255), font=self.subtitle_font)
                except:
                    pass
            
            # Элементы игр
            y = header_h + margin
            
            for game in games_to_show:
                if y + game_card_height > new_h - margin:
                    break
                    
                media_filename = game.get('media_filename') or game.get('photo_filename')
                game_id = str(game.get('id', '')) if game.get('id') is not None else None
                img = self.load_game_photo(media_filename, game_id)
                
                # Карточка игры
                card_x = x0 + margin
                card_y = y
                
                # Тень карточки
                self._draw_rounded_rectangle(draw, card_x + 2, card_y + 2, 
                                           card_x + thumb_w + 2, card_y + game_card_height + 2,
                                           radius=6, fill=(0, 0, 0, 30))
                
                # Основная карточка
                self._draw_rounded_rectangle(draw, card_x, card_y, 
                                           card_x + thumb_w, card_y + game_card_height,
                                           radius=6, fill=(255, 255, 255), 
                                           outline=self.cell_border_color, width=1)
                
                # Миниатюра игры
                if img:
                    try:
                        # Обрезаем и масштабируем изображение
                        thumb = img.copy()
                        thumb = thumb.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                        out.paste(thumb, (card_x, card_y))
                    except Exception:
                        # Fallback - рисуем плашку
                        self._draw_rounded_rectangle(draw, card_x, card_y, 
                                                   card_x + thumb_w, card_y + thumb_h,
                                                   radius=4, fill=(243, 244, 246))
                else:
                    # Плашка-заглушка
                    self._draw_rounded_rectangle(draw, card_x, card_y, 
                                               card_x + thumb_w, card_y + thumb_h,
                                               radius=4, fill=(243, 244, 246))
                    
                    if self.font:
                        try:
                            text_bbox = draw.textbbox((0, 0), "Нет фото", font=self.font)
                            text_width = text_bbox[2] - text_bbox[0]
                            text_height = text_bbox[3] - text_bbox[1]
                            
                            tx = card_x + (thumb_w - text_width) // 2
                            ty = card_y + (thumb_h - text_height) // 2
                            draw.text((tx, ty), "Нет фото", fill=self.secondary_text_color, font=self.font)
                        except:
                            pass
                
                # Информация об игре под миниатюрой
                info_y = card_y + thumb_h + 8
                
                # Счет (самая важная информация)
                score = str(game.get('score', ''))
                
                if self.bold_font and score:
                    try:
                        score_text = f"Счет: {score}"
                        score_bbox = draw.textbbox((0, 0), score_text, font=self.bold_font)
                        score_width = score_bbox[2] - score_bbox[0]
                        draw.text((card_x + (thumb_w - score_width) // 2, info_y), 
                                 score_text, fill=self.winner_color, font=self.bold_font)
                    except:
                        pass
                
                # Дата игры
                date = game.get('date', '')
                if date and self.font:
                    try:
                        # Форматируем дату
                        date_str = str(date)[:16]  # Берем первую часть даты
                        date_bbox = draw.textbbox((0, 0), date_str, font=self.font)
                        date_width = date_bbox[2] - date_bbox[0]
                        draw.text((card_x + (thumb_w - date_width) // 2, info_y + 20), 
                                 date_str, fill=self.secondary_text_color, font=self.font)
                    except:
                        pass
                
                y += game_card_height + gap
                
            return out
            
        except Exception as e:
            print(f"Ошибка добавления сайдбара с играми: {e}")
            return base_image
    
    def _create_empty_bracket_image(self, message: str) -> Image.Image:
        """Создает пустое изображение с сообщением"""
        try:
            image = Image.new('RGB', (600, 300), self.bg_color)
            draw = ImageDraw.Draw(image)
            
            if self.title_font:
                bbox = draw.textbbox((0, 0), message, font=self.title_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = (600 - text_width) // 2
                y = (300 - text_height) // 2
                
                draw.text((x, y), message, fill=self.secondary_text_color, font=self.title_font)
            
            return image
        except:
            # Фолбэк на случай ошибки
            return Image.new('RGB', (600, 300), self.bg_color)
    
    def generate_bracket_image(self, bracket: TournamentBracket) -> Image.Image:
        """Генерирует изображение турнирной сетки в зависимости от типа"""
        try:
            tournament_type = getattr(bracket, 'tournament_type', 'Олимпийская система')
            if tournament_type == "Олимпийская система":
                return self.generate_olympic_bracket_image(bracket)
            elif tournament_type == "Круговая":
                return self.generate_round_robin_image(bracket)
            else:
                return self._create_empty_bracket_image("Неизвестный тип турнира")
        except Exception as e:
            print(f"Ошибка генерации изображения сетки: {e}")
            return self._create_empty_bracket_image(f"Ошибка: {str(e)}")


def create_bracket_image(bracket: TournamentBracket, games: Optional[List[Dict[str, Any]]] = None) -> Image.Image:
    """Создает изображение турнирной сетки с необязательной колонкой игр."""
    try:
        generator = BracketImageGenerator()
        print(bracket.tournament_type)
        print(bracket.players)
        print(bracket.matches)
        print(bracket.rounds)
        # Сохраняем игры для использования в статистике
        if games:
            generator.games = games
        image = generator.generate_bracket_image(bracket)
        if games:
            image = generator.append_games_sidebar(image, games)
        return image
    except Exception as e:
        print(f"Ошибка создания изображения сетки: {e}")
        # Возвращаем пустое изображение с сообщением об ошибке
        error_image = Image.new('RGB', (800, 400), (248, 250, 252))
        draw = ImageDraw.Draw(error_image)
        draw.text((50, 50), f"Ошибка создания изображения: {str(e)}", fill=(255, 0, 0))
        return error_image


def save_bracket_image(bracket: TournamentBracket, filepath: str, games: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Сохраняет изображение турнирной сетки в файл"""
    try:
        image = create_bracket_image(bracket, games)
        image.save(filepath, 'PNG', quality=95, optimize=True)
        return True
    except Exception as e:
        print(f"Ошибка сохранения изображения: {e}")
        return False