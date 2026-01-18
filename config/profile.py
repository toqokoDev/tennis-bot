from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.translations import t, load_translations

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

# Конфигурация полей для каждого вида спорта
SPORT_FIELD_CONFIG = {
    # === СПОРТИВНЫЕ ВИДЫ С КОРТАМИ И ОПЛАТОЙ ===
    "🎾Большой теннис": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "tennis",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе:",
        "comment_text": "• Комментарий:",
        "level_text": "Уровень игры от 1.0 до 7.0"
    },
    "🏓Настольный теннис": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "table_tennis_rating",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": "Укажите ваш рейтинг (цифры):"
    },
    "🏸Бадминтон": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "tennis",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": "Уровень игры от 1.0 до 7.0"
    },
    "🏖️Пляжный теннис": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "tennis",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": "Уровень игры от 1.0 до 7.0"
    },
    "🎾Падл-теннис": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "tennis",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": "Уровень игры от 1.0 до 7.0"
    },
    "🥎Сквош": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "tennis",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": "Уровень игры от 1.0 до 7.0"
    },
    "🏆Пиклбол": {
        "category": "court_sport",
        "has_level": True,
        "level_type": "tennis",
        "has_role": True,
        "has_payment": True,
        "has_vacation": True,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": "Уровень игры от 1.0 до 7.0"
    },
    
    # === АКТИВНЫЕ ВИДЫ СПОРТА БЕЗ КОРТОВ ===
    "⛳Гольф": {
        "category": "outdoor_sport",
        "has_level": False,
        "has_role": False,
        "has_payment": False,
        "has_vacation": False,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже играете в гольф и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": None
    },
    "🏃‍♂️‍➡️Бег": {
        "category": "outdoor_sport",
        "has_level": False,
        "has_role": False,
        "has_payment": False,
        "has_vacation": False,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже занимаетесь бегом и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": None
    },
    "🏋️‍♀️Фитнес": {
        "category": "outdoor_sport",
        "has_level": False,
        "has_role": False,
        "has_payment": False,
        "has_vacation": False,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже занимаетесь фитнесом и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
        "level_text": None
    },
    "🚴Вело": {
        "category": "outdoor_sport",
        "has_level": False,
        "has_role": False,
        "has_payment": False,
        "has_vacation": False,
        "has_about_me": True,
        "about_me_text": "💬 О себе: Укажите сколько лет вы уже занимаетесь велоспортом или просто катаетесь на велосипеде и как часто в среднем в неделю.",
        "comment_text": "• Комментарий:",
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
        "comment_text": "• Комментарий: Укажите какие проекты вам интересны для обсуждения или коротко опишите ваше предложение по бизнесу, которое вы хотите обсудить во время бизнес-завтрака.",
        "level_text": None,
        "has_meeting_time": True,
        "meeting_time_text": "Напишите место, конкретный день и время или дни недели и временные промежутки, когда вам удобно встретиться."
    },
    "🍻По пиву": {
        "category": "meeting",
        "has_level": False,
        "has_role": False,
        "has_payment": False,
        "has_vacation": False,
        "has_about_me": False,
        "about_me_text": None,
        "comment_text": "• Комментарий: Укажите что бы вы хотели посмотреть или обсудить за пивом, возможно какое-то событие в мире спорта.",
        "level_text": None,
        "has_meeting_time": True,
        "meeting_time_text": "Напишите место, конкретный день и время или дни недели и временные промежутки, когда вам удобно встретиться."
    },
    
    # === ЗНАКОМСТВА ===
    "🍒Знакомства": {
        "category": "dating",
        "has_level": False,
        "has_role": False,
        "has_payment": False,
        "has_vacation": False,
        "has_about_me": True,
        "about_me_text": "💬 О себе:",
        "comment_text": "• Комментарий:",
        "level_text": None,
        "has_dating_goals": True,
        "has_interests": True,
        "has_additional_fields": True
    }
}

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

def get_sport_config(sport: str) -> dict:
    """Получает конфигурацию полей для выбранного вида спорта"""
    return SPORT_FIELD_CONFIG.get(sport, SPORT_FIELD_CONFIG["🎾Большой теннис"])

def get_sport_texts(sport: str, language: str = "ru") -> dict:
    """Получает тексты для выбранного вида спорта (переведенные)"""
    config = get_sport_config(sport)
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
