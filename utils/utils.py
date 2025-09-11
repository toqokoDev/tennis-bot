from datetime import datetime
from typing import List

from config.config import BOT_USERNAME
from services.storage import storage

async def count_users_by_location(search_type=None, country=None, city=None, sport_type=None, exclude_user_id=None):
    """Подсчет пользователей по локации"""
    users = await storage.load_users()
    count = 0
    
    for user_id, profile in users.items():
        # Исключаем текущего пользователя
        if exclude_user_id and str(user_id) == str(exclude_user_id):
            continue
            
        if not profile.get('show_in_search', True):
            continue
            
        # Фильтр по типу поиска
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
        elif search_type == "partner" and profile.get('role') != "Игрок":
            continue
            
        # Фильтр по стране
        if country and profile.get('country') != country:
            continue
            
        # Фильтр по городу
        if city and profile.get('city') != city:
            continue
            
        # Фильтр по виду спорта (только для партнера)
        if search_type == "partner" and sport_type and profile.get('sport') != sport_type:
            continue
            
        count += 1
    
    return count

async def calculate_age(birth_date_str: str) -> int:
    try:
        birth_date = datetime.strptime(birth_date_str, "%d.%m.%Y")
        today = datetime.now()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age
    except:
        return 0

async def level_to_points(level: str) -> int:
    level_points = {
        "0.0": 0, "0.5": 300, "1.0": 500, "1.5": 700,
        "2.0": 900, "2.5": 1100, "3.0": 1200, "3.5": 1400,
        "4.0": 1600, "4.5": 1800, "5.0": 2000, "5.5": 2200,
        "6.0": 2400, "6.5": 2600, "7.0": 2800
    }
    return level_points.get(level, 0)

async def calculate_new_ratings(winner_points: int, loser_points: int, game_difference: int) -> tuple:
    points_change = game_difference * 0.004
    winner_new = winner_points + (loser_points * points_change)
    loser_new = loser_points - (winner_points * points_change)
    return round(winner_new), round(loser_new)

async def search_users(query: str, exclude_ids: List[str] = None) -> List[tuple]:
    users = await storage.load_users()
    results = []
    query = query.lower().strip()
    
    if exclude_ids is None:
        exclude_ids = []
    
    for user_id, user_data in users.items():
        if user_id in exclude_ids:
            continue
            
        first_name = user_data.get('first_name', '').lower()
        last_name = user_data.get('last_name', '').lower()
        
        if (query in first_name or query in last_name or 
            query in f"{first_name} {last_name}"):
            results.append((user_id, user_data))
    
    return results

async def count_users_by_filters(search_type, country=None, city=None, sport=None, gender=None, level=None):
    """
    Подсчет пользователей по заданным фильтрам
    """
    users = await storage.load_users()
    count = 0
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
            
        if search_type == "partner" and profile.get('role') != "Игрок":
            continue
            
        if country and profile.get('country') != country:
            continue
            
        if city and profile.get('city') != city:
            continue
            
        if sport and profile.get('sport') != sport:
            continue
            
        if gender and profile.get('gender') != gender:
            continue
            
        if level and profile.get('player_level') != level:
            continue
            
        count += 1
    
    return count

async def get_weekday_short(date_str: str) -> str:
    """
    Возвращает день недели (сокращенно: Пн, Вт, Ср, Чт, Пт, Сб, Вс)
    по дате в формате YYYY-MM-DD.
    """
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return days[dt.weekday()]  # weekday(): Пн=0 ... Вс=6
    except ValueError:
        return "?"

async def create_user_profile_link(user_data: dict, user_id: str, additional=True) -> str:
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    username = user_data.get('username', '')
    
    if user_data.get('player_level'):
        level = user_data.get('player_level')
        rating = user_data.get('rating_points')
    else:
        level = ""
        rating = "Тренер"

    if additional:
        return f"[{first_name} {last_name} @{username} NTRP {level} (lvl. {rating})](https://t.me/{BOT_USERNAME}?start=profile_{user_id})"
    else:
        return f"[{first_name} {last_name}](https://t.me/{BOT_USERNAME}?start=profile_{user_id})"

async def format_tour_date(date_str):
    if not date_str or date_str == '-':
        return '-'
    try:
        # Пробуем разные форматы дат
        for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"]:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%d.%m.%y")  # 25.08.25
            except ValueError:
                continue
        # Если ни один формат не подошел, возвращаем как есть
        return date_str
    except:
        return date_str
            
def get_sort_key(offer):
    try:
        date = datetime.strptime(offer['date'], '%d.%m.%Y') if isinstance(offer['date'], str) else offer['date']
    except (ValueError, TypeError):
        date = datetime.min  # Если дата некорректна, ставим минимальную дату
        
    try:
        time = datetime.strptime(offer['time'], '%H:%M') if isinstance(offer['time'], str) else offer['time']
    except (ValueError, TypeError):
        time = datetime.min.time()  # Если время некорректно, ставим минимальное время
        
    return (date, time)
