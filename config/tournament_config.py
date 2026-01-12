from utils.translations import t

def get_tournament_types(language: str = "ru") -> list:
    """Возвращает типы турниров с учетом языка"""
    return [
        t("config.tournament_types.olympic", language),
        t("config.tournament_types.round_robin", language)
    ]

def get_tournament_genders(language: str = "ru") -> list:
    """Возвращает полы участников турнира с учетом языка"""
    return [
        t("config.tournament_genders.men", language),
        t("config.tournament_genders.women", language),
        t("config.tournament_genders.men_pair", language),
        t("config.tournament_genders.women_pair", language),
        t("config.tournament_genders.mixed", language)
    ]

def get_tournament_categories(language: str = "ru") -> list:
    """Возвращает категории турниров с учетом языка"""
    return [
        t("config.tournament_categories.category_3", language),
        t("config.tournament_categories.category_2", language),
        t("config.tournament_categories.category_1", language),
        t("config.tournament_categories.masters", language),
        t("config.tournament_categories.pro", language),
        t("config.tournament_categories.no_category", language)
    ]

def get_category_levels(language: str = "ru") -> dict:
    """Возвращает маппинг категорий к уровням с учетом языка"""
    return {
        t("config.tournament_categories.category_3", language): "1.5-2.5",
        t("config.tournament_categories.category_2", language): "2.5-3.5",
        t("config.tournament_categories.category_1", language): "3.5-4.5",
        t("config.tournament_categories.masters", language): "4.5-5.5",
        t("config.tournament_categories.pro", language): "5.5-7.0",
        t("config.tournament_categories.no_category", language): t("config.tournament_categories.no_level", language)
    }

def get_age_groups(language: str = "ru") -> list:
    """Возвращает возрастные группы с учетом языка"""
    return [
        t("config.tournament_age_groups.adults", language),
        t("config.tournament_age_groups.children", language)
    ]

def get_tournament_durations(language: str = "ru") -> list:
    """Возвращает продолжительность турниров с учетом языка"""
    return [
        t("config.tournament_durations.multi_day", language),
        t("config.tournament_durations.one_day", language),
        t("config.tournament_durations.away", language)
    ]

def get_yes_no_options(language: str = "ru") -> list:
    """Возвращает опции Да/Нет с учетом языка"""
    return [
        t("common.yes", language),
        t("common.no", language)
    ]

# Для обратной совместимости
# Типы турниров
TOURNAMENT_TYPES = ["Олимпийская система", "Круговая"]

# Пол участников
GENDERS = ["Мужчины", "Женщины", "Мужская пара", "Женская пара", "Микст"]

# Категории турниров
CATEGORIES = [
    "1 категория", "2 категория", "3 категория", "Мастерс", "Профи", "Без категории"
]

# Маппинг категорий к уровням
CATEGORY_LEVELS = {
    "3 категория": "1.5-2.5",
    "2 категория": "2.5-3.5", 
    "1 категория": "3.5-4.5",
    "Мастерс": "4.5-5.5",
    "Профи": "5.5-7.0",
    "Без категории": "Без уровня"
}

# Возрастные группы
AGE_GROUPS = ["Взрослые", "Дети"]

# Продолжительность турниров
DURATIONS = ["Многодневные", "Однодневные", "Выездной"]

# Опции Да/Нет
YES_NO_OPTIONS = ["Да", "Нет"]

# Районы Москвы
DISTRICTS_MOSCOW = ["Север", "Юг", "Запад", "Восток"]

# Минимальное количество участников для разных типов турниров
MIN_PARTICIPANTS = {
    "Олимпийская система": 4,  # Минимум 4 участника для олимпийской системы
    "Круговая": 4  # Минимум 4 участника для круговой системы
}
