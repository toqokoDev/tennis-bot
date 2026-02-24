from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict

from config.config import BOT_USERNAME
from config.profile import get_sport_config
from services.storage import storage

async def get_users_by_location(search_type=None, country=None, city=None, sport_type=None, 
                               exclude_user_id=None, limit=20) -> Dict[str, int]:
    """
    Получение реальных местоположений пользователей с количеством пользователей в каждом.
    Возвращает словарь: {местоположение: количество_пользователей}
    """
    users = await storage.load_users()
    location_counts = defaultdict(int)
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
        
        if sport_type and profile.get('sport') != sport_type:
            continue
        
        # Фильтр по типу поиска
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
        elif search_type == "partner":
            # Для знакомств не проверяем роль, для остальных видов спорта проверяем
            if sport_type not in ["🍒Знакомства", "🍻По пиву", "☕️Бизнес-завтрак"]:
                user_sport = profile.get('sport', '🎾Большой теннис')
                config = get_sport_config(user_sport)
                if config.get("has_role", True) and profile.get('role') != "Игрок":
                    continue
            
        # Фильтр по стране
        if country and profile.get('country') != country:
            continue
            
        # Фильтр по городу (если указана страна и мы ищем города)
        if country and city is None:
            # Для подсчета городов в стране
            user_city = profile.get('city')
            if user_city:
                location_counts[user_city] += 1
            continue
            
        # Фильтр по городу (если указан конкретный город)
        if city and profile.get('city') != city:
            continue
            
        # Фильтр по виду спорта (только для партнера)
        if search_type == "partner" and sport_type and profile.get('sport') != sport_type:
            continue
            
        # Если не указана страна - считаем страны
        if country is None:
            user_country = profile.get('country')
            if user_country:
                location_counts[user_country] += 1
        # Если указана страна, но не указан город - считаем города
        elif country and city is None:
            user_city = profile.get('city')
            if user_city:
                location_counts[user_city] += 1
        # Если указаны и страна и город - считаем пользователей
        else:
            location_counts["users"] += 1
    
    # Сортируем по количеству пользователей (по убыванию) и ограничиваем лимитом
    sorted_locations = dict(sorted(
        location_counts.items(), 
        key=lambda x: x[1], 
        reverse=True
    ))
    
    # Применяем лимит
    if limit:
        limited_locations = {}
        for i, (location, count) in enumerate(sorted_locations.items()):
            if i >= limit:
                break
            limited_locations[location] = count
        return limited_locations
    
    return sorted_locations

async def count_users_by_location(search_type=None, country=None, city=None, sport_type=None, exclude_user_id=None):
    """Подсчет пользователей по локации"""
    users = await storage.load_users()
    count = 0
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
            
        # Фильтр по типу поиска
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
        elif search_type == "partner":
            # Для знакомств не проверяем роль, для остальных видов спорта проверяем
            if sport_type != "🍒Знакомства":
                user_sport = profile.get('sport', '🎾Большой теннис')
                config = get_sport_config(user_sport)
                if config.get("has_role", True) and profile.get('role') != "Игрок":
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

async def get_top_cities(search_type=None, country=None, sport_type=None, limit=7, exclude_cities=None) -> List[Tuple[str, int]]:
    """
    Получает топ городов с количеством пользователей, исключая указанные города
    """
    users = await storage.load_users()
    city_counts = defaultdict(int)
    
    # Список городов для исключения
    if exclude_cities is None:
        exclude_cities = []
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
            
        # Фильтр по типу поиска
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
        elif search_type == "partner":
            # Для знакомств не проверяем роль, для остальных видов спорта проверяем
            if sport_type != "🍒Знакомства":
                user_sport = profile.get('sport', '🎾Большой теннис')
                config = get_sport_config(user_sport)
                if config.get("has_role", True) and profile.get('role') != "Игрок":
                    continue
            
        # Фильтр по стране
        if country and profile.get('country') != country:
            continue
            
        # Фильтр по виду спорта (только для партнера)
        if search_type == "partner" and sport_type and profile.get('sport') != sport_type:
            continue
            
        user_city = profile.get('city')
        if user_city and user_city not in exclude_cities:
            city_counts[user_city] += 1
    
    # Сортируем по количеству пользователей и возвращаем топ
    sorted_cities = sorted(city_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_cities[:limit]

async def get_top_countries(search_type=None, sport_type=None, limit=7, exclude_countries=None) -> List[Tuple[str, int]]:
    """
    Получает топ стран с количеством пользователей, исключая указанные страны
    Россия всегда будет первой в списке
    """
    users = await storage.load_users()
    country_counts = defaultdict(int)
    
    # Список стран для исключения
    if exclude_countries is None:
        exclude_countries = []
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
            
        # Фильтр по типу поиска
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
        elif search_type == "partner":
            # Для знакомств не проверяем роль, для остальных видов спорта проверяем
            if sport_type != "🍒Знакомства":
                user_sport = profile.get('sport', '🎾Большой теннис')
                config = get_sport_config(user_sport)
                if config.get("has_role", True) and profile.get('role') != "Игрок":
                    continue
            
        # Фильтр по виду спорта (только для партнера)
        if search_type == "partner" and sport_type and profile.get('sport') != sport_type:
            continue
            
        user_country = profile.get('country')
        if user_country and user_country not in exclude_countries:
            country_counts[user_country] += 1
    
    # Сортируем по количеству пользователей, но Россия всегда первая
    sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Выделяем Россию и ставим её первой
    russia_count = None
    other_countries = []
    
    for country, count in sorted_countries:
        if country == "🇷🇺 Россия":
            russia_count = (country, count)
        else:
            other_countries.append((country, count))
    
    # Формируем итоговый список: Россия первая, остальные по убыванию
    result = []
    if russia_count:
        result.append(russia_count)
    result.extend(other_countries)
    
    return result[:limit]

async def calculate_age(birth_date_str: str) -> int:
    try:
        birth_date = datetime.strptime(birth_date_str, "%d.%m.%Y")
        today = datetime.now()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age
    except ValueError:
        try:
            # Формат ДД.ММ (текущий год)
            birth_date = datetime.strptime(birth_date_str, "%d.%m")
            today = datetime.now()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            return age
        except ValueError:
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

def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown"""
    if not text:
        return ""
    # Экранируем только критически важные символы Markdown
    # Убираем избыточное экранирование символов, которые не ломают разметку
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '=', '|', '{', '}']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def create_user_profile_link(user_data: dict, user_id: str, additional=True) -> str:
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    username = user_data.get('username', '')
    
    # Экранируем имена для безопасности
    first_name = escape_markdown(first_name)
    last_name = escape_markdown(last_name)
    # Не экранируем username, так как он используется в ссылках
    
    if user_data.get('player_level'):
        level = user_data.get('player_level')
        rating = user_data.get('rating_points')
        level = escape_markdown(str(level))
        rating = escape_markdown(str(rating))
    else:
        level = ""
        rating = "Тренер"

    if additional:
        return f"[{first_name} {last_name}](https://t.me/{BOT_USERNAME}?start=profile_{user_id})\n@{username} NTRP {level} ({rating})"
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
        if offer.get('date') is None:
            date = datetime.min
        elif isinstance(offer['date'], str):
            date = datetime.strptime(offer['date'], '%d.%m.%Y')
        else:
            date = offer['date']
    except (ValueError, TypeError):
        date = datetime.min  # Если дата некорректна, ставим минимальную дату
        
    try:
        if offer.get('time') is None:
            time = datetime.min.time()
        elif isinstance(offer['time'], str):
            time = datetime.strptime(offer['time'], '%H:%M').time()
        else:
            time = offer['time']
    except (ValueError, TypeError):
        time = datetime.min.time()  # Если время некорректно, ставим минимальное время
        
    return (date, time)

def format_short_name(full_name: str) -> str:
    """
    Преобразует имя формата 'Даниил Щербаков' в 'Д. Щербаков'.
    Если имя уже короткое или состоит из одного слова, возвращает как есть.
    """
    parts = full_name.strip().split()
    if len(parts) == 0:
        return ""
    if len(parts) == 1:
        return parts[0]
    first, last = parts[0], parts[-1]
    if first:
        return f"{first[0]}. {last}"
    return last

def remove_country_flag(country: str) -> str:
    """
    Удаляет флаг (эмодзи) из названия страны для отображения в сообщениях.
    Например: '🇷🇺 Россия' -> 'Россия'
    """
    if not country:
        return ""
    # Удаляем эмодзи флага (обычно это первые 2-3 символа + пробел)
    import re
    # Удаляем все эмодзи в начале строки и пробелы после них
    return re.sub(r'^[\U0001F1E0-\U0001F1FF]{2}\s*', '', country).strip()