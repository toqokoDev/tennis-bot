import logging
from functools import lru_cache
from typing import Optional

from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.translations import t, load_translations

try:
    from deep_translator import GoogleTranslator  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    GoogleTranslator = None  # type: ignore

logger = logging.getLogger(__name__)

_FLAG_PREFIXES = ("🇷🇺", "🇧🇾", "🇰🇿", "🇬🇪", "🇦🇲", "🇺🇿", "🇺🇸")


def _extract_flag(country: str):
    if not country:
        return None, country
    for flag in _FLAG_PREFIXES:
        if country.startswith(flag):
            return flag, country[len(flag):].lstrip()
    return None, country


@lru_cache(maxsize=8)
def _get_translator_instance(target_language: str):
    if GoogleTranslator is None:
        return None
    try:
        return GoogleTranslator(source="auto", target=target_language)
    except Exception as exc:
        logger.debug("Translator init failed for %s: %s", target_language, exc)
        return None


def _looks_like_russian(text: str) -> bool:
    if not text:
        return False
    # Быстрая эвристика: наличие кириллических символов
    for char in text.lower():
        if "а" <= char <= "я" or char == "ё":
            return True
    return False


def _normalize_language_for_translation(language: str, *, force: bool = False) -> Optional[str]:
    if not language:
        return None
    lang = language.lower().split("-", 1)[0]
    if lang == "ru" and not force:
        return None
    return lang


@lru_cache(maxsize=512)
def _translate_text(text: str, language: str, *, force: bool = False) -> Optional[str]:
    if not text:
        return None
    target_language = _normalize_language_for_translation(language, force=force)
    if not target_language:
        return None

    translator = _get_translator_instance(target_language)
    if translator is None:
        return None

    try:
        translated = translator.translate(text)
        if translated and isinstance(translated, str):
            return translated
    except Exception as exc:
        logger.debug(
            "Auto translation failed for '%s' to %s: %s",
            text,
            target_language,
            exc,
        )
    return None


def _strip_country_flag(country: str) -> str:
    _, without_flag = _extract_flag(country)
    return without_flag

def get_tennis_levels(language: str = "ru") -> dict:
    """Возвращает уровни тенниса с переведенными описаниями"""
    base_levels = {
        "1.0": {"points": 500},
        "1.5": {"points": 700},
        "2.0": {"points": 900},
        "2.5": {"points": 1100},
        "3.0": {"points": 1200},
        "3.5": {"points": 1400},
        "4.0": {"points": 1600},
        "4.5": {"points": 1800},
        "5.0": {"points": 2000},
        "5.5": {"points": 2200},
        "6.0": {"points": 2400},
        "6.5": {"points": 2600},
        "7.0": {"points": 2800}
    }
    # Получаем переводы напрямую из словаря, чтобы избежать проблем с ключами типа "1.0"
    translations = load_translations(language)
    tennis_levels_dict = translations.get("config", {}).get("tennis_levels", {})
    
    result = {}
    for level, data in base_levels.items():
        # Берем перевод из словаря напрямую по ключу "1.0", "1.5" и т.д.
        desc = tennis_levels_dict.get(level, f"config.tennis_levels.{level}")
        result[level] = {
            "desc": desc,
            "points": data["points"]
        }
    return result

# Уровни игроков с описаниями и рейтинговыми очками для большого тенниса
tennis_levels = {
    "1.0": {"desc": "Теннисист делает первые шаги", "points": 500},
    "1.5": {"desc": "Игрок обладает небольшим опытом, совершенствует стабильность ударов в игре", "points": 700},
    "2.0": {"desc": "У игрока заметны недостатки при выполнении основных ударов. Имеет укороченный замах, не может выбирать направление удара. Часто теннисист такого уровня практически не применяет бэкхенд, неправильно держит в руке ракетку. Как правило, у сетки играет крайне неохотно", "points": 900},
    "2.5": {"desc": "Игрок пытается предвидеть направление полета мяча, но чувство корта еще развито плохо. Кроме того, имеются некоторые проблемы с хватом ракетки, подходом к мячу, предпочитает забегать под форхенд. По-прежнему испытывает трудности при игре у сетки. Может поддерживать игру в низком темпе с партнерами своего уровня", "points": 1100},
    "3.0": {"desc": "Теннисист уже хорошо отбивает средние по темпу мячи, но не всегда может контролировать силу, направление и глубину своих ударов. Лучше всего удаются форхенды. Пытается усиливать подачу, что приводит к ошибкам при ее выполнении. Вторая подача, как правило, значительно слабее первой. У сетки испытывает трудности с низкими обводящими ударами. Умеет неплохо исполнять простые и средней сложности свечи", "points": 1200},
    "3.5": {"desc": "Теннисист может контролировать направление ударов средней сложности, хотя ему немного недостает контроля глубины и разнообразия, улучшается видение и чувство корта. Игрок умеет выполнять несильные направленные удары слева, но мощные удары и высокие отскоки еще требуют доработки. При подаче наблюдается достаточная сила и контроль. Играет более активно у сетки, достает некоторые обводящие удары. Стабильно выполняет смэш на легких мячах", "points": 1400},
    "4.0": {"desc": "Игрок может выполнять разнообразные удары, умеет контролировать глубину и направление удара, как справа, так и слева. Имеет в своем арсенале свечу, смэш, удары с лета и мощные выбивающие удары. Первую подачу выполняет сильно, иногда в ущерб точности. Имеет опыт использования командной тактики при игре в паре", "points": 1600},
    "4.5": {"desc": "Очень разнообразные удары по мячу, эффективно использует силу и вращение мяча. Мощно атакует слева, при этом ошибается только под прессингом. Игрок грамотно использует силу и подкрутку при ударах, умеет управлять темпом игры, хорошо работает ногами, контролирует глубину своих ударов и способен менять тактику в игре в зависимости от соперника. Теннисист обладает сильной и точной первой подачей, стабильно выполняет вторую, способен атаковать возле сетки", "points": 1800},
    "5.0": {"desc": "Игрок прекрасно чувствует мяч и часто может выполнять особенные удары, на которых строится игра. Спортсмен способен выигрывать очки, 'убивать' мячи с лета, укороченными мячами может вынудить противника совершать ошибки, успешно применяет свечи, смэши, удары с полулета, а вторую подачу выполняет глубоко и с сильным верхним вращением", "points": 2000},
    "5.5": {"desc": "Главным оружием теннисиста в игре являются мощные удары и стабильность. В зависимости от ситуации спортсмен способен изменить стратегию и технику игры, может выполнять надежные удары в сложных моментах", "points": 2200},
    "6.0": {"desc": "Теннисист такого уровня обладает хорошей квалификацией и не нуждается в классификации NTRP. Обычно спортсмены с рейтингом 6.0 участвуют в национальных соревнованиях среди юниоров и имеют национальный рейтинг", "points": 2400},
    "6.5": {"desc": "Теннисист уровня 6.5 по мастерству игры близок к 7.0 и обладает опытом участия в играх-сателлитах", "points": 2600},
    "7.0": {"desc": "Спортсмен мирового класса, принимающий участие в различных турнирах по теннису международного уровня. Основным источником доходов для игрока высшего уровня служат денежные призы, разыгрываемые на соревнованиях", "points": 2800}
}

def get_table_tennis_levels(language: str = "ru") -> dict:
    """Возвращает уровни настольного тенниса с переведенными описаниями"""
    base_levels = {
        "1.0": {"points": 500},
        "1.5": {"points": 700},
        "2.0": {"points": 900},
        "2.5": {"points": 1100},
        "3.0": {"points": 1200},
        "3.5": {"points": 1400},
        "4.0": {"points": 1600},
        "4.5": {"points": 1800},
        "5.0": {"points": 2000},
        "5.5": {"points": 2200},
        "6.0": {"points": 2400},
        "6.5": {"points": 2600},
        "7.0": {"points": 2800}
    }
    # Получаем переводы напрямую из словаря, чтобы избежать проблем с ключами типа "1.0"
    translations = load_translations(language)
    table_tennis_levels_dict = translations.get("config", {}).get("table_tennis_levels", {})
    
    result = {}
    for level, data in base_levels.items():
        # Берем перевод из словаря напрямую по ключу "1.0", "1.5" и т.д.
        desc = table_tennis_levels_dict.get(level, f"config.table_tennis_levels.{level}")
        result[level] = {
            "desc": desc,
            "points": data["points"]
        }
    return result

# Уровни для настольного тенниса (NTRP) - обновленные согласно https://tabletennis-play.com/ntrp/
table_tennis_levels = {
    "1.0": {"desc": "Новичок - только начинает играть, изучает основы", "points": 500},
    "1.5": {"desc": "Начинающий - может отбивать мяч, но с ошибками", "points": 700},
    "2.0": {"desc": "Ученик - понимает основы, но техника нестабильна", "points": 900},
    "2.5": {"desc": "Ученик+ - может играть простые розыгрыши", "points": 1100},
    "3.0": {"desc": "Любитель - стабильная игра, понимает тактику", "points": 1200},
    "3.5": {"desc": "Любитель+ - хорошая техника, может играть с вращением", "points": 1400},
    "4.0": {"desc": "Продвинутый - владеет всеми ударами, хорошая тактика", "points": 1600},
    "4.5": {"desc": "Продвинутый+ - стабильная игра на высоком уровне", "points": 1800},
    "5.0": {"desc": "Эксперт - отличная техника и тактика", "points": 2000},
    "5.5": {"desc": "Эксперт+ - может играть с профессионалами", "points": 2200},
    "6.0": {"desc": "Полупрофессионал - участвует в соревнованиях", "points": 2400},
    "6.5": {"desc": "Полупрофессионал+ - высокий уровень игры", "points": 2600},
    "7.0": {"desc": "Профессионал - мастер спорта", "points": 2800}
}

# Для обратной совместимости
player_levels = tennis_levels

moscow_districts = [
    "ВАО", "ЗАО", "ЗелАО",
    "САО", "СВАО", "СЗАО",
    "ЦАО", "ЮАО", "ЮВАО", "ЮЗАО"
]

def get_moscow_districts(language: str = "ru") -> list:
    """Возвращает округа Москвы с учетом языка
    
    Args:
        language: Язык для перевода ("ru", "en", "es")
    
    Returns:
        list: Список округов Москвы на указанном языке
    """
    # Список ключей для переводов
    district_keys = [
        "vao", "zao", "zela", 
        "sao", "svao", "szao", 
        "cao", "yao", "yvao", "yzao"
    ]
    
    # Получаем переводы для каждого округа
    result = []
    for key in district_keys:
        district = t(f"config.moscow_districts.{key}", language)
        result.append(district)
    
    return result

# Функции для получения переведенных значений
def get_game_types(language: str = "ru") -> list:
    """Возвращает типы игр с учетом языка"""
    return [
        t("config.game_types.single", language),
        t("config.game_types.double", language),
        t("config.game_types.mixed", language),
        t("config.game_types.training", language)
    ]

def get_payment_types(language: str = "ru") -> list:
    """Возвращает типы платежей с учетом языка"""
    return [
        t("config.payment_types.split", language),
        t("config.payment_types.i_pay", language),
        t("config.payment_types.opponent_pays", language),
        t("config.payment_types.loser_pays", language)
    ]

def get_roles(language: str = "ru") -> list:
    """Возвращает роли с учетом языка"""
    return [
        t("config.roles.player", language),
        t("config.roles.trainer", language)
    ]

# Для обратной совместимости
game_types = ["Одиночная", "Парная", "Микст", "Тренировка"]
payment_types = ["💰 Пополам", "💳 Я оплачиваю", "💵 Соперник оплачивает", "🎾 Проигравший оплачивает"]
roles = ["🎯 Игрок", "👨‍🏫 Тренер"]

def get_price_ranges(language: str = "ru") -> list:
    """Возвращает диапазоны цен с учетом языка"""
    return [
        {"min": 0, "max": 1000, "label": t("config.price_ranges.up_to_1000", language)},
        {"min": 1000, "max": 2000, "label": t("config.price_ranges.1000_2000", language)},
        {"min": 2000, "max": 3000, "label": t("config.price_ranges.2000_3000", language)},
        {"min": 3000, "max": 5000, "label": t("config.price_ranges.3000_5000", language)},
        {"min": 5000, "max": 10000, "label": t("config.price_ranges.5000_10000", language)},
        {"min": 10000, "max": 10000000, "label": t("config.price_ranges.from_10000", language)}
    ]

# Для обратной совместимости
PRICE_RANGES = [
    {"min": 0, "max": 1000, "label": "до 1000 руб."},
    {"min": 1000, "max": 2000, "label": "1000-2000 руб."},
    {"min": 2000, "max": 3000, "label": "2000-3000 руб."},
    {"min": 3000, "max": 5000, "label": "3000-5000 руб."},
    {"min": 5000, "max": 10000, "label": "5000-10000 руб."},
    {"min": 10000, "max": 10000000, "label": "от 10000 руб."}
]

def get_gender_types(language: str = "ru") -> list:
    """Возвращает типы пола с учетом языка"""
    return [
        t("config.gender_types.male", language),
        t("config.gender_types.female", language)
    ]

# Для обратной совместимости
GENDER_TYPES=["Мужской", "Женский"]
PLAYER_LEVELS=["0.0", "0.5", "2.0", "2.5", "3.0", "4.5", "5.0", "5.5", "6.0", "6.5", "7.0"]

cities_data = {
    "🇷🇺 Россия": [
        "Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург"
    ],
    "🇧🇾 Беларусь": [
        "Минск", "Гомель", "Могилёв", "Витебск", "Гродно"
    ],
    "🇰🇿 Казахстан": [
        "Алматы", "Астана (Нур-Султан)", "Шымкент", "Караганда", "Актобе"
    ],
    "🇬🇪 Грузия": [
        "Тбилиси", "Батуми", "Кутаиси", "Рустави", "Зугдиди"
    ],
    "🇦🇲 Армения": [
        "Ереван", "Гюмри", "Ванадзор", "Вагаршапат (Эчмиадзин)", "Абовян"
    ],
    "🇺🇿 Узбекистан": [
        "Ташкент", "Самарканд", "Бухара", "Наманган", "Андижан"
    ],
}

def get_weekdays(language: str = "ru") -> dict:
    """Возвращает дни недели с учетом языка"""
    return {
        0: t("config.weekdays.0", language),
        1: t("config.weekdays.1", language),
        2: t("config.weekdays.2", language),
        3: t("config.weekdays.3", language),
        4: t("config.weekdays.4", language),
        5: t("config.weekdays.5", language),
        6: t("config.weekdays.6", language),
    }

# Для обратной совместимости
WEEKDAYS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}

def get_sport_type(language: str = "ru") -> list:
    """Возвращает список видов спорта с учетом языка"""
    return [
        t("config.sports.tennis", language),
        t("config.sports.table_tennis", language),
        t("config.sports.badminton", language),
        t("config.sports.beach_tennis", language),
        t("config.sports.padel", language),
        t("config.sports.squash", language),
        t("config.sports.pickleball", language),
        t("config.sports.golf", language),
        t("config.sports.running", language),
        t("config.sports.fitness", language),
        t("config.sports.cycling", language),
        t("config.sports.beer", language),
        t("config.sports.dating", language),
        t("config.sports.business_breakfast", language)
    ]

def get_sport_translation(sport: str, language: str = "ru") -> str:
    """Возвращает переведенное название вида спорта"""
    # Маппинг русских названий на ключи переводов
    sport_mapping = {
        "🎾Большой теннис": "tennis",
        "🏓Настольный теннис": "table_tennis",
        "🏸Бадминтон": "badminton",
        "🏖️Пляжный теннис": "beach_tennis",
        "🎾Падл-теннис": "padel",
        "🥎Сквош": "squash",
        "🏆Пиклбол": "pickleball",
        "⛳Гольф": "golf",
        "🏃‍♂️‍➡️Бег": "running",
        "🏋️‍♀️Фитнес": "fitness",
        "🚴Вело": "cycling",
        "🍻По пиву": "beer",
        "🍒Знакомства": "dating",
        "☕️Бизнес-завтрак": "business_breakfast"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return sport
    
    # Ищем ключ для перевода
    sport_key = sport_mapping.get(sport)
    if sport_key:
        return t(f"config.sports.{sport_key}", language)
    
    # Если не нашли, возвращаем оригинал
    return sport

def get_country_translation(country: str, language: str = "ru") -> str:
    """Переводит название страны"""
    # Маппинг эмодзи-стран на ключи переводов
    country_mapping = {
        "🇷🇺 Россия": "russia",
        "🇧🇾 Беларусь": "belarus",
        "🇰🇿 Казахстан": "kazakhstan",
        "🇬🇪 Грузия": "georgia",
        "🇦🇲 Армения": "armenia",
        "🇺🇿 Узбекистан": "uzbekistan",
        "🇺🇸 США": "usa",
    }

    flag, stripped_country = _extract_flag(country)

    # Русский язык: оставляем как есть, но пробуем перевести из латиницы
    if language == "ru":
        if _looks_like_russian(stripped_country):
            return country if flag else stripped_country
        auto_translated = _translate_text(stripped_country, language, force=True)
        if auto_translated:
            return f"{flag} {auto_translated}" if flag else auto_translated
        return country if flag else stripped_country

    # Ищем ключ для перевода; если перевода нет — пытаемся перевести автоматически
    country_key = country_mapping.get(country)
    if country_key:
        translated = t(f"config.countries.{country_key}", language, default=None)
        if translated and translated != f"config.countries.{country_key}":
            return translated

    auto_translated = _translate_text(stripped_country, language)
    if auto_translated:
        return auto_translated

    # Если не нашли в маппинге или перевода, возвращаем название без эмодзи
    return stripped_country

def get_cities_for_country(country: str, language: str = "ru") -> list:
    """Возвращает города для страны с учетом языка"""
    # Получаем оригинальные города
    original_cities = cities_data.get(country, [])
    
    # Если язык русский, возвращаем как есть
    if language == "ru":
        return original_cities
    
    # Переводим каждый город
    translated_cities = []
    for city in original_cities:
        # Маппинг городов на ключи (используем нижний регистр и заменяем пробелы на подчеркивания)
        city_key = city.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
        full_key = f"config.cities.{city_key}"
        translated_city = t(full_key, language, default=None)
        if translated_city and translated_city != full_key:
            translated_cities.append(translated_city)
            continue

        auto_translated = _translate_text(city, language)
        translated_cities.append(auto_translated or city)
    
    return translated_cities

def get_city_translation(city: str, language: str = "ru") -> str:
    """Переводит название города"""
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        if _looks_like_russian(city):
            return city
        auto_translated = _translate_text(city, language, force=True)
        return auto_translated or city

    # Маппинг городов на ключи
    city_key = city.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
    full_key = f"config.cities.{city_key}"
    translated_city = t(full_key, language, default=None)
    if translated_city and translated_city != full_key:
        return translated_city

    auto_translated = _translate_text(city, language)
    return auto_translated or city

def get_district_translation(district: str, language: str = "ru") -> str:
    """Переводит название округа Москвы или сторону света"""
    # Маппинг округов Москвы
    district_mapping = {
        "ВАО": "vao",
        "ЗАО": "zao",
        "ЗелАО": "zela",
        "САО": "sao",
        "СВАО": "svao",
        "СЗАО": "szao",
        "ЦАО": "cao",
        "ЮАО": "yao",
        "ЮВАО": "yvao",
        "ЮЗАО": "yzao"
    }
    
    # Маппинг сторон света
    direction_mapping = {
        "Север": "north",
        "Юг": "south",
        "Запад": "west",
        "Восток": "east"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return district
    
    # Сначала проверяем стороны света
    direction_key = direction_mapping.get(district)
    if direction_key:
        return t(f"config.moscow_districts.{direction_key}", language, default=district)
    
    # Затем проверяем округа
    district_key = district_mapping.get(district)
    if district_key:
        return t(f"config.moscow_districts.{district_key}", language, default=district)
    
    # Если не нашли, пробуем обратное преобразование для округов
    for original, key in district_mapping.items():
        if t(f"config.moscow_districts.{key}", language) == district:
            return original
    
    # Обратное преобразование для сторон света
    for original, key in direction_mapping.items():
        if t(f"config.moscow_districts.{key}", language) == district:
            return original
    
    # Если ничего не нашли, возвращаем оригинал
    return district

def get_game_type_translation(game_type: str, language: str = "ru") -> str:
    """Переводит тип игры"""
    # Маппинг типов игр
    type_mapping = {
        "Одиночная": "single",
        "Парная": "double",
        "Микст": "mixed",
        "Тренировка": "training"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return game_type
    
    # Ищем ключ для перевода
    type_key = type_mapping.get(game_type)
    if type_key:
        return t(f"config.game_types.{type_key}", language)
    
    # Обратное преобразование
    for original, key in type_mapping.items():
        if t(f"config.game_types.{key}", language) == game_type:
            return original
    
    return game_type

def get_category_translation(category: str, language: str = "ru") -> str:
    """Переводит категорию турнира"""
    # Маппинг категорий
    category_mapping = {
        "1 категория": "category_1",
        "2 категория": "category_2",
        "3 категория": "category_3",
        "Мастерс": "masters",
        "Профи": "pro",
        "Без категории": "no_category"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return category
    
    # Ищем ключ для перевода
    category_key = category_mapping.get(category)
    if category_key:
        return t(f"config.tournament_categories.{category_key}", language, default=category)
    
    # Обратное преобразование
    for original, key in category_mapping.items():
        translated = t(f"config.tournament_categories.{key}", language)
        if translated == category:
            return original
    
    return category

def get_age_group_translation(age_group: str, language: str = "ru") -> str:
    """Переводит возрастную группу"""
    # Маппинг возрастных групп
    age_mapping = {
        "Взрослые": "adults",
        "Дети": "children"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return age_group
    
    # Ищем ключ для перевода
    age_key = age_mapping.get(age_group)
    if age_key:
        return t(f"config.tournament_age_groups.{age_key}", language, default=age_group)
    
    # Обратное преобразование
    for original, key in age_mapping.items():
        translated = t(f"config.tournament_age_groups.{key}", language)
        if translated == age_group:
            return original
    
    return age_group

def get_duration_translation(duration: str, language: str = "ru") -> str:
    """Переводит продолжительность турнира"""
    # Маппинг продолжительности
    duration_mapping = {
        "Многодневные": "multi_day",
        "Однодневные": "one_day",
        "Выездной": "away"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return duration
    
    # Ищем ключ для перевода
    duration_key = duration_mapping.get(duration)
    if duration_key:
        return t(f"config.tournament_durations.{duration_key}", language, default=duration)
    
    # Обратное преобразование
    for original, key in duration_mapping.items():
        translated = t(f"config.tournament_durations.{key}", language)
        if translated == duration:
            return original
    
    return duration

def get_payment_type_translation(payment_type: str, language: str = "ru") -> str:
    """Переводит тип оплаты"""
    # Маппинг типов оплаты
    type_mapping = {
        "💰 Пополам": "split",
        "💳 Я оплачиваю": "i_pay",
        "💵 Соперник оплачивает": "opponent_pays",
        "🎾 Проигравший оплачивает": "loser_pays"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return payment_type
    
    # Ищем ключ для перевода
    type_key = type_mapping.get(payment_type)
    if type_key:
        return t(f"config.payment_types.{type_key}", language)
    
    # Обратное преобразование
    for original, key in type_mapping.items():
        if t(f"config.payment_types.{key}", language) == payment_type:
            return original
    
    return payment_type

def get_role_translation(role: str, language: str = "ru") -> str:
    """Переводит роль"""
    # Маппинг ролей
    role_mapping = {
        "🎯 Игрок": "player",
        "👨‍🏫 Тренер": "trainer"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return role
    
    # Ищем ключ для перевода
    role_key = role_mapping.get(role)
    if role_key:
        return t(f"config.roles.{role_key}", language)
    
    # Обратное преобразование
    for original, key in role_mapping.items():
        if t(f"config.roles.{key}", language) == role:
            return original
    
    return role

def get_tournament_type_translation(tournament_type: str, language: str = "ru") -> str:
    """Переводит тип турнира"""
    # Маппинг типов турниров
    type_mapping = {
        "Олимпийская система": "olympic",
        "Круговая": "round_robin",
        "Круговая система": "round_robin"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return tournament_type
    
    # Ищем ключ для перевода
    type_key = type_mapping.get(tournament_type)
    if type_key:
        return t(f"config.tournament_types.{type_key}", language, default=tournament_type)
    
    # Обратное преобразование
    for original, key in type_mapping.items():
        translated = t(f"config.tournament_types.{key}", language)
        if translated == tournament_type:
            return original
    
    return tournament_type

def get_gender_translation(gender: str, language: str = "ru") -> str:
    """Переводит пол или формат участия в турнире"""
    if not gender:
        return gender or ""
    
    # Маппинг пола пользователя
    user_gender_mapping = {
        "Мужской": "male",
        "Женский": "female"
    }
    
    # Маппинг форматов участия в турнире
    tournament_gender_mapping = {
        "Мужчины": "men",
        "Женщины": "women",
        "Мужская пара": "men_pair",
        "Женская пара": "women_pair",
        "Микст": "mixed"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return gender
    
    # Убираем пробелы в начале и конце для сравнения
    gender_clean = gender.strip()
    
    # Сначала проверяем формат участия в турнире
    gender_key = tournament_gender_mapping.get(gender_clean)
    if gender_key:
        try:
            translated = t(f"config.tournament_genders.{gender_key}", language, default=None)
            if translated and translated != f"config.tournament_genders.{gender_key}" and translated != gender_clean:
                return translated
            # Если перевод не сработал, используем прямое обращение к переводам
            translations = load_translations(language)
            direct_translation = translations.get("config", {}).get("tournament_genders", {}).get(gender_key)
            if direct_translation:
                return direct_translation
        except Exception:
            pass
    
    # Затем проверяем пол пользователя
    gender_key = user_gender_mapping.get(gender_clean)
    if gender_key:
        try:
            translated = t(f"config.gender_types.{gender_key}", language, default=None)
            if translated and translated != f"config.gender_types.{gender_key}" and translated != gender_clean:
                return translated
            # Если перевод не сработал, используем прямое обращение к переводам
            translations = load_translations(language)
            direct_translation = translations.get("config", {}).get("gender_types", {}).get(gender_key)
            if direct_translation:
                return direct_translation
        except Exception:
            pass
    
    # Обратное преобразование для формата участия
    for original, key in tournament_gender_mapping.items():
        try:
            translated = t(f"config.tournament_genders.{key}", language)
            if translated == gender_clean:
                return original
        except Exception:
            pass
    
    # Обратное преобразование для пола пользователя
    for original, key in user_gender_mapping.items():
        try:
            translated = t(f"config.gender_types.{key}", language)
            if translated == gender_clean:
                return original
        except Exception:
            pass
    
    return gender_clean

def get_tournament_type_translation(tournament_type: str, language: str = "ru") -> str:
    """Переводит тип турнира"""
    # Маппинг типов турниров
    type_mapping = {
        "Олимпийская система": "olympic",
        "Круговая": "round_robin",
        "Круговая система": "round_robin"
    }
    
    # Если язык русский, возвращаем оригинал
    if language == "ru":
        return tournament_type
    
    # Ищем ключ для перевода
    type_key = type_mapping.get(tournament_type)
    if type_key:
        return t(f"config.tournament_types.{type_key}", language, default=tournament_type)
    
    # Обратное преобразование
    for original, key in type_mapping.items():
        translated = t(f"config.tournament_types.{key}", language)
        if translated == tournament_type:
            return original
    
    return tournament_type

def get_price_range_translation(price_range: dict, language: str = "ru") -> dict:
    """Переводит диапазон цен"""
    if language == "ru":
        return price_range
    
    # Создаем переведенную копию
    translated = price_range.copy()
    
    # Маппинг меток ценовых диапазонов
    label_mapping = {
        "до 1000 руб.": "up_to_1000",
        "1000-2000 руб.": "1000_2000",
        "2000-3000 руб.": "2000_3000",
        "3000-5000 руб.": "3000_5000",
        "5000-10000 руб.": "5000_10000",
        "от 10000 руб.": "from_10000"
    }
    
    # Переводим метку
    label_key = label_mapping.get(price_range.get("label", ""))
    if label_key:
        translated["label"] = t(f"config.price_ranges.{label_key}", language)
    
    return translated

def get_weekday_translation(weekday_num: int, language: str = "ru") -> str:
    """Переводит день недели"""
    if language == "ru":
        return WEEKDAYS.get(weekday_num, "")
    return t(f"config.weekdays.{weekday_num}", language)

def get_weekday_name(weekday_num: int, language: str = "ru") -> str:
    """Возвращает полное название дня недели"""
    return t(f"config.full_weekdays.{weekday_num}", language)

def get_month_name(month_num: int, language: str = "ru") -> str:
    """Возвращает название месяца"""
    return t(f"config.months.{month_num}", language)

def get_dating_goal_translation(goal: str, language: str = "ru") -> str:
    """Переводит цель знакомства"""
    # Маппинг целей знакомств
    goal_mapping = {
        "Отношения": "relationship",
        "Общение": "communication",
        "Дружба": "friendship",
        "Никогда не знаешь, что будет": "never_know"
    }
    
    if language == "ru":
        return goal
    
    goal_key = goal_mapping.get(goal)
    if goal_key:
        return t(f"config.dating_goals.{goal_key}", language)
    
    # Обратное преобразование
    for original, key in goal_mapping.items():
        if t(f"config.dating_goals.{key}", language) == goal:
            return original
    
    return goal

def get_dating_interest_translation(interest: str, language: str = "ru") -> str:
    """Переводит интерес для знакомств"""
    # Маппинг интересов
    interest_mapping = {
        "Путешествия": "travel",
        "Музыка": "music",
        "Кино": "cinema",
        "Кофе": "coffee",
        "Гитара": "guitar",
        "Горные лыжи": "skiing",
        "Настолки": "board_games",
        "Квизы": "quizzes"
    }
    
    if language == "ru":
        return interest
    
    interest_key = interest_mapping.get(interest)
    if interest_key:
        return t(f"config.dating_interests.{interest_key}", language)
    
    # Обратное преобразование
    for original, key in interest_mapping.items():
        if t(f"config.dating_interests.{key}", language) == interest:
            return original
    
    return interest

def get_dating_additional_translation(field: str, language: str = "ru") -> str:
    """Переводит дополнительное поле для знакомств"""
    # Маппинг дополнительных полей
    field_mapping = {
        "Работа / Профессия": "work",
        "Образование: Вуз или уровень образования": "education",
        "Рост": "height",
        "Зодиак, Знак зодиака": "zodiac",
        "Вредные привычки: Отношение к курению, алкоголю": "habits"
    }
    
    if language == "ru":
        return field
    
    field_key = field_mapping.get(field)
    if field_key:
        return t(f"config.dating_additional.{field_key}", language)
    
    # Обратное преобразование
    for original, key in field_mapping.items():
        if t(f"config.dating_additional.{key}", language) == field:
            return original
    
    return field

def translate_config_element(element: str, element_type: str, language: str = "ru") -> str:
    """Универсальная функция для перевода элементов конфигурации
    
    Args:
        element: Элемент для перевода
        element_type: Тип элемента ('sport', 'country', 'city', 'district', 'game_type', 
                                   'payment_type', 'role', 'gender', 'price_range', 
                                   'weekday', 'dating_goal', 'dating_interest', 'dating_additional')
        language: Язык перевода
    """
    if language == "ru":
        return element
    
    translation_functions = {
        'sport': get_sport_translation,
        'country': get_country_translation,
        'city': get_city_translation,
        'district': get_district_translation,
        'game_type': get_game_type_translation,
        'payment_type': get_payment_type_translation,
        'role': get_role_translation,
        'gender': get_gender_translation,
        'weekday': lambda x, lang: get_weekday_translation(int(x), lang) if x.isdigit() else x,
        'dating_goal': get_dating_goal_translation,
        'dating_interest': get_dating_interest_translation,
        'dating_additional': get_dating_additional_translation
    }
    
    func = translation_functions.get(element_type)
    if func:
        return func(element, language)
    
    # Для price_range нужна отдельная обработка
    if element_type == 'price_range' and isinstance(element, dict):
        translated = get_price_range_translation(element, language)
        return translated.get("label", element.get("label", ""))
    
    return element

# Для обратной совместимости
sport_type = [
    "🎾Большой теннис",
    "🏓Настольный теннис",
    "🏸Бадминтон",
    "🏖️Пляжный теннис",
    "🎾Падл-теннис",
    "🥎Сквош",
    "🏆Пиклбол",
    "⛳Гольф",
    "🏃‍♂️‍➡️Бег",
    "🏋️‍♀️Фитнес",
    "🚴Вело",
    "🍻По пиву",
    "🍒Знакомства",
    "☕️Бизнес-завтрак"
]

channels_id = {
    "🎾Большой теннис": ["-1001286936422", "-1001806787770"],
    "🏓Настольный теннис": "-1003099455273",
    "🏸Бадминтон": "-1003058878130",
    "🏖️Пляжный теннис": "-1002811227579",
    "🎾Падл-теннис": "-1002817029858",
    "🥎Сквош": "-1002945287162",
    "🏆Пиклбол": "-1002773528423",
    "⛳Гольф": "-1003005884812",
    "🏃‍♂️‍➡️Бег": "-1003023220088",
    "🏋️‍♀️Фитнес": "-1003076187384",
    "🚴Вело": "-1002946643810",
    "🍻По пиву": "-1002684882636",
    "🍒Знакомства": "-1002809521669",
    "☕️Бизнес-завтрак": "-1003009416582"
}

channels_usernames = {
    "🎾Большой теннис": "tennisplaycom",
    "🏓Настольный теннис": "tabletennis_play",
    "🏸Бадминтон": "badminton_play",
    "🏖️Пляжный теннис": "beachtennis_play",
    "🎾Падл-теннис": "padeltennis_play",
    "🥎Сквош": "squashplay",
    "🏆Пиклбол": "pickleball_play",
    "⛳Гольф": "golf_partner",
    "🏃‍♂️‍➡️Бег": "run_partner",
    "🏋️‍♀️Фитнес": "fitness_partners",
    "🚴Вело": "velo_partner",
    "🍻По пиву": "beer_partner",
    "🍒Знакомства": "dating_sport",
    "☕️Бизнес-завтрак": "business_partnery"
}

tour_channel_id = "-1002972370826"

def create_sport_keyboard(pref: str = "partner_sport_", exclude_sports: list = None, language: str = "ru"):
    """Создает клавиатуру с видами спорта в заданном формате
    
    Args:
        pref: Префикс для callback_data
        exclude_sports: Список видов спорта для исключения (например, ["🎾Большой теннис", "🏓Настольный теннис"])
        language: Язык для отображения названий видов спорта
    """
    if exclude_sports is None:
        exclude_sports = []
    
    builder = InlineKeyboardBuilder()
    
    # Получаем оригинальные названия для callback_data и переведенные для текста
    tennis_ru = "🎾Большой теннис"
    table_tennis_ru = "🏓Настольный теннис"
    badminton_ru = "🏸Бадминтон"
    beach_tennis_ru = "🏖️Пляжный теннис"
    padel_ru = "🎾Падл-теннис"
    squash_ru = "🥎Сквош"
    pickleball_ru = "🏆Пиклбол"
    golf_ru = "⛳Гольф"
    running_ru = "🏃‍♂️‍➡️Бег"
    fitness_ru = "🏋️‍♀️Фитнес"
    cycling_ru = "🚴Вело"
    beer_ru = "🍻По пиву"
    dating_ru = "🍒Знакомства"
    business_breakfast_ru = "☕️Бизнес-завтрак"
    
    # Большой теннис, настольный теннис - 2 в ряд
    tennis_buttons = []
    if tennis_ru not in exclude_sports:
        tennis_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(tennis_ru, language),
            callback_data=f"{pref}{tennis_ru}"
        ))
    if table_tennis_ru not in exclude_sports:
        tennis_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(table_tennis_ru, language),
            callback_data=f"{pref}{table_tennis_ru}"
        ))
    
    if tennis_buttons:
        builder.row(*tennis_buttons)
    
    # Бадминтон, пляжный теннис - 2 в ряд
    racket_buttons = []
    if badminton_ru not in exclude_sports:
        racket_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(badminton_ru, language),
            callback_data=f"{pref}{badminton_ru}"
        ))
    if beach_tennis_ru not in exclude_sports:
        racket_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(beach_tennis_ru, language),
            callback_data=f"{pref}{beach_tennis_ru}"
        ))
    
    if racket_buttons:
        builder.row(*racket_buttons)
    
    # Падл-теннис, сквош - 2 в ряд
    paddle_buttons = []
    if padel_ru not in exclude_sports:
        paddle_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(padel_ru, language),
            callback_data=f"{pref}{padel_ru}"
        ))
    if squash_ru not in exclude_sports:
        paddle_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(squash_ru, language),
            callback_data=f"{pref}{squash_ru}"
        ))
    
    if paddle_buttons:
        builder.row(*paddle_buttons)
    
    # Пиклбол, гольф, бег - 3 в ряд
    outdoor_buttons = []
    if pickleball_ru not in exclude_sports:
        outdoor_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(pickleball_ru, language),
            callback_data=f"{pref}{pickleball_ru}"
        ))
    if golf_ru not in exclude_sports:
        outdoor_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(golf_ru, language),
            callback_data=f"{pref}{golf_ru}"
        ))
    if running_ru not in exclude_sports:
        outdoor_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(running_ru, language),
            callback_data=f"{pref}{running_ru}"
        ))
    
    if outdoor_buttons:
        builder.row(*outdoor_buttons)
    
    # Фитнес, вело, по пиву - 3 в ряд
    fitness_buttons = []
    if fitness_ru not in exclude_sports:
        fitness_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(fitness_ru, language),
            callback_data=f"{pref}{fitness_ru}"
        ))
    if cycling_ru not in exclude_sports:
        fitness_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(cycling_ru, language),
            callback_data=f"{pref}{cycling_ru}"
        ))
    if beer_ru not in exclude_sports:
        fitness_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(beer_ru, language),
            callback_data=f"{pref}{beer_ru}"
        ))
    
    if fitness_buttons:
        builder.row(*fitness_buttons)
    
    # Знакомства, бизнес-завтрак - 2 в ряд
    social_buttons = []
    if dating_ru not in exclude_sports:
        social_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(dating_ru, language),
            callback_data=f"{pref}{dating_ru}"
        ))
    if business_breakfast_ru not in exclude_sports:
        social_buttons.append(InlineKeyboardButton(
            text=get_sport_translation(business_breakfast_ru, language),
            callback_data=f"{pref}{business_breakfast_ru}"
        ))
    
    if social_buttons:
        builder.row(*social_buttons)
    
    return builder.as_markup()

countries = ["🇷🇺 Россия"] + [country for country in cities_data.keys() if country != "🇷🇺 Россия"]

def get_sport_field_config(language: str = "ru") -> dict:
    """Возвращает конфигурацию полей для каждого вида спорта с учетом языка"""
    return {
        # === СПОРТИВНЫЕ ВИДЫ С КОРТАМИ И ОПЛАТОЙ ===
        "🎾Большой теннис": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "tennis",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.tennis.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.tennis.level", language)
        },
        "🏓Настольный теннис": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "table_tennis_rating",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.table_tennis.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.table_tennis.level", language)
        },
        "🏸Бадминтон": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "tennis",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.badminton.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.badminton.level", language)
        },
        "🏖️Пляжный теннис": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "tennis",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.beach_tennis.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.beach_tennis.level", language)
        },
        "🎾Падл-теннис": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "tennis",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.padel.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.padel.level", language)
        },
        "🥎Сквош": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "tennis",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.squash.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.squash.level", language)
        },
        "🏆Пиклбол": {
            "category": "court_sport",
            "has_level": True,
            "level_type": "tennis",
            "has_role": True,
            "has_payment": True,
            "has_vacation": True,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.pickleball.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": t("config.sport_fields.pickleball.level", language)
        },
        
        # === АКТИВНЫЕ ВИДЫ СПОРТА БЕЗ КОРТОВ ===
        "⛳Гольф": {
            "category": "outdoor_sport",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.golf.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": None
        },
        "🏃‍♂️‍➡️Бег": {
            "category": "outdoor_sport",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.running.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": None
        },
        "🏋️‍♀️Фитнес": {
            "category": "outdoor_sport",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.fitness.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": None
        },
        "🚴Вело": {
            "category": "outdoor_sport",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.cycling.about_me", language),
            "comment_text": t("config.sport_fields.common.comment", language),
            "level_text": None
        },
        
        # === ВСТРЕЧИ И ОБЩЕНИЕ ===
        "☕️Бизнес-завтрак": {
            "category": "meeting",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": False,
            "about_me_text": None,
            "comment_text": t("config.sport_fields.business_breakfast.comment", language),
            "level_text": None,
            "has_meeting_time": True,
            "meeting_time_text": t("config.sport_fields.business_breakfast.meeting_time", language)
        },
        "🍻По пиву": {
            "category": "meeting",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": False,
            "about_me_text": None,
            "comment_text": t("config.sport_fields.beer.comment", language),
            "level_text": None,
            "has_meeting_time": True,
            "meeting_time_text": t("config.sport_fields.beer.meeting_time", language)
        },
        
        # === ЗНАКОМСТВА ===
        "🍒Знакомства": {
            "category": "dating",
            "has_level": False,
            "has_role": False,
            "has_payment": False,
            "has_vacation": False,
            "has_about_me": True,
            "about_me_text": t("config.sport_fields.dating.about_me", language),
            "comment_text": t("config.sport_fields.dating.comment", language),
            "level_text": None,
            "has_dating_goals": True,
            "has_interests": True,
            "has_additional_fields": True
        }
    }

# Для обратной совместимости (русская версия по умолчанию)
SPORT_FIELD_CONFIG = get_sport_field_config(language="ru")

def get_dating_goals(language: str = "ru") -> list:
    """Возвращает цели знакомств с учетом языка"""
    return [
        t("config.dating_goals.relationship", language),
        t("config.dating_goals.communication", language),
        t("config.dating_goals.friendship", language),
        t("config.dating_goals.never_know", language)
    ]

def get_dating_interests(language: str = "ru") -> list:
    """Возвращает интересы для знакомств с учетом языка"""
    return [
        t("config.dating_interests.travel", language),
        t("config.dating_interests.music", language),
        t("config.dating_interests.cinema", language),
        t("config.dating_interests.coffee", language),
        t("config.dating_interests.guitar", language),
        t("config.dating_interests.skiing", language),
        t("config.dating_interests.board_games", language),
        t("config.dating_interests.quizzes", language)
    ]

def get_dating_additional_fields(language: str = "ru") -> list:
    """Возвращает дополнительные поля для знакомств с учетом языка"""
    return [
        t("config.dating_additional.work", language),
        t("config.dating_additional.education", language),
        t("config.dating_additional.height", language),
        t("config.dating_additional.zodiac", language),
        t("config.dating_additional.habits", language)
    ]

# Для обратной совместимости
# Цели знакомств
DATING_GOALS = [
    "Отношения",
    "Общение", 
    "Дружба",
    "Никогда не знаешь, что будет"
]

# Интересы для знакомств
DATING_INTERESTS = [
    "Путешествия",
    "Музыка",
    "Кино", 
    "Кофе",
    "Гитара",
    "Горные лыжи",
    "Настолки",
    "Квизы"
]

# Дополнительные поля для знакомств (необязательные)
DATING_ADDITIONAL_FIELDS = [
    "Работа / Профессия",
    "Образование: Вуз или уровень образования",
    "Рост",
    "Зодиак, Знак зодиака",
    "Вредные привычки: Отношение к курению, алкоголю"
]

def get_sport_config(sport: str, language: str = "ru") -> dict:
    """Получает конфигурацию полей для выбранного вида спорта с учетом языка"""
    config = get_sport_field_config(language)
    return config.get(sport, config["🎾Большой теннис"])

def get_sport_texts(sport: str, language: str = "ru") -> dict:
    """Получает тексты для выбранного вида спорта (переведенные)"""
    config = get_sport_config(sport, language)
    category = config.get("category", "court_sport")
    
    if category == "dating":
        return {
            "offer_button": t("game_offers.dating.offer_button", language),
            "my_offers_button": t("game_offers.dating.my_offers_button", language),
            "offer_title": t("game_offers.dating.offer_title", language),
            "my_offers_title": t("game_offers.dating.my_offers_title", language),
            "no_offers_text": t("game_offers.dating.no_offers_text", language),
            "city_prompt": t("game_offers.dating.city_prompt", language),
            "offer_created": t("game_offers.dating.offer_created", language),
            "offer_prefix": t("game_offers.dating.offer_prefix", language)
        }
    elif category == "meeting":
        if sport == "☕️Бизнес-завтрак":
            return {
                "offer_button": t("game_offers.meeting.business.offer_button", language),
                "my_offers_button": t("game_offers.meeting.business.my_offers_button", language),
                "offer_title": t("game_offers.meeting.business.offer_title", language),
                "my_offers_title": t("game_offers.meeting.business.my_offers_title", language),
                "no_offers_text": t("game_offers.meeting.business.no_offers_text", language),
                "city_prompt": t("game_offers.meeting.business.city_prompt", language),
                "offer_created": t("game_offers.meeting.business.offer_created", language),
                "offer_prefix": t("game_offers.meeting.business.offer_prefix", language)
            }
        else:  # По пиву
            return {
                "offer_button": t("game_offers.meeting.beer.offer_button", language),
                "my_offers_button": t("game_offers.meeting.beer.my_offers_button", language),
                "offer_title": t("game_offers.meeting.beer.offer_title", language),
                "my_offers_title": t("game_offers.meeting.beer.my_offers_title", language),
                "no_offers_text": t("game_offers.meeting.beer.no_offers_text", language),
                "city_prompt": t("game_offers.meeting.beer.city_prompt", language),
                "offer_created": t("game_offers.meeting.beer.offer_created", language),
                "offer_prefix": t("game_offers.meeting.beer.offer_prefix", language)
            }
    elif category == "outdoor_sport":
        return {
            "offer_button": t("game_offers.outdoor.offer_button", language),
            "my_offers_button": t("game_offers.outdoor.my_offers_button", language),
            "offer_title": t("game_offers.outdoor.offer_title", language),
            "my_offers_title": t("game_offers.outdoor.my_offers_title", language),
            "no_offers_text": t("game_offers.outdoor.no_offers_text", language),
            "city_prompt": t("game_offers.outdoor.city_prompt", language),
            "offer_created": t("game_offers.outdoor.offer_created", language),
            "offer_prefix": t("game_offers.outdoor.offer_prefix", language)
        }
    else:  # court_sport
        return {
            "offer_button": t("game_offers.court.offer_button", language),
            "my_offers_button": t("game_offers.court.my_offers_button", language),
            "offer_title": t("game_offers.court.offer_title", language),
            "my_offers_title": t("game_offers.court.my_offers_title", language),
            "no_offers_text": t("game_offers.court.no_offers_text", language),
            "city_prompt": t("game_offers.court.city_prompt", language),
            "offer_created": t("game_offers.court.offer_created", language),
            "offer_prefix": t("game_offers.court.offer_prefix", language)
        }

def get_base_keyboard(sport: str = "🎾Большой теннис", language: str = "ru") -> ReplyKeyboardMarkup:
    """Возвращает базовую клавиатуру (переводится по language)"""
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu.search_partner", language)),
                KeyboardButton(text=t("menu.game_offers", language))
            ],
            [
                KeyboardButton(text=t("menu.tournaments", language)),
                KeyboardButton(text=t("menu.enter_score", language))
            ],
            [
                KeyboardButton(text=t("menu.invite", language)),
                KeyboardButton(text=t("menu.payments", language))
            ],
            [
                KeyboardButton(text=t("menu.more", language))
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# Для обратной совместимости
base_keyboard = get_base_keyboard(language="ru")
