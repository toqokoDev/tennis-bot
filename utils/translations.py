"""
Утилита для работы с переводами
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Путь к директории с переводами
TRANSLATIONS_DIR = Path(__file__).parent.parent / "translations"

# Кэш переводов
_translations_cache: Dict[str, Dict[str, Any]] = {}


def load_translations(language: str = "ru") -> Dict[str, Any]:
    """Загружает переводы для указанного языка"""
    if language in _translations_cache:
        return _translations_cache[language]
    
    translation_file = TRANSLATIONS_DIR / f"{language}.json"
    
    if not translation_file.exists():
        # Если файл не найден, используем русский как fallback
        if language != "ru":
            return load_translations("ru")
        else:
            return {}
    
    try:
        with open(translation_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
            _translations_cache[language] = translations
            return translations
    except Exception as e:
        print(f"Error loading translations for {language}: {e}")
        if language != "ru":
            return load_translations("ru")
        return {}


def get_translation(key: str, language: str = "ru", **kwargs) -> str:
    """
    Получает перевод по ключу
    
    Args:
        key: Ключ перевода в формате "section.key" или "section.subsection.key" (например, "registration.welcome" или "config.sports.tennis")
        language: Язык перевода ("ru" или "en")
        **kwargs: Параметры для подстановки в строку
    
    Returns:
        Переведенная строка или ключ, если перевод не найден
    """
    translations = load_translations(language)
    
    # Разбиваем ключ на части
    parts = key.split(".")
    if len(parts) < 2:
        return key
    
    # Начинаем с корневого словаря переводов
    current = translations
    
    # Проходим по всем частям ключа, кроме последней
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
            if current is None:
                return key
        else:
            return key
    
    # Получаем финальное значение
    if isinstance(current, dict):
        text = current.get(parts[-1], key)
    else:
        text = key
    
    # Подставляем параметры, если они есть
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, AttributeError):
            # Если не все параметры переданы или text не строка, возвращаем как есть
            pass
    
    return text


def get_user_language(user_id: str, users: Optional[Dict[str, Any]] = None) -> str:
    """
    Получает язык пользователя из профиля
    
    Args:
        user_id: ID пользователя
        users: Словарь пользователей (опционально, для оптимизации)
    
    Returns:
        Код языка ("ru" или "en"), по умолчанию "ru"
    """
    # 1) Пытаемся прочитать язык из отдельного файла языков
    try:
        from services.storage import storage
        import asyncio

        lang = asyncio.run(storage.get_user_language(str(user_id)))
        if lang in {"ru", "en"}:
            return lang
    except Exception:
        pass

    # 2) Fallback: язык в профиле пользователя (users.json)
    if users is None:
        from services.storage import storage
        import asyncio
        users = asyncio.run(storage.load_users())

    user_data = users.get(str(user_id), {})
    return user_data.get("language", "ru")


async def get_user_language_async(user_id: str) -> str:
    """
    Асинхронно получает язык пользователя из профиля
    
    Args:
        user_id: ID пользователя
    
    Returns:
        Код языка ("ru" или "en"), по умолчанию "ru"
    """
    from services.storage import storage

    # 1) Отдельный файл языков
    lang = await storage.get_user_language(str(user_id))
    if lang in {"ru", "en"}:
        return lang

    # 2) Fallback: язык в профиле пользователя
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    return user_data.get("language", "ru")


def t(key: str, language: str = "ru", **kwargs) -> str:
    """
    Короткая функция для получения перевода
    
    Args:
        key: Ключ перевода
        language: Язык перевода
        **kwargs: Параметры для подстановки
    
    Returns:
        Переведенная строка
    """
    return get_translation(key, language, **kwargs)
