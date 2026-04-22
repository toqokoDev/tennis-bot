from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Optional
from aiogram.fsm.context import FSMContext
import logging
import os
from datetime import datetime
from html import escape as html_escape

from services.storage import storage
from services.channels import send_game_notification_to_channel, send_tournament_created_to_channel, send_tournament_application_to_channel, send_tournament_started_to_channel
from models.states import CreateTournamentStates, EditTournamentStates, ViewTournamentsStates, AdminEditGameStates
from utils.admin import is_admin
from config.profile import sport_type, cities_data, create_sport_keyboard, get_country_translation, get_city_translation, get_sport_translation, get_district_translation, get_tournament_type_translation, get_gender_translation, get_tournament_gender_display, format_admin_tournament_level, get_tournament_gender_name_suffix, get_category_translation, get_age_group_translation, get_duration_translation
from config.tournament_config import (
    TOURNAMENT_TYPES, GENDERS, CATEGORIES, AGE_GROUPS, 
    DURATIONS, YES_NO_OPTIONS, DISTRICTS_MOSCOW, MIN_PARTICIPANTS, CATEGORY_LEVELS
)
from utils.tournament_brackets import Player
from utils.bracket_image_generator import (
    build_tournament_bracket_image_bytes,
    create_simple_text_image_bytes,
)
from utils.round_robin_image_generator import build_round_robin_table
from utils.tournament_manager import tournament_manager
from utils.utils import calculate_new_ratings, remove_country_flag
from handlers.profile import calculate_level_from_points
from utils.tournament_notifications import TournamentNotifications
from utils.tournament_lifecycle import (
    admin_sort_tournament_items,
    participants_count_label,
    maybe_begin_payment_collection,
    maybe_clear_payment_window_if_resolved,
    tournament_strip_removed_participant_payment_state,
)
from utils.translations import get_user_language_async, t
from config.config import SHOP_ID, SECRET_KEY
from yookassa import Configuration, Payment
from models.states import TournamentPaymentStates
from services.payments import check_tinkoff_payment_status, generate_tinkoff_payment_link, generate_yookassa_payment_link
from utils.email import send_tournament_payment_notification_to_admin

router = Router()
logger = logging.getLogger(__name__)

# Получаем стоимость участия в турнире из переменной окружения
def get_tournament_entry_fee() -> int:
    """Получает стоимость участия в турнире из переменной окружения TOURNAMENT_ENTRY_FEE"""
    try:
        return int(os.getenv('TOURNAMENT_ENTRY_FEE', '800'))
    except ValueError:
        logger.warning("Некорректное значение TOURNAMENT_ENTRY_FEE в переменных окружения, используется 500 по умолчанию")
        return 800

# Глобальные переменные для хранения состояния пагинации
tournament_pages = {}
my_tournaments_pages = {}
my_applications_pages = {}

# Глобальная переменная для хранения данных создаваемого турнира
tournament_data = {}

# Хелпер-функция для обрезки caption (лимит Telegram - 1024 символа)
def truncate_caption(text: str, max_length: int = 1020) -> str:
    """Обрезает текст до максимальной длины, добавляя '...' в конце"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

# Списки для выбора (используем данные из конфигурации)
SPORTS = sport_type
COUNTRIES = list(cities_data.keys())

# Получаем города для каждой страны из конфигурации
def get_cities_for_country(country):
    """Получить список городов для страны"""
    cities = cities_data.get(country, [])
    return cities + ["Другое"] if cities else ["Другое"]

async def get_other_countries_from_tournaments(sport: str) -> list[str]:
    """Получить страны из турниров, которых нет в основном списке"""
    tournaments = await storage.load_tournaments()
    other_countries = set()
    
    for tournament in tournaments.values():
        if tournament.get('sport') == sport and tournament.get('status') in ['active', 'started']:
            country = tournament.get('country', '')
            if country and country not in COUNTRIES:
                other_countries.add(country)
    
    return sorted(list(other_countries))[:5]  # Максимум 5

async def get_other_cities_from_tournaments(sport: str, country: str) -> list[str]:
    """Получить города из турниров, которых нет в списке для страны"""
    tournaments = await storage.load_tournaments()
    known_cities = set(cities_data.get(country, []))
    other_cities = set()
    
    for tournament in tournaments.values():
        if (tournament.get('sport') == sport and 
            tournament.get('country') == country and 
            tournament.get('status') in ['active', 'started']):
            city = tournament.get('city', '')
            if city and city not in known_cities:
                other_cities.add(city)
    
    return sorted(list(other_cities))[:5]  # Максимум 5

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
def _build_payments_status_text(tournament: dict, language: str) -> str:
    try:
        participants = tournament.get('participants', {}) or {}
        payments = tournament.get('payments', {}) or {}
        if not participants:
            return t("tournament.no_participants_short", language)
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
def generate_tournament_name(tournament_data, tournament_number, language='ru'):
    """Генерирует название турнира: префикс, уровень, место, №, затем Муж/Жен/Пара/Муж Пара/Микст для людей."""
    level = tournament_data.get('level') or t("tournament.not_specified", language)
    
    # Формируем место проведения
    if tournament_data['city'] == "Москва" and 'district' in tournament_data:
        location = tournament_data['district']
    else:
        location = f"{tournament_data['city']}, {remove_country_flag(tournament_data['country'])}"
    
    name = f"{t('tournament.image.tournament_name_prefix', language)} {level} {location} №{tournament_number}"
    tail = get_tournament_gender_name_suffix(tournament_data, language)
    if tail:
        name = f"{name} {tail}"
    return name

# Функция для создания продвинутой визуальной сетки турнира
def create_advanced_tournament_bracket(tournament_data, bracket_text, users_data=None, completed_games=None, language: str = 'ru') -> bytes:
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
        # Если есть и имя и фамилия - используем инициалы, если только имя - используем его полностью
        if first_name and last_name:
            initials = (first_name[:1] + last_name[:1]).upper()
        elif first_name:
            initials = first_name.upper()
        else:
            initials = '??'
        
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
        set_diff = {}  # Разница очков в сетах для тай-брейка (как в round_robin_image_generator)
        
        # Инициализируем результаты
        for i in range(n):
            player_id = players[i]['id']
            results[player_id] = {}
            wins[player_id] = 0
            set_diff[player_id] = 0
        
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
                    sets_data = []  # Сохраняем детализацию по сетам для подсчета очков
                    for set_score in sets:
                        try:
                            p1_games, p2_games = map(int, set_score.split(':'))
                            sets_data.append((p1_games, p2_games))
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
                        'sets_lost': player2_sets,
                        'sets_data': sets_data  # Храним детализацию для подсчета очков в сетах
                    }
                    results[player2_id][player1_id] = {
                        'score': score,
                        'sets_won': player2_sets,
                        'sets_lost': player1_sets,
                        'sets_data': [(b, a) for a, b in sets_data]  # Инвертируем для второго игрока
                    }

                    # Подсчитываем победы (просто по сетам, без системы 3/1/0)
                    if player1_sets > player2_sets:
                        wins[player1_id] += 1
                    elif player2_sets > player1_sets:
                        wins[player2_id] += 1
                except Exception:
                    pass
        
        # Подсчет сыгранных матчей на игрока по заполненным результатам
        games_played = {}
        for p in players:
            pid = p['id']
            games_played[pid] = len(results.get(pid, {}))

        # Подсчет тай-брейка: разница очков в сетах только среди игроков с равным количеством побед
        # (как в round_robin_image_generator.py)
        # 1) Группируем игроков по количеству побед
        from collections import defaultdict
        wins_groups = defaultdict(list)
        for pid in [p['id'] for p in players]:
            wins_groups[wins[pid]].append(pid)

        # 2) Для каждой группы с размером > 1 считаем разницу очков в сетах только между игроками этой группы
        for win_count, group in wins_groups.items():
            if len(group) <= 1:
                continue
            for pid in group:
                points_diff = 0
                for opp in group:
                    if opp == pid:
                        continue
                    if pid in results and opp in results[pid]:
                        match_res = results[pid][opp]
                        # Считаем сумму разниц очков в каждом сете
                        sets_data = match_res.get('sets_data', [])
                        for set_score in sets_data:
                            points_diff += set_score[0] - set_score[1]
                set_diff[pid] = points_diff

        # 3) Сортируем игроков: по победам, затем по тай-брейку (разница очков в сетах)
        sorted_players = sorted(
            players,
            key=lambda p: (wins[p['id']], set_diff.get(p['id'], 0)),
            reverse=True
        )

        return {
            'players': sorted_players,
            'results': results,
            'wins': wins,
            'set_diff': set_diff,  # Изменено с league_points и tie_points на set_diff
            'games_played': games_played,
            'wins_groups': wins_groups  # Изменено с tied_ids на wins_groups
        }
    
    # Рисуем заголовок турнира
    tournament_name = tournament_data.get('name') or t("tournament.no_name", language)
    draw.rectangle([0, 0, width, 60], fill=header_color)
    draw.text((20, 20), tournament_name, fill=text_color, font=title_font)
    
    # Рисуем информацию о турнире
    location = f"{tournament_data.get('city', '')} {tournament_data.get('district', '')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    
    gender_line = get_tournament_gender_display(
        tournament_data.get("gender"),
        language,
        tournament_name=tournament_data.get("name"),
        tournament_comment=tournament_data.get("comment"),
    )
    not_spec = t("tournament.not_specified", language)
    gender_part = "" if gender_line == not_spec else gender_line
    tournament_info = f"{location} - {tournament_data.get('duration', '')} | {tournament_data.get('category', '')} {gender_part}".rstrip()
    draw.text((20, 45), tournament_info, fill=text_color, font=player_font)
    
    # Рисуем статус турнира
    status_text = t("tournament.image.status_active", language) if tournament_data.get('status') == 'active' else t("tournament.image.status_finished", language)
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
            draw_round_robin_table(draw, table_data, x_start, y_start, language)
    else:
        # Рисуем обычную сетку турнира
        draw_tournament_bracket(draw, bracket_text, users_data, x_start, y_start, load_user_avatar, language)
    
    # Рисуем завершенные игры справа
    if completed_games and tournament_type != 'Круговая система':
        draw_completed_games(draw, completed_games, width, y_start, language)
    
    # Рисуем информацию об участниках
    participants_count = len(tournament_data.get('participants', {}))
    max_participants = tournament_data.get('participants_count', 0)
    
    participants_text = f"{t('tournament.image.participants_text', language)} {participants_count}/{max_participants}"
    draw.text((width - 200, height - 30), participants_text, fill=text_color, font=player_font)
    
    # Сохраняем в байты
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def draw_round_robin_table(draw, table_data, x_start, y_start, language: str = 'ru'):
    """Рисует таблицу круговой системы"""
    players = table_data['players']
    results = table_data['results']
    wins = table_data['wins']
    set_diff = table_data.get('set_diff', {})
    wins_groups = table_data.get('wins_groups', {})
    
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
    draw.text((x_pos + 10, y_start + 5), t("tournament.image.table_players", language), fill=text_color, font=header_font)
    
    # Заголовки игроков
    for i, player in enumerate(players):
        x_pos = x_start + player_width + i * cell_width
        if player['avatar']:
            # Рисуем аватар
            draw.rectangle([x_pos + 5, y_start + 5, x_pos + 25, y_start + 25], fill=(200, 200, 200))
            # Здесь можно было бы вставить аватар, но для простоты рисуем инициалы
            name_parts = player['name'].split()
            if len(name_parts) >= 2:
                initials = (name_parts[0][:1] + name_parts[1][:1]).upper()
            else:
                initials = player['name'].upper()
            draw.text((x_pos + 15, y_start + 15), initials, fill=text_color, font=small_font, anchor="mm")
        
        # Имя игрока
        draw.text((x_pos + 30, y_start + 5), player['name'][:8], fill=text_color, font=small_font)
    
    # Колонки результатов
    x_pos = x_start + player_width + len(players) * cell_width
    draw.text((x_pos + 10, y_start + 5), t("tournament.image.table_games", language), fill=text_color, font=header_font)
    x_pos += cell_width
    draw.text((x_pos + 10, y_start + 5), t("tournament.image.table_wins", language), fill=text_color, font=header_font)
    x_pos += cell_width
    draw.text((x_pos + 10, y_start + 5), t("tournament.image.table_points", language), fill=text_color, font=header_font)
    x_pos += cell_width
    draw.text((x_pos + 10, y_start + 5), t("tournament.image.table_places", language), fill=text_color, font=header_font)
    
    # Рисуем строки игроков
    for i, player in enumerate(players):
        y_pos = y_start + header_height + i * cell_height
        
        # Имя игрока
        if player['avatar']:
            draw.rectangle([x_start + 5, y_pos + 5, x_start + 25, y_pos + 25], fill=(200, 200, 200))
            name_parts = player['name'].split()
            if len(name_parts) >= 2:
                initials = (name_parts[0][:1] + name_parts[1][:1]).upper()
            else:
                initials = player['name'].upper()
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
        # Очки (разница очков в сетах для тай-брейка)
        draw.rectangle([x_pos, y_pos, x_pos + cell_width, y_pos + cell_height], 
                      fill=bg_color, outline=table_border_color)
        # Показываем разницу очков только для игроков с равным числом побед
        sd_value = set_diff.get(player['id'], 0)
        wins_count = wins.get(player['id'], 0)
        sd_text = str(sd_value) if sd_value != 0 or len(wins_groups.get(wins_count, [])) > 1 else "-"
        draw.text((x_pos + cell_width//2, y_pos + cell_height//2), sd_text, 
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

    footnote = t("tournament.image.table_footnote", language)
    footnote_y = y_start + header_height + len(players) * cell_height + 10
    draw.text((x_start, footnote_y), footnote, fill=text_color, font=note_font)

def draw_tournament_bracket(draw, bracket_text, users_data, x_start, y_start, load_user_avatar_func, language: str = 'ru'):
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
                draw.text((x_pos + 10, y_pos + 45), t("tournament.image.auto_advance", language), fill=text_color, font=small_font)
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
                    free_slot_text = t("tournament.image.free_slot", language)
                    player1_color = empty_color if player1_name == free_slot_text else text_color
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
                free_slot_text = t("tournament.image.free_slot", language)
                player2_color = empty_color if player2_name == free_slot_text else text_color
                draw.text((text_x2, y_pos + 35), player2_name, fill=player2_color, font=player_font)
                if player2_score:
                    draw.text((x_pos + round_width - 60, y_pos + 35), player2_score, fill=winner_color, font=score_font)
                
                # Рисуем разделитель
                draw.line([x_pos + 10, y_pos + 30, x_pos + round_width - 30, y_pos + 30], fill=(200, 200, 200))
            
            y_pos += match_height + 10

def draw_completed_games(draw, completed_games, width, y_start, language: str = 'ru'):
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
    draw.text((games_x + 10, games_y + 5), t("tournament.image.completed_games", language), fill=text_color, font=header_font)
    
    games_y += 40
    
    # Показываем до 10 последних игр
    games_to_show = completed_games[:10]
    
    for i, game in enumerate(games_to_show):
        if games_y > 900:  # Не выходим за границы
            break
            
        # Информация об игре
        game_info = f"{t('tournament.image.game_label', language)}{i+1}"
        draw.text((games_x + 10, games_y), game_info, fill=games_color, font=small_font)
        
        # Игроки и счет
        if 'players' in game and 'score' in game:
            players = game['players']
            score = game['score']
            
            if len(players) >= 2:
                player1_name = players[0].get('name', t("tournament.image.player_1", language))
                player2_name = players[1].get('name', t("tournament.image.player_2", language))
                
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

async def build_and_render_tournament_image(tournament_data: dict, tournament_id: str, language: str = 'ru') -> tuple[bytes, str]:
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
                name=pdata.get('name', u.get('first_name', t("tournament.image.unknown_player", language))),
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
        # Добавляем номера посева к именам игроков, чтобы изменения были видны на сетке
        if seeding:
            seed_index = {pid: i + 1 for i, pid in enumerate(seeding)}
            players = [
                Player(
                    id=p.id,
                    name=(f"№{seed_index.get(p.id)} {p.name}" if seed_index.get(p.id) else p.name),
                    photo_url=getattr(p, 'photo_url', None),
                    initial=getattr(p, 'initial', None),
                )
                for p in players
            ]
        while len(players) < min_participants:
            players.append(Player(id=f"empty_{len(players)}", name=" ", photo_url=None, initial=None))

    # Загружаем и нормализуем завершенные игры этого турнира
    completed_games: list[dict] = []
    try:
        games = await storage.load_games()
        normalized: list[dict] = []
        for g in games:
            if g.get('tournament_id') != tournament_id:
                continue
            if g.get('type') not in (None, 'tournament'):
                continue
            # Извлекаем игроков (поддержка разных форматов)
            p = g.get('players') or {}
            team1_list: list[str] = []
            team2_list: list[str] = []
            if isinstance(p, dict):
                t1 = p.get('team1') or []
                t2 = p.get('team2') or []
                if t1:
                    team1_list = [str(t1[0])] if not isinstance(t1[0], dict) else [str(t1[0].get('id'))]
                if t2:
                    team2_list = [str(t2[0])] if not isinstance(t2[0], dict) else [str(t2[0].get('id'))]
            elif isinstance(p, list) and len(p) >= 2:
                a, b = p[0], p[1]
                team1_list = [str(a)] if not isinstance(a, dict) else [str(a.get('id'))]
                team2_list = [str(b)] if not isinstance(b, dict) else [str(b.get('id'))]

            norm_game = {
                'tournament_id': tournament_id,
                'score': g.get('score') or (', '.join(g.get('sets', []) or [])),
                'players': {
                    'team1': team1_list,
                    'team2': team2_list,
                },
                'winner_id': str(g.get('winner_id')) if g.get('winner_id') is not None else None,
                'media_filename': g.get('media_filename'),
                'date': g.get('date') or g.get('created_at'),
                'status': g.get('status') or 'completed',
            }
            normalized.append(norm_game)
        # Сортируем по дате по убыванию
        completed_games = sorted(normalized, key=lambda x: x.get('date') or '', reverse=True)
        logger.info(f"[BRACKET][HANDLER] Собрано игр для турнира {tournament_id}: {len(completed_games)}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке игр: {e}")

    # Если сетка скрыта — простая картинка
    if tournament_data.get('hide_bracket', False):
        tour_name = tournament_data.get('name') or t("tournament.no_name", language)
        placeholder = (
            t("tournament.image.bracket_hidden", language)
            + f"{tour_name}\n"
            + f"{t('tournament.image.participants_label', language)} {len(participants)}"
        )
        return create_simple_text_image_bytes(placeholder, tour_name), t("tournament.image.bracket_hidden_title", language)

    # Генерируем изображение сетки через утилиту
    try:
        if tournament_type == 'Круговая':
            # Собираем компактный список игроков для таблицы (добавляем фото профиля)
            table_players = [{"id": p.id, "name": p.name, "photo_path": getattr(p, 'photo_url', None)} for p in players]
            tour_name = tournament_data.get('name') or t("tournament.no_name", language)
            image_bytes = build_round_robin_table(table_players, completed_games, tour_name)
            return image_bytes, t("tournament.image.round_robin_table", language)
        else:
            return build_tournament_bracket_image_bytes(tournament_data, players, completed_games)
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        fallback = t("tournament.image.bracket_error", language)
        return create_simple_text_image_bytes(fallback, t("tournament.image.bracket_error_title", language)), ""

# Обработчик создания турнира (только для админов)
@router.callback_query(F.data == "admin_create_tournament")
async def create_tournament_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик создания турнира (только админы)"""
    language = await get_user_language_async(str(callback.from_user.id))
    if not await is_admin(callback.from_user.id):
        await callback.answer(t("tournament.no_admin_rights", language))
        return
    
    # Очищаем данные предыдущего создания
    global tournament_data
    tournament_data = {}
    
    # Начинаем с выбора вида спорта
    await state.set_state(CreateTournamentStates.SPORT)
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_1_sport", language),
        reply_markup=create_sport_keyboard(pref="tournament_sport:", exclude_sports=[
            "🍻По пиву", 
            "🍒Знакомства", 
            "☕️Бизнес-завтрак"
        ], language=language)
    )
    await callback.answer()

# Обработчик выбора вида спорта
@router.callback_query(F.data.startswith("tournament_sport:"))
async def select_sport(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора вида спорта"""
    sport = callback.data.split(":", 1)[1]
    tournament_data["sport"] = sport
    language = await get_user_language_async(str(callback.message.chat.id))
    
    await state.set_state(CreateTournamentStates.COUNTRY)
    
    builder = InlineKeyboardBuilder()
    for country in COUNTRIES:
        builder.button(text=get_country_translation(country, language), callback_data=f"tournament_country:{country}")
    builder.button(text=t("tournament.buttons.other_country", language), callback_data="tournament_country:Другое")
    builder.adjust(2)
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_2_country", language, sport=get_sport_translation(sport, language)),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора страны
@router.callback_query(F.data.startswith("tournament_country:"))
async def select_country(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора страны"""
    country = callback.data.split(":", 1)[1]
    tournament_data["country"] = country
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if country == "Другое":
        await state.set_state(CreateTournamentStates.COUNTRY_INPUT)
        await safe_edit_message(callback,
            t("tournament.create.title", language) + t("tournament.create.step_2_enter_country", language,
                sport=get_sport_translation(tournament_data['sport'], language),
                country=country),
            reply_markup=None
        )
    else:
        await state.set_state(CreateTournamentStates.CITY)
        cities = get_cities_for_country(country)
        builder = InlineKeyboardBuilder()
        for city in cities:
            text = t("tournament.buttons.other_city", language) if city == "Другое" else get_city_translation(city, language)
            builder.button(text=text, callback_data=f"tournament_city:{city}")
        builder.adjust(2)
        await safe_edit_message(callback,
            t("tournament.create.title", language) + t("tournament.create.step_3_city", language,
                sport=get_sport_translation(tournament_data['sport'], language),
                country=get_country_translation(country, language)),
            reply_markup=builder.as_markup()
        )
    
    await callback.answer()

# Обработчик ввода страны вручную
@router.message(CreateTournamentStates.COUNTRY_INPUT)
async def input_country(message: Message, state: FSMContext):
    """Обработчик ввода страны вручную"""
    country = message.text.strip()
    tournament_data["country"] = country
    language = await get_user_language_async(str(message.chat.id))
    
    await state.set_state(CreateTournamentStates.CITY)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("tournament.buttons.other_city", language), callback_data="tournament_city_input")
    
    await message.answer(
        t("tournament.create.title", language) + t("tournament.create.step_3_city_method", language,
            sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(country, language)),
        reply_markup=builder.as_markup()
    )

# Обработчик кнопки ввода города вручную
@router.callback_query(F.data == "tournament_city_input")
async def tournament_city_input(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки ввода города вручную"""
    await state.set_state(CreateTournamentStates.CITY_INPUT)
    language = await get_user_language_async(str(callback.message.chat.id))
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_3_enter_city", language,
            sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=""),
        reply_markup=None
    )
    await callback.answer()

# Обработчик выбора города
@router.callback_query(F.data.startswith("tournament_city:"))
async def select_city(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города"""
    city = callback.data.split(":", 1)[1]
    tournament_data["city"] = city
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if city == "Другое":
        await state.set_state(CreateTournamentStates.CITY_INPUT)
        await safe_edit_message(callback,
            t("tournament.create.title", language) + t("tournament.create.step_3_enter_city", language,
                sport=get_sport_translation(tournament_data['sport'], language),
                country=get_country_translation(tournament_data['country'], language),
                city=city),
            reply_markup=None
        )
    else:
        if city == "Москва":
            await state.set_state(CreateTournamentStates.DISTRICT)
            builder = InlineKeyboardBuilder()
            for district in DISTRICTS_MOSCOW:
                builder.button(text=get_district_translation(district, language), callback_data=f"tournament_district:{district}")
            builder.adjust(2)
            await safe_edit_message(callback,
                t("tournament.create.title", language) + t("tournament.create.step_4_district", language,
                    sport=get_sport_translation(tournament_data['sport'], language),
                    country=get_country_translation(tournament_data['country'], language),
                    city=get_city_translation(city, language)),
                reply_markup=builder.as_markup()
            )
        else:
            await state.set_state(CreateTournamentStates.TYPE)
            builder = InlineKeyboardBuilder()
            for t_type in TOURNAMENT_TYPES:
                builder.button(text=get_tournament_type_translation(t_type, language), callback_data=f"tournament_type:{t_type}")
            builder.adjust(1)
            await safe_edit_message(callback,
                t("tournament.create.title", language) + t("tournament.create.step_4_type", language,
                    sport=get_sport_translation(tournament_data['sport'], language),
                    country=get_country_translation(tournament_data['country'], language),
                    city=get_city_translation(city, language)),
                reply_markup=builder.as_markup()
            )
    
    await callback.answer()

# Обработчик ввода города вручную
@router.message(CreateTournamentStates.CITY_INPUT)
async def input_city(message: Message, state: FSMContext):
    """Обработчик ввода города вручную"""
    city = message.text.strip()
    tournament_data["city"] = city
    language = await get_user_language_async(str(message.chat.id))
    
    if city == "Москва":
        await state.set_state(CreateTournamentStates.DISTRICT)
        builder = InlineKeyboardBuilder()
        for district in DISTRICTS_MOSCOW:
            builder.button(text=get_district_translation(district, language), callback_data=f"tournament_district:{district}")
        builder.adjust(2)
        await message.answer(
            t("tournament.create.title", language) + t("tournament.create.step_4_district", language,
                sport=get_sport_translation(tournament_data['sport'], language),
                country=get_country_translation(tournament_data['country'], language),
                city=get_city_translation(city, language)) + "\n\n" + t("tournament.create.select_district", language),
            reply_markup=builder.as_markup()
        )
    else:
        await state.set_state(CreateTournamentStates.TYPE)
        builder = InlineKeyboardBuilder()
        for t_type in TOURNAMENT_TYPES:
            builder.button(text=get_tournament_type_translation(t_type, language), callback_data=f"tournament_type:{t_type}")
        builder.adjust(1)
        await message.answer(
            t("tournament.create.title", language) + t("tournament.create.step_4_type", language,
                sport=get_sport_translation(tournament_data['sport'], language),
                country=get_country_translation(tournament_data['country'], language),
                city=get_city_translation(city, language)) + "\n\n" + t("tournament.create.select_type", language),
            reply_markup=builder.as_markup()
        )

# Обработчик выбора района
@router.callback_query(F.data.startswith("tournament_district:"))
async def select_district(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора района"""
    district = callback.data.split(":", 1)[1]
    tournament_data["district"] = district
    language = await get_user_language_async(str(callback.message.chat.id))
    
    await state.set_state(CreateTournamentStates.TYPE)
    
    builder = InlineKeyboardBuilder()
    for t_type in TOURNAMENT_TYPES:
        builder.button(text=get_tournament_type_translation(t_type, language), callback_data=f"tournament_type:{t_type}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_5_type", language,
            sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language)),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора типа турнира
@router.callback_query(F.data.startswith("tournament_type:"))
async def select_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа турнира"""
    t_type = callback.data.split(":", 1)[1]
    tournament_data["type"] = t_type
    language = await get_user_language_async(str(callback.message.chat.id))
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    
    await state.set_state(CreateTournamentStates.GENDER)
    
    builder = InlineKeyboardBuilder()
    for gender in GENDERS:
        builder.button(text=gender, callback_data=f"tournament_gender:{gender}")
    builder.adjust(2)
    
    step = "5" if "district" not in tournament_data else "6"
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_gender", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(t_type, language)),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора пола
@router.callback_query(F.data.startswith("tournament_gender:"))
async def select_gender(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора пола участников"""
    gender = callback.data.split(":", 1)[1]
    tournament_data["gender"] = gender
    language = await get_user_language_async(str(callback.message.chat.id))
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    
    await state.set_state(CreateTournamentStates.CATEGORY)
    
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        builder.button(text=category, callback_data=f"tournament_category:{category}")
    builder.adjust(2)
    
    step = "6" if "district" not in tournament_data else "7"
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_category", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=gender),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора категории
@router.callback_query(F.data.startswith("tournament_category:"))
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора категории"""
    category = callback.data.split(":", 1)[1]
    tournament_data["category"] = category
    language = await get_user_language_async(str(callback.message.chat.id))
    tournament_data["level"] = CATEGORY_LEVELS.get(category, t("tournament.not_specified", language))
    
    await state.set_state(CreateTournamentStates.AGE_GROUP)
    
    builder = InlineKeyboardBuilder()
    for age_group in AGE_GROUPS:
        builder.button(text=age_group, callback_data=f"tournament_age_group:{age_group}")
    builder.adjust(2)
    
    step = "7" if "district" not in tournament_data else "8"
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_age", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=tournament_data['gender'], category=category),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора возрастной группы
@router.callback_query(F.data.startswith("tournament_age_group:"))
async def select_age_group(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора возрастной группы"""
    age_group = callback.data.split(":", 1)[1]
    tournament_data["age_group"] = age_group
    language = await get_user_language_async(str(callback.message.chat.id))
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    
    await state.set_state(CreateTournamentStates.DURATION)
    
    builder = InlineKeyboardBuilder()
    for duration in DURATIONS:
        builder.button(text=duration, callback_data=f"tournament_duration:{duration}")
    builder.adjust(1)
    
    step = "8" if "district" not in tournament_data else "9"
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_duration", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=tournament_data['gender'],
            category=tournament_data['category'], age_group=age_group),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора продолжительности
@router.callback_query(F.data.startswith("tournament_duration:"))
async def select_duration(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора продолжительности"""
    duration = callback.data.split(":", 1)[1]
    tournament_data["duration"] = duration
    language = await get_user_language_async(str(callback.message.chat.id))
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    
    await state.set_state(CreateTournamentStates.PARTICIPANTS_COUNT)
    
    step = "9" if "district" not in tournament_data else "10"
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_participants", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=tournament_data['gender'],
            category=tournament_data['category'], age_group=tournament_data['age_group'], duration=duration),
        reply_markup=None
    )
    await callback.answer()

# Обработчик ввода количества участников
@router.message(CreateTournamentStates.PARTICIPANTS_COUNT)
async def input_participants_count(message: Message, state: FSMContext):
    """Обработчик ввода количества участников"""
    try:
        count = int(message.text.strip())
        language = await get_user_language_async(str(message.chat.id))
        if count <= 0:
            await message.answer(t("tournament.participants_count_error", language))
            return
        
        tournament_data["participants_count"] = count
        
        await state.set_state(CreateTournamentStates.SHOW_IN_LIST)
        
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            builder.button(text=option, callback_data=f"tournament_show_in_list:{option}")
        builder.adjust(2)
        
        step = "10" if "district" not in tournament_data else "11"
        
        language = await get_user_language_async(str(message.chat.id))
        district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
        await message.answer(
            t("tournament.create.title", language) + t("tournament.create.step_show_list", language,
                step=step, sport=get_sport_translation(tournament_data['sport'], language),
                country=get_country_translation(tournament_data['country'], language),
                city=get_city_translation(tournament_data['city'], language),
                district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=tournament_data['gender'],
                category=tournament_data['category'], age_group=tournament_data['age_group'],
                duration=tournament_data['duration'], participants_count=count) + "\n\n" + t("tournament.create.show_list_question", language),
            reply_markup=builder.as_markup()
        )
    except ValueError:
        language = await get_user_language_async(str(message.chat.id))
        await message.answer(t("tournament.invalid_number", language))

# Обработчик выбора отображения в списке
@router.callback_query(F.data.startswith("tournament_show_in_list:"))
async def select_show_in_list(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора отображения в списке"""
    show_in_list = callback.data.split(":", 1)[1]
    tournament_data["show_in_list"] = show_in_list == "Да"
    language = await get_user_language_async(str(callback.message.chat.id))
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    show_in_list_val = t("tournament.create.yes", language) if tournament_data['show_in_list'] else t("tournament.create.no", language)
    
    await state.set_state(CreateTournamentStates.HIDE_BRACKET)
    
    builder = InlineKeyboardBuilder()
    for option in YES_NO_OPTIONS:
        builder.button(text=option, callback_data=f"tournament_hide_bracket:{option}")
    builder.adjust(2)
    
    step = "11" if "district" not in tournament_data else "12"
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_hide_bracket", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=tournament_data['gender'],
            category=tournament_data['category'], age_group=tournament_data['age_group'],
            duration=tournament_data['duration'], participants_count=tournament_data['participants_count'],
            show_in_list=show_in_list_val),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора скрытия сетки
@router.callback_query(F.data.startswith("tournament_hide_bracket:"))
async def select_hide_bracket(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора скрытия турнирной сетки"""
    hide_bracket = callback.data.split(":", 1)[1]
    tournament_data["hide_bracket"] = hide_bracket == "Да"
    language = await get_user_language_async(str(callback.message.chat.id))
    district_line = t("tournament.create.district_label", language, district=get_district_translation(tournament_data['district'], language)) if "district" in tournament_data else ""
    show_in_list = t("tournament.create.yes", language) if tournament_data['show_in_list'] else t("tournament.create.no", language)
    hide_bracket_val = t("tournament.create.yes", language) if tournament_data['hide_bracket'] else t("tournament.create.no", language)
    
    await state.set_state(CreateTournamentStates.COMMENT)
    
    step = "12" if "district" not in tournament_data else "13"
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("tournament.buttons.skip", language), callback_data="skip_comment")
    
    await safe_edit_message(callback,
        t("tournament.create.title", language) + t("tournament.create.step_comment", language,
            step=step, sport=get_sport_translation(tournament_data['sport'], language),
            country=get_country_translation(tournament_data['country'], language),
            city=get_city_translation(tournament_data['city'], language),
            district_line=district_line, t_type=get_tournament_type_translation(tournament_data['type'], language), gender=tournament_data['gender'],
            category=tournament_data['category'], age_group=tournament_data['age_group'],
            duration=tournament_data['duration'], participants_count=tournament_data['participants_count'],
            show_in_list=show_in_list, hide_bracket=hide_bracket_val),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик кнопки пропуска комментария
@router.callback_query(F.data == "skip_comment")
async def skip_comment(callback: CallbackQuery, state: FSMContext):
    """Обработчик пропуска комментария"""
    tournament_data["comment"] = ""
    language = await get_user_language_async(str(callback.message.chat.id))
    
    await state.set_state(CreateTournamentStates.CONFIRM)
    
    location = f"{get_city_translation(tournament_data['city'], language)}"
    if "district" in tournament_data:
        location += f" ({get_district_translation(tournament_data['district'], language)})"
    location += f", {get_country_translation(tournament_data['country'], language)}"
    
    show_in_list = t("tournament.create.yes", language) if tournament_data['show_in_list'] else t("tournament.create.no", language)
    hide_bracket_val = t("tournament.create.yes", language) if tournament_data['hide_bracket'] else t("tournament.create.no", language)
    
    text = t("tournament.create.title", language) + t("tournament.create.confirm_header", language)
    text += t("tournament.create.confirm_sport", language, sport=get_sport_translation(tournament_data['sport'], language))
    text += t("tournament.create.confirm_place", language, location=location)
    text += t("tournament.create.confirm_type", language, t_type=get_tournament_type_translation(tournament_data['type'], language))
    text += t("tournament.create.confirm_gender", language, gender=tournament_data['gender'])
    text += t("tournament.create.confirm_category", language, category=tournament_data['category'])
    text += t("tournament.create.confirm_level", language, level=tournament_data.get('level', t("tournament.not_specified", language)))
    text += t("tournament.create.confirm_age", language, age_group=tournament_data['age_group'])
    text += t("tournament.create.confirm_duration", language, duration=tournament_data['duration'])
    text += t("tournament.create.confirm_participants", language, participants_count=tournament_data['participants_count'])
    text += t("tournament.create.confirm_show_list", language, show_in_list=show_in_list)
    text += t("tournament.create.confirm_hide_bracket", language, hide_bracket=hide_bracket_val)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("tournament.buttons.create_tournament", language), callback_data="confirm_tournament")
    builder.button(text=t("tournament.buttons.cancel", language), callback_data="cancel_tournament")
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
        language = await get_user_language_async(str(callback.message.chat.id))
        name = generate_tournament_name(tournament_data, tournament_number, language)
        
        # Формируем описание
        location = f"{tournament_data['city']}"
        if "district" in tournament_data:
            location += f" ({tournament_data['district']})"
        location += f", {remove_country_flag(tournament_data['country'])}"
        
        sport_display = get_sport_translation(tournament_data['sport'], language).lower()
        level_display = tournament_data.get('level') or t("tournament.not_specified", language)
        description = t("tournament.create.description_sport", language, sport=sport_display)
        description += t("tournament.create.description_place", language, location=location)
        description += t("tournament.create.description_type", language, type=get_tournament_type_translation(tournament_data['type'], language))
        description += t("tournament.create.description_gender", language, gender=tournament_data['gender'])
        description += t("tournament.create.description_category", language, category=tournament_data['category'])
        description += t("tournament.create.description_level", language, level=level_display)
        description += t("tournament.create.description_age", language, age_group=tournament_data['age_group'])
        description += t("tournament.create.description_duration", language, duration=tournament_data['duration'])
        description += t("tournament.create.description_participants", language, count=tournament_data['participants_count'])
        
        if tournament_data['comment']:
            description += t("tournament.create.description_label", language, comment=tournament_data['comment'])
        
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
            'level': tournament_data.get('level') or t("tournament.not_specified", language),
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
        
        language = await get_user_language_async(str(callback.message.chat.id))
        await safe_edit_message(callback,
            t("tournament.create.success_header", language)
            + t("tournament.create.success_name", language, name=name)
            + t("tournament.create.success_place", language, location=location)
            + t("tournament.create.success_participants", language, count=tournament_data['participants_count'])
            + t("tournament.added_ready", language)
        )
        
        # Очищаем состояние
        await state.clear()
        tournament_data = {}
        
    except Exception as e:
        logger.error(f"Ошибка при создании турнира: {e}")
        language = await get_user_language_async(str(callback.message.chat.id))
        await safe_edit_message(callback,
            t("tournament.create.error", language)
        )
    
    await callback.answer()

# Обработчик отмены создания турнира (из skip_comment)
@router.callback_query(F.data == "cancel_tournament")
async def cancel_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены создания турнира (из skip_comment)"""
    await state.clear()
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback,
        t("tournament.create.cancelled", language)
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
    location += f", {remove_country_flag(tournament_data['country'])}"
    
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
            loc += f", {remove_country_flag(payload['country'])}"
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
            language = await get_user_language_async(str(callback.message.chat.id))
            await safe_edit_message(callback,
                t("tournament.create.updated_success", language)
            )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка создания турнира: {e}")
        language = await get_user_language_async(str(callback.message.chat.id))
        await safe_edit_message(callback,
            t("tournament.create.error", language)
        )
        await callback.answer()

# Обработчик отмены создания турнира
@router.callback_query(F.data == "tournament_cancel_create")
async def cancel_create_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены создания турнира"""
    await state.clear()
    
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback,
        t("tournament.create.cancelled", language)
    )
    await callback.answer()

# Команда для просмотра турниров
@router.message(F.text.in_([t("menu.tournaments", "ru"), t("menu.tournaments", "en")]))
@router.message(Command("tournaments"))
async def tournaments_main(message: Message, state: FSMContext):
    """Главное меню турниров"""
    language = await get_user_language_async(str(message.chat.id))
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') in ['active', 'started'] and v.get('show_in_list', True)}
    
    text = t("tournament.menu.text", language, active_count=len(active_tournaments))
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("tournament.menu.view_list", language), callback_data="view_tournaments_start")
    builder.button(text=t("tournament.menu.my_tournaments", language), callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Начало просмотра турниров - выбор вида спорта
@router.callback_query(F.data == "view_tournaments_start")
async def view_tournaments_start(callback: CallbackQuery, state: FSMContext):
    """Начало просмотра турниров - выбор вида спорта (не зависит от наличия турниров)"""
    await state.set_state(ViewTournamentsStates.SELECT_SPORT)

    # Красивый выбор видов спорта, исключаем несоревновательные
    language = await get_user_language_async(str(callback.from_user.id))
    sport_kb = create_sport_keyboard(pref="view_tournament_sport:", exclude_sports=[
        "🍻По пиву",
        "🍒Знакомства",
        "☕️Бизнес-завтрак"
    ], language=language)

    await callback.message.delete()
    await callback.message.answer(
        t("tournament.browse.step1", language),
        reply_markup=sport_kb
    )
    await callback.answer()

# Обработчик выбора вида спорта для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_sport:"))
async def select_sport_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора вида спорта для просмотра турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
    sport = callback.data.split(":", 1)[1]

    await state.set_state(ViewTournamentsStates.SELECT_COUNTRY)
    await state.update_data(selected_sport=sport)

    # Порядок стран как в конфиге (Россия первой)
    ordered_countries = ["🇷🇺 Россия"] + [c for c in cities_data.keys() if c != "🇷🇺 Россия"]
    builder = InlineKeyboardBuilder()
    for country in ordered_countries:
        builder.button(text=get_country_translation(country, language), callback_data=f"view_tournament_country:{country}")
    # Кнопка ввода своей страны
    builder.button(text=t("tournament.buttons.other_country", language), callback_data="view_tournament_country:Другое")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        t("tournament.browse.step2", language, sport=get_sport_translation(sport, language)),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора страны для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_country:"))
async def select_country_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора страны для просмотра турниров"""
    country = callback.data.split(":", 1)[1]
    language = await get_user_language_async(str(callback.message.chat.id))
    data = await state.get_data()
    sport = data.get('selected_sport')

    if country == "Другое":
        # Получаем другие страны из турниров
        other_countries = await get_other_countries_from_tournaments(sport)
        
        # Устанавливаем состояние для ввода страны
        await state.set_state(ViewTournamentsStates.COUNTRY_INPUT)
        
        builder = InlineKeyboardBuilder()
        # Показываем страны из турниров (макс 5)
        for other_country in other_countries:
            builder.button(text=get_country_translation(other_country, language), callback_data=f"view_tournament_country:{other_country}")
        builder.adjust(2)
        
        # Кнопка "Назад" внизу
        builder.row(InlineKeyboardButton(text=t("tournament.buttons.back", language), callback_data="view_tournaments_start"))
        
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        text = t("tournament.browse.step2_enter", language, sport=get_sport_translation(sport, language))
        if other_countries:
            text += t("tournament.browse.choose_country_prompt", language)
        else:
            text += t("tournament.browse.type_country_prompt", language)
        
        await callback.message.answer(
            text,
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    # Выбор города без зависимости от существующих турниров
    await state.set_state(ViewTournamentsStates.CITY_INPUT)
    await state.update_data(selected_country=country)

    # Получаем другие города из турниров
    other_cities = await get_other_cities_from_tournaments(sport, country)
    
    builder = InlineKeyboardBuilder()
    # Порядок городов как в конфиге
    for city in cities_data.get(country, []):
        builder.button(text=get_city_translation(city, language), callback_data=f"view_tournament_city:{city}")
    # Добавляем города из турниров (если есть и не дублируются)
    known_cities = set(cities_data.get(country, []))
    for other_city in other_cities:
        if other_city not in known_cities:
            builder.button(text=f"📍 {get_city_translation(other_city, language)}", callback_data=f"view_tournament_city:{other_city}")
    builder.adjust(2)
    
    # Кнопка "Назад" внизу
    builder.row(InlineKeyboardButton(text=t("tournament.buttons.back", language), callback_data="view_tournaments_start"))

    await callback.message.delete()
    
    text = t("tournament.browse.step3_city_full", language, sport=get_sport_translation(sport, language), country=get_country_translation(country, language))
    
    await callback.message.answer(
        text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.message(ViewTournamentsStates.COUNTRY_INPUT)
async def view_country_input(message: Message, state: FSMContext):
    """Ввод страны вручную в просмотре турниров"""
    country = (message.text or "").strip()
    language = await get_user_language_async(str(message.chat.id))
    data = await state.get_data()
    sport = data.get('selected_sport')
    await state.set_state(ViewTournamentsStates.CITY_INPUT)
    await state.update_data(selected_country=country)

    # Получаем другие города из турниров
    other_cities = await get_other_cities_from_tournaments(sport, country)

    builder = InlineKeyboardBuilder()
    # Если страна известна в конфиге, показываем города
    cities = cities_data.get(country, [])
    if cities:
        for city in cities:
            builder.button(text=get_city_translation(city, language), callback_data=f"view_tournament_city:{city}")
    # Добавляем города из турниров (если есть и не дублируются)
    known_cities = set(cities)
    for other_city in other_cities:
        if other_city not in known_cities:
            builder.button(text=f"📍 {get_city_translation(other_city, language)}", callback_data=f"view_tournament_city:{other_city}")
    builder.adjust(2)
    
    # Кнопка "Назад" внизу
    builder.row(InlineKeyboardButton(text=t("tournament.buttons.back", language), callback_data="view_tournaments_start"))

    text = t("tournament.browse.step3_city_full", language, sport=get_sport_translation(sport, language), country=get_country_translation(country, language))

    await message.answer(
        text,
        reply_markup=builder.as_markup()
    )

# Обработчик выбора города для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_city:"))
async def select_city_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города для просмотра турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
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
            builder.button(text=get_district_translation(district, language), callback_data=f"view_tournament_district:{district}")
        builder.adjust(2)

        await callback.message.delete()
        await callback.message.answer(
            t("tournament.browse.step4_district", language,
              sport=get_sport_translation(sport, language),
              country=get_country_translation(country, language),
              city=get_city_translation(city, language)),
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
        emoji = "👤 " if "👤" in label else "👥 "
        translated_text = get_gender_translation(value, language)
        button_text = emoji + translated_text
        builder.button(text=button_text, callback_data=f"view_tournament_gender:{value}")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        t("tournament.browse.step4_gender", language,
          sport=get_sport_translation(sport, language),
          country=get_country_translation(country, language),
          city=get_city_translation(city, language)),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.message(ViewTournamentsStates.CITY_INPUT)
async def view_city_input(message: Message, state: FSMContext):
    """Ввод города вручную в просмотре турниров"""
    language = await get_user_language_async(str(message.chat.id))
    city = (message.text or "").strip()
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    await state.update_data(selected_city=city)
    if city == "Москва":
        await state.set_state(ViewTournamentsStates.SELECT_DISTRICT)
        builder = InlineKeyboardBuilder()
        for district in DISTRICTS_MOSCOW:
            builder.button(text=get_district_translation(district, language), callback_data=f"view_tournament_district:{district}")
        builder.adjust(2)
        await message.answer(
            t("tournament.browse.step4_district", language,
              sport=get_sport_translation(sport, language),
              country=get_country_translation(country, language),
              city=get_city_translation(city, language)),
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
        emoji = "👤 " if "👤" in label else "👥 "
        translated_text = get_gender_translation(value, language)
        button_text = emoji + translated_text
        builder.button(text=button_text, callback_data=f"view_tournament_gender:{value}")
    builder.adjust(2)
    await message.answer(
        t("tournament.browse.step4_gender", language,
          sport=get_sport_translation(sport, language),
          country=get_country_translation(country, language),
          city=get_city_translation(city, language)),
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("view_tournament_district:"))
async def view_select_district(callback: CallbackQuery, state: FSMContext):
    """Выбор района Москвы для просмотра турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
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
        emoji = "👤 " if "👤" in label else "👥 "
        translated_text = get_gender_translation(value, language)
        button_text = emoji + translated_text
        builder.button(text=button_text, callback_data=f"view_tournament_gender:{value}")
    builder.adjust(2)

    await callback.message.delete()
    await callback.message.answer(
        t("tournament.browse.step5_gender", language,
          sport=get_sport_translation(sport, language),
          country=get_country_translation(country, language),
          city=get_city_translation(city, language),
          district=get_district_translation(district, language)),
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
    await _continue_view_without_type(callback, state)
    await callback.answer()
    return

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
        from datetime import datetime
        if birth:
            try:
                dt = datetime.strptime(birth, "%d.%m.%Y")
                today = datetime.now()
                age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
            except ValueError:
                try:
                    dt = datetime.strptime(birth, "%d.%m")
                    today = datetime.now()
                    age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
                except ValueError:
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
    """Совместимость: игнорируем тип и продолжаем без фильтра по типу"""
    await _continue_view_without_type(callback, state)
    await callback.answer()

async def _continue_view_without_type(callback: CallbackQuery, state: FSMContext):
    """Продолжает просмотр турниров без фильтрации по типу турнира."""
    language = await get_user_language_async(str(callback.message.chat.id))
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

    # Фильтруем по всем параметрам кроме типа турнира
    def _district_match(t: dict) -> bool:
        if city == "Москва" and selected_district:
            return (t.get('district') or '') == selected_district
        return True
    filtered = {k: v for k, v in active_tournaments.items() if (
        v.get('sport') == sport and v.get('country') == country and v.get('city') == city and
        _district_match(v) and
        v.get('gender') == gender and
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
            'type': 'Круговая',
            'gender': gender,
            'category': category,
            'level': level_range,
            'age_group': age_group,
            'duration': duration,
            'participants_count': MIN_PARTICIPANTS.get('Круговая', 4),
            'show_in_list': True,
            'hide_bracket': False,
            'comment': '',
        }

        # Сохраняем предложение в состоянии
        await state.update_data(proposed_tournament=base)

        # Подготовим красивое превью
        name = generate_tournament_name(base, len(tournaments) + 1, language)
        location = f"{base['city']}" + (f" ({base['district']})" if base.get('district') else "") + f", {remove_country_flag(base['country'])}"
        text = (
            t("tournament.proposed_preview_title", language, name=name)
            + t("tournament.proposed_preview_place", language, location=location)
            + t("tournament.proposed_preview_type", language, type=get_tournament_type_translation(base['type'], language))
            + t("tournament.proposed_preview_format", language, gender=get_gender_translation(base['gender'], language))
            + t("tournament.proposed_preview_category", language, category=get_category_translation(base['category'], language))
            + t("tournament.proposed_preview_age", language, age_group=get_age_group_translation(base['age_group'], language))
            + t("tournament.proposed_preview_duration", language, duration=get_duration_translation(base['duration'], language))
            + t("tournament.proposed_preview_participants", language, count=base['participants_count'])
            + t("tournament.proposed_preview_footer", language)
        )

        builder = InlineKeyboardBuilder()
        builder.button(text=t("tournament.buttons.participate", language), callback_data="apply_proposed_tournament")
        builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
        builder.adjust(1)

        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    # Показать список/первый турнир, если уже есть подходящие
    await show_tournaments_list(callback, filtered, sport, country, city)

async def _continue_view_with_type(callback: CallbackQuery, state: FSMContext, tournament_type: str):
    """Продолжает просмотр турниров с указанным типом (используется и для админа, и для пользователя)."""
    language = await get_user_language_async(str(callback.message.chat.id))
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
        v.get('gender') == gender and
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
        name = generate_tournament_name(base, len(tournaments) + 1, language)
        location = f"{base['city']}" + (f" ({base['district']})" if base.get('district') else "") + f", {remove_country_flag(base['country'])}"
        text = (
            t("tournament.proposed_preview_title", language, name=name)
            + t("tournament.proposed_preview_place", language, location=location)
            + t("tournament.proposed_preview_type", language, type=get_tournament_type_translation(base['type'], language))
            + t("tournament.proposed_preview_format", language, gender=get_gender_translation(base['gender'], language))
            + t("tournament.proposed_preview_category", language, category=get_category_translation(base['category'], language))
            + t("tournament.proposed_preview_age", language, age_group=get_age_group_translation(base['age_group'], language))
            + t("tournament.proposed_preview_duration", language, duration=get_duration_translation(base['duration'], language))
            + t("tournament.proposed_preview_participants", language, count=base['participants_count'])
            + t("tournament.proposed_preview_footer", language)
        )

        builder = InlineKeyboardBuilder()
        builder.button(text=t("tournament.buttons.participate", language), callback_data="apply_proposed_tournament")
        # Меняем текст кнопки "Назад" в зависимости от роли пользователя
        try:
            is_admin_user = await is_admin(callback.from_user.id)
        except Exception:
            is_admin_user = False
        builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
        builder.adjust(1)

        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    # Показать список/первый турнир, если уже есть подходящие
    await show_tournaments_list(callback, filtered, sport, country, city)

# Функция для показа списка турниров
async def show_tournaments_list(callback: CallbackQuery, tournaments: dict, sport: str, country: str, city: str):
    """Показывает список турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not tournaments:
        await callback.message.delete()
        await callback.message.answer(t("tournament.no_tournaments_found", language,
                                       sport=sport,
                                       city=city,
                                       country=remove_country_flag(country)))
        return
    
    # Преобразуем в список для пагинации
    tournament_list = list(tournaments.items())
    total_tournaments = len(tournament_list)
    
    sport_display = get_sport_translation(sport, language)
    country_display = remove_country_flag(country)
    city_display = get_city_translation(city, language) if city else t("tournament.not_specified", language)
    text = t("tournament.browse.tournaments_by_sport", language, sport=sport_display)
    text += t("tournament.browse.place_header", language, city=city_display, country=country_display)
    text += t("tournament.browse.found_count", language, count=total_tournaments)
    
    # Показываем первый турнир
    tournament_id, tournament_data = tournament_list[0]
    
    # Компактная информация о турнире
    loc_raw = tournament_data.get('city') or ''
    location = get_city_translation(loc_raw, language) if loc_raw else t("tournament.not_specified", language)
    if tournament_data.get('district'):
        location += f" ({get_district_translation(tournament_data['district'], language)})"
    country_raw = tournament_data.get('country') or ''
    if country_raw:
        country_display = get_country_translation(country_raw, language)
        location += f", {remove_country_flag(country_display)}"
    
    type_display = get_tournament_type_translation(tournament_data.get('type') or '', language) if tournament_data.get('type') else t("tournament.not_specified", language)
    name_display = tournament_data.get('name') or t("tournament.no_name", language)
    category_display = get_category_translation(tournament_data.get('category'), language) if tournament_data.get('category') else t("tournament.not_specified", language)
    gender_display = get_tournament_gender_display(
        tournament_data.get("gender"),
        language,
        tournament_name=tournament_data.get("name"),
        tournament_comment=tournament_data.get("comment"),
    )
    text += f"🏆 {name_display}\n"
    text += t("tournament.browse.card_place_type", language, location=location, type=type_display)
    text += t("tournament.browse.card_participants", language, current=len(tournament_data.get('participants', {})), total=tournament_data.get('participants_count', '?'))
    text += t("tournament.browse.card_format_category", language, format=gender_display, category=category_display)
    
    if tournament_data.get('comment'):
        comment = tournament_data['comment']
        if len(comment) > 100:
            comment = comment[:100] + "..."
        text += f"💬 {comment}\n"
    
    # Проверяем, зарегистрирован ли пользователь
    user_id = callback.from_user.id
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += t("tournament.browse.you_registered", language)
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации (если турниров больше одного) - в одну строку
    if total_tournaments > 1:
        builder.row(
            InlineKeyboardButton(text="⬅️", callback_data=f"view_tournament_prev:0"),
            InlineKeyboardButton(text="➡️", callback_data=f"view_tournament_next:0")
        )
    
    # Кнопка посева для админа — только если турнир ещё не запущен
    if await is_admin(user_id) and tournament_data.get('status') != 'started':
        builder.button(text=t("tournament.buttons.seeding", language), callback_data=f"tournament_seeding_menu:{tournament_id}")
    
    # Кнопка "Участвовать" только если не зарегистрирован, турнир не запущен и не достигнут лимит участников
    tournament_status = tournament_data.get('status', 'active')
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(tournament_data.get('participants', {}))
    if not is_registered and tournament_status == 'active' and (not max_participants or current_count < max_participants):
        builder.button(text=t("tournament.buttons.participate", language), callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка оплаты участия, если есть взнос и пользователь зарегистрирован, но не оплатил
    fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if fee > 0 and is_registered and not paid:
        builder.button(text=t("tournament.buttons.pay_participate_fee", language, fee=fee), callback_data=f"tournament_pay:{tournament_id}")
    
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    builder.adjust(1)
    
    # Создаем турнирную сетку (вынесено в утилиту)
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id, language)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    # Если админ — добавим статусы оплат
    try:
        is_admin_user = await is_admin(callback.from_user.id)
    except Exception:
        is_admin_user = False
    final_caption = text
    if is_admin_user:
        payments_block = _build_payments_status_text(tournament_data, language)
        if payments_block:
            final_caption = text + t("tournament.browse.payments_header", language) + payments_block

    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(final_caption),
        reply_markup=builder.as_markup()
    )

# Обработчики пагинации для новой системы просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_prev:"))
async def view_tournament_prev(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Предыдущий' в просмотре турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
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
        v.get('gender') == gender and
        v.get('category') == category and v.get('age_group') == age_group and v.get('duration', duration) == duration and
        _is_level_match(user_level_text, v.get('level'))
    )}
    
    if not filtered_tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_tournaments_to_display", language))
        return
    
    city_tournaments = filtered_tournaments
    
    # Вычисляем предыдущую страницу
    tournament_list = list(city_tournaments.items())
    total_tournaments = len(tournament_list)
    
    if total_tournaments <= 1:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.first_tournament", language))
        return
    
    prev_page = (page - 1) % total_tournaments
    if prev_page < 0:
        prev_page = total_tournaments - 1
    
    # Показываем предыдущий турнир
    tournament_id, tournament_data = tournament_list[prev_page]
    
    # Компактная информация о турнире
    sport_display = get_sport_translation(sport, language)
    city_display = get_city_translation(city, language) if city else t("tournament.not_specified", language)
    loc_raw = tournament_data.get('city') or ''
    location = get_city_translation(loc_raw, language) if loc_raw else t("tournament.not_specified", language)
    if tournament_data.get('district'):
        location += f" ({get_district_translation(tournament_data['district'], language)})"
    country_raw = tournament_data.get('country') or ''
    if country_raw:
        country_display = get_country_translation(country_raw, language)
        location += f", {remove_country_flag(country_display)}"
    
    type_display = get_tournament_type_translation(tournament_data.get('type') or '', language) if tournament_data.get('type') else t("tournament.not_specified", language)
    name_display = tournament_data.get('name') or t("tournament.no_name", language)
    category_display = get_category_translation(tournament_data.get('category'), language) if tournament_data.get('category') else t("tournament.not_specified", language)
    gender_display = get_tournament_gender_display(
        tournament_data.get("gender"),
        language,
        tournament_name=tournament_data.get("name"),
        tournament_comment=tournament_data.get("comment"),
    )
    text = t("tournament.browse.tournaments_by_sport", language, sport=sport_display)
    text += t("tournament.browse.place_header", language, city=city_display, country=remove_country_flag(get_country_translation(country, language)))
    text += t("tournament.browse.found_count", language, count=total_tournaments)
    text += f"🏆 {name_display}\n"
    text += t("tournament.browse.card_place_type", language, location=location, type=type_display)
    text += t("tournament.browse.card_participants", language, current=len(tournament_data.get('participants', {})), total=tournament_data.get('participants_count', '?'))
    text += t("tournament.browse.card_format_category", language, format=gender_display, category=category_display)
    
    if tournament_data.get('comment'):
        comment = tournament_data['comment']
        if len(comment) > 100:
            comment = comment[:100] + "..."
        text += f"💬 {comment}\n"
    
    user_id = callback.from_user.id
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += t("tournament.browse.you_registered", language)
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации в одну строку
    if total_tournaments > 1:
        builder.row(
            InlineKeyboardButton(text="⬅️", callback_data=f"view_tournament_prev:{prev_page}"),
            InlineKeyboardButton(text="➡️", callback_data=f"view_tournament_next:{prev_page}")
        )
    
    # Кнопка "Участвовать" только если не зарегистрирован, турнир не запущен и не достигнут лимит участников
    tournament_status = tournament_data.get('status', 'active')
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(tournament_data.get('participants', {}))
    if not is_registered and tournament_status == 'active' and (not max_participants or current_count < max_participants):
        builder.button(text=t("tournament.buttons.participate", language), callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка оплаты участия
    fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if fee > 0 and is_registered and not paid:
        builder.button(text=t("tournament.buttons.pay_participate_fee", language, fee=fee), callback_data=f"tournament_pay:{tournament_id}")
    
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
    
    builder.adjust(1)
    
    # Создаем турнирную сетку (вынесено в утилиту)
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id, language)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    # Если админ — добавим статусы оплат
    try:
        is_admin_user = await is_admin(callback.from_user.id)
    except Exception:
        is_admin_user = False
    final_caption = text
    if is_admin_user:
        payments_block = _build_payments_status_text(tournament_data, language)
        if payments_block:
            final_caption = text + t("tournament.browse.payments_header", language) + payments_block

    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(final_caption),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("view_tournament_next:"))
async def view_tournament_next(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Следующий' в просмотре турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
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
        v.get('gender') == gender and
        v.get('category') == category and v.get('age_group') == age_group and v.get('duration', duration) == duration and
        _is_level_match(user_level_text, v.get('level'))
    )}
    
    if not filtered_tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_tournaments_to_display", language))
        return
    
    city_tournaments = filtered_tournaments
    
    # Вычисляем следующую страницу
    tournament_list = list(city_tournaments.items())
    total_tournaments = len(tournament_list)
    
    if total_tournaments <= 1:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.last_tournament", language))
        return
    
    next_page = (page + 1) % total_tournaments
    
    # Показываем следующий турнир
    tournament_id, tournament_data = tournament_list[next_page]
    
    # Компактная информация о турнире
    sport_display = get_sport_translation(sport, language)
    city_display = get_city_translation(city, language) if city else t("tournament.not_specified", language)
    loc_raw = tournament_data.get('city') or ''
    location = get_city_translation(loc_raw, language) if loc_raw else t("tournament.not_specified", language)
    if tournament_data.get('district'):
        location += f" ({get_district_translation(tournament_data['district'], language)})"
    country_raw = tournament_data.get('country') or ''
    if country_raw:
        country_display = get_country_translation(country_raw, language)
        location += f", {remove_country_flag(country_display)}"
    
    type_display = get_tournament_type_translation(tournament_data.get('type') or '', language) if tournament_data.get('type') else t("tournament.not_specified", language)
    name_display = tournament_data.get('name') or t("tournament.no_name", language)
    category_display = get_category_translation(tournament_data.get('category'), language) if tournament_data.get('category') else t("tournament.not_specified", language)
    gender_display = get_tournament_gender_display(
        tournament_data.get("gender"),
        language,
        tournament_name=tournament_data.get("name"),
        tournament_comment=tournament_data.get("comment"),
    )
    text = t("tournament.browse.tournaments_by_sport", language, sport=sport_display)
    text += t("tournament.browse.place_header", language, city=city_display, country=remove_country_flag(get_country_translation(country, language)))
    text += t("tournament.browse.found_count", language, count=total_tournaments)
    text += f"🏆 {name_display}\n"
    text += t("tournament.browse.card_place_type", language, location=location, type=type_display)
    text += t("tournament.browse.card_participants", language, current=len(tournament_data.get('participants', {})), total=tournament_data.get('participants_count', '?'))
    text += t("tournament.browse.card_format_category", language, format=gender_display, category=category_display)
    
    if tournament_data.get('comment'):
        comment = tournament_data['comment']
        if len(comment) > 100:
            comment = comment[:100] + "..."
        text += f"💬 {comment}\n"
    
    user_id = callback.from_user.id
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += t("tournament.browse.you_registered", language)
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации в одну строку
    if total_tournaments > 1:
        builder.row(
            InlineKeyboardButton(text="⬅️", callback_data=f"view_tournament_prev:{next_page}"),
            InlineKeyboardButton(text="➡️", callback_data=f"view_tournament_next:{next_page}")
        )
    
    # Кнопка "Участвовать" только если не зарегистрирован, турнир не запущен и не достигнут лимит участников
    tournament_status = tournament_data.get('status', 'active')
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(tournament_data.get('participants', {}))
    if not is_registered and tournament_status == 'active' and (not max_participants or current_count < max_participants):
        builder.button(text=t("tournament.buttons.participate", language), callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка оплаты участия
    fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if fee > 0 and is_registered and not paid:
        builder.button(text=t("tournament.buttons.pay_participate_fee", language, fee=fee), callback_data=f"tournament_pay:{tournament_id}")
    
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
    
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(text),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик кнопки "Участвовать"
@router.callback_query(F.data.startswith("apply_tournament:"))
async def apply_tournament_handler(callback: CallbackQuery):
    """Немедленное участие в турнире (без заявок)"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    language = await get_user_language_async(str(callback.from_user.id))
    
    if tournament_id not in tournaments:
        await callback.answer(t("tournament.tournament_not_found", language))
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Проверяем статус турнира
    if tournament_data.get('status') != 'active':
        await callback.answer(t("tournament.registration_closed", language), show_alert=True)
        return
    
    # Проверяем ограничение по количеству участников (если задано)
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(tournament_data.get('participants', {}))
    if max_participants and current_count >= max_participants:
        await callback.answer(t("tournament.tournament_full", language))
        return
    
    # Регистрируем пользователя сразу
    user_id = callback.from_user.id
    if str(user_id) in tournament_data.get('participants', {}):
        await callback.answer(t("tournament.already_registered", language))
        return
    
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    if not user_data:
        await callback.answer(t("tournament.not_registered", language))
        return
    
    # Проверяем соответствие уровня игрока уровню турнира
    user_level = str(user_data.get('player_level', ''))
    tournament_level = tournament_data.get('level', '')
    if not _is_level_match(user_level, tournament_level):
        await callback.answer(
            t("tournament.level_mismatch", language, user_level=user_level, tournament_level=tournament_level),
            show_alert=True
        )
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

    await maybe_begin_payment_collection(callback.message.bot, tournament_id)

    # Уведомление в канал об участнике
    try:
        await send_tournament_application_to_channel(callback.message.bot, tournament_id, tournament_data, str(user_id), user_data)
    except Exception:
        pass
    
    auto_started_text = ""
    
    # Готовим визуализацию сетки
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Проверяем статус оплаты
    entry_fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    is_paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку оплаты, если требуется
    if entry_fee > 0 and not is_paid:
        builder.button(text=t("tournament.buttons.pay_participate", language), callback_data=f"tournament_pay:{tournament_id}")
    
    builder.button(text=t("tournament.buttons.all_tournaments", language), callback_data="view_tournaments_start")
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
    builder.adjust(1)
    
    tour_name = tournament_data.get('name') or t("tournament.no_name", language)
    caption = (
        t("tournament.applied_success", language)
        + t("tournament.applied_tournament_line", language, name=tour_name)
        + t("tournament.applied_participants_line", language, current=len(tournament_data.get('participants', {})), total=tournament_data.get('participants_count', '—'))
        + auto_started_text
    )
    
    # Добавляем информацию об оплате
    if entry_fee > 0:
        if is_paid:
            caption += t("tournament.payment_paid_line", language, fee=entry_fee)
        else:
            caption += t("tournament.payment_required_line", language, fee=entry_fee)
    
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(caption),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "apply_proposed_tournament")
async def apply_proposed_tournament(callback: CallbackQuery, state: FSMContext):
    """Создает предложенный турнир и регистрирует пользователя"""
    language = await get_user_language_async(str(callback.from_user.id))
    data = await state.get_data()
    base = data.get('proposed_tournament')
    if not base:
        await callback.answer(t("tournament.tournament_offer_not_found", language))
        return

    tournaments = await storage.load_tournaments()

    # Создаем турнир
    from datetime import datetime
    name = generate_tournament_name(base, len(tournaments) + 1, language)
    tournament_id = f"tournament_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(tournaments)+1}"
    location = f"{base['city']}" + (f" ({base['district']})" if base.get('district') else "") + f", {remove_country_flag(base['country'])}"
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
        await callback.answer(t("tournament.not_registered", language))
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
    await maybe_begin_payment_collection(callback.message.bot, tournament_id)

    # Уведомление в канал об участнике
    try:
        await send_tournament_application_to_channel(callback.message.bot, tournament_id, tournament_data, str(user_id), user_data)
    except Exception:
        pass

    # Очистим предложение
    await state.update_data(proposed_tournament=None)

    # Старт выполняется администратором после подтверждения посева
    auto_started_text = ""

    # Визуализация сетки
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Проверяем статус оплаты
    entry_fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    is_paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'

    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку оплаты, если требуется
    if entry_fee > 0 and not is_paid:
        builder.button(text=t("tournament.buttons.pay_participate", language), callback_data=f"tournament_pay:{tournament_id}")
    
    builder.button(text=t("tournament.buttons.all_tournaments", language), callback_data="view_tournaments_start")
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
    builder.adjust(1)

    tour_name = tournament_data.get('name') or t("tournament.no_name", language)
    caption = (
        t("tournament.applied_success", language)
        + t("tournament.applied_tournament_line", language, name=tour_name)
        + t("tournament.applied_participants_line", language, current=len(tournament_data.get('participants', {})), total=tournament_data.get('participants_count', '—'))
        + auto_started_text
    )
    
    # Добавляем информацию об оплате
    if entry_fee > 0:
        if is_paid:
            caption += t("tournament.payment_paid_line", language, fee=entry_fee)
        else:
            caption += t("tournament.payment_required_line", language, fee=entry_fee)

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(caption),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Просмотр своих заявок с пагинацией
@router.callback_query(F.data.startswith("my_applications_list:"))
async def my_applications_list(callback: CallbackQuery):
    language = await get_user_language_async(str(callback.from_user.id))

    """Заявки отключены: показываем уведомление"""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("tournament.buttons.all_tournaments", language), callback_data="view_tournaments_start")
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
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
    language = await get_user_language_async(str(callback.from_user.id))
    
    if not tournament:
        await callback.answer(t("tournament.tournament_not_found", language))
        return
    user_id = callback.from_user.id
    if str(user_id) not in tournament.get('participants', {}):
        await callback.answer(t("tournament.not_registered_in_tournament", language))
        return
    fee = int(tournament.get('entry_fee', get_tournament_entry_fee()) or 0)
    if fee <= 0:
        await callback.answer(t("tournament.payment_not_required", language))
        return
    paid = tournament.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    if paid:
        await callback.answer(t("tournament.payment_already_paid", language))
        return
    await state.update_data(tournament_id=tournament_id, tournament_fee=fee)
    await callback.message.answer(
        t("tournament.payment_email_prompt", language),
        parse_mode='html'
    )
    await state.set_state(TournamentPaymentStates.WAITING_EMAIL)
    await callback.answer()

@router.message(TournamentPaymentStates.WAITING_EMAIL, F.text)
async def tournament_pay_get_email(message: Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    email = message.text.strip()
    if '@' not in email or '.' not in email:
        await message.answer(t("tournament.invalid_email", language))
        return
    data = await state.get_data()
    tournament_id = data['tournament_id']
    fee = data['tournament_fee']
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    
    try:
        payment_link, payment_id = await generate_tinkoff_payment_link(message.chat.id, fee, t("tournament.payment_description", language, tournament_id=tournament_id), email)
        await state.update_data(payment_id=payment_id, user_email=email)
        kb = InlineKeyboardBuilder()
        kb.button(text=t("tournament.buttons.to_payments", language), url=payment_link)
        kb.button(text=t("tournament.buttons.confirm_payment", language), callback_data=f"tournament_pay_confirm:{tournament_id}")
        kb.adjust(1)
        await message.answer(
            t("tournament.payment_link_message", language, payment_link=payment_link, email=email),
            reply_markup=kb.as_markup()
        )
        await state.set_state(TournamentPaymentStates.CONFIRM_PAYMENT)
    except Exception as e:
        await message.answer(t("tournament.payment_error_create", language, error=str(e)))
        await state.clear()

@router.callback_query(TournamentPaymentStates.CONFIRM_PAYMENT, F.data.startswith("tournament_pay_confirm:"))
async def tournament_pay_confirm(callback: CallbackQuery, state: FSMContext):
    language = await get_user_language_async(str(callback.message.chat.id))
    data = await state.get_data()
    payment_id = data.get('payment_id')
    tournament_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    try:
        payment = await check_tinkoff_payment_status(payment_id)
        if payment['status'] == "CONFIRMED":
            tournaments = await storage.load_tournaments()
            tournament = tournaments.get(tournament_id, {})
            payments = tournament.get('payments', {})
            payments[str(user_id)] = {
                'payment_id': payment_id,
                'status': 'succeeded',
                'amount': float(data['tournament_fee']),
                'paid_at': datetime.now().isoformat(),
                'email': data.get('user_email')
            }
            tournament['payments'] = payments
            tournaments[tournament_id] = tournament
            await storage.save_tournaments(tournaments)
            await maybe_clear_payment_window_if_resolved(tournament_id)

            profile = await storage.get_user(user_id) or {}
            tour_name = tournament.get('name') or t("tournament.no_name", language)
            await send_tournament_payment_notification_to_admin(
                user_id=user_id,
                profile=profile,
                payment_id=payment_id,
                user_email=data.get('user_email', ''),
                payment_amount=int(data['tournament_fee']),
                tournament_name=tour_name,
                tournament_id=tournament_id
            )

            # Показываем турнир с обновленной информацией
            entry_fee = int(tournament.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
            bracket_image, bracket_text = await build_and_render_tournament_image(tournament, tournament_id)
            
            builder = InlineKeyboardBuilder()
            builder.button(text=t("tournament.buttons.my_tournaments", language), callback_data="my_tournaments_list:0")
            builder.button(text=t("tournament.buttons.all_tournaments", language), callback_data="view_tournaments_start")
            builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
            builder.adjust(1)

            caption = (
                t("tournament.payment_confirmed_message", language)
                + t("tournament.payment_confirmed_tournament_line", language, name=tour_name)
                + t("tournament.payment_confirmed_paid_line", language, fee=entry_fee)
            )
            
            await callback.message.answer_photo(
                photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
                caption=truncate_caption(caption),
                reply_markup=builder.as_markup()
            )
        else:
            language = await get_user_language_async(str(callback.message.chat.id))
            await callback.message.answer(t("tournament.payment_not_completed", language))
    except Exception as e:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.message.answer(t("tournament.payment_check_error", language, error=str(e)))
    await state.clear()
    await callback.answer()

# Просмотр турнира из заявки
@router.callback_query(F.data.startswith("view_tournament:"))
async def view_tournament_from_application(callback: CallbackQuery):
    """Показывает турнир"""
    language = await get_user_language_async(str(callback.message.chat.id))
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer(t("tournament.tournament_not_found", language))
        return
    
    # Находим индекс турнира в списке активных турниров
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active' and v.get('show_in_list', True)}
    tournament_ids = list(active_tournaments.keys())
    
    if tournament_id not in tournament_ids:
        await callback.answer(t("tournament.tournament_not_active", language))
        return
    
    page = tournament_ids.index(tournament_id)
    
    # Переходим к просмотру турнира через новую систему
    tournament_data = tournaments[tournament_id]
    user_id = callback.from_user.id
    
    # Компактная информация о турнире
    loc_raw = tournament_data.get('city') or ''
    location = get_city_translation(loc_raw, language) if loc_raw else t("tournament.not_specified", language)
    if tournament_data.get('district'):
        location += f" ({get_district_translation(tournament_data['district'], language)})"
    country_raw = tournament_data.get('country') or ''
    if country_raw:
        country_display = get_country_translation(country_raw, language)
        location += f", {remove_country_flag(country_display)}"
    
    type_display = get_tournament_type_translation(tournament_data.get('type') or '', language) if tournament_data.get('type') else t("tournament.not_specified", language)
    name_display = tournament_data.get('name') or t("tournament.no_name", language)
    category_display = get_category_translation(tournament_data.get('category'), language) if tournament_data.get('category') else t("tournament.not_specified", language)
    gender_display = get_tournament_gender_display(
        tournament_data.get("gender"),
        language,
        tournament_name=tournament_data.get("name"),
        tournament_comment=tournament_data.get("comment"),
    )
    text = f"🏆 {name_display}\n"
    text += t("tournament.browse.card_place_type", language, location=location, type=type_display)
    text += t("tournament.browse.card_participants", language, current=len(tournament_data.get('participants', {})), total=tournament_data.get('participants_count', '?'))
    text += t("tournament.browse.card_format_category", language, format=gender_display, category=category_display)
    
    if tournament_data.get('comment'):
        comment = tournament_data['comment']
        # Ограничиваем длину комментария
        if len(comment) > 100:
            comment = comment[:100] + "..."
        text += f"💬 {comment}\n"
    
    is_registered = str(user_id) in tournament_data.get('participants', {})
    if is_registered:
        text += t("tournament.browse.you_registered", language)
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Участвовать" только если не зарегистрирован, турнир не запущен и не достигнут лимит участников
    tournament_status = tournament_data.get('status', 'active')
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(tournament_data.get('participants', {}))
    if not is_registered and tournament_status == 'active' and (not max_participants or current_count < max_participants):
        builder.button(text=t("tournament.buttons.participate", language), callback_data=f"apply_tournament:{tournament_id}")
    
    builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
    
    builder.adjust(1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(text),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Просмотр своих турниров с пагинацией
@router.callback_query(F.data.startswith("my_tournaments_list:"))
async def my_tournaments_list(callback: CallbackQuery):
    """Показывает турниры пользователя с пагинацией"""
    language = await get_user_language_async(str(callback.message.chat.id))
    page = int(callback.data.split(':')[1])
    user_id = callback.from_user.id
    tournaments = await storage.load_tournaments()
    
    # Получаем все турниры пользователя
    user_tournaments = []
    for tournament_id, tournament_data in tournaments.items():
        if str(user_id) in tournament_data.get('participants', {}):
            user_tournaments.append((tournament_id, tournament_data))
    
    if not user_tournaments:
        await safe_edit_message(callback, t("tournament.no_my_tournaments", language))
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
    
    # Проверяем статус оплаты
    entry_fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    is_paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
    
    # Компактный текст для текущего турнира
    tour_name = tournament_data.get('name') or t("tournament.no_name", language)
    city_display = tournament_data.get('city') or t("tournament.not_specified", language)
    type_display = get_tournament_type_translation(tournament_data.get('type') or '', language) if tournament_data.get('type') else t("tournament.not_specified", language)
    text = t("tournament.my_tournament_page_header", language, page=page + 1, total=total_pages)
    text += f"{tour_name}\n"
    text += t("tournament.my_tournament_place_type_line", language, city=city_display, type=type_display)
    text += t("tournament.my_tournament_participants_count", language, count=len(tournament_data.get('participants', {})))
    
    # Добавляем информацию об оплате
    if entry_fee > 0:
        if is_paid:
            text += t("tournament.payment_paid_line", language, fee=entry_fee)
        else:
            text += t("tournament.payment_required_line", language, fee=entry_fee)
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        # Если первая страница - только кнопка "вперед"
        if page == 0:
            builder.row(InlineKeyboardButton(text="➡️", callback_data=f"my_tournaments_list:{page+1}"))
        # Если последняя страница - только кнопка "назад"
        elif page == total_pages - 1:
            builder.row(InlineKeyboardButton(text="⬅️", callback_data=f"my_tournaments_list:{page-1}"))
        # Если середина - обе кнопки в одном ряду
        else:
            builder.row(
                InlineKeyboardButton(text="⬅️", callback_data=f"my_tournaments_list:{page-1}"),
                InlineKeyboardButton(text="➡️", callback_data=f"my_tournaments_list:{page+1}")
            )
    
    # Кнопка оплаты, если требуется
    if entry_fee > 0 and not is_paid:
        builder.row(InlineKeyboardButton(text=t("tournament.buttons.pay_participate", language), callback_data=f"tournament_pay:{tournament_id}"))
    
    # Остальные кнопки всегда в отдельном ряду
    builder.row(
        InlineKeyboardButton(text=t("tournament.buttons.all_tournaments", language), callback_data="view_tournaments_start"),
        InlineKeyboardButton(text=t("tournament.buttons.back_to_menu", language), callback_data="tournaments_main_menu")
    )
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    # Всегда отправляем изображение сетки
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=truncate_caption(text),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Команда просмотра заявок на турниры (только для админов)
@router.message(Command("view_tournament_applications"))
async def view_tournament_applications_command(message: Message, state: FSMContext):
    """Заявки отключены"""
    language = await get_user_language_async(str(message.from_user.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("tournament.no_admin_rights", language))
        return
    await message.answer(t("tournament.applications_disabled", language))

# Обработчик меню принятия заявки
@router.callback_query(F.data == "admin_accept_application_menu")
async def admin_accept_application_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора заявки для принятия"""
    if not await is_admin(callback.from_user.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
    
    # Проверяем соответствие уровня игрока уровню турнира
    user_level = str(user_data.get('player_level', ''))
    tournament_level = tournament_data.get('level', '')
    if not _is_level_match(user_level, tournament_level):
        await callback.answer(
            f"❌ Уровень пользователя ({user_level}) не соответствует уровню турнира ({tournament_level})",
            show_alert=True
        )
        # Отклоняем заявку
        applications[app_id]['status'] = 'rejected'
        applications[app_id]['rejected_at'] = datetime.now().isoformat()
        applications[app_id]['rejected_by'] = callback.from_user.id
        applications[app_id]['rejection_reason'] = 'Уровень не соответствует турниру'
        await storage.save_tournament_applications(applications)
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
    tournaments[tournament_id] = tournament_data
    await storage.save_tournaments(tournaments)
    await maybe_begin_payment_collection(callback.message.bot, tournament_id)
    
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(message.from_user.id))
        await message.answer(t("tournament.no_admin_rights", language))
        return
    
    tournaments = await storage.load_tournaments()
    
    language = await get_user_language_async(str(message.from_user.id))
    if not tournaments:
        await message.answer(t("tournament.no_tournaments_to_display", language))
        return

    builder = InlineKeyboardBuilder()
    for tournament_id, tdata in admin_sort_tournament_items(list(tournaments.items())):
        name = tdata.get('name', t("tournament.no_name", language))
        city_raw = tdata.get('city', t("tournament.not_specified", language))
        city_display = get_city_translation(city_raw, language) if isinstance(city_raw, str) else city_raw
        label = participants_count_label(tdata)
        builder.button(
            text=f"🏆 {name} ({city_display}) — 👥 {label}",
            callback_data=f"admin_view_participants:{tournament_id}",
        )

    builder.button(text=t("admin.back", language), callback_data="admin_back_to_main")
    builder.adjust(1)

    await message.answer(
        t("tournament.view_participants_title", language) + "\n\n" + t("tournament.view_participants_prompt", language),
        reply_markup=builder.as_markup()
    )

# Обработчик просмотра участников турнира (для админа)
@router.callback_query(F.data.startswith("admin_view_participants:"))
async def admin_view_tournament_participants(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра участников турнира для админа"""
    if not await is_admin(callback.from_user.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if tournament_id not in tournaments:
        await callback.answer(t("tournament.tournament_not_found", language))
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    # Короткая информация о турнире
    location = get_city_translation(tournament_data.get('city', t("tournament.not_specified", language)), language)
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    
    text = f"👥 Участники: {len(participants)}/{tournament_data.get('participants_count', '?')}\n"
    
    # Статус оплаты (если есть взнос)
    fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    if fee > 0:
        paid_count = sum(1 for uid in participants.keys() 
                        if tournament_data.get('payments', {}).get(uid, {}).get('status') == 'succeeded')
        text += f"💰 Оплатили: {paid_count}/{len(participants)}\n"
    
    text += f"\n📋 Список:\n"
    
    # Ограничиваем количество участников в caption (максимум 30)
    max_display = 30
    if participants:
        for i, (user_id, participant_data) in enumerate(list(participants.items())[:max_display], 1):
            name = participant_data.get('name', t("tournament.unknown", language))
            pay_status = tournament_data.get('payments', {}).get(user_id, {}).get('status')
            paid_mark = "✅" if pay_status == 'succeeded' else ("❌" if fee > 0 else "")
            
            text += f"{i}. {name} {paid_mark}\n"
        
        if len(participants) > max_display:
            text += f"\n... и еще {len(participants) - max_display}"
    else:
        text += "Участников пока нет"
    
    builder = InlineKeyboardBuilder()
    
    if participants:
        for user_id, participant_data in list(participants.items())[:max_display]:
            user_id_str = str(user_id)
            if not user_id_str.isdigit():
                continue
            pname = participant_data.get('name', t("tournament.unknown", language))
            builder.button(text=f"📞 Связаться: {pname}", url=f"tg://user?id={user_id_str}")
        builder.button(text="🗑️ Удалить участника", callback_data=f"admin_rm_part_menu:{tournament_id}")
    
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
        caption=truncate_caption(text),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


# Обработчик редактирования игры админом
@router.callback_query(F.data.startswith("admin_edit_game:"))
async def admin_edit_game(callback: CallbackQuery, state: FSMContext):
    """Обработчик редактирования игры админом"""
    if not await is_admin(callback.from_user.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(message.from_user.id))
        await message.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(message.from_user.id))
        await message.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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

# Вспомогательная функция для отображения турнира
async def _show_tournament_edit(callback: CallbackQuery, state: FSMContext, tournament_id: str):
    language = await get_user_language_async(str(callback.from_user.id))
    
    """Показывает экран редактирования турнира"""
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Короткая информация
    location = tournament_data.get('city', 'Не указан')
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    
    participants = tournament_data.get('participants', {})
    text = f"🏆 {tournament_data.get('name', 'Турнир')}\n"
    text += f"📍 {location} | {tournament_data.get('sport', 'Не указан')}\n"
    text += f"👥 {len(participants)}/{tournament_data.get('participants_count', '?')} участников"
    
    # Проверяем готовность турнира к запуску
    tournament_ready = False
    try:
        tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
        if tournament_ready and tournament_data.get('status') == 'active':
            text += "\n✅ Готов к запуску"
    except Exception:
        pass
    
    # Кнопки для быстрого редактирования
    builder = InlineKeyboardBuilder()
    builder.button(text="🏓 Спорт", callback_data="edit_field:sport")
    builder.button(text="📍 Место", callback_data="edit_field:city")
    builder.button(text="⚔️ Тип", callback_data="edit_field:type")
    builder.button(text="👥 Пол", callback_data="edit_field:gender")
    builder.button(text="🏆 Категория", callback_data="edit_field:category")
    builder.button(text="👶 Возраст", callback_data="edit_field:age_group")
    builder.button(text="👥 Кол-во", callback_data="edit_field:participants_count")
    builder.button(text="💬 Описание", callback_data="edit_field:comment")
    builder.button(text="⚙️ Ещё", callback_data="edit_tournament_more")
    builder.button(text="👥 Участники", callback_data=f"manage_participants:{tournament_id}")
    
    # Кнопка посева (жеребьевки) — показываем только до старта турнира
    if tournament_data.get('status') not in ['started', 'finished']:
        builder.button(text=t("tournament.buttons.seeding", language), callback_data=f"tournament_seeding_menu:{tournament_id}")
    
    # Кнопка внесения счета матчей (показываем когда турнир запущен)
    if tournament_data.get('status') == 'started':
        builder.button(text="📝 Внести счет", callback_data=f"admin_enter_match_score:{tournament_id}")
    
    # Кнопка управления играми
    builder.button(text="🎮 Управление играми", callback_data=f"admin_tournament_games:{tournament_id}")
    
    # Кнопка запуска турнира, если готов
    if tournament_ready and tournament_data.get('status') == 'active':
        builder.button(text="🚀 Запустить", callback_data="tournament_start_now")
    
    builder.button(text="🗑️ Удалить", callback_data=f"delete_tournament_confirm:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data="edit_tournaments_back")
    builder.adjust(2, 2, 2, 2, 1, 1, 1, 1, 1, 1)
    
    # Создаем турнирную сетку
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )

# Обработчик выбора турнира для редактирования
@router.callback_query(F.data.startswith("edit_tournament:"))
async def select_tournament_for_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора турнира для редактирования"""
    tournament_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_tournament_id=tournament_id)
    await _show_tournament_edit(callback, state, tournament_id)
    await callback.answer()

# Обработчик дополнительных опций редактирования
@router.callback_query(F.data == "edit_tournament_more")
async def edit_tournament_more(callback: CallbackQuery, state: FSMContext):
    """Обработчик дополнительных опций редактирования"""
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🌍 Страна", callback_data="edit_field:country")
    builder.button(text="📍 Район", callback_data="edit_field:district")
    builder.button(text="⏱️ Продолжительность", callback_data="edit_field:duration")
    builder.button(text="📋 В списке города", callback_data="edit_field:show_in_list")
    builder.button(text="🔒 Скрыть сетку", callback_data="edit_field:hide_bracket")
    builder.button(text="🔙 Назад", callback_data=f"edit_tournament:{tournament_id}")
    builder.adjust(2, 2, 1, 1)
    
    await safe_edit_message(callback,
        "⚙️ Дополнительные настройки",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора поля для редактирования
@router.callback_query(F.data.startswith("edit_field:"))
async def select_field_to_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора поля для редактирования"""
    field = callback.data.split(":", 1)[1]
    await state.update_data(editing_field=field)
    
    tournaments = await storage.load_tournaments()
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    tournament_data = tournaments[tournament_id]
    current = tournament_data.get(field, 'Не указано')
    
    builder = InlineKeyboardBuilder()
    
    if field == "sport":
        for sport in SPORTS:
            mark = "✅ " if sport == current else ""
            builder.button(text=f"{mark}{sport}", callback_data=f"update_field:{sport}")
        builder.adjust(2)
        await safe_edit_message(callback, f"🏓 Вид спорта: {current}", reply_markup=builder.as_markup())
    
    elif field == "country":
        for country in COUNTRIES:
            mark = "✅ " if country == current else ""
            builder.button(text=f"{mark}{country}", callback_data=f"update_field:{country}")
        builder.adjust(2)
        await safe_edit_message(callback, f"🌍 Страна: {current}", reply_markup=builder.as_markup())
    
    elif field == "city":
        current_country = tournament_data.get('country', '🇷🇺 Россия')
        cities = get_cities_for_country(current_country)
        for city in cities:
            mark = "✅ " if city == current else ""
            builder.button(text=f"{mark}{city}", callback_data=f"update_field:{city}")
        builder.adjust(2)
        await safe_edit_message(callback, f"🏙️ Город: {current}", reply_markup=builder.as_markup())
    
    elif field == "district":
        if tournament_data.get('city') == "Москва":
            for district in DISTRICTS_MOSCOW:
                mark = "✅ " if district == tournament_data.get('district') else ""
                builder.button(text=f"{mark}{district}", callback_data=f"update_field:{district}")
            builder.adjust(2)
            await safe_edit_message(callback, f"📍 Район: {tournament_data.get('district', 'Не указан')}", reply_markup=builder.as_markup())
        else:
            builder.button(text="🔙 Назад", callback_data="edit_tournament_more")
            await safe_edit_message(callback, "❌ Район доступен только для Москвы", reply_markup=builder.as_markup())
    
    elif field == "type":
        for t_type in TOURNAMENT_TYPES:
            mark = "✅ " if t_type == current else ""
            builder.button(text=f"{mark}{t_type}", callback_data=f"update_field:{t_type}")
        builder.adjust(1)
        await safe_edit_message(callback, f"⚔️ Тип: {current}", reply_markup=builder.as_markup())
    
    elif field == "gender":
        for gender in GENDERS:
            mark = "✅ " if gender == current else ""
            builder.button(text=f"{mark}{gender}", callback_data=f"update_field:{gender}")
        builder.adjust(2)
        await safe_edit_message(callback, f"👥 Пол: {current}", reply_markup=builder.as_markup())
    
    elif field == "category":
        for category in CATEGORIES:
            mark = "✅ " if category == current else ""
            builder.button(text=f"{mark}{category}", callback_data=f"update_field:{category}")
        builder.adjust(2)
        await safe_edit_message(callback, f"🏆 Категория: {current}", reply_markup=builder.as_markup())
    
    elif field == "age_group":
        for age_group in AGE_GROUPS:
            mark = "✅ " if age_group == current else ""
            builder.button(text=f"{mark}{age_group}", callback_data=f"update_field:{age_group}")
        builder.adjust(2)
        await safe_edit_message(callback, f"👶 Возраст: {current}", reply_markup=builder.as_markup())
    
    elif field == "duration":
        for duration in DURATIONS:
            mark = "✅ " if duration == current else ""
            builder.button(text=f"{mark}{duration}", callback_data=f"update_field:{duration}")
        builder.adjust(1)
        await safe_edit_message(callback, f"⏱️ Продолжительность: {current}", reply_markup=builder.as_markup())
    
    elif field == "participants_count":
        builder.button(text="🔙 Отмена", callback_data=f"edit_tournament:{tournament_id}")
        await safe_edit_message(callback, f"👥 Текущее: {current}\n\nВведите новое количество:", reply_markup=builder.as_markup())
        await state.set_state(EditTournamentStates.EDIT_PARTICIPANTS_COUNT)
    
    elif field == "show_in_list":
        current_value = tournament_data.get('show_in_list', False)
        for option in YES_NO_OPTIONS:
            mark = "✅ " if (option == "Да" and current_value) or (option == "Нет" and not current_value) else ""
            builder.button(text=f"{mark}{option}", callback_data=f"update_field:{option}")
        builder.adjust(2)
        await safe_edit_message(callback, f"📋 В списке: {'Да' if current_value else 'Нет'}", reply_markup=builder.as_markup())
    
    elif field == "hide_bracket":
        current_value = tournament_data.get('hide_bracket', False)
        for option in YES_NO_OPTIONS:
            mark = "✅ " if (option == "Да" and current_value) or (option == "Нет" and not current_value) else ""
            builder.button(text=f"{mark}{option}", callback_data=f"update_field:{option}")
        builder.adjust(2)
        await safe_edit_message(callback, f"🔒 Скрыть сетку: {'Да' if current_value else 'Нет'}", reply_markup=builder.as_markup())
    
    elif field == "comment":
        builder.button(text="🔙 Отмена", callback_data=f"edit_tournament:{tournament_id}")
        await safe_edit_message(callback, f"💬 Текущее: {tournament_data.get('comment', 'Нет')}\n\nВведите новое (или '-' чтобы удалить):", reply_markup=builder.as_markup())
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
        tournament_data["level"] = CATEGORY_LEVELS.get(new_value, "Без уровня")
    else:
        tournament_data[field] = new_value
    
    await storage.save_tournaments(tournaments)
    
    # Возвращаемся к турниру сразу после сохранения
    await callback.answer("✅ Сохранено")
    
    # Показываем обновленный турнир
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    location = tournament_data.get('city', 'Не указан')
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    
    participants = tournament_data.get('participants', {})
    text = f"🏆 {tournament_data.get('name', 'Турнир')}\n"
    text += f"📍 {location} | {tournament_data.get('sport', 'Не указан')}\n"
    text += f"👥 {len(participants)}/{tournament_data.get('participants_count', '?')} участников"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏓 Спорт", callback_data="edit_field:sport")
    builder.button(text="📍 Место", callback_data="edit_field:city")
    builder.button(text="⚔️ Тип", callback_data="edit_field:type")
    builder.button(text="👥 Пол", callback_data="edit_field:gender")
    builder.button(text="🏆 Категория", callback_data="edit_field:category")
    builder.button(text="👶 Возраст", callback_data="edit_field:age_group")
    builder.button(text="👥 Кол-во", callback_data="edit_field:participants_count")
    builder.button(text="💬 Описание", callback_data="edit_field:comment")
    builder.button(text="⚙️ Ещё", callback_data="edit_tournament_more")
    builder.button(text="👥 Участники", callback_data=f"manage_participants:{tournament_id}")
    builder.button(text="🗑️ Удалить", callback_data=f"delete_tournament_confirm:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data="edit_tournaments_back")
    builder.adjust(2, 2, 2, 2, 1, 1, 1, 1)
    
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )

# Обработчик ввода количества участников
@router.message(EditTournamentStates.EDIT_PARTICIPANTS_COUNT)
async def edit_participants_count(message: Message, state: FSMContext):
    """Обработчик ввода количества участников"""
    try:
        count = int(message.text.strip())
        if count <= 0:
            await message.answer("❌ Должно быть > 0")
            return
        
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        tournament_data['participants_count'] = count
        
        await storage.save_tournaments(tournaments)
        await state.clear()
        
        # Возвращаемся к турниру
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        await state.update_data(editing_tournament_id=tournament_id)
        
        location = tournament_data.get('city', 'Не указан')
        if tournament_data.get('district'):
            location += f" ({tournament_data['district']})"
        
        participants = tournament_data.get('participants', {})
        text = f"🏆 {tournament_data.get('name', 'Турнир')}\n"
        text += f"📍 {location} | {tournament_data.get('sport', 'Не указан')}\n"
        text += f"👥 {len(participants)}/{tournament_data.get('participants_count', '?')} участников"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🏓 Спорт", callback_data="edit_field:sport")
        builder.button(text="📍 Место", callback_data="edit_field:city")
        builder.button(text="⚔️ Тип", callback_data="edit_field:type")
        builder.button(text="👥 Пол", callback_data="edit_field:gender")
        builder.button(text="🏆 Категория", callback_data="edit_field:category")
        builder.button(text="👶 Возраст", callback_data="edit_field:age_group")
        builder.button(text="👥 Кол-во", callback_data="edit_field:participants_count")
        builder.button(text="💬 Описание", callback_data="edit_field:comment")
        builder.button(text="⚙️ Ещё", callback_data="edit_tournament_more")
        builder.button(text="👥 Участники", callback_data=f"manage_participants:{tournament_id}")
        builder.button(text="🗑️ Удалить", callback_data=f"delete_tournament_confirm:{tournament_id}")
        builder.button(text="🔙 Назад", callback_data="edit_tournaments_back")
        builder.adjust(2, 2, 2, 2, 1, 1, 1, 1)
        
        bracket_image, _ = await build_and_render_tournament_image(tournament_data, tournament_id)
        
        await message.answer_photo(
            photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
            caption=text,
            reply_markup=builder.as_markup()
        )
        
    except ValueError:
        await message.answer("❌ Введите число")

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
    await state.clear()
    
    # Возвращаемся к турниру
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    await state.update_data(editing_tournament_id=tournament_id)
    
    location = tournament_data.get('city', 'Не указан')
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    
    participants = tournament_data.get('participants', {})
    text = f"🏆 {tournament_data.get('name', 'Турнир')}\n"
    text += f"📍 {location} | {tournament_data.get('sport', 'Не указан')}\n"
    text += f"👥 {len(participants)}/{tournament_data.get('participants_count', '?')} участников"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏓 Спорт", callback_data="edit_field:sport")
    builder.button(text="📍 Место", callback_data="edit_field:city")
    builder.button(text="⚔️ Тип", callback_data="edit_field:type")
    builder.button(text="👥 Пол", callback_data="edit_field:gender")
    builder.button(text="🏆 Категория", callback_data="edit_field:category")
    builder.button(text="👶 Возраст", callback_data="edit_field:age_group")
    builder.button(text="👥 Кол-во", callback_data="edit_field:participants_count")
    builder.button(text="💬 Описание", callback_data="edit_field:comment")
    builder.button(text="⚙️ Ещё", callback_data="edit_tournament_more")
    builder.button(text="👥 Участники", callback_data=f"manage_participants:{tournament_id}")
    builder.button(text="🗑️ Удалить", callback_data=f"delete_tournament_confirm:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data="edit_tournaments_back")
    builder.adjust(2, 2, 2, 2, 1, 1, 1, 1)
    
    bracket_image, _ = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    await message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )

# Обработчик управления участниками
@router.callback_query(F.data.startswith("manage_participants"))
async def manage_participants(callback: CallbackQuery, state: FSMContext):
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
    fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
    users = await storage.load_users()
    
    text = f"👥 Участники: {len(participants)}/{tournament_data.get('participants_count', '?')}\n\n"
    
    if participants:
        for user_id, participant_data in participants.items():
            user_id_str = str(user_id)
            name = html_escape(str(participant_data.get('name', 'Неизвестно')))
            pay_status = tournament_data.get('payments', {}).get(user_id_str, {}).get('status')
            pay_text = "Оплатил" if pay_status == 'succeeded' else ("Не оплатил" if fee > 0 else "Без взноса")
            user_profile = users.get(user_id_str, {})
            username = (user_profile.get('username') or participant_data.get('username') or '').strip().lstrip('@')
            phone = str(user_profile.get('phone') or participant_data.get('phone') or '').strip()
            if username:
                contact_url = f"https://t.me/{username}"
                text += f'• {name} — {pay_text} — <a href="{contact_url}">Связаться</a>\n'
            elif phone:
                contact_url = f"https://t.me/{phone if phone.startswith('+') else '+' + phone}"
                text += f'• {name} — {pay_text} — <a href="{contact_url}">Связаться</a>\n'
            else:
                text += f"• {name} — {pay_text} — Нет контакта\n"
    else:
        text += "Участников пока нет"
    
    # Проверяем готовность турнира к запуску
    tournament_ready = False
    try:
        tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
        if tournament_ready and tournament_data.get('status') == 'active':
            text += "\n\n✅ Готов к запуску"
    except Exception:
        pass
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data=f"add_tournament_participant:{tournament_id}")
    if participants:
        builder.button(text="➖ Удалить", callback_data=f"remove_participant:{tournament_id}")
    
    # Кнопка запуска турнира, если готов
    if tournament_ready and tournament_data.get('status') == 'active':
        builder.button(text="🚀 Запустить", callback_data="tournament_start_now")
    
    builder.button(text="🔙 Назад", callback_data="edit_tournament_back")
    builder.adjust(2, 1, 1)
    
    bracket_image, bracket_text = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
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

@router.callback_query(F.data.startswith("tournament_seeding_menu"))
async def tournament_seeding_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Получаем tournament_id из callback_data или из состояния
    parts = callback.data.split(":")
    if len(parts) > 1:
        tournament_id = parts[1]
    else:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        if not tournament_id:
            await callback.answer("❌ Турнир не выбран")
            return
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tournament_id, {})
    if not t:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Сохраняем tournament_id в состоянии
    await state.update_data(seeding_tournament_id=tournament_id)
    
    # Посев теперь доступен и для круговой системы — порядок влияет на генерацию расписания
    seeding = await _ensure_seeding(tournament_id)
    users = await storage.load_users()

    # Текст с порядком
    text_lines = [f"🎲 Посев: {t.get('name', 'Турнир')[:30]}..."]
    for idx, uid in enumerate(seeding, start=1):
        name = users.get(uid, {}).get('first_name') or users.get(uid, {}).get('name') or str(uid)
        text_lines.append(f"{idx}. {name}")
    if t.get('type') == 'Олимпийская система':
        text_lines.append(_format_first_round_pairs(seeding, users))
    else:
        text_lines.append("\n📋 Круговая система")

    # Клавиатура: переместить вверх/вниз, перемешать, запустить, назад
    kb = InlineKeyboardBuilder()
    for idx, uid in enumerate(seeding):
        up_cb = f"seeding_move:{idx}:up"
        down_cb = f"seeding_move:{idx}:down"
        kb.row(InlineKeyboardButton(text=f"⬆️ {idx+1}", callback_data=up_cb), InlineKeyboardButton(text="⬇️", callback_data=down_cb))
    kb.row(InlineKeyboardButton(text="🔀 Перемешать", callback_data="seeding_shuffle"))
    # Кнопка запустить (доступна если минимум участников набран)
    try:
        ready = await tournament_manager.check_tournament_readiness(tournament_id)
        if ready:
            kb.row(InlineKeyboardButton(text="🚀 Запустить турнир", callback_data="tournament_start_now"))
    except Exception:
        pass
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="edit_tournament_back"))

    # Рендерим изображение сетки, чтобы визуально подтвердить изменения посева
    bracket_image, _ = await build_and_render_tournament_image(t, tournament_id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_seeding.png"),
        caption=truncate_caption("\n".join(text_lines)),
        reply_markup=kb.as_markup()
    )
    await callback.answer()

# Обработчик быстрого запуска турнира
@router.callback_query(F.data == "tournament_start_now")
async def tournament_start_now(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Получаем tournament_id из состояния
    data = await state.get_data()
    tid = data.get('editing_tournament_id') or data.get('seeding_tournament_id')
    if not tid:
        await callback.answer("❌ Турнир не выбран")
        return
    
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.not_enough_participants", language))
        return
    
    # Запускаем турнир
    logger.info(f"Запуск турнира {tid}...")
    started = await tournament_manager.start_tournament(tid)
    logger.info(f"Результат: {started}")
    
    if started:
        # Перезагружаем данные турнира
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments.get(tid, {})
        
        # Уведомления участникам
        try:
            notifications = TournamentNotifications(callback.message.bot)
            await notifications.notify_tournament_started(tid, tournament_data)
        except Exception as e:
            logger.error(f"Ошибка уведомлений: {e}")
        
        # Отправляем в канал
        try:
            bracket_image_bytes, _ = await build_and_render_tournament_image(tournament_data, tid)
            await send_tournament_started_to_channel(callback.message.bot, tid, tournament_data, bracket_image_bytes)
        except Exception as e:
            logger.error(f"Ошибка отправки в канал: {e}")
        
        await safe_edit_message(callback, "✅ Турнир запущен!", 
            InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_back").as_markup())
    else:
        await safe_edit_message(callback, "❌ Не удалось запустить турнир", 
            InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_back").as_markup())
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.not_enough_participants_to_start", language))
        return
    # Запускаем турнир и уведомляем
    logger.info(f"Запуск турнира {tid}...")
    started = await tournament_manager.start_tournament(tid)
    logger.info(f"Результат запуска турнира {tid}: {started}")
    
    if started:
        # Перезагружаем данные турнира после запуска (они обновились с матчами)
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments.get(tid, {})
        
        logger.info(f"Турнир {tid} загружен после запуска. Участников: {len(tournament_data.get('participants', {}))}, Матчей: {len(tournament_data.get('matches', []))}")
        
        # Уведомления участникам с сеткой и первой игрой (олимпийская) или списком соперников (круговая)
        try:
            logger.info(f"Создание объекта TournamentNotifications для турнира {tid}")
            notifications = TournamentNotifications(callback.message.bot)
            logger.info(f"Отправка уведомлений о старте турнира {tid}")
            notification_sent = await notifications.notify_tournament_started(tid, tournament_data)
            if notification_sent:
                logger.info(f"✅ Уведомления о старте турнира {tid} успешно отправлены")
            else:
                logger.warning(f"⚠️ Не удалось отправить уведомления о старте турнира {tid}")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомлений о старте турнира {tid}: {e}", exc_info=True)
        
        # Отправляем уведомление в канал с фото сетки
        try:
            logger.info(f"Генерация изображения сетки для отправки в канал турнира {tid}")
            bracket_image_bytes, _ = await build_and_render_tournament_image(tournament_data, tid)
            logger.info(f"Отправка уведомления о начале турнира {tid} в канал")
            await send_tournament_started_to_channel(callback.message.bot, tid, tournament_data, bracket_image_bytes)
            logger.info(f"✅ Уведомление о начале турнира {tid} отправлено в канал")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомления в канал: {e}", exc_info=True)
        await safe_edit_message(callback, "✅ Турнир запущен! Участникам отправлены уведомления", InlineKeyboardBuilder().button(text="🔙 К турниру", callback_data=f"view_tournament:{tid}").as_markup())
    else:
        await safe_edit_message(callback, "❌ Не удалось запустить турнир", InlineKeyboardBuilder().button(text="🔙 Назад", callback_data=f"tournament_seeding_menu:{tid}").as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("seeding_move:"))
async def seeding_move(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Получаем параметры из callback_data
    _, idx_str, direction = callback.data.split(":")
    
    # Получаем tournament_id из состояния
    data = await state.get_data()
    tid = data.get('seeding_tournament_id') or data.get('editing_tournament_id')
    if not tid:
        await callback.answer("❌ Турнир не выбран")
        return
    
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
    
    # Перемещаем участника
    users = await storage.load_users()
    moved_user_id = seeding[idx]
    moved_user_name = users.get(moved_user_id, {}).get('first_name') or str(moved_user_id)
    
    if direction == 'up' and idx > 0:
        seeding[idx-1], seeding[idx] = seeding[idx], seeding[idx-1]
        move_text = f"⬆️ {moved_user_name} вверх"
    elif direction == 'down' and idx < len(seeding) - 1:
        seeding[idx+1], seeding[idx] = seeding[idx], seeding[idx+1]
        move_text = f"⬇️ {moved_user_name} вниз"
    else:
        await callback.answer("❌ Невозможно переместить", show_alert=True)
        return
    
    t['seeding'] = seeding
    tournaments[tid] = t
    await storage.save_tournaments(tournaments)
    
    # Обновляем отображение
    await callback.message.delete()
    text_lines = [f"🎲 Посев: {t.get('name', 'Турнир')[:30]}...", "", f"✅ {move_text}", ""]
    for idx_new, uid in enumerate(seeding, start=1):
        name = users.get(uid, {}).get('first_name') or str(uid)
        text_lines.append(f"{idx_new}. {name}")
    
    kb = InlineKeyboardBuilder()
    for idx_new, uid in enumerate(seeding):
        kb.row(InlineKeyboardButton(text=f"⬆️ {idx_new+1}", callback_data=f"seeding_move:{idx_new}:up"), 
               InlineKeyboardButton(text="⬇️", callback_data=f"seeding_move:{idx_new}:down"))
    kb.row(InlineKeyboardButton(text="🔀 Перемешать", callback_data="seeding_shuffle"))
    try:
        ready = await tournament_manager.check_tournament_readiness(tid)
        if ready:
            kb.row(InlineKeyboardButton(text="🚀 Запустить", callback_data="tournament_start_now"))
    except Exception:
        pass
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="edit_tournament_back"))
    
    bracket_image, _ = await build_and_render_tournament_image(t, tid)
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="seeding.png"),
        caption=truncate_caption("\n".join(text_lines)),
        reply_markup=kb.as_markup()
    )
    await callback.answer()

# Legacy обработчик для старых callback_data
@router.callback_query(F.data.startswith("tournament_seeding_move:"))
async def tournament_seeding_move(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    _, tid, idx_str, direction = callback.data.split(":")
    await state.update_data(seeding_tournament_id=tid)
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
    
    # Получаем имя участника для показа в уведомлении
    users = await storage.load_users()
    moved_user_id = seeding[idx]
    moved_user_name = users.get(moved_user_id, {}).get('first_name') or users.get(moved_user_id, {}).get('name') or str(moved_user_id)
    
    if direction == 'up' and idx > 0:
        seeding[idx-1], seeding[idx] = seeding[idx], seeding[idx-1]
        move_text = f"⬆️ {moved_user_name} перемещён вверх"
    elif direction == 'down' and idx < len(seeding) - 1:
        seeding[idx+1], seeding[idx] = seeding[idx], seeding[idx+1]
        move_text = f"⬇️ {moved_user_name} перемещён вниз"
    else:
        await callback.answer("❌ Невозможно переместить дальше", show_alert=True)
        return
    
    t['seeding'] = seeding
    tournaments[tid] = t
    await storage.save_tournaments(tournaments)
    
    # Удаляем старое сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Перезагружаем турнир и перерисовываем меню
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tid, {})
    seeding = await _ensure_seeding(tid)
    users = await storage.load_users()

    # Текст с порядком
    text_lines = [f"🎲 Посев турнира: {t.get('name', 'Турнир')}", f"", f"✅ {move_text}", ""]
    for idx_new, uid in enumerate(seeding, start=1):
        name = users.get(uid, {}).get('first_name') or users.get(uid, {}).get('name') or str(uid)
        text_lines.append(f"{idx_new}. {name}")
    if t.get('type') == 'Олимпийская система':
        text_lines.append(_format_first_round_pairs(seeding, users))
    else:
        text_lines.append("\nКруговая система: порядок влияет на составление календаря матчей.")

    # Клавиатура
    kb = InlineKeyboardBuilder()
    for idx_new, uid in enumerate(seeding):
        up_cb = f"tournament_seeding_move:{tid}:{idx_new}:up"
        down_cb = f"tournament_seeding_move:{tid}:{idx_new}:down"
        kb.row(InlineKeyboardButton(text=f"⬆️ {idx_new+1}", callback_data=up_cb), InlineKeyboardButton(text="⬇️", callback_data=down_cb))
    kb.row(InlineKeyboardButton(text="🔀 Перемешать", callback_data=f"tournament_seeding_shuffle:{tid}"))
    try:
        ready = await tournament_manager.check_tournament_readiness(tid)
        if ready:
            kb.row(InlineKeyboardButton(text="💾 Сохранить и запустить", callback_data=f"tournament_seeding_save_start:{tid}"))
    except Exception:
        pass
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_tournament:{tid}"))

    # Рендерим изображение сетки
    bracket_image, _ = await build_and_render_tournament_image(t, tid)
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_seeding.png"),
        caption=truncate_caption("\n".join(text_lines)),
        reply_markup=kb.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "seeding_shuffle")
async def seeding_shuffle(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Получаем tournament_id из состояния
    data = await state.get_data()
    tid = data.get('seeding_tournament_id') or data.get('editing_tournament_id')
    if not tid:
        await callback.answer("❌ Турнир не выбран")
        return
    
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tid, {})
    if not t:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Перемешиваем
    seeding = await _ensure_seeding(tid)
    import random
    random.shuffle(seeding)
    t['seeding'] = seeding
    tournaments[tid] = t
    await storage.save_tournaments(tournaments)
    
    # Обновляем отображение
    await callback.message.delete()
    users = await storage.load_users()
    text_lines = [f"🎲 Посев: {t.get('name', 'Турнир')[:30]}...", "", "🔀 Перемешано", ""]
    for idx, uid in enumerate(seeding, start=1):
        name = users.get(uid, {}).get('first_name') or str(uid)
        text_lines.append(f"{idx}. {name}")
    
    kb = InlineKeyboardBuilder()
    for idx, uid in enumerate(seeding):
        kb.row(InlineKeyboardButton(text=f"⬆️ {idx+1}", callback_data=f"seeding_move:{idx}:up"), 
               InlineKeyboardButton(text="⬇️", callback_data=f"seeding_move:{idx}:down"))
    kb.row(InlineKeyboardButton(text="🔀 Перемешать", callback_data="seeding_shuffle"))
    try:
        ready = await tournament_manager.check_tournament_readiness(tid)
        if ready:
            kb.row(InlineKeyboardButton(text="🚀 Запустить", callback_data="tournament_start_now"))
    except Exception:
        pass
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="edit_tournament_back"))
    
    bracket_image, _ = await build_and_render_tournament_image(t, tid)
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="seeding.png"),
        caption=truncate_caption("\n".join(text_lines)),
        reply_markup=kb.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tournament_seeding_shuffle:"))
async def tournament_seeding_shuffle(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    tid = callback.data.split(":")[1]
    await state.update_data(seeding_tournament_id=tid)
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
    
    # Удаляем старое сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Перезагружаем турнир и перерисовываем меню
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tid, {})
    seeding = await _ensure_seeding(tid)
    users = await storage.load_users()

    # Текст с порядком
    text_lines = [f"🎲 Посев турнира: {t.get('name', 'Турнир')}", "", "🔀 Порядок перемешан", ""]
    for idx_new, uid in enumerate(seeding, start=1):
        name = users.get(uid, {}).get('first_name') or users.get(uid, {}).get('name') or str(uid)
        text_lines.append(f"{idx_new}. {name}")
    if t.get('type') == 'Олимпийская система':
        text_lines.append(_format_first_round_pairs(seeding, users))
    else:
        text_lines.append("\nКруговая система: порядок влияет на составление календаря матчей.")

    # Клавиатура
    kb = InlineKeyboardBuilder()
    for idx_new, uid in enumerate(seeding):
        up_cb = f"tournament_seeding_move:{tid}:{idx_new}:up"
        down_cb = f"tournament_seeding_move:{tid}:{idx_new}:down"
        kb.row(InlineKeyboardButton(text=f"⬆️ {idx_new+1}", callback_data=up_cb), InlineKeyboardButton(text="⬇️", callback_data=down_cb))
    kb.row(InlineKeyboardButton(text="🔀 Перемешать", callback_data=f"tournament_seeding_shuffle:{tid}"))
    try:
        ready = await tournament_manager.check_tournament_readiness(tid)
        if ready:
            kb.row(InlineKeyboardButton(text="💾 Сохранить и запустить", callback_data=f"tournament_seeding_save_start:{tid}"))
    except Exception:
        pass
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_tournament:{tid}"))

    # Рендерим изображение сетки
    bracket_image, _ = await build_and_render_tournament_image(t, tid)
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_seeding.png"),
        caption=truncate_caption("\n".join(text_lines)),
        reply_markup=kb.as_markup()
    )
    await callback.answer()


# Обработчик поиска участника по имени/фамилии
@router.message(EditTournamentStates.SEARCH_PARTICIPANT)
async def search_participant_by_name(message: Message, state: FSMContext):
    """Обработчик поиска участника по имени/фамилии"""
    search_query = message.text.strip().lower()
    
    if len(search_query) < 2:
        await message.answer("❌ Введите минимум 2 символа для поиска")
        return
    
    # Загружаем всех пользователей
    users = await storage.load_users()
    
    # Ищем пользователей по имени или фамилии
    found_users = []
    for user_id, user_data in users.items():
        first_name = (user_data.get('first_name') or '').lower()
        last_name = (user_data.get('last_name') or '').lower()
        full_name = f"{first_name} {last_name}".strip()
        
        if search_query in first_name or search_query in last_name or search_query in full_name:
            found_users.append({
                'id': user_id,
                'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                'phone': user_data.get('phone', 'Не указан'),
                'city': user_data.get('city', 'Не указан')
            })
    
    if not found_users:
        await message.answer(f"❌ Не найдено: '{message.text}'\n\nПопробуйте другой запрос")
        return
    
    # Ограничиваем количество результатов
    if len(found_users) > 20:
        found_users = found_users[:20]
        results_text = f"🔍 Найдено: {len(found_users)} (первые 20)\n\nВыберите:"
    else:
        results_text = f"🔍 Найдено: {len(found_users)}\n\nВыберите:"
    
    builder = InlineKeyboardBuilder()
    for user in found_users:
        button_text = f"{user['name']} ({user['city']})"
        builder.button(
            text=button_text,
            callback_data=f"select_participant:{user['id']}"
        )
    
    data = await state.get_data()
    tournament_id = data.get('admin_editing_tournament_id') or data.get('editing_tournament_id')
    is_admin_mode = 'admin_editing_tournament_id' in data
    
    if is_admin_mode:
        builder.button(text="🔄 Поиск", callback_data=f"admin_add_participant:{tournament_id}")
        builder.button(text="🔙 Назад", callback_data=f"admin_view_participants:{tournament_id}")
    else:
        builder.button(text="🔄 Поиск", callback_data=f"add_tournament_participant:{tournament_id}")
        builder.button(text="🔙 Назад", callback_data=f"manage_participants:{tournament_id}")
    builder.adjust(1)
    
    await message.answer(results_text, reply_markup=builder.as_markup())

# Обработчик выбора участника из списка найденных
@router.callback_query(F.data.startswith("select_participant:"))
async def select_participant_from_search(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора участника из списка"""
    user_id = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    tournament_id = data.get('admin_editing_tournament_id') or data.get('editing_tournament_id')
    is_admin_mode = 'admin_editing_tournament_id' in data
    
    # Проверяем, существует ли пользователь
    users = await storage.load_users()
    if str(user_id) not in users:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    user_data = users[str(user_id)]
    user_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
    
    # Загружаем турниры
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден", show_alert=True)
        await state.clear()
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    # Проверяем, не является ли пользователь уже участником
    if str(user_id) in participants:
        await callback.answer("❌ Этот пользователь уже является участником турнира", show_alert=True)
        return
    
    # Проверяем ограничение по количеству участников
    max_participants = int(tournament_data.get('participants_count', 0) or 0)
    current_count = len(participants)
    if max_participants and current_count >= max_participants:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(
            t("tournament.max_participants_reached", language, max=max_participants),
            show_alert=True
        )
        return
    
    # Добавляем участника
    participants[str(user_id)] = {
        'name': user_name,
        'phone': user_data.get('phone', 'Не указан'),
        'added_at': datetime.now().isoformat()
    }
    
    tournament_data['participants'] = participants
    tournaments[tournament_id] = tournament_data
    await storage.save_tournaments(tournaments)

    await maybe_begin_payment_collection(callback.message.bot, tournament_id)
    
    try:
        await send_tournament_application_to_channel(callback.message.bot, tournament_id, tournament_data, str(user_id), user_data)
        logger.info(f"Уведомление о добавлении участника {user_id} в турнир {tournament_id} отправлено в канал")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в канал при добавлении участника: {e}")
    
    # Формируем сообщение об успехе
    builder = InlineKeyboardBuilder()

    builder.button(text="➕ Добавить еще", callback_data=f"admin_add_participant:{tournament_id}")
    builder.button(text="👥 К участникам", callback_data=f"admin_view_participants:{tournament_id}")
    builder.button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
    
    builder.adjust(1)
    
    await callback.message.delete()
    await callback.message.answer(
        f"✅ Участник добавлен!\n\n"
        f"👤 {user_name}\n"
        f"📞 {user_data.get('phone', 'Не указан')}\n"
        f"🆔 {user_id}\n\n"
        f"👥 Участников в турнире: {len(participants)}/{tournament_data.get('participants_count', '—')}",
        reply_markup=builder.as_markup()
    )
    
    await state.clear()
    await callback.answer()

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
                back_callback = "manage_participants"
            
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
                back_callback = "manage_participants"
            
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
        await maybe_begin_payment_collection(message.bot, tournament_id)
        await state.clear()
        
        # Возвращаемся к управлению участниками
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        
        if is_admin_mode:
            await state.update_data(admin_editing_tournament_id=tournament_id)
        else:
            await state.update_data(editing_tournament_id=tournament_id)
        
        participants = tournament_data.get('participants', {})
        text = f"👥 Участники: {len(participants)}/{tournament_data.get('participants_count', '?')}\n\n"
        
        if participants:
            for uid, pdata in participants.items():
                text += f"• {pdata.get('name', 'Неизвестно')}\n"
        else:
            text += "Участников пока нет"
        
        # Проверяем готовность турнира
        tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
        if tournament_ready and tournament_data.get('status') == 'active':
            text += f"\n✅ Можно запустить турнир"
        
        builder = InlineKeyboardBuilder()
        if is_admin_mode:
            builder.button(text="➕ Добавить", callback_data=f"admin_add_participant:{tournament_id}")
            if participants:
                builder.button(text="➖ Удалить", callback_data=f"admin_rm_part_menu:{tournament_id}")
            builder.button(text="🔙 Назад", callback_data=f"admin_view_participants:{tournament_id}")
        else:
            builder.button(text="➕ Добавить", callback_data=f"add_tournament_participant:{tournament_id}")
            if participants:
                builder.button(text="➖ Удалить", callback_data=f"remove_participant:{tournament_id}")
            builder.button(text="🔙 Назад", callback_data=f"edit_tournament:{tournament_id}")
        builder.adjust(2, 1)
        
        bracket_image, _ = await build_and_render_tournament_image(tournament_data, tournament_id)
        
        await message.answer_photo(
            photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
            caption=text,
            reply_markup=builder.as_markup()
        )
        
    except ValueError:
        await message.answer("❌ Введите число")

@router.callback_query(F.data.startswith("add_tournament_participant:"))
async def add_tournament_participant(callback: CallbackQuery, state: FSMContext):
    """Старт добавления участника из экрана управления участниками"""
    tournament_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_tournament_id=tournament_id)
    await state.set_state(EditTournamentStates.SEARCH_PARTICIPANT)
    await safe_edit_message(
        callback,
        "🔍 Введите имя или фамилию:",
        InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data=f"manage_participants:{tournament_id}").as_markup()
    )
    await callback.answer()

# Обработчик меню удаления участника
@router.callback_query(F.data.startswith("remove_participant:"))
async def remove_participant_menu(callback: CallbackQuery, state: FSMContext):
    """Показывает меню удаления участника из турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_tournament_id=tournament_id)
    
    tournaments = await storage.load_tournaments()
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if tournament_id not in tournaments:
        await callback.answer(t("tournament.tournament_not_found", language))
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if not participants:
        await callback.answer(t("tournament.no_participants_to_remove", language))
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, participant_data in participants.items():
        name = participant_data.get('name', t("tournament.unknown", language))
        builder.button(text=f"➖ {name}", callback_data=f"confirm_remove_participant:{user_id}")
    
    builder.button(text="🔙 Назад", callback_data=f"manage_participants:{tournament_id}")
    builder.adjust(1)
    
    await safe_edit_message(callback,
        "➖ Удаление участника из турнира\n\n"
        "Выберите участника для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик подтверждения удаления участника
@router.callback_query(F.data.startswith("confirm_remove_participant:"))
async def confirm_remove_participant(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления участника"""
    user_id = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    if not tournament_id:
        await callback.answer("❌ Турнир не выбран")
        return
    
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
    tournament_strip_removed_participant_payment_state(tournament_data, user_id)
    tournaments[tournament_id] = tournament_data
    await storage.save_tournaments(tournaments)
    
    await callback.answer(f"✅ {participant_data.get('name', 'Участник')} удален")
    
    # Возвращаемся к управлению участниками
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    text = f"👥 Участники: {len(participants)}/{tournament_data.get('participants_count', '?')}\n\n"
    
    if participants:
        for uid, pdata in participants.items():
            text += f"• {pdata.get('name', 'Неизвестно')}\n"
    else:
        text += "Участников пока нет"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data=f"add_tournament_participant:{tournament_id}")
    if participants:
        builder.button(text="➖ Удалить", callback_data=f"remove_participant:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data=f"edit_tournament:{tournament_id}")
    builder.adjust(2, 1)
    
    bracket_image, _ = await build_and_render_tournament_image(tournament_data, tournament_id)
    
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
        caption=text,
        reply_markup=builder.as_markup()
    )

# Обработчик подтверждения удаления турнира
@router.callback_query(F.data.startswith("delete_tournament_confirm"))
async def confirm_delete_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления турнира"""
    # Получаем tournament_id из callback_data или из состояния
    parts = callback.data.split(":")
    if len(parts) > 1:
        tournament_id = parts[1]
    else:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        if not tournament_id:
            await callback.answer("❌ Турнир не выбран")
            return
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Удалить", callback_data="delete_tournament_yes")
    builder.button(text="❌ Отмена", callback_data="edit_tournament_back")
    builder.adjust(2)
    
    await safe_edit_message(callback,
        f"⚠️ Удалить турнир?\n\n"
        f"{tournament_data.get('name', 'Без названия')}\n"
        f"👥 {len(tournament_data.get('participants', {}))} участников",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик удаления турнира
@router.callback_query(F.data.startswith("delete_tournament_yes"))
async def delete_tournament_yes(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления турнира"""
    # Получаем tournament_id из callback_data или из состояния
    parts = callback.data.split(":")
    if len(parts) > 1:
        tournament_id = parts[1]
    else:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        if not tournament_id:
            await callback.answer("❌ Турнир не выбран")
            return
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    # Удаляем турнир
    del tournaments[tournament_id]
    await storage.save_tournaments(tournaments)
    
    await state.clear()
    
    await safe_edit_message(callback, f"✅ Турнир удален")
    await callback.answer()

# Обработчик меню удаления участника (для админа)
@router.callback_query(F.data.startswith("admin_rm_part_menu:"))
async def admin_rm_part_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления участника для админа"""
    if not await is_admin(callback.from_user.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
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
    tournament_strip_removed_participant_payment_state(tournament_data, user_id)
    tournaments[tournament_id] = tournament_data
    await storage.save_tournaments(tournaments)
    
    await safe_edit_message(callback,
        f"✅ Участник успешно удален из турнира!\n\n"
        f"👤 Имя: {participant_data.get('name', 'Неизвестно')}\n"
        f"🆔 ID: {user_id}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🗑️ Удалить еще", callback_data=f"admin_rm_part_menu:{tournament_id}")
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
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("tournament.no_admin_rights", language))
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    
    # Сохраняем ID турнира в состоянии
    await state.update_data(admin_editing_tournament_id=tournament_id)
    await state.set_state(EditTournamentStates.SEARCH_PARTICIPANT)
    
    await safe_edit_message(callback,
        "➕ Добавление участника в турнир\n\n"
        "Введите фамилию или имя участника для поиска:",
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
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if not tournaments:
        await callback.message.delete()
        await callback.message.answer(t("tournament.no_tournaments_to_display", language))
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tdata in admin_sort_tournament_items(list(tournaments.items())):
        name = tdata.get('name', t("tournament.no_name", language))
        city_raw = tdata.get('city', t("tournament.not_specified", language))
        city_display = get_city_translation(city_raw, language) if isinstance(city_raw, str) else city_raw
        label = participants_count_label(tdata)
        builder.button(
            text=f"🏆 {name} ({city_display}) — 👥 {label}",
            callback_data=f"admin_view_participants:{tournament_id}",
        )
    
    builder.button(text=t("admin.back", language), callback_data="admin_back_to_main")
    builder.adjust(1)
    
    # Удаляем старое сообщение и отправляем новое
    await callback.message.delete()
    await callback.message.answer(
        t("tournament.view_participants_title", language) + "\n\n" + t("tournament.view_participants_prompt", language),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчики навигации
@router.callback_query(F.data == "edit_tournaments_back")
async def edit_tournaments_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку турниров для редактирования"""
    await show_edit_tournaments_page(callback, page=0)

async def show_edit_tournaments_page(callback: CallbackQuery, page: int = 0):
    """Показывает страницу со списком турниров для редактирования с пагинацией"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await callback.message.delete()
        await callback.message.answer("📋 Нет турниров")
        await callback.answer()
        return
    
    import re
    TOURNAMENTS_PER_PAGE = 5
    
    # Преобразуем в список для пагинации
    tournament_items = admin_sort_tournament_items(list(tournaments.items()))
    total_tournaments = len(tournament_items)
    total_pages = (total_tournaments + TOURNAMENTS_PER_PAGE - 1) // TOURNAMENTS_PER_PAGE
    
    # Проверяем границы страницы
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    # Получаем турниры для текущей страницы
    start_idx = page * TOURNAMENTS_PER_PAGE
    end_idx = min(start_idx + TOURNAMENTS_PER_PAGE, total_tournaments)
    page_tournaments = tournament_items[start_idx:end_idx]
    
    builder = InlineKeyboardBuilder()
    
    for tournament_id, tournament_data in page_tournaments:
        level = tournament_data.get('level', '?')
        city = tournament_data.get('city', 'Не указан')
        district = tournament_data.get('district', '')
        country = tournament_data.get('country', '')
        name = tournament_data.get('name', '')
        
        # Формируем место проведения
        if city == "Москва" and district:
            location = f"{city}, {district}"
        elif city and country:
            location = f"{city}, {country}"
        else:
            location = city or 'Не указано'
        
        # Извлекаем номер из названия турнира (если есть)
        number_match = re.search(r'№(\d+)', name)
        tournament_number = number_match.group(1) if number_match else '?'
        
        level_line = format_admin_tournament_level(str(level), tournament_data)
        button_text = f"№{tournament_number} | {level_line} | {location} | {participants_count_label(tournament_data)}"
        builder.button(text=button_text, callback_data=f"edit_tournament:{tournament_id}")
    
    builder.adjust(1)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"edit_tournaments_page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"edit_tournaments_page:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_main"))
    
    text = f"🏆 Выберите турнир:\n\nСтраница {page + 1}/{total_pages} (всего: {total_tournaments})"
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup())
    
    await callback.answer()

# Обработчик пагинации для списка редактирования турниров
@router.callback_query(F.data.startswith("edit_tournaments_page:"))
async def edit_tournaments_page_handler(callback: CallbackQuery):
    page = int(callback.data.split(":", 1)[1])
    await show_edit_tournaments_page(callback, page=page)

@router.callback_query(F.data == "edit_tournament_back")
async def edit_tournament_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к турниру"""
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    if tournament_id:
        await _show_tournament_edit(callback, state, tournament_id)
        await callback.answer()
    else:
        await edit_tournaments_back(callback, state)

@router.callback_query(F.data == "1edit_tournament_back")
async def edit_tournament_back_legacy(callback: CallbackQuery, state: FSMContext):
    """Возврат к турниру (legacy)"""
    await edit_tournament_back(callback, state)

# Возврат в главное меню турниров
@router.callback_query(F.data == "tournaments_main_menu")
async def tournaments_main_menu(callback: CallbackQuery):
    """Возврат в главное меню турниров"""
    language = await get_user_language_async(str(callback.message.chat.id))
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') in ['active', 'started']}
    
    text = t("tournament.menu.text", language, active_count=len(active_tournaments))
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("tournament.menu.view_list", language), callback_data="view_tournaments_start")
    builder.button(text=t("tournament.menu.my_tournaments", language), callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    # Удаляем старое сообщение и отправляем новое
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()

async def show_tournament_brief_info(message: Message, tournament_id: str, user_id: str):
    """Показывает краткую информацию о турнире из deep link с сеткой и кнопками"""
    try:
        language = await get_user_language_async(str(message.chat.id))
        tournaments = await storage.load_tournaments()
        
        if tournament_id not in tournaments:
            await message.answer(t("tournament.tournament_not_found", language))
            return
        
        tournament_data = tournaments[tournament_id]
        
        # Получаем информацию о турнире
        tournament_name = tournament_data.get('name') or t("tournament.no_name", language)
        tournament_type = get_tournament_type_translation(tournament_data.get('type') or '', language) if tournament_data.get('type') else t("tournament.not_specified", language)
        tournament_status = tournament_data.get('status', 'active')
        
        # Подсчет участников
        participants = tournament_data.get('participants', {}) or {}
        participants_count = len(participants)
        max_participants = tournament_data.get('participants_count', '?')
        
        # Подсчет завершенных игр турнира
        completed_games_count = 0
        try:
            games = await storage.load_games()
            for game in games:
                if game.get('tournament_id') == tournament_id and game.get('status') in ['completed', None]:
                    completed_games_count += 1
        except Exception as e:
            logger.error(f"Ошибка при подсчете игр: {e}")
        
        # Формируем краткий текст
        loc_raw = tournament_data.get('city') or ''
        location = get_city_translation(loc_raw, language) if loc_raw else t("tournament.not_specified", language)
        if tournament_data.get('district'):
            location += f" ({get_district_translation(tournament_data['district'], language)})"
        
        status_emoji = "🏁" if tournament_status == 'started' else "🏆" if tournament_status == 'active' else "✅"
        status_text = (t("tournament.brief.status_started", language) if tournament_status == 'started'
            else t("tournament.brief.status_active", language) if tournament_status == 'active'
            else t("tournament.brief.status_finished", language))
        
        text = f"{status_emoji} *{tournament_name}*\n\n"
        text += f"📊 *{t('tournament.brief.label_status', language)}:* {status_text}\n"
        text += f"📍 *{t('tournament.brief.label_place', language)}:* {location}\n"
        text += f"🎯 *{t('tournament.brief.label_type', language)}:* {tournament_type}\n"
        text += f"👥 *{t('tournament.brief.label_participants', language)}:* {participants_count}/{max_participants}\n"
        text += f"🎾 *{t('tournament.brief.label_games_completed', language)}:* {completed_games_count}\n"
        
        if tournament_data.get('category'):
            text += f"🏅 *{t('tournament.brief.label_category', language)}:* {tournament_data['category']}\n"
        if tournament_data.get('level'):
            text += f"🧩 *{t('tournament.brief.label_level', language)}:* {tournament_data['level']}\n"
        
        # Создаем клавиатуру
        builder = InlineKeyboardBuilder()
        
        # Проверяем, является ли пользователь участником
        is_registered = await storage.is_user_registered(user_id)
        is_participant = str(user_id) in participants
        
        # Если зарегистрирован в боте и не участник турнира - показываем кнопку "Участвовать"
        if is_registered and not is_participant and tournament_status == 'active':
            max_participants_int = int(max_participants) if str(max_participants).isdigit() else 0
            if not max_participants_int or participants_count < max_participants_int:
                builder.button(text=t("tournament.buttons.participate", language), callback_data=f"apply_tournament:{tournament_id}")
        
        # Если пользователь - участник, показываем "Мои турниры" и кнопку оплаты (если нужна)
        if is_participant:
            # Проверяем статус оплаты
            entry_fee = int(tournament_data.get('entry_fee', get_tournament_entry_fee()) or get_tournament_entry_fee())
            is_paid = tournament_data.get('payments', {}).get(str(user_id), {}).get('status') == 'succeeded'
            
            # Добавляем информацию об оплате в текст
            if entry_fee > 0:
                if is_paid:
                    text += t("tournament.payment_paid_line_md", language, fee=entry_fee)
                else:
                    text += t("tournament.payment_required_line_md", language, fee=entry_fee)
            
            # Кнопка оплаты, если требуется
            if entry_fee > 0 and not is_paid:
                builder.button(text=t("tournament.buttons.pay_participate", language), callback_data=f"tournament_pay:{tournament_id}")
            
            builder.button(text=t("tournament.buttons.my_tournaments", language), callback_data="my_tournaments_list:0")
        
        builder.button(text=t("tournament.buttons.all_tournaments", language), callback_data="view_tournaments_start")
        builder.button(text=t("tournament.buttons.main_menu", language), callback_data="tournaments_main_menu")
        builder.adjust(1)
        
        # Генерируем изображение сетки турнира
        try:
            bracket_image, _ = await build_and_render_tournament_image(tournament_data, tournament_id)
            await message.answer_photo(
                photo=BufferedInputFile(bracket_image, filename=f"tournament_{tournament_id}_bracket.png"),
                caption=truncate_caption(text),
                parse_mode="Markdown",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            logger.error(f"Ошибка при генерации сетки турнира: {e}", exc_info=True)
            # Если не удалось сгенерировать изображение, отправляем только текст
            await message.answer(
                text=text,
                parse_mode="Markdown",
                reply_markup=builder.as_markup()
            )
    
    except Exception as e:
        logger.error(f"Ошибка при показе информации о турнире {tournament_id}: {e}", exc_info=True)
        language = await get_user_language_async(str(message.chat.id))
        await message.answer(t("tournament.brief.load_error", language))


# ==================== ВНЕСЕНИЕ СЧЕТА МАТЧЕЙ ТУРНИРА ====================

@router.callback_query(F.data.startswith("admin_enter_match_score:"))
async def admin_enter_match_score_menu(callback: CallbackQuery, state: FSMContext):
    """Показывает список незавершенных матчей турнира для внесения счета"""
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_tournament_id=tournament_id)
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id, {})
    
    if not tournament_data:
        await callback.answer("❌ Турнир не найден")
        return
    
    matches = tournament_data.get('matches', [])
    participants = tournament_data.get('participants', {})
    
    # Фильтруем незавершенные матчи (не BYE)
    pending_matches = [m for m in matches 
                      if m.get('status') == 'pending' 
                      and not m.get('is_bye', False)
                      and m.get('player1_id') and m.get('player2_id')]
    
    if not pending_matches:
        await callback.answer("📋 Нет незавершенных матчей", show_alert=True)
        return
    
    # Группируем матчи по раундам
    from collections import defaultdict
    rounds = defaultdict(list)
    for match in pending_matches:
        round_num = match.get('round', 0)
        rounds[round_num].append(match)
    
    # Создаем список матчей с индексами для коротких callback_data
    match_list = []
    for round_num in sorted(rounds.keys()):
        match_list.extend(rounds[round_num])
    
    # Сохраняем список в состоянии для дальнейшего использования
    await state.update_data(pending_matches_list=[m.get('id') for m in match_list])
    
    builder = InlineKeyboardBuilder()
    
    for idx, match in enumerate(match_list):
        p1_id = match.get('player1_id')
        p2_id = match.get('player2_id')
        p1_name = participants.get(str(p1_id), {}).get('name', 'Игрок 1')
        p2_name = participants.get(str(p2_id), {}).get('name', 'Игрок 2')
        
        round_num = match.get('round', 0)
        match_label = f"Раунд {round_num + 1}"
        if match.get('is_consolation'):
            place = match.get('consolation_place', '')
            match_label = f"За {place} место"
        
        button_text = f"{match_label}: {p1_name} vs {p2_name}"
        # Используем индекс вместо полного ID для короткого callback_data
        builder.button(text=button_text, callback_data=f"admin_match:{idx}")
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}"))
    
    text = f"📝 <b>Внесение счета матча</b>\n\n"
    text += f"🏆 {tournament_data.get('name', 'Турнир')}\n"
    text += f"📊 Незавершенных матчей: {len(pending_matches)}\n\n"
    text += f"Выберите матч для внесения счета:"
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode='HTML')
    except:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode='HTML')
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_match:"))
async def admin_select_match_for_score(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора матча для внесения счета"""
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Получаем индекс матча из callback_data
    match_idx = int(callback.data.split(":", 1)[1])
    
    # Получаем данные из состояния
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    pending_matches_list = data.get('pending_matches_list', [])
    
    if not tournament_id or match_idx >= len(pending_matches_list):
        await callback.answer("❌ Ошибка: данные не найдены")
        return
    
    # Получаем ID матча по индексу
    match_id = pending_matches_list[match_idx]
    
    await state.update_data(editing_match_id=match_id)
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id, {})
    participants = tournament_data.get('participants', {})
    
    # Находим матч
    match = None
    for m in tournament_data.get('matches', []):
        if m.get('id') == match_id:
            match = m
            break
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if not match:
        await callback.answer(t("tournament.match_not_found", language))
        return
    
    p1_id = match.get('player1_id')
    p2_id = match.get('player2_id')
    p1_name = participants.get(str(p1_id), {}).get('name', 'Игрок 1')
    p2_name = participants.get(str(p2_id), {}).get('name', 'Игрок 2')
    
    match_label = f"Раунд {match.get('round', 0) + 1}"
    if match.get('is_consolation'):
        place = match.get('consolation_place', '')
        match_label = t("tournament.match_for_place", language, place=place)
    
    text = f"📝 <b>Внесение счета</b>\n\n"
    text += f"🏆 {tournament_data.get('name', 'Турнир')}\n"
    text += f"📊 {match_label}\n\n"
    text += f"👤 <b>Игрок 1:</b> {p1_name}\n"
    text += f"👤 <b>Игрок 2:</b> {p2_name}\n\n"
    text += f"<b>Кто победил?</b>"
    
    # Сохраняем ID игроков в состоянии
    await state.update_data(
        match_player1_id=p1_id,
        match_player2_id=p2_id
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🥇 {p1_name}", callback_data="admin_winner:1")
    builder.button(text=f"🥇 {p2_name}", callback_data="admin_winner:2")
    builder.button(text="🔙 Назад", callback_data=f"admin_enter_match_score:{tournament_id}")
    builder.adjust(1)
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode='HTML')
    except:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode='HTML')
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_winner:"))
async def admin_set_winner_and_ask_score(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора победителя, запрашивает счет"""
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Получаем номер игрока (1 или 2)
    player_num = callback.data.split(":", 1)[1]
    
    # Получаем данные из состояния
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    match_id = data.get('editing_match_id')
    
    # Определяем ID победителя
    if player_num == "1":
        winner_id = data.get('match_player1_id')
    else:
        winner_id = data.get('match_player2_id')
    
    if not winner_id or not tournament_id or not match_id:
        await callback.answer("❌ Ошибка: данные не найдены")
        return
    
    await state.update_data(match_winner_id=winner_id)
    await state.set_state(AdminEditGameStates.ENTER_TOURNAMENT_SCORE)
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id, {})
    participants = tournament_data.get('participants', {})
    
    winner_name = participants.get(str(winner_id), {}).get('name', 'Игрок')
    
    text = (
        f"📝 <b>Внесение счета</b>\n\n"
        f"🏆 Победитель: <b>{winner_name}</b>\n\n"
        f"Введите счет матча в формате:\n"
        f"<code>6:4, 6:2</code> (для нескольких сетов)\n"
        f"или\n"
        f"<code>6:4</code> (для одного сета)\n\n"
        f"Примеры:\n"
        f"• <code>6:4, 6:2</code>\n"
        f"• <code>7:5, 6:4, 6:2</code>\n"
        f"• <code>6:0</code>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Отмена", callback_data=f"admin_enter_match_score:{tournament_id}")
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode='HTML')
    except:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode='HTML')
    
    await callback.answer()


@router.message(AdminEditGameStates.ENTER_TOURNAMENT_SCORE, F.text)
async def admin_process_tournament_score_input(message: Message, state: FSMContext):
    """Обработчик ввода счета матча турнира"""
    if not await is_admin(message.from_user.id):
        language = await get_user_language_async(str(message.from_user.id))
        await message.answer(t("tournament.no_admin_rights", language))
        await state.clear()
        return
    
    score = message.text.strip()
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    match_id = data.get('editing_match_id')
    winner_id = data.get('match_winner_id')
    
    # Валидация счета
    try:
        sets = [s.strip() for s in score.split(',')]
        for s in sets:
            parts = s.split(':')
            if len(parts) != 2:
                raise ValueError("Неверный формат счета")
            int(parts[0])
            int(parts[1])
    except ValueError:
        await message.answer(
            "❌ <b>Неверный формат счета!</b>\n\n"
            "Используйте формат: <code>6:4, 6:2</code>",
            parse_mode='HTML'
        )
        return
    
    success = await tournament_manager.update_match_result(match_id, winner_id, score, message.bot)
    
    # Инициализируем переменные для использования позже
    rating_changes = {}
    winner_id_str = str(winner_id)
    loser_id = None
    users = None
    
    if success:
        # Создаем запись в games.json
        try:
            tournaments = await storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            
            # Находим обновленный матч
            match = None
            for m in tournament_data.get('matches', []):
                if m.get('id') == match_id:
                    match = m
                    break
            
            if match:
                # Формируем данные игры
                game_id = datetime.now().strftime('%Y%m%d_%H%M%S')
                p1_id = str(match.get('player1_id'))
                p2_id = str(match.get('player2_id'))
                
                # Загружаем пользователей для расчета рейтинга
                users = await storage.load_users()
                
                # Определяем победителя и проигравшего
                winner_id_str = str(winner_id)
                loser_id = p2_id if winner_id_str == p1_id else p1_id
                
                # Рассчитываем разницу геймов для изменения рейтинга
                total_game_diff = 0
                for set_score in [s.strip() for s in score.split(',')]:
                    games1, games2 = map(int, set_score.split(':'))
                    total_game_diff += abs(games1 - games2)
                
                # Получаем текущие рейтинги игроков
                winner_rating = float(users.get(winner_id_str, {}).get('rating_points', 500))
                loser_rating = float(users.get(loser_id, {}).get('rating_points', 500))
                
                # Рассчитываем новые рейтинги
                new_winner_rating, new_loser_rating = await calculate_new_ratings(
                    winner_rating, loser_rating, total_game_diff
                )
                
                # Обновляем рейтинги пользователей
                if winner_id_str in users:
                    users[winner_id_str]['rating_points'] = new_winner_rating
                    users[winner_id_str]['player_level'] = calculate_level_from_points(
                        int(new_winner_rating),
                        users[winner_id_str].get('sport', '🎾Большой теннис')
                    )
                
                if loser_id in users:
                    users[loser_id]['rating_points'] = new_loser_rating
                    users[loser_id]['player_level'] = calculate_level_from_points(
                        int(new_loser_rating),
                        users[loser_id].get('sport', '🎾Большой теннис')
                    )
                
                # Сохраняем обновленные рейтинги
                await storage.save_users(users)
                
                # Формируем изменения рейтинга для записи в game_data
                rating_changes = {
                    p1_id: float(new_winner_rating - winner_rating) if winner_id_str == p1_id else float(new_loser_rating - loser_rating),
                    p2_id: float(new_loser_rating - loser_rating) if winner_id_str == p1_id else float(new_winner_rating - winner_rating)
                }
                
                game_data = {
                    'id': game_id,
                    'date': datetime.now().isoformat(),
                    'type': 'tournament',
                    'score': score,
                    'sets': [s.strip() for s in score.split(',')],
                    'media_filename': None,
                    'players': {
                        'team1': [p1_id],
                        'team2': [p2_id]
                    },
                    'rating_changes': rating_changes,
                    'tournament_id': tournament_id,
                    'status': 'completed',
                    'winner_id': winner_id_str
                }
                
                # Сохраняем в games.json
                games = await storage.load_games()
                games.append(game_data)
                await storage.save_games(games)
                logger.info(f"Создана запись игры {game_id} в games.json для матча {match_id}")
                
                # Публикуем результат в телеграм-канал
                try:
                    # Определяем winner_side на основе того, кто победил
                    winner_side = 'team1' if winner_id_str == p1_id else 'team2'
                    
                    # Формируем данные для канала
                    channel_data = {
                        'game_type': 'tournament',
                        'score': score,
                        'sets': [s.strip() for s in score.split(',')],
                        'winner_side': winner_side,
                        'tournament_id': tournament_id,
                        'opponent1': {'telegram_id': p2_id},
                        'current_user_id': p1_id
                    }
                    
                    # Отправляем уведомление в канал
                    await send_game_notification_to_channel(
                        message.bot, 
                        channel_data, 
                        users, 
                        p1_id
                    )
                    logger.info(f"Результат турнирной игры {game_id} опубликован в канал (admin input)")
                except Exception as channel_error:
                    logger.error(f"Ошибка при публикации в канал: {channel_error}")
                
        except Exception as e:
            logger.error(f"Ошибка создания записи в games.json: {e}")
        
        # Формируем сообщение с изменениями рейтинга
        rating_msg = ""
        if rating_changes and users and loser_id:
            winner_change = rating_changes.get(winner_id_str, 0)
            loser_change = rating_changes.get(loser_id, 0)
            winner_name = users.get(winner_id_str, {}).get('first_name', 'Игрок')
            loser_name = users.get(loser_id, {}).get('first_name', 'Игрок')
            
            rating_msg = (
                f"\n📈 <b>Изменение рейтинга:</b>\n"
                f"• {winner_name}: {'+' if winner_change >= 0 else ''}{winner_change:.1f}\n"
                f"• {loser_name}: {'+' if loser_change >= 0 else ''}{loser_change:.1f}"
            )
        
        await message.answer(
            f"✅ <b>Счет успешно внесен!</b>\n\n"
            f"📊 Счет: <b>{score}</b>"
            f"{rating_msg}\n\n"
            f"Матч завершен, сетка турнира обновлена.",
            parse_mode='HTML'
        )
        
        # Возвращаемся к турниру
        await state.clear()
        
        # Показываем обновленный турнир
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        
        if tournament_data:
            from aiogram.types import CallbackQuery, BufferedInputFile
            
            # Генерируем обновленную сетку
            bracket_image, _ = await build_and_render_tournament_image(tournament_data, tournament_id)
            
            location = tournament_data.get('city', 'Не указан')
            if tournament_data.get('district'):
                location += f" ({tournament_data['district']})"
            
            participants = tournament_data.get('participants', {})
            text = f"🏆 {tournament_data.get('name', 'Турнир')}\n"
            text += f"📍 {location} | {tournament_data.get('sport', 'Не указан')}\n"
            text += f"👥 {len(participants)}/{tournament_data.get('participants_count', '?')} участников"
            
            builder = InlineKeyboardBuilder()
            builder.button(text="📝 Внести счет", callback_data=f"admin_enter_match_score:{tournament_id}")
            builder.button(text="🎮 Управление играми", callback_data=f"admin_tournament_games:{tournament_id}")
            builder.button(text="🔙 К списку турниров", callback_data="edit_tournaments_back")
            builder.adjust(1)
            
            await message.answer_photo(
                photo=BufferedInputFile(bracket_image, filename="tournament_bracket.png"),
                caption=text,
                reply_markup=builder.as_markup()
            )
    else:
        await message.answer(
            "❌ <b>Ошибка при внесении счета</b>\n\n"
            "Попробуйте еще раз или обратитесь к разработчику.",
            parse_mode='HTML'
        )
    
    await state.clear()
