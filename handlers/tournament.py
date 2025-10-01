from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Optional
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from datetime import datetime

from services.storage import storage
from services.channels import send_tournament_created_to_channel, send_tournament_application_to_channel
from models.states import CreateTournamentStates, EditTournamentStates, ViewTournamentsStates, AdminEditGameStates
from utils.admin import is_admin
from config.profile import sport_type, cities_data, create_sport_keyboard
from config.tournament_config import (
    TOURNAMENT_TYPES, GENDERS, CATEGORIES, AGE_GROUPS, 
    DURATIONS, YES_NO_OPTIONS, DISTRICTS_MOSCOW, MIN_PARTICIPANTS, CATEGORY_LEVELS
)
from utils.tournament_brackets import create_tournament_bracket, Player, format_bracket_text
from utils.bracket_image_generator import (
    create_bracket_image,
    build_tournament_bracket_image_bytes,
    create_simple_text_image_bytes,
)
from utils.round_robin_image_generator import build_round_robin_table
from utils.tournament_manager import tournament_manager
from utils.utils import calculate_age, level_to_points
from utils.tournament_notifications import TournamentNotifications
import io
from config.config import SHOP_ID, SECRET_KEY, TOURNAMENT_ENTRY_FEE
from yookassa import Configuration, Payment
from models.states import TournamentPaymentStates

router = Router()
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения состояния пагинации
tournament_pages = {}
my_tournaments_pages = {}
my_applications_pages = {}

# Глобальная переменная для хранения данных создаваемого турнира
tournament_data = {}

# Списки для выбора (используем данные из конфигурации)
SPORTS = sport_type
COUNTRIES = list(cities_data.keys())

# Получаем города для каждой страны из конфигурации
def get_cities_for_country(country):
    """Получить список городов для страны"""
    cities = cities_data.get(country, [])
    return cities + ["Другое"] if cities else ["Другое"]

# Проверка соответствия уровня игрока диапазону уровня турнира вида "x.y-a.b"
def _is_level_match(user_level: str | None, tournament_level: str | None) -> bool:
    try:
        if not user_level or not tournament_level:
            return True  # если данных нет, не отфильтровываем
        user_level_val = float(str(user_level).replace(',', '.'))
        if '-' in tournament_level:
            parts = tournament_level.replace(',', '.').split('-')
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return low <= user_level_val <= high
        # если указан один уровень, сравниваем на равенство
        return abs(float(tournament_level.replace(',', '.')) - user_level_val) < 1e-6
    except Exception:
        return True

def _category_from_level(level_text: str | None) -> str | None:
    """Подбирает категорию на основе уровня согласно CATEGORY_LEVELS."""
    try:
        if not level_text:
            return None
        t = str(level_text).replace(',', '.').strip()
        if '-' in t:
            a, b = t.split('-', 1)
            user_level_val = (float(a) + float(b)) / 2.0
        else:
            user_level_val = float(t)
        for cat, rng in CATEGORY_LEVELS.items():
            r = str(rng).replace(',', '.')
            if '-' in r:
                low, high = [float(x.strip()) for x in r.split('-', 1)]
                if low <= user_level_val <= high:
                    return cat
        return None
    except Exception:
        return None

# Формирует текст по оплатам для админа
def _build_payments_status_text(tournament: dict) -> str:
    try:
        participants = tournament.get('participants', {}) or {}
        payments = tournament.get('payments', {}) or {}
        if not participants:
            return "Нет участников"
        lines = []
        for uid, pdata in participants.items():
            name = pdata.get('name') or str(uid)
            paid = payments.get(str(uid), {}).get('status') == 'succeeded'
            mark = '✅' if paid else '❌'
            lines.append(f"{mark} {name}")
        return "\n".join(lines)
    except Exception:
        return ""

# Функция для генерации названия турнира
def generate_tournament_name(tournament_data, tournament_number):
    """Генерирует название турнира в формате: Турнир уровень {} {Страна и город, если москва, то только сторону света} №{номер турнира}"""
    level = tournament_data.get('level', 'Не указан')
    
    # Формируем место проведения
    if tournament_data['city'] == "Москва" and 'district' in tournament_data:
        location = tournament_data['district']
    else:
        location = f"{tournament_data['city']}, {tournament_data['country']}"
    
    # Генерируем название
    name = f"Турнир уровень {level} {location} №{tournament_number}"
    return name

# Функция для создания продвинутой визуальной сетки турнира
def create_advanced_tournament_bracket(tournament_data, bracket_text, users_data=None, completed_games=None) -> bytes:
    """Создает продвинутую визуальную сетку турнира с аватарами и играми"""
    from PIL import Image, ImageDraw, ImageFont
    import io
    import os
    
    # Размеры изображения (увеличиваем для таблицы круговой системы)
    width, height = 1800, 1000
    
    # Создаем изображение с белым фоном
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Загружаем шрифты
    try:
        title_font = ImageFont.truetype("arial.ttf", 24)
        header_font = ImageFont.truetype("arial.ttf", 18)
        player_font = ImageFont.truetype("arial.ttf", 14)
        score_font = ImageFont.truetype("arial.ttf", 12)
        small_font = ImageFont.truetype("arial.ttf", 10)
        table_font = ImageFont.truetype("arial.ttf", 11)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        player_font = ImageFont.load_default()
        score_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        table_font = ImageFont.load_default()
    
    # Цвета
    bg_color = (255, 255, 255)
    header_color = (240, 240, 240)
    text_color = (50, 50, 50)
    winner_color = (0, 150, 0)
    loser_color = (150, 150, 150)
    games_color = (70, 130, 180)
    table_header_color = (220, 220, 220)
    table_border_color = (180, 180, 180)
    
    # Функция для загрузки аватара пользователя
    def load_user_avatar(user_id, users_data):
        """Загружает аватар пользователя или создает заглушку"""
        if not users_data or str(user_id) not in users_data:
            return None
        
        user_data = users_data[str(user_id)]
        photo_path = user_data.get('photo_path')
        
        if photo_path and os.path.exists(photo_path):
            try:
                avatar = Image.open(photo_path)
                # Изменяем размер аватара
                avatar = avatar.resize((30, 30), Image.Resampling.LANCZOS)
                return avatar
            except:
                pass
        
        # Создаем заглушку с инициалами
        avatar = Image.new('RGB', (30, 30), color=(200, 200, 200))
        avatar_draw = ImageDraw.Draw(avatar)
        
        # Получаем инициалы
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        initials = (first_name[:1] + last_name[:1]).upper() if first_name and last_name else '??'
        
        try:
            avatar_draw.text((15, 15), initials, fill=(100, 100, 100), font=small_font, anchor="mm")
        except:
            avatar_draw.text((15, 15), initials, fill=(100, 100, 100), anchor="mm")
        
        return avatar
    
    # Функция для создания таблицы круговой системы
    def create_round_robin_table(tournament_data, users_data, completed_games):
        """Создает таблицу круговой системы"""
        participants = tournament_data.get('participants', {})
        if len(participants) < 2:
            return None
        
        # Получаем список игроков
        players = []
        for user_id, participant_data in participants.items():
            user_data = users_data.get(user_id, {}) if users_data else {}
            player_name = participant_data.get('name', user_data.get('first_name', 'Неизвестно'))
            players.append({
                'id': user_id,
                'name': player_name,
                'avatar': load_user_avatar(user_id, users_data)
            })
        
        # Создаем матрицу результатов
        n = len(players)
        results = {}
        wins = {}
        league_points = {}
        tie_points = {}
        
        # Инициализируем результаты
        for i in range(n):
            player_id = players[i]['id']
            results[player_id] = {}
            wins[player_id] = 0
            league_points[player_id] = 0
            tie_points[player_id] = 0
        
        # Обрабатываем завершенные игры
        if completed_games:
            for game in completed_games:
                try:
                    if 'players' not in game:
                        continue
                    score = game.get('score', '')
                    if not score:
                        continue
                    player1_id = None
                    player2_id = None
                    gp = game['players']
                    # Поддержка форматов: {'team1': [...], 'team2': [...]} или [ {id:..}, {id:..} ] или [id1, id2]
                    if isinstance(gp, dict):
                        team1 = gp.get('team1') or []
                        team2 = gp.get('team2') or []
                        if isinstance(team1, list) and len(team1) >= 1 and isinstance(team2, list) and len(team2) >= 1:
                            player1_id = team1[0] if not isinstance(team1[0], dict) else team1[0].get('id')
                            player2_id = team2[0] if not isinstance(team2[0], dict) else team2[0].get('id')
                    elif isinstance(gp, list) and len(gp) >= 2:
                        a, b = gp[0], gp[1]
                        player1_id = a if isinstance(a, str) else (a.get('id') if isinstance(a, dict) else None)
                        player2_id = b if isinstance(b, str) else (b.get('id') if isinstance(b, dict) else None)

                    if not player1_id or not player2_id:
                        continue

                    # Парсим счет (например, "6:1, 6:3")
                    sets = [s.strip() for s in str(score).split(',') if ':' in s]
                    player1_sets = 0
                    player2_sets = 0
                    for set_score in sets:
                        try:
                            p1_games, p2_games = map(int, set_score.split(':'))
                        except Exception:
                            continue
                        if p1_games > p2_games:
                            player1_sets += 1
                        elif p2_games > p1_games:
                            player2_sets += 1

                    # Сохраняем результат
                    results.setdefault(player1_id, {})
                    results.setdefault(player2_id, {})
                    results[player1_id][player2_id] = {
                        'score': score,
                        'sets_won': player1_sets,
                        'sets_lost': player2_sets
                    }
                    results[player2_id][player1_id] = {
                        'score': score,
                        'sets_won': player2_sets,
                        'sets_lost': player1_sets
                    }

                    # Подсчитываем победы и очки (3/1/0)
                    if player1_sets > player2_sets:
                        wins[player1_id] += 1
                        league_points[player1_id] += 3
                        league_points[player2_id] += 0
                    elif player2_sets > player1_sets:
                        wins[player2_id] += 1
                        league_points[player2_id] += 3
                        league_points[player1_id] += 0
                    else:
                        # Ничья
                        league_points[player1_id] += 1
                        league_points[player2_id] += 1
                except Exception:
                    pass
        
        # Подсчет сыгранных матчей на игрока по заполненным результатам
        games_played = {}
        for p in players:
            pid = p['id']
            games_played[pid] = len(results.get(pid, {}))

        # Подсчет тай-брейка: разница сетов только среди игроков с равным количеством очков
        # 1) Группируем игроков по очкам (3/1/0)
        pts_to_players = {}
        for p in players:
            pid = p['id']
            pts_to_players.setdefault(league_points[pid], []).append(pid)

        # 2) Для каждой группы с размером > 1 считаем суммарную разницу сетов в личных встречах
        tied_ids = set()
        for pts, ids_in_group in pts_to_players.items():
            if len(ids_in_group) <= 1:
                continue
            tied_ids.update(ids_in_group)
            for pid in ids_in_group:
                group_sd = 0
                for opp_id in ids_in_group:
                    if opp_id == pid:
                        continue
                    if pid in results and opp_id in results[pid]:
                        match_res = results[pid][opp_id]
                        group_sd += int(match_res.get('sets_won', 0)) - int(match_res.get('sets_lost', 0))
                tie_points[pid] = group_sd

        # 3) Сортируем игроков: по очкам (3/1/0), затем по тай-брейку (разница сетов в группе)
        sorted_players = sorted(
            players,
            key=lambda p: (league_points[p['id']], tie_points.get(p['id'], 0)),
            reverse=True
        )

        return {
            'players': sorted_players,
            'results': results,
            'wins': wins,
            'league_points': league_points,
            'tie_points': tie_points,
            'games_played': games_played,
            'tied_ids': tied_ids
        }
    
    # Рисуем заголовок турнира
    tournament_name = tournament_data.get('name', 'Турнир')
    draw.rectangle([0, 0, width, 60], fill=header_color)
    draw.text((20, 20), tournament_name, fill=text_color, font=title_font)
    
    # Рисуем информацию о турнире
    location = f"{tournament_data.get('city', '')} {tournament_data.get('district', '')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    
    tournament_info = f"{location} - {tournament_data.get('duration', '')} | {tournament_data.get('category', '')} {tournament_data.get('gender', '')}"
    draw.text((20, 45), tournament_info, fill=text_color, font=player_font)
    
    # Рисуем статус турнира
    status_text = "АКТИВНЫЙ" if tournament_data.get('status') == 'active' else "ЗАВЕРШЕН"
    status_color = (0, 150, 0) if tournament_data.get('status') == 'active' else (255, 165, 0)
    draw.text((width - 150, 25), status_text, fill=status_color, font=header_font)
    
    # Рисуем сетку турнира
    y_start = 80
    x_start = 50
    
    # Проверяем тип турнира
    tournament_type = tournament_data.get('type', 'Олимпийская система')
    
    if tournament_type == 'Круговая система':
        # Рисуем таблицу круговой системы
        table_data = create_round_robin_table(tournament_data, users_data, completed_games)
        if table_data:
            draw_round_robin_table(draw, table_data, x_start, y_start)
    else:
        # Рисуем обычную сетку турнира
        draw_tournament_bracket(draw, bracket_text, users_data, x_start, y_start, load_user_avatar)
    
    # Рисуем завершенные игры справа
    if completed_games and tournament_type != 'Круговая система':
        draw_completed_games(draw, completed_games, width, y_start)
    
    # Рисуем информацию об участниках
    participants_count = len(tournament_data.get('participants', {}))
    max_participants = tournament_data.get('participants_count', 0)
    
    participants_text = f"Участников: {participants_count}/{max_participants}"
    draw.text((width - 200, height - 30), participants_text, fill=text_color, font=player_font)
    
    # Сохраняем в байты
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def draw_round_robin_table(draw, table_data, x_start, y_start):
    """Рисует таблицу круговой системы"""
    players = table_data['players']
    results = table_data['results']
    wins = table_data['wins']
    league_points = table_data.get('league_points', {})
    tie_points = table_data.get('tie_points', {})
    tied_ids = table_data.get('tied_ids', set())
    
    if not players:
        return
    
    # Размеры таблицы
    cell_width = 80
    cell_height = 40
    header_height = 30
    player_width = 120
    
    # Цвета для таблицы
    table_header_color = (220, 220, 220)
    table_border_color = (180, 180, 180)
    text_color = (50, 50, 50)
    winner_color = (0, 150, 0)
    bg_color = (255, 255, 255)
    
    # Загружаем шрифты
    try:
        from PIL import ImageFont
        small_font = ImageFont.truetype("arial.ttf", 10)
        header_font = ImageFont.truetype("arial.ttf", 18)
        player_font = ImageFont.truetype("arial.ttf", 14)
        table_font = ImageFont.truetype("arial.ttf", 11)
    except:
        small_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        player_font = ImageFont.load_default()
        table_font = ImageFont.load_default()
    
    # Рисуем заголовок таблицы
    # +4 колонки: Игры, Победы, Очки, Места
    draw.rectangle([x_start, y_start, x_start + player_width + len(players) * cell_width + 4 * cell_width, 
                   y_start + header_height], fill=table_header_color)
    
    # Заголовки колонок
    x_pos = x_start + player_width
    draw.text((x_pos + 10, y_start + 5), "Игроки", fill=text_color, font=header_font)
    
    # Заголовки игроков
    for i, player in enumerate(players):
        x_pos = x_start + player_width + i * cell_width
        if player['avatar']:
            # Рисуем аватар
            draw.rectangle([x_pos + 5, y_start + 5, x_pos + 25, y_start + 25], fill=(200, 200, 200))
            # Здесь можно было бы вставить аватар, но для простоты рисуем инициалы
            initials = player['name'][:2].upper()
            draw.text((x_pos + 15, y_start + 15), initials, fill=text_color, font=small_font, anchor="mm")
        
        # Имя игрока
        draw.text((x_pos + 30, y_start + 5), player['name'][:8], fill=text_color, font=small_font)
    
    # Колонки результатов
    x_pos = x_start + player_width + len(players) * cell_width
    draw.text((x_pos + 10, y_start + 5), "Игры", fill=text_color, font=header_font)
    x_pos += cell_width
    draw.text((x_pos + 10, y_start + 5), "Победы", fill=text_color, font=header_font)
    x_pos += cell_width
    draw.text((x_pos + 10, y_start + 5), "Очки", fill=text_color, font=header_font)
    x_pos += cell_width
    draw.text((x_pos + 10, y_start + 5), "Места", fill=text_color, font=header_font)
    
    # Рисуем строки игроков
    for i, player in enumerate(players):
        y_pos = y_start + header_height + i * cell_height
        
        # Имя игрока
        if player['avatar']:
            draw.rectangle([x_start + 5, y_pos + 5, x_start + 25, y_pos + 25], fill=(200, 200, 200))
            initials = player['name'][:2].upper()
            draw.text((x_start + 15, y_pos + 15), initials, fill=text_color, font=small_font, anchor="mm")
        
        draw.text((x_start + 30, y_pos + 5), player['name'], fill=text_color, font=player_font)
        
        # Результаты матчей
        for j, opponent in enumerate(players):
            if i == j:
                # Диагональ - пустая ячейка
                x_pos = x_start + player_width + j * cell_width
                draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                             fill=(240, 240, 240), outline=table_border_color)
                draw.text((x_pos + cell_width//2, y_pos + cell_height//2), "-", 
                         fill=text_color, font=table_font, anchor="mm")
            else:
                # Результат матча
                x_pos = x_start + player_width + j * cell_width
                draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                             fill=bg_color, outline=table_border_color)
                
                if player['id'] in results and opponent['id'] in results[player['id']]:
                    score = results[player['id']][opponent['id']]['score']
                    draw.text((x_pos + cell_width//2, y_pos + cell_height//2), score, 
                             fill=winner_color, font=table_font, anchor="mm")
        
        # Колонки результатов
        x_pos = x_start + player_width + len(players) * cell_width
        # Игры
        draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                      fill=bg_color, outline=table_border_color)
        draw.text((x_pos + cell_width//2, y_pos + cell_height//2), str(table_data.get('games_played', {}).get(player['id'], 0)), 
                 fill=text_color, font=table_font, anchor="mm")
        
        x_pos += cell_width
        # Победы
        draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                      fill=bg_color, outline=table_border_color)
        draw.text((x_pos + cell_width//2, y_pos + cell_height//2), str(wins[player['id']]), 
                 fill=winner_color, font=table_font, anchor="mm")
        
        x_pos += cell_width
        # Очки (3/1/0)
        draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                      fill=bg_color, outline=table_border_color)
        draw.text((x_pos + cell_width//2, y_pos + cell_height//2), str(league_points.get(player['id'], 0)), 
                 fill=text_color, font=table_font, anchor="mm")

        x_pos += cell_width
        draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                      fill=bg_color, outline=table_border_color)
        draw.text((x_pos + cell_width//2, y_pos + cell_height//2), str(i + 1), 
                 fill=winner_color, font=table_font, anchor="mm")

    # Примечание под таблицей
    try:
        from PIL import ImageFont
        note_font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        note_font = table_font

    footnote = (
        "* При равенстве очков места определяются по разнице сетов в матчах между этими игроками."
    )
    footnote_y = y_start + header_height + len(players) * cell_height + 10
    draw.text((x_start, footnote_y), footnote, fill=text_color, font=note_font)

def draw_tournament_bracket(draw, bracket_text, users_data, x_start, y_start, load_user_avatar_func):
    """Рисует обычную турнирную сетку"""
    # Цвета и шрифты
    header_color = (240, 240, 240)
    text_color = (50, 50, 50)
    winner_color = (0, 150, 0)
    empty_color = (200, 200, 200)
    
    # Загружаем шрифты
    try:
        from PIL import ImageFont
        header_font = ImageFont.truetype("arial.ttf", 18)
        player_font = ImageFont.truetype("arial.ttf", 14)
        score_font = ImageFont.truetype("arial.ttf", 12)
        small_font = ImageFont.truetype("arial.ttf", 10)
    except:
        header_font = ImageFont.load_default()
        player_font = ImageFont.load_default()
        score_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Разбиваем текст сетки на раунды
    lines = bracket_text.split('\n')
    current_round = 0
    round_width = 200
    match_height = 80
    
    # Обрабатываем каждый раунд
    for line in lines:
        if 'Раунд' in line:
            current_round += 1
            x_pos = x_start + (current_round - 1) * round_width
            
            # Рисуем заголовок раунда
            draw.rectangle([x_pos, y_start, x_pos + round_width - 20, y_start + 30], fill=header_color)
            draw.text((x_pos + 10, y_start + 5), line.replace('📋 ', ''), fill=text_color, font=header_font)
            
            y_pos = y_start + 40
            
        elif 'vs' in line or 'против' in line or 'автоматически' in line:
            # Это матч
            x_pos = x_start + (current_round - 1) * round_width
            
            # Рисуем рамку матча
            draw.rectangle([x_pos, y_pos, x_pos + round_width - 20, y_pos + match_height], outline=(200, 200, 200))
            
            # Проверяем, является ли это автоматическим проходом
            if 'автоматически' in line:
                # Это автоматический проход
                player_name = line.split(' (автоматически')[0].replace('🆓 ', '').strip()
                draw.text((x_pos + 10, y_pos + 25), f"🆓 {player_name}", fill=winner_color, font=player_font)
                draw.text((x_pos + 10, y_pos + 45), "автоматически в следующий раунд", fill=text_color, font=small_font)
            else:
                # Разбираем строку матча
                parts = line.split(' - ')
                if len(parts) >= 2:
                    player1 = parts[0].strip()
                    player2_part = parts[1].strip()
                    
                    # Извлекаем имена игроков и счета
                    if '(' in player1:
                        player1_name = player1.split('(')[0].strip()
                        player1_score = player1.split('(')[1].split(')')[0].strip()
                    else:
                        player1_name = player1
                        player1_score = ""
                    
                    if '(' in player2_part:
                        player2_name = player2_part.split('(')[0].strip()
                        player2_score = player2_part.split('(')[1].split(')')[0].strip()
                    else:
                        player2_name = player2_part
                        player2_score = ""
                    
                    # Пытаемся найти ID игроков для загрузки аватаров
                    player1_id = None
                    player2_id = None
                    
                    if users_data:
                        for user_id, user_data in users_data.items():
                            full_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
                            if full_name == player1_name:
                                player1_id = user_id
                            elif full_name == player2_name:
                                player2_id = user_id
                    
                    # Рисуем аватар первого игрока
                    if player1_id:
                        avatar1 = load_user_avatar_func(player1_id, users_data)
                        if avatar1:
                            # Здесь нужно получить доступ к img, но для простоты пропускаем
                            text_x = x_pos + 50
                        else:
                            text_x = x_pos + 10
                    else:
                        text_x = x_pos + 10
                    
                    # Рисуем имя первого игрока
                    player1_color = empty_color if player1_name == "Свободное место" else text_color
                    draw.text((text_x, y_pos + 10), player1_name, fill=player1_color, font=player_font)
                    if player1_score:
                        draw.text((x_pos + round_width - 60, y_pos + 10), player1_score, fill=winner_color, font=score_font)
                    
                    # Рисуем аватар второго игрока
                    if player2_id:
                        avatar2 = load_user_avatar_func(player2_id, users_data)
                        if avatar2:
                            # Здесь нужно получить доступ к img, но для простоты пропускаем
                            text_x2 = x_pos + 50
                    else:
                        text_x2 = x_pos + 10
                else:
                    text_x2 = x_pos + 10
                
                # Рисуем имя второго игрока
                player2_color = empty_color if player2_name == "Свободное место" else text_color
                draw.text((text_x2, y_pos + 35), player2_name, fill=player2_color, font=player_font)
                if player2_score:
                    draw.text((x_pos + round_width - 60, y_pos + 35), player2_score, fill=winner_color, font=score_font)
                
                # Рисуем разделитель
                draw.line([x_pos + 10, y_pos + 30, x_pos + round_width - 30, y_pos + 30], fill=(200, 200, 200))
            
            y_pos += match_height + 10

def draw_completed_games(draw, completed_games, width, y_start):
    """Рисует список завершенных игр"""
    # Цвета и шрифты
    header_color = (240, 240, 240)
    text_color = (50, 50, 50)
    winner_color = (0, 150, 0)
    games_color = (70, 130, 180)
    
    # Загружаем шрифты
    try:
        from PIL import ImageFont
        header_font = ImageFont.truetype("arial.ttf", 18)
        small_font = ImageFont.truetype("arial.ttf", 10)
    except:
        header_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    games_x = 1000  # Начинаем справа
    games_y = y_start
    
    # Заголовок для игр
    draw.rectangle([games_x, games_y, games_x + 300, games_y + 30], fill=header_color)
    draw.text((games_x + 10, games_y + 5), "Завершенные игры", fill=text_color, font=header_font)
    
    games_y += 40
    
    # Показываем до 10 последних игр
    games_to_show = completed_games[:10]
    
    for i, game in enumerate(games_to_show):
        if games_y > 900:  # Не выходим за границы
            break
            
        # Информация об игре
        game_info = f"Игра #{i+1}"
        draw.text((games_x + 10, games_y), game_info, fill=games_color, font=small_font)
        
        # Игроки и счет
        if 'players' in game and 'score' in game:
            players = game['players']
            score = game['score']
            
            if len(players) >= 2:
                player1_name = players[0].get('name', 'Игрок 1')
                player2_name = players[1].get('name', 'Игрок 2')
                
                # Рисуем имена игроков
                draw.text((games_x + 10, games_y + 15), player1_name, fill=text_color, font=small_font)
                draw.text((games_x + 10, games_y + 28), player2_name, fill=text_color, font=small_font)
                
                # Рисуем счет
                draw.text((games_x + 250, games_y + 20), score, fill=winner_color, font=small_font)
        
        games_y += 45

# Универсальная функция для безопасного редактирования сообщений
async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode=None):
    """Безопасно редактирует сообщение с fallback на удаление и отправку нового"""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass  # Игнорируем ошибку удаления
        # Всегда отправляем новое сообщение после попытки редактирования
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

# Функция для создания простого изображения из текста
def create_simple_text_image(*args, **kwargs):
    """Заглушка: перенесено в utils.bracket_image_generator.create_simple_text_image_bytes"""
    return create_simple_text_image_bytes(kwargs.get('text') or (args[0] if args else ''), kwargs.get('title', 'Турнирная сетка'))

async def build_and_render_tournament_image(tournament_data: dict, tournament_id: str) -> tuple[bytes, str]:
    """Собирает игроков и игры и делегирует генерацию изображения в утилиты."""
    participants = tournament_data.get('participants', {}) or {}
    tournament_type = tournament_data.get('type', 'Олимпийская система')

    # Собираем игроков
    users = await storage.load_users()
    players: list[Player] = []
    for user_id, pdata in participants.items():
        u = users.get(user_id, {})
        players.append(
            Player(
                id=user_id,
                name=pdata.get('name', u.get('first_name', 'Неизвестно')),
                photo_url=u.get('photo_path'),
                initial=None,
            )
        )

    # Применяем посев (seeding). Если его нет — случайно перемешиваем и сохраняем.
    min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
    # загружаем ранее сохраненный порядок
    seeding = tournament_data.get('seeding') or []
    id_to_player = {p.id: p for p in players}
    ordered: list[Player] = []
    # добираем из seeding
    for pid in seeding:
        if pid in id_to_player:
            ordered.append(id_to_player.pop(pid))
    # оставшиеся игроки — случайно
    import random
    remaining = list(id_to_player.values())
    random.shuffle(remaining)
    ordered.extend(remaining)
    # если посева не было — сохраним его
    if not seeding:
        tournaments_all = await storage.load_tournaments()
        td = tournaments_all.get(tournament_id, {})
        td['seeding'] = [p.id for p in ordered]
        tournaments_all[tournament_id] = td
        await storage.save_tournaments(tournaments_all)

    players = ordered

    # Для олимпийской системы — добавляем свободные места до минимума
    if tournament_type == 'Олимпийская система':
        while len(players) < min_participants:
            players.append(Player(id=f"empty_{len(players)}", name="Свободное место", photo_url=None, initial=None))

    # Загружаем завершенные игры этого турнира
    completed_games: list[dict] = []
    try:
        games = await storage.load_games()
        for g in games:
            if g.get('tournament_id') == tournament_id:
                completed_games.append(g)
        completed_games.sort(key=lambda x: x.get('date') or x.get('created_at', ''), reverse=True)
    except Exception as e:
        logger.error(f"Ошибка при загрузке игр: {e}")

    # Если сетка скрыта — простая картинка
    if tournament_data.get('hide_bracket', False):
        placeholder = (
            "Турнирная сетка скрыта администратором.\n\n"
            f"{tournament_data.get('name', 'Турнир')}\n"
            f"Участников: {len(participants)}"
        )
        return create_simple_text_image_bytes(placeholder, tournament_data.get('name', 'Турнир')), "Сетка скрыта"

    # Генерируем изображение сетки через утилиту
    try:
        if tournament_type == 'Круговая':
            # Собираем компактный список игроков для таблицы
            table_players = [{"id": p.id, "name": p.name} for p in players]
            image_bytes = build_round_robin_table(table_players, completed_games, tournament_data.get('name', 'Турнир'))
            return image_bytes, "Круговая таблица"
        else:
            return build_tournament_bracket_image_bytes(tournament_data, players, completed_games)
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        fallback = "Турнирная сетка\n\nНе удалось загрузить данные"
        return create_simple_text_image_bytes(fallback, "Ошибка"), ""

# Обработчик создания турнира (только для админов)
@router.callback_query(F.data == "admin_create_tournament")
async def create_tournament_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик создания турнира (только админы)"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    # Очищаем данные предыдущего создания
    global tournament_data
    tournament_data = {}
    
    # Начинаем с выбора вида спорта
    await state.set_state(CreateTournamentStates.SPORT)
    
    await safe_edit_message(callback,
        "🏆 Создание турнира\n\n"
        "📋 Шаг 1/13: Выберите вид спорта",
        reply_markup=create_sport_keyboard(pref="tournament_sport:", exclude_sports=[
            "🍻По пиву", 
            "🍒Знакомства", 
            "☕️Бизнес-завтрак"
        ])
    )
    await callback.answer()

# Обработчик выбора вида спорта
@router.callback_query(F.data.startswith("tournament_sport:"))
async def select_sport(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора вида спорта"""
    sport = callback.data.split(":", 1)[1]
    tournament_data["sport"] = sport
    
    await state.set_state(CreateTournamentStates.COUNTRY)
    
    builder = InlineKeyboardBuilder()
    for country in COUNTRIES:
        builder.button(text=country, callback_data=f"tournament_country:{country}")
    # Добавляем кнопку для ввода страны вручную
    builder.button(text="✏️ Другая страна", callback_data="tournament_country:Другое")
    builder.adjust(2)
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 2/13: Выберите страну\n"
        f"✅ Вид спорта: {sport}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора страны
@router.callback_query(F.data.startswith("tournament_country:"))
async def select_country(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора страны"""
    country = callback.data.split(":", 1)[1]
    tournament_data["country"] = country
    
    if country == "Другое":
        await state.set_state(CreateTournamentStates.COUNTRY_INPUT)
        await safe_edit_message(callback,
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 2/13: Введите название страны\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {country}\n\n"
            f"Введите название страны:",
            reply_markup=None
        )
    else:
        await state.set_state(CreateTournamentStates.CITY)
        
        # Выбираем список городов в зависимости от страны
        cities = get_cities_for_country(country)
        
        builder = InlineKeyboardBuilder()
        for city in cities:
            builder.button(text=city, callback_data=f"tournament_city:{city}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 3/13: Выберите город\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {country}",
            reply_markup=builder.as_markup()
        )
    
    await callback.answer()

# Обработчик ввода страны вручную
@router.message(CreateTournamentStates.COUNTRY_INPUT)
async def input_country(message: Message, state: FSMContext):
    """Обработчик ввода страны вручную"""
    country = message.text.strip()
    tournament_data["country"] = country
    
    await state.set_state(CreateTournamentStates.CITY)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Другой город", callback_data="tournament_city_input")
    
    await message.answer(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 3/13: Выберите город\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {country}\n\n"
        f"Выберите способ выбора города:",
        reply_markup=builder.as_markup()
    )

# Обработчик кнопки ввода города вручную
@router.callback_query(F.data == "tournament_city_input")
async def tournament_city_input(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки ввода города вручную"""
    await state.set_state(CreateTournamentStates.CITY_INPUT)
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 3/13: Введите название города\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n\n"
        f"Введите название города:",
        reply_markup=None
    )
    await callback.answer()

# Обработчик выбора города
@router.callback_query(F.data.startswith("tournament_city:"))
async def select_city(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города"""
    city = callback.data.split(":", 1)[1]
    tournament_data["city"] = city
    
    if city == "Другое":
        await state.set_state(CreateTournamentStates.CITY_INPUT)
        await safe_edit_message(callback,
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 3/13: Введите название города\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {city}\n\n"
            f"Введите название города:",
            reply_markup=None
        )
    else:
        # Проверяем, нужно ли выбирать район (только для Москвы)
        if city == "Москва":
            await state.set_state(CreateTournamentStates.DISTRICT)
            
            builder = InlineKeyboardBuilder()
            for district in DISTRICTS_MOSCOW:
                builder.button(text=district, callback_data=f"tournament_district:{district}")
            builder.adjust(2)
            
            await safe_edit_message(callback,
                f"🏆 Создание турнира\n\n"
                f"📋 Шаг 4/13: Выберите часть города\n"
                f"✅ Вид спорта: {tournament_data['sport']}\n"
                f"✅ Страна: {tournament_data['country']}\n"
                f"✅ Город: {city}",
                reply_markup=builder.as_markup()
            )
        else:
            # Пропускаем выбор района
            await state.set_state(CreateTournamentStates.TYPE)
            
            builder = InlineKeyboardBuilder()
            for t_type in TOURNAMENT_TYPES:
                builder.button(text=t_type, callback_data=f"tournament_type:{t_type}")
            builder.adjust(1)
            
            await safe_edit_message(callback,
                f"🏆 Создание турнира\n\n"
                f"📋 Шаг 4/13: Выберите тип турнира\n"
                f"✅ Вид спорта: {tournament_data['sport']}\n"
                f"✅ Страна: {tournament_data['country']}\n"
                f"✅ Город: {city}",
                reply_markup=builder.as_markup()
            )
    
    await callback.answer()

# Обработчик ввода города вручную
@router.message(CreateTournamentStates.CITY_INPUT)
async def input_city(message: Message, state: FSMContext):
    """Обработчик ввода города вручную"""
    city = message.text.strip()
    tournament_data["city"] = city
    
    # Проверяем, нужно ли выбирать район (только для Москвы)
    if city == "Москва":
        await state.set_state(CreateTournamentStates.DISTRICT)
        
        builder = InlineKeyboardBuilder()
        for district in DISTRICTS_MOSCOW:
            builder.button(text=district, callback_data=f"tournament_district:{district}")
        builder.adjust(2)
        
        await message.answer(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 4/13: Выберите часть города\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {city}\n\n"
            f"Выберите часть города:",
            reply_markup=builder.as_markup()
        )
    else:
        # Пропускаем выбор района
        await state.set_state(CreateTournamentStates.TYPE)
        
        builder = InlineKeyboardBuilder()
        for t_type in TOURNAMENT_TYPES:
            builder.button(text=t_type, callback_data=f"tournament_type:{t_type}")
        builder.adjust(1)
        
        await message.answer(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 4/13: Выберите тип турнира\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {city}\n\n"
            f"Выберите тип турнира:",
            reply_markup=builder.as_markup()
        )

# Обработчик выбора района
@router.callback_query(F.data.startswith("tournament_district:"))
async def select_district(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора района"""
    district = callback.data.split(":", 1)[1]
    tournament_data["district"] = district
    
    await state.set_state(CreateTournamentStates.TYPE)
    
    builder = InlineKeyboardBuilder()
    for t_type in TOURNAMENT_TYPES:
        builder.button(text=t_type, callback_data=f"tournament_type:{t_type}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 5/13: Выберите тип турнира\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"✅ Район: {district}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора типа турнира
@router.callback_query(F.data.startswith("tournament_type:"))
async def select_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа турнира"""
    t_type = callback.data.split(":", 1)[1]
    tournament_data["type"] = t_type
    
    await state.set_state(CreateTournamentStates.GENDER)
    
    builder = InlineKeyboardBuilder()
    for gender in GENDERS:
        builder.button(text=gender, callback_data=f"tournament_gender:{gender}")
    builder.adjust(2)
    
    step = "5" if "district" not in tournament_data else "6"
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите пол участников\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {t_type}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора пола
@router.callback_query(F.data.startswith("tournament_gender:"))
async def select_gender(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора пола участников"""
    gender = callback.data.split(":", 1)[1]
    tournament_data["gender"] = gender
    
    await state.set_state(CreateTournamentStates.CATEGORY)
    
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        builder.button(text=category, callback_data=f"tournament_category:{category}")
    builder.adjust(2)
    
    step = "6" if "district" not in tournament_data else "7"
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите категорию\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {gender}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора категории
@router.callback_query(F.data.startswith("tournament_category:"))
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора категории"""
    category = callback.data.split(":", 1)[1]
    tournament_data["category"] = category
    
    # Сохраняем уровень на основе выбранной категории
    tournament_data["level"] = CATEGORY_LEVELS.get(category, "Без уровня")
    
    await state.set_state(CreateTournamentStates.AGE_GROUP)
    
    builder = InlineKeyboardBuilder()
    for age_group in AGE_GROUPS:
        builder.button(text=age_group, callback_data=f"tournament_age_group:{age_group}")
    builder.adjust(2)
    
    step = "7" if "district" not in tournament_data else "8"
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите возрастную группу\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {category}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора возрастной группы
@router.callback_query(F.data.startswith("tournament_age_group:"))
async def select_age_group(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора возрастной группы"""
    age_group = callback.data.split(":", 1)[1]
    tournament_data["age_group"] = age_group
    
    await state.set_state(CreateTournamentStates.DURATION)
    
    builder = InlineKeyboardBuilder()
    for duration in DURATIONS:
        builder.button(text=duration, callback_data=f"tournament_duration:{duration}")
    builder.adjust(1)
    
    step = "8" if "district" not in tournament_data else "9"
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите продолжительность\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {age_group}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора продолжительности
@router.callback_query(F.data.startswith("tournament_duration:"))
async def select_duration(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора продолжительности"""
    duration = callback.data.split(":", 1)[1]
    tournament_data["duration"] = duration
    
    await state.set_state(CreateTournamentStates.PARTICIPANTS_COUNT)
    
    step = "9" if "district" not in tournament_data else "10"
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Введите количество участников\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {tournament_data['age_group']}\n"
        f"✅ Продолжительность: {duration}\n\n"
        f"Введите количество участников (число):",
        reply_markup=None
    )
    await callback.answer()

# Обработчик ввода количества участников
@router.message(CreateTournamentStates.PARTICIPANTS_COUNT)
async def input_participants_count(message: Message, state: FSMContext):
    """Обработчик ввода количества участников"""
    try:
        count = int(message.text.strip())
        if count <= 0:
            await message.answer("❌ Количество участников должно быть больше 0. Попробуйте еще раз:")
            return
        
        tournament_data["participants_count"] = count
        
        await state.set_state(CreateTournamentStates.SHOW_IN_LIST)
        
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            builder.button(text=option, callback_data=f"tournament_show_in_list:{option}")
        builder.adjust(2)
        
        step = "10" if "district" not in tournament_data else "11"
        
        await message.answer(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг {step}/13: Отображать в общем списке турниров города?\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {tournament_data['city']}\n"
            f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
            f"✅ Тип: {tournament_data['type']}\n"
            f"✅ Пол: {tournament_data['gender']}\n"
            f"✅ Категория: {tournament_data['category']}\n"
            f"✅ Возраст: {tournament_data['age_group']}\n"
            f"✅ Продолжительность: {tournament_data['duration']}\n"
            f"✅ Участников: {count}\n\n"
            f"Отображать турнир в общем списке турниров города?",
            reply_markup=builder.as_markup()
        )
    except ValueError:
        await message.answer("❌ Введите корректное число. Попробуйте еще раз:")

# Обработчик выбора отображения в списке
@router.callback_query(F.data.startswith("tournament_show_in_list:"))
async def select_show_in_list(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора отображения в списке"""
    show_in_list = callback.data.split(":", 1)[1]
    tournament_data["show_in_list"] = show_in_list == "Да"
    
    await state.set_state(CreateTournamentStates.HIDE_BRACKET)
    
    builder = InlineKeyboardBuilder()
    for option in YES_NO_OPTIONS:
        builder.button(text=option, callback_data=f"tournament_hide_bracket:{option}")
    builder.adjust(2)
    
    step = "11" if "district" not in tournament_data else "12"
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Скрывать турнирную сетку?\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {tournament_data['age_group']}\n"
        f"✅ Продолжительность: {tournament_data['duration']}\n"
        f"✅ Участников: {tournament_data['participants_count']}\n"
        f"✅ В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n\n"
        f"Скрывать турнирную сетку от участников?",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора скрытия сетки
@router.callback_query(F.data.startswith("tournament_hide_bracket:"))
async def select_hide_bracket(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора скрытия турнирной сетки"""
    hide_bracket = callback.data.split(":", 1)[1]
    tournament_data["hide_bracket"] = hide_bracket == "Да"
    
    await state.set_state(CreateTournamentStates.COMMENT)
    
    step = "12" if "district" not in tournament_data else "13"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data="skip_comment")
    
    await safe_edit_message(callback,
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Введите описание к турниру\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{'✅ Район: ' + tournament_data['district'] + chr(10) if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {tournament_data['age_group']}\n"
        f"✅ Продолжительность: {tournament_data['duration']}\n"
        f"✅ Участников: {tournament_data['participants_count']}\n"
        f"✅ В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n"
        f"✅ Скрыть сетку: {'Да' if tournament_data['hide_bracket'] else 'Нет'}\n\n"
        f"Введите описание к турниру:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик кнопки пропуска комментария
@router.callback_query(F.data == "skip_comment")
async def skip_comment(callback: CallbackQuery, state: FSMContext):
    """Обработчик пропуска комментария"""
    tournament_data["comment"] = ""
    
    await state.set_state(CreateTournamentStates.CONFIRM)
    
    # Формируем итоговую информацию
    location = f"{tournament_data['city']}"
    if "district" in tournament_data:
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data['country']}"
    
    text = f"🏆 Создание турнира\n\n"
    text += f"📋 Подтверждение данных:\n\n"
    text += f"- Вид спорта: {tournament_data['sport']}\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data['type']}\n"
    text += f"- Пол: {tournament_data['gender']}\n"
    text += f"- Категория: {tournament_data['category']}\n"
    text += f"- Уровень: {tournament_data.get('level', 'Не указан')}\n"
    text += f"- Возраст: {tournament_data['age_group']}\n"
    text += f"- Продолжительность: {tournament_data['duration']}\n"
    text += f"- Участников: {tournament_data['participants_count']}\n"
    text += f"- В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n"
    text += f"- Скрыть сетку: {'Да' if tournament_data['hide_bracket'] else 'Нет'}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать турнир", callback_data="confirm_tournament")
    builder.button(text="❌ Отменить", callback_data="cancel_tournament")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик подтверждения создания турнира (из skip_comment)
@router.callback_query(F.data == "confirm_tournament")
async def confirm_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения создания турнира (из skip_comment)"""
    global tournament_data
    
    try:
        # Загружаем существующие турниры
        tournaments = await storage.load_tournaments()
        
        # Создаем ID турнира
        tournament_id = f"tournament_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Генерируем номер турнира (количество существующих турниров + 1)
        tournament_number = len(tournaments) + 1
        
        # Формируем название турнира
        name = generate_tournament_name(tournament_data, tournament_number)
        
        # Формируем описание
        location = f"{tournament_data['city']}"
        if "district" in tournament_data:
            location += f" ({tournament_data['district']})"
        location += f", {tournament_data['country']}"
        
        description = f"Турнир по {tournament_data['sport'].lower()}\n"
        description += f"Место: {location}\n"
        description += f"Тип: {tournament_data['type']}\n"
        description += f"Пол: {tournament_data['gender']}\n"
        description += f"Категория: {tournament_data['category']}\n"
        description += f"Уровень: {tournament_data.get('level', 'Не указан')}\n"
        description += f"Возраст: {tournament_data['age_group']}\n"
        description += f"Продолжительность: {tournament_data['duration']}\n"
        description += f"Участников: {tournament_data['participants_count']}"
        
        if tournament_data['comment']:
            description += f"\n\nОписание: {tournament_data['comment']}"
        
        # Создаем турнир
        tournaments[tournament_id] = {
            'name': name,
            'description': description,
            'sport': tournament_data['sport'],
            'country': tournament_data['country'],
            'city': tournament_data['city'],
            'district': tournament_data.get('district', ''),
            'type': tournament_data['type'],
            'gender': tournament_data['gender'],
            'category': tournament_data['category'],
            'level': tournament_data.get('level', 'Не указан'),
            'age_group': tournament_data['age_group'],
            'duration': tournament_data['duration'],
            'participants_count': tournament_data['participants_count'],
            'show_in_list': tournament_data['show_in_list'],
            'hide_bracket': tournament_data['hide_bracket'],
            'comment': tournament_data['comment'],
            'created_at': datetime.now().isoformat(),
            'created_by': callback.from_user.id,
            'participants': {},
            'status': 'active'
        }
        
        # Сохраняем турниры
        await storage.save_tournaments(tournaments)
        
        await safe_edit_message(callback,
            f"✅ Турнир успешно создан!\n\n"
            f"🏆 Название: {name}\n"
            f"📍 Место: {location}\n"
            f"👥 Участников: {tournament_data['participants_count']}\n\n"
            f"Турнир добавлен в систему и готов к регистрации участников."
        )
        
        # Очищаем состояние
        await state.clear()
        tournament_data = {}
        
    except Exception as e:
        logger.error(f"Ошибка при создании турнира: {e}")
        await safe_edit_message(callback,
            "❌ Произошла ошибка при создании турнира. Попробуйте еще раз."
        )
    
    await callback.answer()

# Обработчик отмены создания турнира (из skip_comment)
@router.callback_query(F.data == "cancel_tournament")
async def cancel_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены создания турнира (из skip_comment)"""
    await state.clear()
    
    await safe_edit_message(callback,
        "❌ Создание турнира отменено.\n\n"
        "Для создания нового турнира используйте команду /create_tournament"
    )
    await callback.answer()

# Обработчик ввода комментария
@router.message(CreateTournamentStates.COMMENT)
async def input_comment(message: Message, state: FSMContext):
    """Обработчик ввода комментария"""
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    tournament_data["comment"] = comment
    
    await state.set_state(CreateTournamentStates.CONFIRM)
    
    # Формируем итоговую информацию
    location = f"{tournament_data['city']}"
    if "district" in tournament_data:
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data['country']}"
    
    text = f"🏆 Создание турнира\n\n"
    text += f"📋 Подтверждение данных:\n\n"
    text += f"- Вид спорта: {tournament_data['sport']}\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data['type']}\n"
    text += f"- Пол: {tournament_data['gender']}\n"
    text += f"- Категория: {tournament_data['category']}\n"
    text += f"- Уровень: {tournament_data.get('level', 'Не указан')}\n"
    text += f"- Возраст: {tournament_data['age_group']}\n"
    text += f"- Продолжительность: {tournament_data['duration']}\n"
    text += f"- Участников: {tournament_data['participants_count']}\n"
    text += f"- В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n"
    text += f"- Скрыть сетку: {'Да' if tournament_data['hide_bracket'] else 'Нет'}\n"
    if tournament_data['comment']:
        text += f"- Описание: {tournament_data['comment']}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать турнир", callback_data="tournament_confirm_create")
    builder.button(text="❌ Отменить", callback_data="tournament_cancel_create")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Обработчик подтверждения создания турнира
@router.callback_query(F.data == "tournament_confirm_create")
async def confirm_create_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения создания турнира"""
    try:
        # Загружаем существующие турниры
        tournaments = await storage.load_tournaments()

        # Вспомогательные функции
        def make_key(payload: dict) -> tuple:
            return (
                payload['sport'], payload['country'], payload['city'], payload.get('district', ''),
                payload['type'], payload['gender'], payload['category'], payload['age_group']
            )

        def find_existing(payload: dict) -> Optional[str]:
            for tid, t in tournaments.items():
                if make_key(t) == make_key(payload):
                    return tid
            return None

        def build_description(payload: dict) -> str:
            loc = f"{payload['city']}"
            if payload.get('district'):
                loc += f" ({payload['district']})"
            loc += f", {payload['country']}"
            desc = f"Турнир по {payload['sport'].lower()}\n"
            desc += f"Место: {loc}\n"
            desc += f"Тип: {payload['type']}\n"
            desc += f"Пол: {payload['gender']}\n"
            desc += f"Категория: {payload['category']}\n"
            desc += f"Уровень: {payload.get('level', 'Не указан')}\n"
            desc += f"Возраст: {payload['age_group']}\n"
            desc += f"Продолжительность: {payload['duration']}\n"
            desc += f"Участников: {payload['participants_count']}"
            if payload.get('comment'):
                desc += f"\n\nОписание: {payload['comment']}"
            return desc

        # Базовые данные из состояния
        base = dict(tournament_data)
        created = 0
        updated = 0

        # Список задач создания/обновления
        payloads: list[dict] = []

        # Если Москва — тиражируем по сторонам света и по наборам полов и категорий
        if tournament_data.get('city') == 'Москва':
            singles_genders = ['Мужчины', 'Женщины']
            # Доступные категории в конфиге
            categories4 = [c for c in CATEGORIES if c in ['1 категория', '2 категория', '3 категория', 'Мастерс', 'Профи']]

            # По 4 сторонам света x 4 категории x 2 пола = 32 турнира
            for district in DISTRICTS_MOSCOW:
                for category in categories4:
                    for gender in singles_genders:
                        p = dict(base)
                        p['district'] = district
                        p['category'] = category
                        p['level'] = CATEGORY_LEVELS.get(category, p.get('level', 'Без уровня'))
                        p['gender'] = gender
                        payloads.append(p)

            # Дополнительно: городские парные соревнования по категориям (без района)
            pair_genders = ['Мужская пара', 'Женская пара', 'Микст']
            for category in categories4:
                for gender in pair_genders:
                    p = dict(base)
                    p['district'] = ''
                    p['category'] = category
                    p['level'] = CATEGORY_LEVELS.get(category, p.get('level', 'Без уровня'))
                    p['gender'] = gender
                    payloads.append(p)
        else:
            # Обычное одиночное создание для не-Москвы
            payloads.append(base)

        # Нумерация для новых турниров
        next_number = len(tournaments) + 1

        # Обрабатываем все задачи
        for p in payloads:
            existing_id = find_existing(p)
            if existing_id:
                # Обновляем существующий (не трогаем участников и технические поля)
                t = tournaments[existing_id]
                t.update({
                    'description': build_description(p),
                    'type': p['type'],
                    'gender': p['gender'],
                    'category': p['category'],
                    'level': p.get('level', t.get('level', 'Не указан')),
                    'age_group': p['age_group'],
                    'duration': p['duration'],
                    'participants_count': p['participants_count'],
                    'show_in_list': p['show_in_list'],
                    'hide_bracket': p['hide_bracket'],
                    'comment': p['comment'],
                    'city': p['city'],
                    'country': p['country'],
                    'district': p.get('district', ''),
                    'sport': p['sport'],
                    'status': t.get('status', 'active'),
                })
                updated += 1
            else:
                # Создаем новый
                p_for_name = dict(p)
                # generate_tournament_name использует уровень и локацию
                name = generate_tournament_name(p_for_name, next_number)
                tournament_id = f"tournament_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{next_number}"
                tournaments[tournament_id] = {
                    'name': name,
                    'description': build_description(p),
                    'sport': p['sport'],
                    'country': p['country'],
                    'city': p['city'],
                    'district': p.get('district', ''),
                    'type': p['type'],
                    'gender': p['gender'],
                    'category': p['category'],
                    'level': p.get('level', 'Не указан'),
                    'age_group': p['age_group'],
                    'duration': p['duration'],
                    'participants_count': p['participants_count'],
                    'show_in_list': p['show_in_list'],
                    'hide_bracket': p['hide_bracket'],
                    'comment': p['comment'],
                    'created_at': datetime.now().isoformat(),
                    'created_by': callback.from_user.id,
                    'participants': {},
                    'status': 'active',
                    'rules': 'Стандартные правила турнира',
                    'prize_fund': 'Будет определен позже'
                }
                created += 1
                next_number += 1

        # Сохраняем турниры
        await storage.save_tournaments(tournaments)

        # Отправляем уведомления в канал о новых турнирах (только для созданных)
        try:
            bot: Bot = callback.message.bot
            # Собираем id созданных турниров из текущего прогона
            for tid, tdata in tournaments.items():
                # По признаку created_at с текущей минутой можно грубо отфильтровать только что созданные
                # но безопаснее отправлять для тех, что соответствуют текущему пользователю и только что созданы
                if tdata.get('created_by') == callback.from_user.id and tdata.get('created_at'):
                    # Сообщение при создании (может отправиться несколько для Москвы — ок)
                    await send_tournament_created_to_channel(bot, tid, tdata)
        except Exception:
            pass

        # Очищаем состояние
        await state.clear()

        # Сообщение-результат
        if tournament_data.get('city') == 'Москва':
            await safe_edit_message(callback,
                (
                    "✅ Массовое создание/обновление турниров для Москвы завершено!\n\n"
                    f"Создано: {created}\n"
                    f"Обновлено: {updated}\n"
                )
            )
        else:
            # Для не-Москвы — короткое подтверждение (один турнир)
            await safe_edit_message(callback,
                (
                    "✅ Турнир успешно создан/обновлен!"
                )
            )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка создания турнира: {e}")
        await safe_edit_message(callback,
            "❌ Ошибка при создании турнира. Попробуйте еще раз."
        )
        await callback.answer()

# Обработчик отмены создания турнира
@router.callback_query(F.data == "tournament_cancel_create")
async def cancel_create_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены создания турнира"""
    await state.clear()
    
    await safe_edit_message(callback,
        "❌ Создание турнира отменено.\n\n"
        "Для создания нового турнира используйте команду /create_tournament"
    )
    await callback.answer()

# Команда для просмотра турниров
@router.message(F.text == "🏆 Турниры")
@router.message(Command("tournaments"))
async def tournaments_main(message: Message, state: FSMContext):
    """Главное меню турниров"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') in ['active', 'started'] and v.get('show_in_list', True)}
    
    text = (
        f"🏆 Турниры\n\n"
        f"Сейчас проходит: {len(active_tournaments)} активных турниров\n"
        f"Участвуйте в соревнованиях и покажите свои навыки!\n\n"
        f"📋 Вы можете просмотреть список доступных турниров, "
        f"подать заявку на участие или посмотреть свои текущие турниры."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть список", callback_data="view_tournaments_start")
    builder.button(text="🎯 Мои турниры", callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Начало просмотра турниров - выбор вида спорта
@router.callback_query(F.data == "view_tournaments_start")
async def view_tournaments_start(callback: CallbackQuery, state: FSMContext):
    """Начало просмотра турниров - выбор вида спорта (не зависит от наличия турниров)"""
    await state.set_state(ViewTournamentsStates.SELECT_SPORT)

    # Красивый выбор видов спорта, исключаем несоревновательные
    sport_kb = create_sport_keyboard(pref="view_tournament_sport:", exclude_sports=[
        "🍻По пиву",
        "🍒Знакомства",
        "☕️Бизнес-завтрак"
    ])

    await callback.message.delete()
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 1/5: Выберите вид спорта",
        reply_markup=sport_kb
    )
    await callback.answer()

# Обработчик выбора вида спорта для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_sport:"))
async def select_sport_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора вида спорта для просмотра турниров"""
    sport = callback.data.split(":", 1)[1]

    await state.set_state(ViewTournamentsStates.SELECT_COUNTRY)
    await state.update_data(selected_sport=sport)

    # Порядок стран как в конфиге (Россия первой)
    ordered_countries = ["🇷🇺 Россия"] + [c for c in cities_data.keys() if c != "🇷🇺 Россия"]
    builder = InlineKeyboardBuilder()
    for country in ordered_countries:
        builder.button(text=country, callback_data=f"view_tournament_country:{country}")
    # Кнопка ввода своей страны
    builder.button(text="✏️ Другая страна", callback_data="view_tournament_country:Другое")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 2/5: Выберите страну\n"
        f"✅ Вид спорта: {sport}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора страны для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_country:"))
async def select_country_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора страны для просмотра турниров"""
    country = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    sport = data.get('selected_sport')

    if country == "Другое":
        # Переходим на ввод страны вручную
        await state.set_state(ViewTournamentsStates.COUNTRY_INPUT)
        await state.update_data(selected_country=None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            f"🏆 Просмотр турниров\n\n"
            f"📋 Шаг 2/5: Введите страну\n"
            f"✅ Вид спорта: {sport}\n\n"
            f"Введите название страны:",
        )
        await callback.answer()
        return

    # Выбор города без зависимости от существующих турниров
    await state.set_state(ViewTournamentsStates.SELECT_CITY)
    await state.update_data(selected_country=country)

    builder = InlineKeyboardBuilder()
    # Порядок городов как в конфиге, плюс возможность ввода своего города
    for city in cities_data.get(country, []):
        builder.button(text=city, callback_data=f"view_tournament_city:{city}")
    builder.button(text="✏️ Другой город", callback_data="view_tournament_city_input")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 3/5: Выберите город\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.message(ViewTournamentsStates.COUNTRY_INPUT)
async def view_country_input(message: Message, state: FSMContext):
    """Ввод страны вручную в просмотре турниров"""
    country = (message.text or "").strip()
    data = await state.get_data()
    sport = data.get('selected_sport')
    await state.set_state(ViewTournamentsStates.SELECT_CITY)
    await state.update_data(selected_country=country)

    builder = InlineKeyboardBuilder()
    # Если страна неизвестна в конфиге, предлагаем сразу ввод города
    cities = cities_data.get(country, [])
    if cities:
        for city in cities:
            builder.button(text=city, callback_data=f"view_tournament_city:{city}")
    builder.button(text="✏️ Другой город", callback_data="view_tournament_city_input")
    builder.adjust(2)

    await message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 3/5: Выберите город\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}",
        reply_markup=builder.as_markup()
    )

# Обработчик выбора города для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_city:"))
async def select_city_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города для просмотра турниров"""
    city = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    
    # Если Москва — переходим к выбору района
    await state.update_data(selected_city=city)
    if city == "Москва":
        await state.set_state(ViewTournamentsStates.SELECT_DISTRICT)
        builder = InlineKeyboardBuilder()
        for district in DISTRICTS_MOSCOW:
            builder.button(text=district, callback_data=f"view_tournament_district:{district}")
        builder.adjust(2)

        await callback.message.delete()
        await callback.message.answer(
            f"🏆 Просмотр турниров\n\n"
            f"📋 Шаг 4/5: Выберите часть города\n"
            f"✅ Вид спорта: {sport}\n"
            f"✅ Страна: {country}\n"
            f"✅ Город: {city}",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    # Иначе сразу к выбору формата
    await state.set_state(ViewTournamentsStates.SELECT_GENDER)

    builder = InlineKeyboardBuilder()
    gender_options = [
        ("👤 Мужчины", "Мужчины"),
        ("👤 Женщины", "Женщины"),
        ("👥 Мужская пара", "Мужская пара"),
        ("👥 Женская пара", "Женская пара"),
        ("👥 Микст", "Микст"),
    ]
    for label, value in gender_options:
        builder.button(text=label, callback_data=f"view_tournament_gender:{value}")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 4/5: Выберите формат участия\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}\n"
        f"✅ Город: {city}\n\n"
        f"Выберите одиночный или парный формат:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "view_tournament_city_input")
async def view_city_input_request(callback: CallbackQuery, state: FSMContext):
    """Запрос ввода города вручную"""
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    await state.set_state(ViewTournamentsStates.CITY_INPUT)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 3/5: Введите город\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}\n\n"
        f"Введите название города:",
    )
    await callback.answer()

@router.message(ViewTournamentsStates.CITY_INPUT)
async def view_city_input(message: Message, state: FSMContext):
    """Ввод города вручную в просмотре турниров"""
    city = (message.text or "").strip()
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    await state.update_data(selected_city=city)
    if city == "Москва":
        await state.set_state(ViewTournamentsStates.SELECT_DISTRICT)
        builder = InlineKeyboardBuilder()
        for district in DISTRICTS_MOSCOW:
            builder.button(text=district, callback_data=f"view_tournament_district:{district}")
        builder.adjust(2)
        await message.answer(
            f"🏆 Просмотр турниров\n\n"
            f"📋 Шаг 4/5: Выберите часть города\n"
            f"✅ Вид спорта: {sport}\n"
            f"✅ Страна: {country}\n"
            f"✅ Город: {city}",
            reply_markup=builder.as_markup()
        )
        return

    # Переход к выбору формата
    await state.set_state(ViewTournamentsStates.SELECT_GENDER)
    builder = InlineKeyboardBuilder()
    gender_options = [
        ("👤 Мужчины", "Мужчины"),
        ("👤 Женщины", "Женщины"),
        ("👥 Мужская пара", "Мужская пара"),
        ("👥 Женская пара", "Женская пара"),
        ("👥 Микст", "Микст"),
    ]
    for label, value in gender_options:
        builder.button(text=label, callback_data=f"view_tournament_gender:{value}")
    builder.adjust(2)
    await message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 4/5: Выберите формат участия\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}\n"
        f"✅ Город: {city}\n\n"
        f"Выберите одиночный или парный формат:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("view_tournament_district:"))
async def view_select_district(callback: CallbackQuery, state: FSMContext):
    """Выбор района Москвы для просмотра турниров"""
    district = callback.data.split(":", 1)[1]
    await state.update_data(selected_district=district)
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    city = data.get('selected_city')

    await state.set_state(ViewTournamentsStates.SELECT_GENDER)
    builder = InlineKeyboardBuilder()
    gender_options = [
        ("👤 Мужчины", "Мужчины"),
        ("👤 Женщины", "Женщины"),
        ("👥 Мужская пара", "Мужская пара"),
        ("👥 Женская пара", "Женская пара"),
        ("👥 Микст", "Микст"),
    ]
    for label, value in gender_options:
        builder.button(text=label, callback_data=f"view_tournament_gender:{value}")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 5/5: Выберите формат участия\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}\n"
        f"✅ Город: {city}\n"
        f"✅ Район: {district}\n\n"
        f"Выберите одиночный или парный формат:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("view_tournament_gender:"))
async def select_gender_for_view(callback: CallbackQuery, state: FSMContext):
    """Шаг выбора формата участия (гендера/состава)"""
    gender = callback.data.split(":", 1)[1]

    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    city = data.get('selected_city')

    await state.update_data(selected_gender=gender)
    await state.set_state(ViewTournamentsStates.SELECT_TYPE)

    builder = InlineKeyboardBuilder()
    for t in TOURNAMENT_TYPES:
        builder.button(text=t, callback_data=f"view_tournament_type:{t}")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 5/5: Выберите тип турнира\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}\n"
        f"✅ Город: {city}\n"
        f"✅ Формат: {gender}\n\n"
        f"Какой тип турнира вас интересует?",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

def _auto_category_and_age(user_profile: dict) -> tuple[str, str, str]:
    """Определяет категорию, уровень текста и возрастную группу по профилю."""
    # Категория по уровню игрока и очкам
    player_level = str(user_profile.get('player_level') or '')
    rating_points = user_profile.get('rating_points')
    if rating_points is None:
        # Попробуем вычислить по уровню
        try:
            # level_to_points is async; but we are in sync context – fallback to mapping
            level_to_points_map = {
                "0.0": 0, "0.5": 300, "1.0": 500, "1.5": 700,
                "2.0": 900, "2.5": 1100, "3.0": 1200, "3.5": 1400,
                "4.0": 1600, "4.5": 1800, "5.0": 2000, "5.5": 2200,
                "6.0": 2400, "6.5": 2600, "7.0": 2800
            }
            rating_points = level_to_points_map.get(player_level, 0)
        except Exception:
            rating_points = 0
    # Определяем диапазон уровня игрока на основе CATEGORY_LEVELS
    level_range = None
    try:
        player_level_val = float(str(player_level).replace(',', '.'))
        for cat, rng in CATEGORY_LEVELS.items():
            r = str(rng).replace(',', '.')
            if '-' in r:
                low, high = [float(x.strip()) for x in r.split('-', 1)]
                if low <= player_level_val <= high:
                    level_range = f"{low}-{high}"
                    break
    except Exception:
        level_range = None

    # Категория: сначала пробуем по уровню, иначе по очкам
    category = _category_from_level(player_level)
    if not category:
        if rating_points >= 2600:
            category = "Профи"
        elif rating_points >= 2400:
            category = "Мастерс"
        elif rating_points >= 1600:
            category = "1 категория"
        elif rating_points >= 1100:
            category = "2 категория"
        else:
            category = "3 категория"

    # Возрастная группа по возрасту
    birth = user_profile.get('birth_date') or user_profile.get('birth')
    age_group = "Взрослые"
    try:
        # calculate_age is async; simple local evaluation using datetime if missing
        from datetime import datetime
        if birth:
            try:
                dt = datetime.strptime(birth, "%d.%m.%Y")
                today = datetime.now()
                age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
            except Exception:
                age = 18
        else:
            age = 18
        age_group = "Дети" if age < 18 else "Взрослые"
    except Exception:
        age_group = "Взрослые"

    level_text = level_range or "Не указан"
    return category, age_group, player_level, level_range

@router.callback_query(F.data.startswith("view_tournament_type:"))
async def select_type_for_view(callback: CallbackQuery, state: FSMContext):
    """Финальный шаг: фильтрация по всем параметрам, авто-создание при отсутствии"""
    tournament_type = callback.data.split(":", 1)[1]
    # Сохраняем выбранный тип в состоянии для пагинации
    await state.update_data(selected_type=tournament_type)

    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    city = data.get('selected_city')
    gender = data.get('selected_gender')
    selected_district = data.get('selected_district', '')

    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active' and v.get('show_in_list', True)}

    # Загружаем профиль пользователя для автоопределения
    users = await storage.load_users()
    user_profile = users.get(str(callback.from_user.id), {})
    category, age_group, level_text, level_range = _auto_category_and_age(user_profile)
    duration = "Многодневные"

    # Сохраняем вычисленные параметры для пагинации
    await state.update_data(
        selected_category=category,
        selected_age_group=age_group,
        user_level_text=level_text,
        selected_duration=duration,
        selected_level_range=level_range
    )

    # Фильтруем по всем параметрам
    def _district_match(t: dict) -> bool:
        if city == "Москва" and selected_district:
            return (t.get('district') or '') == selected_district
        return True
    filtered = {k: v for k, v in active_tournaments.items() if (
        v.get('sport') == sport and v.get('country') == country and v.get('city') == city and
        _district_match(v) and
        v.get('gender') == gender and v.get('type') == tournament_type and
        v.get('category') == category and v.get('age_group') == age_group and v.get('duration', duration) == duration and
        _is_level_match(level_text, v.get('level'))
    )}

    if not filtered:
        # Готовим новый турнир, но НЕ сохраняем — только по нажатию "Участвовать"
        base = {
            'sport': sport,
            'country': country,
            'city': city,
            'district': (selected_district if city == 'Москва' else ''),
            'type': tournament_type,
            'gender': gender,
            'category': category,
            'level': level_range,
            'age_group': age_group,
            'duration': duration,
            'participants_count': MIN_PARTICIPANTS.get(tournament_type, 4),
            'show_in_list': True,
            'hide_bracket': False,
            'comment': '',
        }

        # Сохраняем предложение в состоянии
        await state.update_data(proposed_tournament=base)

        # Подготовим красивое превью
        name = generate_tournament_name(base, len(tournaments) + 1)
        location = f"{base['city']}" + (f" ({base['district']})" if base.get('district') else "") + f", {base['country']}"
        text = (
            f"🏷️ {name}\n\n"
            f"- Место: {location}\n"
            f"- Тип: {base['type']}\n"
            f"- Формат: {base['gender']}\n"
            f"- Категория: {base['category']}\n"
            f"- Возраст: {base['age_group']}\n"
            f"- Продолжительность: {base['duration']}\n"
            f"- Участников: {base['participants_count']}\n\n"
            f"Нажмите \"Участвовать\" чтобы записаться на турнир."
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Участвовать", callback_data="apply_proposed_tournament")
        builder.button(text="🔙 Назад к выбору типа", callback_data=f"view_tournament_gender:{gender}")
        builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
        builder.adjust(1)

        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=builder.as_markup())
        await callback.answer()
        return

    # Показать список/первый турнир, если уже есть подходящие
    await show_tournaments_list(callback, filtered, sport, country, city)
    await callback.answer()

# Функция для показа списка турниров
async def show_tournaments_list(callback: CallbackQuery, tournaments: dict, sport: str, country: str, city: str):
    """Показывает список турниров"""
    if not tournaments:
        await callback.message.delete()
        await callback.message.answer(f"🏆 Нет активных турниров по {sport} в {city}, {country}")
        return
    
    # Преобразуем в список для пагинации
    tournament_list = list(tournaments.items())
    total_tournaments = len(tournament_list)
    
    text = f"🏆 Турниры по {sport}\n"
    text += f"📍 {city}, {country}\n\n"
    text += f"Найдено турниров: {total_tournaments}\n\n"
    
    # Показываем первый турнир
    tournament_id, tournament_data = tournament_list[0]
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text += f"🏆 {tournament_data.get('name', 'Турнир без названия')}\n\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"- Формат: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"- Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"- Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"- Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"- Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"- Описание: {tournament_data['comment']}\n"
    
    # Проверяем, зарегистрирован ли пользователь уже в турнире
    user_id = callback.from_user.id
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации (если турниров больше одного)
    if total_tournaments > 1:
        builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournament_prev:0")
        builder.button(text="Следующий ➡️", callback_data=f"view_tournament_next:0")
    
    # Кнопка участия (только если пользователь еще не зарегистрирован)
    if not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка истории игр (для всех пользователей)
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    if await is_admin(user_id):
        builder.button(text="🎲 Посев", callback_data=f"tournament_seeding_menu:{tournament_id}")
    
    # Кнопка оплаты участия, если есть взнос и пользователь зарегистрирован, но не оплатил
    fee = int(tournament_data.get('entry_fee', TOURNAMENT_ENTRY_FEE) or 0)
    paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if fee > 0 and is_registered and not paid:
        builder.button(text=f"💳 Оплатить участие ({fee}₽)", callback_data=f"tournament_pay:{tournament_id}")
    
    builder.button(text="🔙 Назад к выбору города", callback_data=f"view_tournament_country:{country}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_tournaments > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    if not is_registered:
        builder.adjust(1)  # Кнопка участия в отдельном ряду
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    # Создаем турнирную сетку (вынесено в утилиту)
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    # Если админ — добавим статусы оплат
    try:
        is_admin_user = await is_admin(callback.from_user.id)
    except Exception:
        is_admin_user = False
    final_caption = text
    if is_admin_user:
        payments_block = _build_payments_status_text(tournament_data)
        if payments_block:
            final_caption = f"{text}\n\n💳 Оплаты:\n{payments_block}"

    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=final_caption,
        reply_markup=builder.as_markup()
    )

# Обработчики пагинации для новой системы просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_prev:"))
async def view_tournament_prev(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Предыдущий' в просмотре турниров"""
    page = int(callback.data.split(':')[1])
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    city = data.get('selected_city')
    gender = data.get('selected_gender')
    tournament_type = data.get('selected_type')
    category = data.get('selected_category')
    age_group = data.get('selected_age_group')
    duration = data.get('selected_duration', 'Многодневные')
    user_level_text = data.get('user_level_text')
    selected_district = data.get('selected_district', '')
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active' and v.get('show_in_list', True)}
    
    # Фильтруем турниры по сохраненным параметрам
    def _district_match(t: dict) -> bool:
        if city == "Москва" and selected_district:
            return (t.get('district') or '') == selected_district
        return True
    filtered_tournaments = {k: v for k, v in active_tournaments.items() if (
        v.get('sport') == sport and v.get('country') == country and v.get('city') == city and
        _district_match(v) and
        v.get('gender') == gender and v.get('type') == tournament_type and
        v.get('category') == category and v.get('age_group') == age_group and v.get('duration', duration) == duration and
        _is_level_match(user_level_text, v.get('level'))
    )}
    
    if not filtered_tournaments:
        await callback.answer("❌ Нет турниров для отображения")
        return
    
    city_tournaments = filtered_tournaments
    
    # Вычисляем предыдущую страницу
    tournament_list = list(city_tournaments.items())
    total_tournaments = len(tournament_list)
    
    if total_tournaments <= 1:
        await callback.answer("❌ Это первый турнир")
        return
    
    prev_page = (page - 1) % total_tournaments
    if prev_page < 0:
        prev_page = total_tournaments - 1
    
    # Показываем предыдущий турнир
    tournament_id, tournament_data = tournament_list[prev_page]
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 Турниры по {sport}\n"
    text += f"📍 {city}, {country}\n\n"
    text += f"Найдено турниров: {total_tournaments}\n\n"
    text += f"🏆 {tournament_data.get('name', 'Турнир без названия')}\n\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"- Формат: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"- Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"- Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"- Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"- Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"- Описание: {tournament_data['comment']}\n"
    
    user_id = callback.from_user.id
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if total_tournaments > 1:
        builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournament_prev:{prev_page}")
        builder.button(text="Следующий ➡️", callback_data=f"view_tournament_next:{prev_page}")
    
    if not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка истории игр (для всех пользователей)
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    fee = int(tournament_data.get('entry_fee', TOURNAMENT_ENTRY_FEE) or 0)
    paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if fee > 0 and is_registered and not paid:
        builder.button(text=f"💳 Оплатить участие ({fee}₽)", callback_data=f"tournament_pay:{tournament_id}")
    
    # Кнопка турнирной сетки (для всех пользователей)
    builder.button(text="🏆 Турнирная сетка", callback_data=f"tournament_bracket:{tournament_id}")
    
    builder.button(text="🔙 Назад к выбору города", callback_data=f"view_tournament_country:{country}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    if total_tournaments > 1:
        builder.adjust(2)
    if not is_registered:
        builder.adjust(1)
    builder.adjust(1)
    
    # Создаем турнирную сетку (вынесено в утилиту)
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    # Если админ — добавим статусы оплат
    try:
        is_admin_user = await is_admin(callback.from_user.id)
    except Exception:
        is_admin_user = False
    final_caption = text
    if is_admin_user:
        payments_block = _build_payments_status_text(tournament_data)
        if payments_block:
            final_caption = f"{text}\n\n💳 Оплаты:\n{payments_block}"

    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=final_caption,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("view_tournament_next:"))
async def view_tournament_next(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Следующий' в просмотре турниров"""
    page = int(callback.data.split(':')[1])
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    city = data.get('selected_city')
    gender = data.get('selected_gender')
    tournament_type = data.get('selected_type')
    category = data.get('selected_category')
    age_group = data.get('selected_age_group')
    duration = data.get('selected_duration', 'Многодневные')
    user_level_text = data.get('user_level_text')
    selected_district = data.get('selected_district', '')
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active' and v.get('show_in_list', True)}
    
    # Фильтруем турниры по сохраненным параметрам
    def _district_match(t: dict) -> bool:
        if city == "Москва" and selected_district:
            return (t.get('district') or '') == selected_district
        return True
    filtered_tournaments = {k: v for k, v in active_tournaments.items() if (
        v.get('sport') == sport and v.get('country') == country and v.get('city') == city and
        _district_match(v) and
        v.get('gender') == gender and v.get('type') == tournament_type and
        v.get('category') == category and v.get('age_group') == age_group and v.get('duration', duration) == duration and
        _is_level_match(user_level_text, v.get('level'))
    )}
    
    if not filtered_tournaments:
        await callback.answer("❌ Нет турниров для отображения")
        return
    
    city_tournaments = filtered_tournaments
    
    # Вычисляем следующую страницу
    tournament_list = list(city_tournaments.items())
    total_tournaments = len(tournament_list)
    
    if total_tournaments <= 1:
        await callback.answer("❌ Это последний турнир")
        return
    
    next_page = (page + 1) % total_tournaments
    
    # Показываем следующий турнир
    tournament_id, tournament_data = tournament_list[next_page]
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 Турниры по {sport}\n"
    text += f"📍 {city}, {country}\n\n"
    text += f"Найдено турниров: {total_tournaments}\n\n"
    text += f"🏆 {tournament_data.get('name', 'Турнир без названия')}\n\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"- Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"- Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"- Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"- Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"- Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"- Описание: {tournament_data['comment']}\n"
    
    user_id = callback.from_user.id
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if total_tournaments > 1:
        builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournament_prev:{next_page}")
        builder.button(text="Следующий ➡️", callback_data=f"view_tournament_next:{next_page}")
    
    if not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка истории игр (для всех пользователей)
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    
    # Кнопка турнирной сетки (для всех пользователей)
    builder.button(text="🏆 Турнирная сетка", callback_data=f"tournament_bracket:{tournament_id}")
    
    builder.button(text="🔙 Назад к выбору города", callback_data=f"view_tournament_country:{country}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    if total_tournaments > 1:
        builder.adjust(2)
    if not is_registered:
        builder.adjust(1)
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик кнопки "Участвовать"
@router.callback_query(F.data.startswith("apply_tournament:"))
async def apply_tournament_handler(callback: CallbackQuery):
    """Немедленное участие в турнире (без заявок)"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Проверяем ограничение по количеству участников (если задано)
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(tournament_data.get('participants', {}))
    if max_participants and current_count >= max_participants:
        await callback.answer("❌ В этом турнире больше нет мест")
        return
    
    # Регистрируем пользователя сразу
    user_id = callback.from_user.id
    if str(user_id) in tournament_data.get('participants', {}):
        await callback.answer("✅ Вы уже зарегистрированы в этом турнире")
        return
    
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    if not user_data:
        await callback.answer("❌ Сначала зарегистрируйтесь в системе")
        return
    
    participants = tournament_data.get('participants', {})
    participants[str(user_id)] = {
        'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
        'phone': user_data.get('phone', 'Не указан'),
        'added_at': datetime.now().isoformat(),
        'added_by': user_id
    }
    tournament_data['participants'] = participants
    tournaments[tournament_id] = tournament_data
    await storage.save_tournaments(tournaments)

    # Уведомление в канал об участнике
    try:
        bot: Bot = callback.message.bot
        await send_tournament_application_to_channel(bot, tournament_id, tournament_data, str(user_id), user_data)
    except Exception:
        pass
    
    auto_started_text = ""
    
    # Готовим визуализацию сетки
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_start")
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    builder.adjust(1)
    
    caption = (
        "✅ Вы успешно зарегистрированы в турнире!\n\n"
        f"🏆 {tournament_data.get('name', 'Турнир')}\n"
        f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', '—')}"
        f"{auto_started_text}"
    )
    
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=caption,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "apply_proposed_tournament")
async def apply_proposed_tournament(callback: CallbackQuery, state: FSMContext):
    """Создает предложенный турнир и регистрирует пользователя"""
    data = await state.get_data()
    base = data.get('proposed_tournament')
    if not base:
        await callback.answer("❌ Не удалось найти предложение турнира")
        return

    tournaments = await storage.load_tournaments()

    # Создаем турнир
    from datetime import datetime
    name = generate_tournament_name(base, len(tournaments) + 1)
    tournament_id = f"tournament_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(tournaments)+1}"
    location = f"{base['city']}" + (f" ({base['district']})" if base.get('district') else "") + f", {base['country']}"
    description = (
        f"Турнир по {base['sport'].lower()}\n"
        f"Место: {location}\n"
        f"Тип: {base['type']}\n"
        f"Формат: {base['gender']}\n"
        f"Категория: {base['category']}\n"
        f"Уровень: {base.get('level', 'Не указан')}\n"
        f"Возраст: {base['age_group']}\n"
        f"Продолжительность: {base['duration']}\n"
        f"Участников: {base['participants_count']}"
    )

    tournaments[tournament_id] = {
        'name': name,
        'description': description,
        **base,
        'created_at': datetime.now().isoformat(),
        'created_by': callback.from_user.id,
        'participants': {},
        'status': 'active',
        'rules': 'Стандартные правила турнира',
    }
    await storage.save_tournaments(tournaments)

    # Уведомление о создании турнира
    try:
        bot: Bot = callback.message.bot
        await send_tournament_created_to_channel(bot, tournament_id, tournaments[tournament_id])
    except Exception:
        pass

    # Зарегистрируем пользователя
    user_id = callback.from_user.id
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    if not user_data:
        await callback.answer("❌ Сначала зарегистрируйтесь в системе")
        return

    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    participants[str(user_id)] = {
        'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
        'phone': user_data.get('phone', 'Не указан'),
        'added_at': datetime.now().isoformat(),
        'added_by': user_id
    }
    tournament_data['participants'] = participants
    tournaments[tournament_id] = tournament_data
    await storage.save_tournaments(tournaments)

    # Уведомление в канал об участнике
    try:
        bot: Bot = callback.message.bot
        await send_tournament_application_to_channel(bot, tournament_id, tournament_data, str(user_id), user_data)
    except Exception:
        pass

    # Очистим предложение
    await state.update_data(proposed_tournament=None)

    # Старт выполняется администратором после подтверждения посева
    auto_started_text = ""

    # Визуализация сетки
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_start")
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    builder.adjust(1)

    caption = (
        "✅ Вы успешно зарегистрированы в турнире!\n\n"
        f"🏆 {tournament_data.get('name', 'Турнир')}\n"
        f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', '—')}"
        f"{auto_started_text}"
    )

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=caption,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Просмотр своих заявок с пагинацией
@router.callback_query(F.data.startswith("my_applications_list:"))
async def my_applications_list(callback: CallbackQuery):
    """Заявки отключены: показываем уведомление"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_start")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    builder.adjust(1)
    await safe_edit_message(callback, "📋 Система заявок отключена. Вы сразу записываетесь в турнир.", builder.as_markup())
    await callback.answer()

# --- Оплата участия в турнире ---
@router.callback_query(F.data.startswith("tournament_pay:"))
async def tournament_pay_start(callback: CallbackQuery, state: FSMContext):
    """Старт оплаты участия в турнире через ЮKassa"""
    tournament_id = callback.data.split(":")[1]
    tournaments = await storage.load_tournaments()
    tournament = tournaments.get(tournament_id)
    if not tournament:
        await callback.answer("❌ Турнир не найден")
        return
    user_id = callback.from_user.id
    if str(user_id) not in tournament.get('participants', {}):
        await callback.answer("❌ Сначала зарегистрируйтесь в турнире")
        return
    fee = int(tournament.get('entry_fee', TOURNAMENT_ENTRY_FEE) or 0)
    if fee <= 0:
        await callback.answer("ℹ️ Оплата не требуется")
        return
    paid = tournament.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if paid:
        await callback.answer("✅ Участие уже оплачено")
        return
    await state.update_data(tournament_id=tournament_id, tournament_fee=fee)
    await callback.message.answer(
        "📧 Укажите email для чека (ЮKassa):",
    )
    await state.set_state(TournamentPaymentStates.WAITING_EMAIL)
    await callback.answer()

@router.message(TournamentPaymentStates.WAITING_EMAIL, F.text)
async def tournament_pay_get_email(message: Message, state: FSMContext):
    email = message.text.strip()
    if '@' not in email or '.' not in email:
        await message.answer("❌ Неверный email. Введите корректный email:")
        return
    data = await state.get_data()
    tournament_id = data['tournament_id']
    fee = data['tournament_fee']
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    from services.payments import create_payment
    try:
        payment_link, payment_id = await create_payment(message.chat.id, fee, f"Оплата участия в турнире {tournament_id}", email)
        await state.update_data(payment_id=payment_id, user_email=email)
        kb = InlineKeyboardBuilder()
        kb.button(text="🔗 Перейти к оплате", url=payment_link)
        kb.button(text="✅ Подтвердить оплату", callback_data=f"tournament_pay_confirm:{tournament_id}")
        kb.adjust(1)
        await message.answer(
            f"💳 Перейдите по ссылке для оплаты:\n{payment_link}\n\n"
            f"После оплаты нажмите 'Подтвердить оплату'\n\n"
            f"📧 Чек придет на: {email}",
            reply_markup=kb.as_markup()
        )
        await state.set_state(TournamentPaymentStates.CONFIRM_PAYMENT)
    except Exception as e:
        await message.answer(f"❌ Ошибка создания платежа: {e}")
        await state.clear()

@router.callback_query(TournamentPaymentStates.CONFIRM_PAYMENT, F.data.startswith("tournament_pay_confirm:"))
async def tournament_pay_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get('payment_id')
    tournament_id = callback.data.split(":")[1]
    try:
        payment = Payment.find_one(payment_id)
        if payment.status == 'succeeded':
            tournaments = await storage.load_tournaments()
            tournament = tournaments.get(tournament_id, {})
            payments = tournament.get('payments', {})
            payments[str(callback.from_user.id)] = {
                'payment_id': payment_id,
                'status': 'succeeded',
                'amount': payment.amount.value,
                'paid_at': datetime.now().isoformat(),
                'email': data.get('user_email')
            }
            tournament['payments'] = payments
            tournaments[tournament_id] = tournament
            await storage.save_tournaments(tournaments)
            await callback.message.answer("✅ Оплата успешно подтверждена! Удачи в турнире.")
        else:
            await callback.message.answer("⌛ Платеж еще не завершен. Подождите и попробуйте снова.")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка проверки платежа: {e}")
    await state.clear()
    await callback.answer()

# Просмотр турнира из заявки
@router.callback_query(F.data.startswith("view_tournament:"))
async def view_tournament_from_application(callback: CallbackQuery):
    """Показывает турнир"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Находим индекс турнира в списке активных турниров
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active' and v.get('show_in_list', True)}
    tournament_ids = list(active_tournaments.keys())
    
    if tournament_id not in tournament_ids:
        await callback.answer("❌ Турнир больше не активен")
        return
    
    page = tournament_ids.index(tournament_id)
    
    # Переходим к просмотру турнира через новую систему
    tournament_data = tournaments[tournament_id]
    user_id = callback.from_user.id
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 {tournament_data.get('name', 'Турнир без названия')}\n\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"- Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"- Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"- Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"- Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"- Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"- Описание: {tournament_data['comment']}\n"
    
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    if not is_registered:
        builder.adjust(1)
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Просмотр своих турниров с пагинацией
@router.callback_query(F.data.startswith("my_tournaments_list:"))
async def my_tournaments_list(callback: CallbackQuery):
    """Показывает турниры пользователя с пагинацией"""
    page = int(callback.data.split(':')[1])
    user_id = callback.from_user.id
    tournaments = await storage.load_tournaments()
    
    # Получаем все турниры пользователя
    user_tournaments = []
    for tournament_id, tournament_data in tournaments.items():
        if str(user_id) in tournament_data.get('participants', {}):
            user_tournaments.append((tournament_id, tournament_data))
    
    if not user_tournaments:
        await safe_edit_message(callback,"🎾 Вы пока не участвуете ни в одном турнире.")
        await callback.answer()
        return
    
    # Сохраняем список турниров для пагинации
    my_tournaments_pages[callback.from_user.id] = user_tournaments
    
    # Вычисляем общее количество страниц
    total_pages = len(user_tournaments)
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Получаем турнир для текущей страницы
    tournament_id, tournament_data = user_tournaments[page]
    participant_data = tournament_data['participants'][str(user_id)]
    
    # Формируем текст для текущего турнира
    text = f"🏆 Ваш турнир {page + 1}/{total_pages}\n\n"
    text += f"📋 Название: {tournament_data.get('name', 'Без названия')}\n"
    text += f"🏙️ Город: {tournament_data.get('city', 'Не указан')}\n"
    text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"👥 Участников: {len(tournament_data.get('participants', {}))}\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            builder.button(text="⬅️ Предыдущий", callback_data=f"my_tournaments_list:{page-1}")
        if page < total_pages - 1:
            builder.button(text="Следующий ➡️", callback_data=f"my_tournaments_list:{page+1}")
    
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_start")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_pages > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Команда просмотра заявок на турниры (только для админов)
@router.message(Command("view_tournament_applications"))
async def view_tournament_applications_command(message: Message, state: FSMContext):
    """Заявки отключены"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    await message.answer("📋 Система заявок отключена: пользователи записываются сразу.")

# Обработчик меню принятия заявки
@router.callback_query(F.data == "admin_accept_application_menu")
async def admin_accept_application_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора заявки для принятия"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Фильтруем только ожидающие заявки
    pending_applications = {k: v for k, v in applications.items() if v.get('status') == 'pending'}
    
    if not pending_applications:
        await safe_edit_message(callback,"📋 Нет заявок на рассмотрение")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for app_id, app_data in pending_applications.items():
        tournament_id = app_data.get('tournament_id')
        tournament_data = tournaments.get(tournament_id, {})
        tournament_name = tournament_data.get('name', 'Неизвестный турнир')
        user_name = app_data.get('user_name', 'Не указано')
        
        builder.button(
            text=f"✅ {user_name} - {tournament_name}", 
            callback_data=f"admin_accept_application:{app_id}"
        )
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        "✅ Принятие заявки на турнир\n\n"
        "Выберите заявку для принятия:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик принятия заявки
@router.callback_query(F.data.startswith("admin_accept_application:"))
async def admin_accept_application(callback: CallbackQuery, state: FSMContext):
    """Принятие заявки на турнир"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    app_id = callback.data.split(":", 1)[1]
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    if app_id not in applications:
        await callback.answer("❌ Заявка не найдена")
        return
    
    app_data = applications[app_id]
    tournament_id = app_data.get('tournament_id')
    user_id = app_data.get('user_id')
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    # Проверяем, не добавлен ли уже этот пользователь
    if str(user_id) in participants:
        await callback.answer("❌ Пользователь уже участвует в турнире")
        return
    
    # Загружаем данные пользователя
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден в системе")
        return
    
    # Обновляем статус заявки
    applications[app_id]['status'] = 'accepted'
    applications[app_id]['accepted_at'] = datetime.now().isoformat()
    applications[app_id]['accepted_by'] = callback.from_user.id
    await storage.save_tournament_applications(applications)
    
    # Добавляем участника в турнир
    participants[str(user_id)] = {
        'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
        'phone': user_data.get('phone', 'Не указан'),
        'added_at': datetime.now().isoformat(),
        'added_by': callback.from_user.id,
        'application_id': app_id
    }
    
    tournament_data['participants'] = participants
    await storage.save_tournaments(tournaments)
    
    # Проверяем, готов ли турнир к запуску
    tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
    
    success_message = f"✅ Заявка принята!\n\n"
    success_message += f"👤 Пользователь: {app_data.get('user_name', 'Не указано')}\n"
    success_message += f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
    success_message += f"📅 Принята: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    
    if tournament_ready and tournament_data.get('status') == 'active':
        success_message += f"🟨 Достигнут минимум участников. Админ может запустить турнир после подтверждения посева.\n\n"
    else:
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
        current_count = len(participants)
        success_message += f"📊 Участников: {current_count}/{min_participants}\n"
        success_message += f"⏳ Дождитесь набора минимального количества участников\n"
    
    # Отправляем уведомление пользователю
    try:
        from main import bot
        await bot.send_message(
            user_id,
            f"🎉 Ваша заявка принята!\n\n"
            f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
            f"📅 Принята: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Добро пожаловать в турнир!"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 К заявкам", callback_data="admin_accept_application_menu")
    builder.button(text="🔙 Главное меню", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        success_message,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )
    await callback.answer()

# Обработчик меню отклонения заявки
@router.callback_query(F.data == "admin_reject_application_menu")
async def admin_reject_application_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора заявки для отклонения"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Фильтруем только ожидающие заявки
    pending_applications = {k: v for k, v in applications.items() if v.get('status') == 'pending'}
    
    if not pending_applications:
        await safe_edit_message(callback,"📋 Нет заявок на рассмотрение")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for app_id, app_data in pending_applications.items():
        tournament_id = app_data.get('tournament_id')
        tournament_data = tournaments.get(tournament_id, {})
        tournament_name = tournament_data.get('name', 'Неизвестный турнир')
        user_name = app_data.get('user_name', 'Не указано')
        
        builder.button(
            text=f"❌ {user_name} - {tournament_name}", 
            callback_data=f"admin_reject_application:{app_id}"
        )
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        "❌ Отклонение заявки на турнир\n\n"
        "Выберите заявку для отклонения:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик отклонения заявки
@router.callback_query(F.data.startswith("admin_reject_application:"))
async def admin_reject_application(callback: CallbackQuery, state: FSMContext):
    """Отклонение заявки на турнир"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    app_id = callback.data.split(":", 1)[1]
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    if app_id not in applications:
        await callback.answer("❌ Заявка не найдена")
        return
    
    app_data = applications[app_id]
    tournament_id = app_data.get('tournament_id')
    user_id = app_data.get('user_id')
    
    tournament_data = tournaments.get(tournament_id, {})
    
    # Обновляем статус заявки
    applications[app_id]['status'] = 'rejected'
    applications[app_id]['rejected_at'] = datetime.now().isoformat()
    applications[app_id]['rejected_by'] = callback.from_user.id
    applications[app_id]['rejected_reason'] = 'Отклонено администратором'
    await storage.save_tournament_applications(applications)
    
    # Отправляем уведомление пользователю
    try:
        from main import bot
        await bot.send_message(
            user_id,
            f"❌ Ваша заявка отклонена\n\n"
            f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
            f"📅 Отклонена: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"📝 Причина: Отклонено администратором\n\n"
            f"Вы можете подать заявку на другой турнир."
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 К заявкам", callback_data="admin_reject_application_menu")
    builder.button(text="🔙 Главное меню", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        f"❌ Заявка отклонена!\n\n"
        f"👤 Пользователь: {app_data.get('user_name', 'Не указано')}\n"
        f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
        f"📅 Отклонена: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Пользователь получил уведомление об отклонении.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Команда просмотра участников турниров (только для админов)
@router.message(Command("view_tournament_participants"))
async def view_tournament_participants_command(message: Message, state: FSMContext):
    """Команда для просмотра участников турниров (только админы)"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await message.answer("📋 Нет турниров для просмотра")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        participants_count = len(tournament_data.get('participants', {}))
        builder.button(text=f"🏆 {name} ({city}) - {participants_count} участников", 
                      callback_data=f"admin_view_participants:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await message.answer(
        "👥 Просмотр участников турниров\n\n"
        "Выберите турнир для просмотра участников:",
        reply_markup=builder.as_markup()
    )

# Команда редактирования турниров (только для админов)
@router.message(Command("edit_tournaments"))
async def edit_tournaments_command(message: Message, state: FSMContext):
    """Команда для редактирования турниров (только админы)"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await message.answer("📋 Нет турниров для редактирования")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        builder.button(text=f"🏆 {name} ({city})", callback_data=f"edit_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await message.answer(
        "🏆 Редактирование турниров\n\n"
        "Выберите турнир для редактирования:",
        reply_markup=builder.as_markup()
    )

# Обработчик просмотра участников турнира (для админа)
@router.callback_query(F.data.startswith("admin_view_participants:"))
async def admin_view_tournament_participants(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра участников турнира для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"👥 Участники турнира\n\n"
    text += f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
    text += f"- Место: {location}\n"
    text += f"- Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"- Всего участников: {len(participants)}/{tournament_data.get('participants_count', 'Не указано')}\n\n"
    
    # Добавляем статус оплаты, если настроен взнос
    fee = int(tournament_data.get('entry_fee', TOURNAMENT_ENTRY_FEE) or 0)
    if fee > 0:
        text += f"💰 Взнос: {fee}₽\n\n"
    
    if participants:
        text += "📋 Список участников:\n"
        for i, (user_id, participant_data) in enumerate(participants.items(), 1):
            name = participant_data.get('name', 'Неизвестно')
            phone = participant_data.get('phone', 'Не указан')
            added_at = participant_data.get('added_at', '')
            pay_status = tournament_data.get('payments', {}).get(user_id, {}).get('status')
            paid_mark = "✅ Оплачено" if pay_status == 'succeeded' else ("⏳ Ожидает оплаты" if fee > 0 else "")
            
            # Форматируем дату добавления
            if added_at:
                try:
                    added_date = datetime.fromisoformat(added_at)
                    added_str = added_date.strftime('%d.%m.%Y %H:%M')
                except:
                    added_str = added_at
            else:
                added_str = 'Не указано'
            
            text += f"{i}. {name}\n"
            text += f"   📞 Телефон: {phone}\n"
            text += f"   🆔 ID: {user_id}\n"
            if fee > 0:
                text += f"   💳 Оплата: {paid_mark}\n"
            text += f"   📅 Добавлен: {added_str}\n\n"
    else:
        text += "📋 Участников пока нет\n"
    
    builder = InlineKeyboardBuilder()
    
    if participants:
        builder.button(text="🗑️ Удалить участника", callback_data=f"admin_remove_participant_menu:{tournament_id}")
    
    builder.button(text="➕ Добавить участника", callback_data=f"admin_add_participant:{tournament_id}")
    # Кнопка старта (если минимум участников набран и турнир еще не запущен)
    try:
        ready = await tournament_manager.check_tournament_readiness(tournament_id)
    except Exception:
        ready = False
    if ready and tournament_data.get('status') == 'active':
        builder.button(text="🚀 Запустить турнир", callback_data=f"tournament_seeding_menu:{tournament_id}")
    builder.button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
    builder.button(text="🏠 Главное меню", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик просмотра истории игр турнира
@router.callback_query(F.data.startswith("tournament_games_history:"))
async def tournament_games_history(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра истории игр турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id)
    
    if not tournament_data:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Загружаем игры
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Фильтруем игры турнира
    tournament_games = []
    for game in games:
        if game.get('tournament_id') == tournament_id:
            tournament_games.append(game)
    
    if not tournament_games:
        await safe_edit_message(callback,
            f"🏆 История игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
            "📊 Пока нет сыгранных игр в этом турнире.",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"view_tournament_city:{tournament_data.get('city', 'Не указан')}")
            .as_markup()
        )
        await callback.answer()
        return
    
    # Сортируем игры по дате (новые сначала)
    tournament_games.sort(key=lambda x: x['date'], reverse=True)
    
    # Формируем краткую информацию об играх
    history_text = f"🏆 История игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
    history_text += f"📊 Всего игр: {len(tournament_games)}\n\n"
    
    for i, game in enumerate(tournament_games[:10], 1):  # Показываем последние 10 игр
        game_date = datetime.fromisoformat(game['date'])
        formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
        
        # Определяем победителя
        team1_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
        team2_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
        
        if team1_wins > team2_wins:
            winner_id = game['players']['team1'][0]
            loser_id = game['players']['team2'][0]
        else:
            winner_id = game['players']['team2'][0]
            loser_id = game['players']['team1'][0]
        
        winner = users.get(winner_id, {})
        loser = users.get(loser_id, {})
        
        winner_name = f"{winner.get('first_name', '')} {winner.get('last_name', '')}".strip()
        loser_name = f"{loser.get('first_name', '')} {loser.get('last_name', '')}".strip()
        
        history_text += f"{i}. 📅 {formatted_date}\n"
        history_text += f"   🥇 {winner_name} победил {loser_name}\n"
        history_text += f"   📊 Счет: {game['score']}\n\n"
    
    if len(tournament_games) > 10:
        history_text += f"... и еще {len(tournament_games) - 10} игр\n\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопка для админа - подробный просмотр
    if await is_admin(callback.from_user.id):
        builder.button(text="🔧 Подробный просмотр (Админ)", callback_data=f"admin_tournament_games:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data=f"view_tournament_city:{tournament_data.get('city', 'Не указан')}")
    
    await safe_edit_message(callback,history_text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик подробного просмотра игр турнира для админа
@router.callback_query(F.data.startswith("admin_tournament_games:"))
async def admin_tournament_games(callback: CallbackQuery, state: FSMContext):
    """Обработчик подробного просмотра игр турнира для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id)
    
    if not tournament_data:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Загружаем игры
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Фильтруем игры турнира
    tournament_games = []
    for game in games:
        if game.get('tournament_id') == tournament_id:
            tournament_games.append(game)
    
    if not tournament_games:
        await safe_edit_message(callback,
            f"🏆 Подробная история игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
            "📊 Пока нет сыгранных игр в этом турнире.",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"tournament_games_history:{tournament_id}")
            .as_markup()
        )
        await callback.answer()
        return
    
    # Сортируем игры по дате (новые сначала)
    tournament_games.sort(key=lambda x: x['date'], reverse=True)
    
    # Формируем подробную информацию об играх
    history_text = f"🏆 Подробная история игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
    history_text += f"📊 Всего игр: {len(tournament_games)}\n\n"
    
    for i, game in enumerate(tournament_games, 1):
        game_date = datetime.fromisoformat(game['date'])
        formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
        
        # Определяем победителя
        team1_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
        team2_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
        
        if team1_wins > team2_wins:
            winner_id = game['players']['team1'][0]
            loser_id = game['players']['team2'][0]
        else:
            winner_id = game['players']['team2'][0]
            loser_id = game['players']['team1'][0]
        
        winner = users.get(winner_id, {})
        loser = users.get(loser_id, {})
        
        winner_name = f"{winner.get('first_name', '')} {winner.get('last_name', '')}".strip()
        loser_name = f"{loser.get('first_name', '')} {loser.get('last_name', '')}".strip()
        
        history_text += f"{i}. 📅 {formatted_date}\n"
        history_text += f"   🥇 {winner_name} победил {loser_name}\n"
        history_text += f"   📊 Счет: {game['score']}\n"
        history_text += f"   🆔 ID игры: {game['id']}\n"
        
        if game.get('media_filename'):
            history_text += f"   📷 Есть медиафайл\n"
        
        history_text += "\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждой игры (редактирование)
    for i, game in enumerate(tournament_games[:5], 1):  # Показываем первые 5 игр
        builder.button(text=f"✏️ Игра {i}", callback_data=f"admin_edit_game:{game['id']}")
    
    if len(tournament_games) > 5:
        builder.button(text="📄 Показать еще", callback_data=f"admin_tournament_games_more:{tournament_id}:5")
    
    builder.button(text="🔙 Назад", callback_data=f"tournament_games_history:{tournament_id}")
    
    await safe_edit_message(callback,history_text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик редактирования игры админом
@router.callback_query(F.data.startswith("admin_edit_game:"))
async def admin_edit_game(callback: CallbackQuery, state: FSMContext):
    """Обработчик редактирования игры админом"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await callback.answer("❌ Игра не найдена")
        return
    
    # Получаем информацию об игроках
    player1_id = game['players']['team1'][0]
    player2_id = game['players']['team2'][0]
    
    player1 = users.get(player1_id, {})
    player2 = users.get(player2_id, {})
    
    player1_name = f"{player1.get('first_name', '')} {player1.get('last_name', '')}".strip()
    player2_name = f"{player2.get('first_name', '')} {player2.get('last_name', '')}".strip()
    
    # Определяем текущего победителя
    team1_wins = sum(1 for set_score in game['sets'] 
                    if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
    team2_wins = sum(1 for set_score in game['sets'] 
                    if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
    
    if team1_wins > team2_wins:
        current_winner = player1_name
    else:
        current_winner = player2_name
    
    game_date = datetime.fromisoformat(game['date'])
    formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
    
    # Формируем информацию об игре
    game_text = f"🔧 Редактирование игры (Админ)\n\n"
    game_text += f"🆔 ID игры: {game_id}\n"
    game_text += f"📅 Дата: {formatted_date}\n"
    game_text += f"👤 Игрок 1: {player1_name}\n"
    game_text += f"👤 Игрок 2: {player2_name}\n"
    game_text += f"📊 Текущий счет: {game['score']}\n"
    game_text += f"🥇 Текущий победитель: {current_winner}\n"
    
    if game.get('media_filename'):
        game_text += f"📷 Медиафайл: {game['media_filename']}\n"
    
    # Создаем клавиатуру для редактирования
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить счет", callback_data=f"admin_edit_game_score:{game_id}")
    builder.button(text="📷 Изменить медиа", callback_data=f"admin_edit_game_media:{game_id}")
    builder.button(text="🔄 Изменить победителя", callback_data=f"admin_edit_game_winner:{game_id}")
    builder.button(text="🗑️ Удалить игру", callback_data=f"admin_delete_game:{game_id}")
    builder.button(text="🔙 Назад", callback_data=f"admin_tournament_games:{game.get('tournament_id', '')}")
    builder.adjust(1)
    
    await safe_edit_message(callback,game_text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик изменения счета игры
@router.callback_query(F.data.startswith("admin_edit_game_score:"))
async def admin_edit_game_score(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения счета игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_SCORE)
    
    await safe_edit_message(callback,
        f"✏️ Изменение счета игры {game_id}\n\n"
        "Введите новый счет в формате:\n"
        "6:4, 6:2 (для нескольких сетов)\n"
        "или\n"
        "6:4 (для одного сета)\n\n"
        "Примеры:\n"
        "• 6:4, 6:2\n"
        "• 7:5, 6:4, 6:2\n"
        "• 6:0",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик изменения медиафайла игры
@router.callback_query(F.data.startswith("admin_edit_game_media:"))
async def admin_edit_game_media(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения медиафайла игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_MEDIA)
    
    await safe_edit_message(callback,
        f"📷 Изменение медиафайла игры {game_id}\n\n"
        "Отправьте новое фото или видео для игры.\n"
        "Или отправьте 'удалить' чтобы удалить медиафайл.",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик изменения победителя игры
@router.callback_query(F.data.startswith("admin_edit_game_winner:"))
async def admin_edit_game_winner(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения победителя игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await callback.answer("❌ Игра не найдена")
        return
    
    # Получаем информацию об игроках
    player1_id = game['players']['team1'][0]
    player2_id = game['players']['team2'][0]
    
    player1 = users.get(player1_id, {})
    player2 = users.get(player2_id, {})
    
    player1_name = f"{player1.get('first_name', '')} {player1.get('last_name', '')}".strip()
    player2_name = f"{player2.get('first_name', '')} {player2.get('last_name', '')}".strip()
    
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_WINNER)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🥇 {player1_name}", callback_data=f"admin_set_winner:{game_id}:team1")
    builder.button(text=f"🥇 {player2_name}", callback_data=f"admin_set_winner:{game_id}:team2")
    builder.button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        f"🔄 Изменение победителя игры {game_id}\n\n"
        f"Текущий счет: {game['score']}\n\n"
        "Выберите нового победителя:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик ввода нового счета
@router.message(AdminEditGameStates.EDIT_SCORE)
async def admin_edit_score_input(message: Message, state: FSMContext):
    """Обработчик ввода нового счета игры"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        await state.clear()
        return
    
    new_score = message.text.strip()
    data = await state.get_data()
    game_id = data.get('editing_game_id')
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await message.answer("❌ Игра не найдена")
        await state.clear()
        return
    
    # Парсим новый счет
    try:
        sets = [s.strip() for s in new_score.split(',')]
        for s in sets:
            parts = s.split(':')
            if len(parts) != 2:
                raise ValueError("Неверный формат счета")
            int(parts[0])
            int(parts[1])
        
        # Обновляем игру
        game['score'] = new_score
        game['sets'] = sets
        
        # Сохраняем изменения
        await storage.save_games(games)
        
        await message.answer(
            f"✅ Счет игры {game_id} успешно изменен на: {new_score}",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат счета. Используйте формат: 6:4, 6:2",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    
    await state.clear()

# Обработчик изменения медиафайла
@router.message(AdminEditGameStates.EDIT_MEDIA)
async def admin_edit_media_input(message: Message, state: FSMContext):
    """Обработчик изменения медиафайла игры"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        await state.clear()
        return
    
    data = await state.get_data()
    game_id = data.get('editing_game_id')
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await message.answer("❌ Игра не найдена")
        await state.clear()
        return
    
    if message.text and message.text.lower() == 'удалить':
        # Удаляем медиафайл
        game['media_filename'] = None
        await storage.save_games(games)
        await message.answer(
            f"✅ Медиафайл игры {game_id} удален",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    elif message.photo:
        # Сохраняем новое фото
        photo_id = message.photo[-1].file_id
        # Здесь можно добавить сохранение фото на диск
        await message.answer(
            f"✅ Новое фото для игры {game_id} получено\n"
            f"ID фото: {photo_id}",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    elif message.video:
        # Сохраняем новое видео
        video_id = message.video.file_id
        await message.answer(
            f"✅ Новое видео для игры {game_id} получено\n"
            f"ID видео: {video_id}",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    else:
        await message.answer(
            "❌ Отправьте фото, видео или напишите 'удалить'",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    
    await state.clear()

# Обработчик установки нового победителя
@router.callback_query(F.data.startswith("admin_set_winner:"))
async def admin_set_winner(callback: CallbackQuery, state: FSMContext):
    """Обработчик установки нового победителя игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    parts = callback.data.split(":")
    game_id = parts[1]
    winner_team = parts[2]
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await callback.answer("❌ Игра не найдена")
        return
    
    # Обновляем счет так, чтобы выбранная команда стала победителем
    if winner_team == "team1":
        # Команда 1 должна выиграть больше сетов
        new_sets = ["6:4", "6:2"]  # Простой пример
    else:
        # Команда 2 должна выиграть больше сетов
        new_sets = ["4:6", "2:6"]  # Простой пример
    
    game['sets'] = new_sets
    game['score'] = ", ".join(new_sets)
    
    # Сохраняем изменения
    await storage.save_games(games)
    
    await safe_edit_message(callback,
        f"✅ Победитель игры {game_id} изменен\n"
        f"Новый счет: {game['score']}",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик удаления игры
@router.callback_query(F.data.startswith("admin_delete_game:"))
async def admin_delete_game(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим и удаляем игру
    games = [g for g in games if g['id'] != game_id]
    
    # Сохраняем изменения
    await storage.save_games(games)
    
    await safe_edit_message(callback,
        f"✅ Игра {game_id} удалена",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 К списку игр", callback_data=f"admin_tournament_games:{callback.data.split(':')[1] if ':' in callback.data else ''}")
        .as_markup()
    )
    await callback.answer()

# Обработчик выбора турнира для редактирования
@router.callback_query(F.data.startswith("edit_tournament:"))
async def select_tournament_for_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора турнира для редактирования"""
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Сохраняем ID турнира в состоянии
    await state.update_data(editing_tournament_id=tournament_id)
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 Редактирование турнира\n\n"
    text += f"📋 Информация о турнире:\n\n"
    text += f"- Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"- Место: {location}\n"
    text += f"- Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"- Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"- Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"- Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"- Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"- Участников: {tournament_data.get('participants_count', 'Не указано')}\n"
    text += f"- В списке города: {'Да' if tournament_data.get('show_in_list', False) else 'Нет'}\n"
    text += f"- Скрыть сетку: {'Да' if tournament_data.get('hide_bracket', False) else 'Нет'}\n"
    if tournament_data.get('comment'):
        text += f"- Описание: {tournament_data['comment']}\n"
    
    # Показываем участников
    participants = tournament_data.get('participants', {})
    if participants:
        text += f"\n👥 Участники ({len(participants)}):\n"
        for user_id, participant_data in participants.items():
            text += f"• {participant_data.get('name', 'Неизвестно')} (ID: {user_id})\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать поля", callback_data="edit_tournament_fields")
    builder.button(text="👥 Управление участниками", callback_data=f"manage_tournament_participants:{tournament_id}")
    builder.button(text="🗑️ Удалить турнир", callback_data=f"delete_tournament_confirm:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data="edit_tournaments_back")
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик редактирования полей турнира
@router.callback_query(F.data == "edit_tournament_fields")
async def edit_tournament_fields(callback: CallbackQuery, state: FSMContext):
    """Обработчик редактирования полей турнира"""
    builder = InlineKeyboardBuilder()
    builder.button(text="- Вид спорта", callback_data="edit_field:sport")
    builder.button(text="- Страна", callback_data="edit_field:country")
    builder.button(text="- Город", callback_data="edit_field:city")
    builder.button(text="- Район", callback_data="edit_field:district")
    builder.button(text="- Тип", callback_data="edit_field:type")
    builder.button(text="- Пол", callback_data="edit_field:gender")
    builder.button(text="- Категория", callback_data="edit_field:category")
    builder.button(text="- Возраст", callback_data="edit_field:age_group")
    builder.button(text="- Продолжительность", callback_data="edit_field:duration")
    builder.button(text="- Количество участников", callback_data="edit_field:participants_count")
    builder.button(text="- Показывать в списке", callback_data="edit_field:show_in_list")
    builder.button(text="- Скрыть сетку", callback_data="edit_field:hide_bracket")
    builder.button(text="- Описание", callback_data="edit_field:comment")
    builder.button(text="🔙 Назад", callback_data="1edit_tournament_back")
    builder.adjust(2)
    
    await safe_edit_message(callback,
        "✏️ Редактирование полей турнира\n\n"
        "Выберите поле для редактирования:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора поля для редактирования
@router.callback_query(F.data.startswith("edit_field:"))
async def select_field_to_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора поля для редактирования"""
    field = callback.data.split(":", 1)[1]
    
    # Сохраняем поле в состоянии
    await state.update_data(editing_field=field)
    
    tournaments = await storage.load_tournaments()
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    tournament_data = tournaments[tournament_id]
    
    if field == "sport":
        builder = InlineKeyboardBuilder()
        for sport in SPORTS:
            selected = "✅" if sport == tournament_data.get('sport') else ""
            builder.button(text=f"{selected} {sport}", callback_data=f"update_field:{sport}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"Редактирование: Вид спорта\n\n"
            f"Текущее значение: {tournament_data.get('sport', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "country":
        builder = InlineKeyboardBuilder()
        for country in COUNTRIES:
            selected = "✅" if country == tournament_data.get('country') else ""
            builder.button(text=f"{selected} {country}", callback_data=f"update_field:{country}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"🌍 Редактирование: Страна\n\n"
            f"Текущее значение: {tournament_data.get('country', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "city":
        current_country = tournament_data.get('country', '🇷🇺 Россия')
        cities = get_cities_for_country(current_country)
        
        builder = InlineKeyboardBuilder()
        for city in cities:
            selected = "✅" if city == tournament_data.get('city') else ""
            builder.button(text=f"{selected} {city}", callback_data=f"update_field:{city}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"🏙️ Редактирование: Город\n\n"
            f"Текущее значение: {tournament_data.get('city', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "district":
        if tournament_data.get('city') == "Москва":
            builder = InlineKeyboardBuilder()
            for district in DISTRICTS_MOSCOW:
                selected = "✅" if district == tournament_data.get('district') else ""
                builder.button(text=f"{selected} {district}", callback_data=f"update_field:{district}")
            builder.adjust(2)
            
            await safe_edit_message(callback,
                f"📍 Редактирование: Район\n\n"
                f"Текущее значение: {tournament_data.get('district', 'Не указан')}\n\n"
                f"Выберите новое значение:",
                reply_markup=builder.as_markup()
            )
        else:
            await safe_edit_message(callback,
                f"📍 Редактирование: Район\n\n"
                f"Для города {tournament_data.get('city', 'Не указан')} выбор района недоступен.\n"
                f"Район можно выбрать только для Москвы.",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_fields").as_markup()
            )
    
    elif field == "type":
        builder = InlineKeyboardBuilder()
        for t_type in TOURNAMENT_TYPES:
            selected = "✅" if t_type == tournament_data.get('type') else ""
            builder.button(text=f"{selected} {t_type}", callback_data=f"update_field:{t_type}")
        builder.adjust(1)
        
        await safe_edit_message(callback,
            f"⚔️ Редактирование: Тип турнира\n\n"
            f"Текущее значение: {tournament_data.get('type', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "gender":
        builder = InlineKeyboardBuilder()
        for gender in GENDERS:
            selected = "✅" if gender == tournament_data.get('gender') else ""
            builder.button(text=f"{selected} {gender}", callback_data=f"update_field:{gender}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"👥 Редактирование: Пол участников\n\n"
            f"Текущее значение: {tournament_data.get('gender', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "category":
        builder = InlineKeyboardBuilder()
        for category in CATEGORIES:
            selected = "✅" if category == tournament_data.get('category') else ""
            builder.button(text=f"{selected} {category}", callback_data=f"update_field:{category}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"🏆 Редактирование: Категория\n\n"
            f"Текущее значение: {tournament_data.get('category', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "age_group":
        builder = InlineKeyboardBuilder()
        for age_group in AGE_GROUPS:
            selected = "✅" if age_group == tournament_data.get('age_group') else ""
            builder.button(text=f"{selected} {age_group}", callback_data=f"update_field:{age_group}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"👶 Редактирование: Возрастная группа\n\n"
            f"Текущее значение: {tournament_data.get('age_group', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "duration":
        builder = InlineKeyboardBuilder()
        for duration in DURATIONS:
            selected = "✅" if duration == tournament_data.get('duration') else ""
            builder.button(text=f"{selected} {duration}", callback_data=f"update_field:{duration}")
        builder.adjust(1)
        
        await safe_edit_message(callback,
            f"⏱️ Редактирование: Продолжительность\n\n"
            f"Текущее значение: {tournament_data.get('duration', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "participants_count":
        await safe_edit_message(callback,
            f"👥 Редактирование: Количество участников\n\n"
            f"Текущее значение: {tournament_data.get('participants_count', 'Не указано')}\n\n"
            f"Введите новое количество участников (число):",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_fields").as_markup()
        )
        await state.set_state(EditTournamentStates.EDIT_PARTICIPANTS_COUNT)
    
    elif field == "show_in_list":
        current_value = tournament_data.get('show_in_list', False)
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            selected = "✅" if (option == "Да" and current_value) or (option == "Нет" and not current_value) else ""
            builder.button(text=f"{selected} {option}", callback_data=f"update_field:{option}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"📋 Редактирование: Показывать в списке города\n\n"
            f"Текущее значение: {'Да' if current_value else 'Нет'}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "hide_bracket":
        current_value = tournament_data.get('hide_bracket', False)
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            selected = "✅" if (option == "Да" and current_value) or (option == "Нет" and not current_value) else ""
            builder.button(text=f"{selected} {option}", callback_data=f"update_field:{option}")
        builder.adjust(2)
        
        await safe_edit_message(callback,
            f"🔒 Редактирование: Скрыть турнирную сетку\n\n"
            f"Текущее значение: {'Да' if current_value else 'Нет'}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "comment":
        await safe_edit_message(callback,
            f"💬 Редактирование: Описание\n\n"
            f"Текущее значение: {tournament_data.get('comment', 'Нет комментария')}\n\n"
            f"Введите новое описание (или отправьте '-' чтобы удалить):",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_fields").as_markup()
        )
        await state.set_state(EditTournamentStates.EDIT_COMMENT)
    
    await callback.answer()

# Обработчик обновления поля
@router.callback_query(F.data.startswith("update_field:"))
async def update_tournament_field(callback: CallbackQuery, state: FSMContext):
    """Обработчик обновления поля турнира"""
    new_value = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    field = data.get('editing_field')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    # Обновляем поле
    if field == "show_in_list":
        tournament_data[field] = new_value == "Да"
    elif field == "hide_bracket":
        tournament_data[field] = new_value == "Да"
    elif field == "category":
        tournament_data[field] = new_value
        # Обновляем уровень на основе новой категории
        tournament_data["level"] = CATEGORY_LEVELS.get(new_value, "Без уровня")
    else:
        tournament_data[field] = new_value
    
    # Сохраняем изменения
    await storage.save_tournaments(tournaments)
    
    await safe_edit_message(callback,
        f"✅ Поле '{field}' успешно обновлено!\n\n"
        f"Новое значение: {new_value}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="✏️ Редактировать еще", callback_data="edit_tournament_fields")
        .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        .adjust(1)
        .as_markup()
    )
    await callback.answer()

# Обработчик ввода количества участников
@router.message(EditTournamentStates.EDIT_PARTICIPANTS_COUNT)
async def edit_participants_count(message: Message, state: FSMContext):
    """Обработчик ввода количества участников"""
    try:
        count = int(message.text.strip())
        if count <= 0:
            await message.answer("❌ Количество участников должно быть больше 0. Попробуйте еще раз:")
            return
        
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        tournament_data['participants_count'] = count
        
        await storage.save_tournaments(tournaments)
        
        await message.answer(
            f"✅ Количество участников обновлено!\n\n"
            f"Новое значение: {count}\n\n"
            f"Выберите действие:",
            reply_markup=InlineKeyboardBuilder()
            .button(text="✏️ Редактировать еще", callback_data="edit_tournament_fields")
            .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
            .adjust(1)
            .as_markup()
        )
        
    except ValueError:
        await message.answer("❌ Введите корректное число. Попробуйте еще раз:")

# Обработчик ввода комментария
@router.message(EditTournamentStates.EDIT_COMMENT)
async def edit_comment(message: Message, state: FSMContext):
    """Обработчик ввода комментария"""
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    tournament_data['comment'] = comment
    
    await storage.save_tournaments(tournaments)
    
    await message.answer(
        f"✅ Описание обновлено!\n\n"
        f"Новое значение: {comment if comment else 'Нет описания'}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="✏️ Редактировать еще", callback_data="edit_tournament_fields")
        .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        .adjust(1)
        .as_markup()
    )

# Обработчик управления участниками
@router.callback_query(F.data.startswith("manage_tournament_participants"))
async def manage_tournament_participants(callback: CallbackQuery, state: FSMContext):
    """Обработчик управления участниками турнира"""
    parts = callback.data.split(":", 1)
    if len(parts) == 2 and parts[1]:
        tournament_id = parts[1]
        await state.update_data(editing_tournament_id=tournament_id)
    else:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        if not tournament_id:
            await callback.answer("❌ Турнир не выбран")
            return
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    text = f"👥 Управление участниками турнира\n\n"
    text += f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
    text += f"👥 Участников: {len(participants)}/{tournament_data.get('participants_count', 'Не указано')}\n\n"
    
    if participants:
        text += "📋 Список участников:\n"
        for user_id, participant_data in participants.items():
            text += f"• {participant_data.get('name', 'Неизвестно')} (ID: {user_id})\n"
    else:
        text += "📋 Участников пока нет\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить участника", callback_data=f"add_tournament_participant:{tournament_id}")
    if participants:
        builder.button(text="➖ Удалить участника", callback_data=f"remove_tournament_participant:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data=f"edit_tournament:{tournament_id}")
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()


# ===== Управление посевом (жеребьевкой) для админа =====
async def _ensure_seeding(tournament_id: str) -> list[str]:
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tournament_id, {})
    participants = t.get('participants', {}) or {}
    seeding: list[str] = t.get('seeding') or []
    ids = [uid for uid in participants.keys()]
    # фильтруем отвалившихся
    seeding = [sid for sid in seeding if sid in ids]
    # добираем отсутствующих случайным образом в конец
    import random
    remaining = [uid for uid in ids if uid not in seeding]
    if remaining:
        random.shuffle(remaining)
        seeding.extend(remaining)
        t['seeding'] = seeding
        tournaments[tournament_id] = t
        await storage.save_tournaments(tournaments)
    return seeding

def _format_first_round_pairs(seeding: list[str], users: dict) -> str:
    lines = ["\nПары 1-го круга:"]
    for i in range(0, len(seeding), 2):
        p1 = seeding[i]
        p2 = seeding[i+1] if i + 1 < len(seeding) else None
        n1 = users.get(p1, {}).get('first_name') or users.get(p1, {}).get('name') or str(p1)
        if p2:
            n2 = users.get(p2, {}).get('first_name') or users.get(p2, {}).get('name') or str(p2)
            lines.append(f"- {n1} vs {n2}")
        else:
            lines.append(f"- {n1} (проходит дальше)")
    return "\n".join(lines)

@router.callback_query(F.data.startswith("tournament_seeding_menu:"))
async def tournament_seeding_menu(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    tournament_id = callback.data.split(":")[1]
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tournament_id, {})
    if not t:
        await callback.answer("❌ Турнир не найден")
        return
    if t.get('type') != 'Олимпийская система':
        await safe_edit_message(callback, "ℹ️ Посев применяется только к олимпийской системе.")
        await callback.answer()
        return
    seeding = await _ensure_seeding(tournament_id)
    users = await storage.load_users()

    # Текст с порядком
    text_lines = [f"🎲 Посев турнира: {t.get('name', 'Турнир')}"]
    for idx, uid in enumerate(seeding, start=1):
        name = users.get(uid, {}).get('first_name') or users.get(uid, {}).get('name') or str(uid)
        text_lines.append(f"{idx}. {name}")
    text_lines.append(_format_first_round_pairs(seeding, users))

    # Клавиатура: переместить вверх/вниз, перемешать, сохранить и запустить, назад
    kb = InlineKeyboardBuilder()
    for idx, uid in enumerate(seeding):
        up_cb = f"tournament_seeding_move:{tournament_id}:{idx}:up"
        down_cb = f"tournament_seeding_move:{tournament_id}:{idx}:down"
        kb.row(InlineKeyboardButton(text=f"⬆️ {idx+1}", callback_data=up_cb), InlineKeyboardButton(text="⬇️", callback_data=down_cb))
    kb.row(InlineKeyboardButton(text="🔀 Перемешать", callback_data=f"tournament_seeding_shuffle:{tournament_id}"))
    # Кнопка сохранить и запустить (доступна если минимум участников набран)
    try:
        ready = await tournament_manager.check_tournament_readiness(tournament_id)
        if ready:
            kb.row(InlineKeyboardButton(text="💾 Сохранить и запустить", callback_data=f"tournament_seeding_save_start:{tournament_id}"))
    except Exception:
        pass
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_tournament:{tournament_id}"))

    await safe_edit_message(callback, "\n".join(text_lines), kb.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("tournament_seeding_save_start:"))
async def tournament_seeding_save_start(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    tid = callback.data.split(":")[1]
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tid, {})
    if not t:
        await callback.answer("❌ Турнир не найден")
        return
    # Проверяем минимум участников
    try:
        ready = await tournament_manager.check_tournament_readiness(tid)
    except Exception:
        ready = False
    if not ready:
        await callback.answer("⏳ Недостаточно участников для старта")
        return
    # Запускаем турнир и уведомляем
    started = await tournament_manager.start_tournament(tid)
    if started:
        # Уведомления участникам с сеткой и первой игрой (олимпийская) или списком соперников (круговая)
        try:
            from main import bot
            notifications = TournamentNotifications(bot)
            await notifications.notify_tournament_started(tid, tournaments.get(tid, {}))
        except Exception:
            pass
        await safe_edit_message(callback, "✅ Турнир запущен! Участникам отправлены уведомления", InlineKeyboardBuilder().button(text="🔙 К турниру", callback_data=f"view_tournament:{tid}").as_markup())
    else:
        await safe_edit_message(callback, "❌ Не удалось запустить турнир", InlineKeyboardBuilder().button(text="🔙 Назад", callback_data=f"tournament_seeding_menu:{tid}").as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("tournament_seeding_move:"))
async def tournament_seeding_move(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    _, tid, idx_str, direction = callback.data.split(":")
    idx = int(idx_str)
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tid, {})
    if not t:
        await callback.answer("❌ Турнир не найден")
        return
    seeding = await _ensure_seeding(tid)
    if not (0 <= idx < len(seeding)):
        await callback.answer("Некорректный индекс")
        return
    if direction == 'up' and idx > 0:
        seeding[idx-1], seeding[idx] = seeding[idx], seeding[idx-1]
    elif direction == 'down' and idx < len(seeding) - 1:
        seeding[idx+1], seeding[idx] = seeding[idx], seeding[idx+1]
    t['seeding'] = seeding
    tournaments[tid] = t
    await storage.save_tournaments(tournaments)
    await callback.answer("✅ Обновлено")
    # перерисовываем меню
    callback.data = f"tournament_seeding_menu:{tid}"
    await tournament_seeding_menu(callback)

@router.callback_query(F.data.startswith("tournament_seeding_shuffle:"))
async def tournament_seeding_shuffle(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    tid = callback.data.split(":")[1]
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tid, {})
    if not t:
        await callback.answer("❌ Турнир не найден")
        return
    seeding = await _ensure_seeding(tid)
    import random
    random.shuffle(seeding)
    t['seeding'] = seeding
    tournaments[tid] = t
    await storage.save_tournaments(tournaments)
    await callback.answer("🔀 Перемешано")
    callback.data = f"tournament_seeding_menu:{tid}"
    await tournament_seeding_menu(callback)


# Обработчик ввода ID участника
@router.message(EditTournamentStates.ADD_PARTICIPANT)
async def input_participant_id(message: Message, state: FSMContext):
    """Обработчик ввода ID участника"""
    try:
        user_id = int(message.text.strip())
        
        # Проверяем, существует ли пользователь
        users = await storage.load_users()
        if str(user_id) not in users:
            data = await state.get_data()
            tournament_id = data.get('editing_tournament_id') or data.get('admin_editing_tournament_id')
            
            # Определяем режим работы (обычный или админский)
            is_admin_mode = 'admin_editing_tournament_id' in data
            
            if is_admin_mode:
                back_callback = f"admin_view_participants:{tournament_id}"
            else:
                back_callback = "manage_tournament_participants"
            
            await message.answer(
                "❌ Пользователь с таким ID не найден в системе.\n\n"
                "Попробуйте еще раз или нажмите 'Назад':",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data=back_callback)
                .as_markup()
            )
            return
        
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id') or data.get('admin_editing_tournament_id')
        
        # Определяем режим работы (обычный или админский)
        is_admin_mode = 'admin_editing_tournament_id' in data
        
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        participants = tournament_data.get('participants', {})
        
        # Проверяем, не добавлен ли уже этот пользователь
        if str(user_id) in participants:
            if is_admin_mode:
                back_callback = f"admin_view_participants:{tournament_id}"
            else:
                back_callback = "manage_tournament_participants"
            
            await message.answer(
                "❌ Этот пользователь уже участвует в турнире.\n\n"
                "Попробуйте еще раз или нажмите 'Назад':",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data=back_callback)
                .as_markup()
            )
            return
        
        # Добавляем участника
        user_data = users[str(user_id)]
        participants[str(user_id)] = {
            'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
            'phone': user_data.get('phone', 'Не указан'),
            'added_at': datetime.now().isoformat(),
            'added_by': message.from_user.id
        }
        
        tournament_data['participants'] = participants
        await storage.save_tournaments(tournaments)
        
        # Проверяем, готов ли турнир к запуску
        tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
        
        success_message = f"✅ Участник успешно добавлен в турнир!\n\n"
        success_message += f"👤 Имя: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        success_message += f"🆔 ID: {user_id}\n"
        success_message += f"📞 Телефон: {user_data.get('phone', 'Не указан')}\n\n"
        
        if tournament_ready and tournament_data.get('status') == 'active':
            success_message += f"🟨 Достигнут минимум участников. Админ может запустить турнир после подтверждения посева.\n\n"
        else:
            tournament_type = tournament_data.get('type', 'Олимпийская система')
            min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
            current_count = len(participants)
            success_message += f"📊 Участников: {current_count}/{min_participants}\n"
            success_message += f"⏳ Дождитесь набора минимального количества участников\n"
        
        # Формируем кнопки в зависимости от режима
        builder = InlineKeyboardBuilder()
        if is_admin_mode:
            builder.button(text="➕ Добавить еще", callback_data=f"admin_add_participant:{tournament_id}")
            builder.button(text="👥 К участникам", callback_data=f"admin_view_participants:{tournament_id}")
            builder.button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
        else:
            builder.button(text="➕ Добавить еще", callback_data="add_tournament_participant")
            builder.button(text="👥 Управление участниками", callback_data="manage_tournament_participants")
            builder.button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        
        builder.adjust(1)
        
        await message.answer(
            success_message,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
        
    except ValueError:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id') or data.get('admin_editing_tournament_id')
        
        # Определяем режим работы (обычный или админский)
        is_admin_mode = 'admin_editing_tournament_id' in data
        
        if is_admin_mode:
            back_callback = f"admin_view_participants:{tournament_id}"
        else:
            back_callback = "manage_tournament_participants"
        
        await message.answer(
            "❌ Введите корректный ID пользователя (число).\n\n"
            "Попробуйте еще раз или нажмите 'Назад':",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=back_callback)
            .as_markup()
        )

# Обработчик удаления участника
@router.callback_query(F.data.startswith("remove_tournament_participant"))
async def remove_tournament_participant(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления участника из турнира"""
    parts = callback.data.split(":", 1)
    if len(parts) == 2 and parts[1]:
        tournament_id = parts[1]
        await state.update_data(editing_tournament_id=tournament_id)
    else:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        if not tournament_id:
            await callback.answer("❌ Турнир не выбран")
            return
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if not participants:
        await callback.answer("❌ В турнире нет участников для удаления")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, participant_data in participants.items():
        name = participant_data.get('name', 'Неизвестно')
        builder.button(text=f"➖ {name} (ID: {user_id})", callback_data=f"remove_participant:{user_id}")
    
    builder.button(text="🔙 Назад", callback_data=f"manage_tournament_participants:{tournament_id}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        "➖ Удаление участника из турнира\n\n"
        "Выберите участника для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("add_tournament_participant:"))
async def add_tournament_participant(callback: CallbackQuery, state: FSMContext):
    """Старт добавления участника из экрана управления участниками"""
    tournament_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_tournament_id=tournament_id)
    await state.set_state(EditTournamentStates.ADD_PARTICIPANT)
    await safe_edit_message(
        callback,
        "➕ Добавление участника в турнир\n\nВведите ID пользователя для добавления:",
        InlineKeyboardBuilder().button(text="🔙 Назад", callback_data=f"manage_tournament_participants:{tournament_id}").as_markup()
    )
    await callback.answer()

# Обработчик подтверждения удаления участника
@router.callback_query(F.data.startswith("remove_participant:"))
async def confirm_remove_participant(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления участника"""
    user_id = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if user_id not in participants:
        await callback.answer("❌ Участник не найден")
        return
    
    participant_data = participants[user_id]
    
    # Удаляем участника
    del participants[user_id]
    tournament_data['participants'] = participants
    await storage.save_tournaments(tournaments)
    
    await safe_edit_message(callback,
        f"✅ Участник успешно удален из турнира!\n\n"
        f"👤 Имя: {participant_data.get('name', 'Неизвестно')}\n"
        f"🆔 ID: {user_id}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="➖ Удалить еще", callback_data="remove_tournament_participant")
        .button(text="👥 Управление участниками", callback_data="manage_tournament_participants")
        .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        .adjust(1)
        .as_markup()
    )
    await callback.answer()

# Обработчик подтверждения удаления турнира
@router.callback_query(F.data.startswith("delete_tournament_confirm:"))
async def confirm_delete_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"delete_tournament_yes:{tournament_id}")
    builder.button(text="❌ Нет, отменить", callback_data=f"edit_tournament:{tournament_id}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        f"⚠️ Вы уверены, что хотите удалить турнир?\n\n"
        f"🏆 Название: {tournament_data.get('name', 'Без названия')}\n"
        f"📍 Место: {tournament_data.get('city', 'Не указан')}\n"
        f"👥 Участников: {len(tournament_data.get('participants', {}))}\n\n"
        f"Это действие необратимо!",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик удаления турнира
@router.callback_query(F.data.startswith("delete_tournament_yes:"))
async def delete_tournament_yes(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    # Удаляем турнир
    del tournaments[tournament_id]
    await storage.save_tournaments(tournaments)
    
    await state.clear()
    
    await safe_edit_message(callback,
        f"✅ Турнир успешно удален!\n\n"
        f"🏆 Название: {tournament_data.get('name', 'Без названия')}\n"
        f"📍 Место: {tournament_data.get('city', 'Не указан')}\n\n"
        f"Все данные о турнире удалены из системы."
    )
    await callback.answer()

# Обработчик меню удаления участника (для админа)
@router.callback_query(F.data.startswith("admin_remove_participant_menu:"))
async def admin_remove_participant_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления участника для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if not participants:
        await callback.answer("❌ В турнире нет участников для удаления")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, participant_data in participants.items():
        name = participant_data.get('name', 'Неизвестно')
        builder.button(text=f"🗑️ {name} (ID: {user_id})", callback_data=f"admin_remove_participant:{tournament_id}:{user_id}")
    
    builder.button(text="🔙 Назад к участникам", callback_data=f"admin_view_participants:{tournament_id}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        "🗑️ Удаление участника из турнира\n\n"
        "Выберите участника для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик удаления участника (для админа)
@router.callback_query(F.data.startswith("admin_remove_participant:"))
async def admin_remove_participant(callback: CallbackQuery, state: FSMContext):
    """Удаление участника из турнира для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    parts = callback.data.split(":")
    tournament_id = parts[1]
    user_id = parts[2]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if user_id not in participants:
        await callback.answer("❌ Участник не найден")
        return
    
    participant_data = participants[user_id]
    
    # Удаляем участника
    del participants[user_id]
    tournament_data['participants'] = participants
    await storage.save_tournaments(tournaments)
    
    await safe_edit_message(callback,
        f"✅ Участник успешно удален из турнира!\n\n"
        f"👤 Имя: {participant_data.get('name', 'Неизвестно')}\n"
        f"🆔 ID: {user_id}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🗑️ Удалить еще", callback_data=f"admin_remove_participant_menu:{tournament_id}")
        .button(text="👥 К участникам", callback_data=f"admin_view_participants:{tournament_id}")
        .button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
        .adjust(1)
        .as_markup()
    )
    await callback.answer()

# Обработчик добавления участника (для админа)
@router.callback_query(F.data.startswith("admin_add_participant:"))
async def admin_add_participant(callback: CallbackQuery, state: FSMContext):
    """Добавление участника в турнир для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    
    # Сохраняем ID турнира в состоянии
    await state.update_data(admin_editing_tournament_id=tournament_id)
    await state.set_state(EditTournamentStates.ADD_PARTICIPANT)
    
    await safe_edit_message(callback,
        "➕ Добавление участника в турнир\n\n"
        "Введите ID пользователя для добавления в турнир:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад к участникам", callback_data=f"admin_view_participants:{tournament_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик возврата к списку турниров (для админа)
@router.callback_query(F.data == "admin_back_to_tournament_list")
async def admin_back_to_tournament_list(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку турниров для админа"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await callback.message.delete()
        await callback.message.answer("📋 Нет турниров для просмотра")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        participants_count = len(tournament_data.get('participants', {}))
        builder.button(text=f"🏆 {name} ({city}) - {participants_count} участников", 
                      callback_data=f"admin_view_participants:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    # Удаляем старое сообщение и отправляем новое
    await callback.message.delete()
    await callback.message.answer(
        "👥 Просмотр участников турниров\n\n"
        "Выберите турнир для просмотра участников:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчики навигации
@router.callback_query(F.data == "edit_tournaments_back")
async def edit_tournaments_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку турниров для редактирования"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await callback.message.delete()
        await callback.message.answer("📋 Нет турниров для редактирования")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        builder.button(text=f"🏆 {name} ({city})", callback_data=f"edit_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    # Удаляем старое сообщение и отправляем новое
    await callback.message.delete()
    await callback.message.answer(
        "🏆 Редактирование турниров\n\n"
        "Выберите турнир для редактирования:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "1edit_tournament_back")
async def edit_tournament_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к турниру"""
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    if tournament_id:
        await select_tournament_for_edit(callback, state)
    else:
        await edit_tournaments_back(callback, state)

# Возврат в главное меню турниров
@router.callback_query(F.data == "tournaments_main_menu")
async def tournaments_main_menu(callback: CallbackQuery):
    """Возврат в главное меню турниров"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') in ['active', 'started']}
    
    text = (
        f"🏆 Турниры\n\n"
        f"Сейчас проходит: {len(active_tournaments)} активных турниров\n"
        f"Участвуйте в соревнованиях и покажите свои навыки!\n\n"
        f"📋 Вы можете просмотреть список доступных турниров, "
        f"подать заявку на участие или посмотреть свои текущие турниры."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть список", callback_data="view_tournaments_start")
    builder.button(text="🎯 Мои турниры", callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    # Удаляем старое сообщение и отправляем новое
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()


# Обработчик отображения турнирной сетки
@router.callback_query(F.data.startswith("tournament_bracket:"))
async def tournament_bracket(callback: CallbackQuery, state: FSMContext):
    """Обработчик отображения турнирной сетки (унифицированный билдер)"""
    tournament_id = callback.data.split(":")[1]

    tournaments = await storage.load_tournaments()
    tournament = tournaments.get(tournament_id, {})
    if not tournament:
        await safe_edit_message(callback, "❌ Турнир не найден")
        await callback.answer()
        return

    participants = tournament.get('participants', {})
    tournament_type = tournament.get('type', 'Олимпийская система')
    min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
    current_participants = len(participants)

    if current_participants < min_participants:
        await safe_edit_message(
            callback,
            (
                "❌ Недостаточно участников для отображения сетки!\n\n"
                f"🏆 Турнир: {tournament.get('name', 'Без названия')}\n"
                f"⚔️ Тип: {tournament_type}\n"
                f"👥 Текущих участников: {current_participants}\n"
                f"📊 Минимум требуется: {min_participants}\n\n"
                "Дождитесь набора минимального количества участников."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад к турниру", callback_data=f"view_tournament:{tournament_id}")]]
            ),
        )
        await callback.answer()
        return

    # Генерируем изображение через общий билдер
    image_bytes, _ = await build_and_render_tournament_image(tournament, tournament_id)
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(image_bytes, filename="tournament_bracket.png"),
        caption=(
            f"🏆 Турнирная сетка\n\n"
            f"📋 Турнир: {tournament.get('name', 'Без названия')}\n"
            f"⚔️ Тип: {tournament_type}\n"
            f"👥 Участников: {current_participants}"
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад к турниру", callback_data=f"view_tournament:{tournament_id}")]]
        ),
    )
    await callback.answer()

