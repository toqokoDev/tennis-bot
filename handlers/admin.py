from datetime import datetime
import asyncio
import re
from html import escape as html_escape
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
import os
import logging

from utils.tournament_manager import tournament_manager
from utils.tournament_lifecycle import admin_sort_tournament_items, participants_count_label
from services.storage import storage
from utils.admin import get_confirmation_keyboard, is_admin
from handlers.profile import calculate_level_from_points
from models.states import AdminEditGameStates, AdminBroadcastStates
from services.channels import send_game_notification_to_channel
from utils.translations import get_user_language_async, t

admin_router = Router()
logger = logging.getLogger(__name__)

# Пагинация для списка игр
GAMES_PER_PAGE = 10

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """
    Безопасное редактирование сообщения с обработкой ошибок
    """
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        except Exception as e2:
            logger.error(f"Не удалось отправить новое сообщение: {e2}")
            return False

async def safe_send_message(message: Message, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """
    Безопасная отправка сообщения
    """
    try:
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение: {e}")
        return False

# Меню просмотра заявок
@admin_router.callback_query(F.data == "admin_view_applications")
async def view_applications_menu(callback: CallbackQuery):
    language = await get_user_language_async(str(callback.message.chat.id))
    if not await is_admin(callback.message.chat.id):
        await callback.answer(t("admin.no_admin_rights", language))
        return
    await safe_edit_message(callback, t("admin.applications_disabled", language))
    await callback.answer()

# Меню принятия заявки
@admin_router.callback_query(F.data == "admin_accept_application_menu")
async def accept_application_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback, t("admin.applications_disabled", language))
    await callback.answer()

# Обработчик принятия заявки
@admin_router.callback_query(F.data.startswith("admin_accept_application:"))
async def accept_application_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback, t("admin.applications_disabled", language))
    await callback.answer()

# Меню отклонения заявки
@admin_router.callback_query(F.data == "admin_reject_application_menu")
async def reject_application_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback, t("admin.applications_disabled", language))
    await callback.answer()

# Обработчик отклонения заявки
@admin_router.callback_query(F.data.startswith("admin_reject_application:"))
async def reject_application_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback, t("admin.applications_disabled", language))
    await callback.answer()

# Меню удаления турнира
@admin_router.callback_query(F.data == "admin_delete_tournament_menu")
async def delete_tournament_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    # Начинаем с первой страницы
    await show_delete_tournaments_page(callback, page=0)

async def show_delete_tournaments_page(callback: CallbackQuery, page: int = 0):
    """Показывает страницу со списком турниров для удаления с пагинацией"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_tournaments", language))
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
        name = tournament_data.get('name', 'Без названия')
        
        # Формируем место проведения
        if city == "Москва" and district:
            location = f"{city}, {district}"
        elif city and country:
            location = f"{city}, {country}"
        else:
            location = city or 'Не указано'
        
        # Извлекаем номер из названия турнира
        number_match = re.search(r'№(\d+)', name)
        tournament_number = number_match.group(1) if number_match else '?'
        
        text = f"🗑️ №{tournament_number} | {level} | {location} | {participants_count_label(tournament_data)}"
        builder.button(text=text, callback_data=f"admin_delete_tournament:{tournament_id}")
    
    builder.adjust(1)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_delete_tournaments_page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_delete_tournaments_page:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    language = await get_user_language_async(str(callback.message.chat.id))
    builder.row(InlineKeyboardButton(text=t("admin.back", language), callback_data="admin_back_to_tournaments"))
    
    text = t("admin.select_tournament_to_delete", language, page=page + 1, total_pages=total_pages, total=total_tournaments)
    
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()

# Обработчик пагинации для удаления турниров
@admin_router.callback_query(F.data.startswith("admin_delete_tournaments_page:"))
async def admin_delete_tournaments_page_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    page = int(callback.data.split(":", 1)[1])
    await show_delete_tournaments_page(callback, page=page)

# Обработчик удаления турнира
@admin_router.callback_query(F.data.startswith("admin_delete_tournament:"))
async def delete_tournament_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.tournament_not_found", language))
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Формируем информацию о месте
    import re
    city = tournament_data.get('city', 'Не указан')
    district = tournament_data.get('district', '')
    country = tournament_data.get('country', '')
    name = tournament_data.get('name', 'Без названия')
    level = tournament_data.get('level', 'Не указан')
    
    # Извлекаем номер из названия турнира
    number_match = re.search(r'№(\d+)', name)
    tournament_number = number_match.group(1) if number_match else '?'
    
    # Формируем место проведения
    if city == "Москва" and district:
        location = f"{city} ({district})"
    else:
        location = f"{city}, {country}"
    
    # Создаем клавиатуру подтверждения
    keyboard = await get_confirmation_keyboard("delete_tournament", tournament_id)
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить турнир?\n\n"
        f"🎯 Название: {name}\n"
        f"🔢 Номер: {tournament_number}\n"
        f"📊 Уровень: {level}\n"
        f"📍 Место: {location}\n"
        f"👥 Участников: {participants_count_label(tournament_data)}\n\n"
        "Это действие удалит все данные о турнире!",
        keyboard
    )
    await callback.answer()

# Подтверждение удаления турнира
@admin_router.callback_query(F.data.startswith("admin_confirm_delete_tournament:"))
async def confirm_delete_tournament(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.tournament_not_found", language))
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Формируем информацию о месте
    import re
    city = tournament_data.get('city', 'Не указан')
    district = tournament_data.get('district', '')
    country = tournament_data.get('country', '')
    name = tournament_data.get('name', 'Без названия')
    level = tournament_data.get('level', 'Не указан')
    
    # Извлекаем номер из названия турнира
    number_match = re.search(r'№(\d+)', name)
    tournament_number = number_match.group(1) if number_match else '?'
    
    # Формируем место проведения
    if city == "Москва" and district:
        location = f"{city} ({district})"
    else:
        location = f"{city}, {country}"
    
    # Удаляем турнир
    del tournaments[tournament_id]
    await storage.save_tournaments(tournaments)
    
    await safe_edit_message(
        callback,
        f"✅ Турнир удален!\n\n"
        f"🎯 Название: {name}\n"
        f"🔢 Номер: {tournament_number}\n"
        f"📊 Уровень: {level}\n"
        f"📍 Место: {location}\n\n"
        f"Все данные о турнире удалены из системы."
    )
    await callback.answer()

# Кнопка назад к турнирам
@admin_router.callback_query(F.data == "admin_back_to_tournaments")
async def back_to_tournaments(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await safe_edit_message(callback, t("admin.tournaments_list_empty", language))
        return
    
    import re
    text = "🏆 Активные турниры:\n\n"
    for tournament_id, tournament_data in admin_sort_tournament_items(list(tournaments.items())):
        city = tournament_data.get('city', 'Не указан')
        district = tournament_data.get('district', '')
        country = tournament_data.get('country', '')
        name = tournament_data.get('name', 'Без названия')
        level = tournament_data.get('level', 'Не указан')
        
        # Извлекаем номер из названия турнира
        number_match = re.search(r'№(\d+)', name)
        tournament_number = number_match.group(1) if number_match else '?'
        
        # Формируем место проведения
        if city == "Москва" and district:
            location = f"{city} ({district})"
        else:
            location = f"{city}, {country}"
        
        text += f"🎯 {name}\n"
        text += f"🔢 Номер: {tournament_number}\n"
        text += f"📊 Уровень: {level}\n"
        text += f"📍 Место: {location}\n"
        text += f"👥 Участников: {participants_count_label(tournament_data)}\n"
        text += f"🆔 ID: {tournament_id}\n"
        text += "─" * 20 + "\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Создать турнир", callback_data="admin_create_tournament")
    builder.button(text="🗑️ Удалить турнир", callback_data="admin_delete_tournament_menu")
    builder.adjust(1)
    
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()
    
# Команда для просмотра забаненных пользователей
@admin_router.message(Command("banned_users"))
async def banned_users_cmd(message: Message):
    if not await is_admin(message.from_user.id):
        language = await get_user_language_async(str(message.chat.id))
        await safe_send_message(message, t("admin.no_admin_rights", language))
        return
    
    banned_users = await storage.load_banned_users()
    
    if not banned_users:
        await safe_send_message(message, "📋 Список забаненных пользователей пуст.")
        return
    
    text = "🚫 Забаненные пользователи:\n\n"
    for user_id, ban_data in banned_users.items():
        text += f"👤 {ban_data.get('first_name', '')} {ban_data.get('last_name', '')}\n"
        text += f"📞 {ban_data.get('phone', '')}\n"
        text += f"🆔 ID: {user_id}\n"
        text += f"⏰ Забанен: {ban_data.get('banned_at', 'Неизвестно')}\n"
        text += "─" * 20 + "\n"
    
    # Добавляем кнопку для разбана
    builder = InlineKeyboardBuilder()
    builder.button(text="🔓 Разбанить пользователя", callback_data="admin_unban_menu")
    builder.button(text="🗑️ Очистить список банов", callback_data="admin_clear_all_bans")
    builder.adjust(1)
    
    await safe_send_message(message, text, builder.as_markup())

# Команда для разбана пользователя
@admin_router.message(Command("unban_user"))
async def unban_user_cmd(message: Message):
    if not await is_admin(message.from_user.id):
        language = await get_user_language_async(str(message.chat.id))
        await safe_send_message(message, t("admin.no_admin_rights", language))
        return
    
    await show_unban_menu(message)

async def show_unban_menu(message: Message):
    banned_users = await storage.load_banned_users()
    
    if not banned_users:
        await safe_send_message(message, "📋 Список забаненных пользователей пуст.")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, ban_data in banned_users.items():
        name = f"{ban_data.get('first_name', '')} {ban_data.get('last_name', '')}"
        builder.button(text=f"🔓 {name}", callback_data=f"admin_unban_user:{user_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_send_message(
        message,
        "🔓 Выберите пользователя для разбана:",
        builder.as_markup()
    )

# Отмена действия
@admin_router.callback_query(F.data == "admin_cancel")
async def cancel_action(callback: CallbackQuery):
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback, t("admin.action_cancelled", language))
    await callback.answer()

# Клавиатура админской панели
def get_admin_keyboard(language=None):
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Забаненные пользователи", callback_data="admin_banned_list")
    builder.button(text="📢 Рассылка объявления", callback_data="admin_broadcast_menu")
    builder.button(text="➕ Создать турнир", callback_data="admin_create_tournament")
    builder.button(text="✏️ Управление турнирами", callback_data="admin_edit_tournaments")
    builder.adjust(1)
    return builder.as_markup()

# Обработчик кнопки создания турнира в админской панели
@admin_router.callback_query(F.data == "admin_create_tournament")
async def admin_create_tournament_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки создания турнира в админской панели"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    # Перенаправляем на обработчик создания турнира из tournament.py
    from handlers.tournament import create_tournament_callback
    await create_tournament_callback(callback, state)

# Обработчик кнопки турниров в админской панели
@admin_router.callback_query(F.data == "admin_tournaments")
async def tournaments_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        language = await get_user_language_async(str(callback.message.chat.id))
        await safe_edit_message(callback, t("admin.tournaments_list_empty", language))
        return
    
    import re
    text = "🏆 Активные турниры:\n\n"
    for tournament_id, tournament_data in admin_sort_tournament_items(list(tournaments.items())):
        # Формируем информацию о турнире
        city = tournament_data.get('city', 'Не указан')
        district = tournament_data.get('district', '')
        country = tournament_data.get('country', 'Не указана')
        name = tournament_data.get('name', 'Без названия')
        level = tournament_data.get('level', 'Не указан')
        
        # Извлекаем номер из названия турнира
        number_match = re.search(r'№(\d+)', name)
        tournament_number = number_match.group(1) if number_match else '?'
        
        # Формируем место проведения
        if city == "Москва" and district:
            location = f"{city} ({district})"
        else:
            location = f"{city}, {country}"
        
        text += f"🏆 {name}\n"
        text += f"🔢 Номер: {tournament_number}\n"
        text += f"📊 Уровень: {level}\n"
        text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
        text += f"🌍 Место: {location}\n"
        text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
        text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
        text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
        text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
        text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
        text += f"👥 Участников: {participants_count_label(tournament_data)}\n"
        text += f"📋 В списке города: {'Да' if tournament_data.get('show_in_list', False) else 'Нет'}\n"
        text += f"🔒 Скрыть сетку: {'Да' if tournament_data.get('hide_bracket', False) else 'Нет'}\n"
        if tournament_data.get('comment'):
            text += f"💬 Комментарий: {tournament_data['comment']}\n"
        text += f"🆔 ID: {tournament_id}\n"
        text += "─" * 30 + "\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Создать турнир", callback_data="admin_create_tournament")
    builder.button(text="🗑️ Удалить турнир", callback_data="admin_delete_tournament_menu")
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()

# Команда админской панели
@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        language = await get_user_language_async(str(message.chat.id))
        await safe_send_message(message, t("admin.no_admin_rights", language))
        return
    
    language = await get_user_language_async(str(message.chat.id))
    await safe_send_message(
        message,
        t("admin.admin_panel", language),
        get_admin_keyboard()
    )

# Обработчики кнопок админской панели - меню выбора
@admin_router.callback_query(F.data == "admin_banned_list")
async def banned_list_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    banned_users = await storage.load_banned_users()
    
    if not banned_users:
        await callback.answer("📋 Список забаненных пользователей пуст.")
        return
    
    text = "🚫 Забаненные пользователи:\n\n"
    for user_id, ban_data in banned_users.items():
        text += f"👤 {ban_data.get('first_name', '')} {ban_data.get('last_name', '')}\n"
        text += f"📞 {ban_data.get('phone', '')}\n"
        text += f"🆔 ID: {user_id}\n"
        text += f"⏰ Забанен: {ban_data.get('banned_at', 'Неизвестно')}\n"
        text += "─" * 20 + "\n"
    
    # Добавляем кнопки для управления банами
    builder = InlineKeyboardBuilder()
    builder.button(text="🔓 Разбанить пользователя", callback_data="admin_unban_menu")
    builder.button(text="🗑️ Очистить список банов", callback_data="admin_clear_all_bans")
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()

# ==================== РАССЫЛКА ОБЪЯВЛЕНИЯ ====================

_FORWARD_ALBUM_DEBOUNCE_SEC = 0.9


def _broadcast_input_media_from_item(m: dict):
    """Один элемент сохранённого медиа → InputMedia для send_media_group."""
    from aiogram.types import InputMediaAnimation, InputMediaPhoto, InputMediaVideo

    if m["type"] == "photo":
        return InputMediaPhoto(media=m["file_id"])
    if m["type"] == "animation":
        return InputMediaAnimation(media=m["file_id"])
    # video, video_file (документ с видео)
    return InputMediaVideo(media=m["file_id"])


def _broadcast_media_from_forward_message(message: Message) -> dict | None:
    """Из пересланного сообщения — type + file_id для send_media_group / send_*."""
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id}
    if (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("video/")
    ):
        return {"type": "video_file", "file_id": message.document.file_id}
    if message.animation:
        return {"type": "animation", "file_id": message.animation.file_id}
    return None


def _forward_caption_as_html(message: Message) -> str | None:
    """Подпись к медиа в HTML (как в исходном сообщении)."""
    if not message.caption:
        return None
    # html_text для сообщения с медиа берёт текст из caption
    return message.html_text


def _broadcast_caption_preview(html: str, max_len: int = 120) -> str:
    plain = re.sub(r"<[^>]+>", "", html)
    if len(plain) > max_len:
        return plain[: max_len - 1] + "…"
    return plain


def _merge_forward_caption_from_raw(raw_sorted: list[dict]) -> str | None:
    """В альбоме подпись обычно у одного из сообщений — берём первую по порядку message_id."""
    for x in raw_sorted:
        c = x.get("caption_html")
        if c:
            return c
    return None


def _forward_entry_from_message(message: Message) -> dict:
    """Служебная запись для сбора альбома (сортировка по message_id)."""
    from_chat_id = message.chat.id
    msg_id = message.message_id
    caption_html = _forward_caption_as_html(message)
    media = _broadcast_media_from_forward_message(message)
    if media:
        d: dict = {"message_id": msg_id, "from_chat_id": from_chat_id, **media}
        if caption_html:
            d["caption_html"] = caption_html
        return d
    return {
        "message_id": msg_id,
        "from_chat_id": from_chat_id,
        "copy_only": True,
    }


async def _broadcast_send_one_media(
    bot, uid: int, m: dict, *, caption: str | None = None
):
    """Одно фото/видео/гиф без медиагруппы (send_media_group требует ≥2 элементов)."""
    t = m["type"]
    fid = m["file_id"]
    if t == "photo":
        return await bot.send_photo(
            chat_id=uid,
            photo=fid,
            caption=caption,
            parse_mode="HTML" if caption else None,
        )
    if t == "animation":
        return await bot.send_animation(
            chat_id=uid,
            animation=fid,
            caption=caption,
            parse_mode="HTML" if caption else None,
        )
    return await bot.send_video(
        chat_id=uid,
        video=fid,
        caption=caption,
        parse_mode="HTML" if caption else None,
    )


async def _broadcast_send_media_list_to_user(bot, uid: int, media_list: list, text: str):
    """Отправка списка медиа одному пользователю: альбом объединён в send_media_group (по 10 шт.)."""
    if not media_list:
        if text:
            await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
        return
    for batch_start in range(0, len(media_list), 10):
        chunk = media_list[batch_start : batch_start + 10]
        cap = text if batch_start == 0 else None
        if len(chunk) == 1:
            await _broadcast_send_one_media(bot, uid, chunk[0], caption=cap)
        else:
            media_group = [_broadcast_input_media_from_item(m) for m in chunk]
            if cap and media_group:
                media_group[0].caption = cap
                media_group[0].parse_mode = "HTML"
            await bot.send_media_group(chat_id=uid, media=media_group)


async def _broadcast_send_manual_to_user(bot, uid: int, media_list: list, text: str):
    """Ручная рассылка: те же правила, что и для пересланного альбома."""
    await _broadcast_send_media_list_to_user(bot, uid, media_list, text)


async def _broadcast_show_confirm_forward(
    bot,
    chat_id: int,
    state: FSMContext,
    *,
    media_items: list[dict] | None = None,
    copy_pairs: list[tuple[int, int]] | None = None,
    caption_html: str | None = None,
):
    """Экран подтверждения: либо альбом/медиа через send_media_group, либо copy_message по списку."""
    if media_items is not None:
        cap = caption_html.strip() if caption_html else None
        await state.update_data(
            broadcast_forward_media_items=media_items,
            broadcast_forward_copy_pairs=None,
            broadcast_forward_caption=cap,
        )
        n = len(media_items)
        if n == 1:
            body = (
                "Будет отправлено <b>одно</b> медиа в личку <b>{count}</b> пользователям."
            )
        else:
            body = (
                f"Будет отправлен <b>один альбом</b> из <b>{n}</b> медиа "
                "в личку <b>{count}</b> пользователям (как единая группа)."
            )
    elif copy_pairs is not None:
        await state.update_data(
            broadcast_forward_copy_pairs=copy_pairs,
            broadcast_forward_media_items=None,
            broadcast_forward_caption=None,
        )
        n = len(copy_pairs)
        if n == 1:
            body = (
                "Будет скопировано <b>одно</b> сообщение в личку <b>{count}</b> пользователям."
            )
        else:
            body = (
                f"Будет скопировано <b>{n}</b> сообщений подряд в личку <b>{{count}}</b> "
                "пользователям (без объединения в альбом — в пересылке есть не-медиа)."
            )
    else:
        return

    await state.set_state(AdminBroadcastStates.CONFIRM)
    users = await storage.load_users()
    count = len([k for k in users.keys() if k and str(k).isdigit()])
    body = body.format(count=count)
    caption_hint = ""
    if media_items is not None and caption_html and caption_html.strip():
        preview = _broadcast_caption_preview(caption_html.strip())
        caption_hint = f"\n\n📝 Подпись: «{html_escape(preview)}»"
    text = (
        f"📋 <b>Подтверждение рассылки</b>\n\n"
        f"{body}{caption_hint}\n\n"
        "Нажмите «Разослать» или «Отмена»."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Разослать", callback_data="admin_broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    builder.adjust(1)
    await bot.send_message(chat_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")


async def _debounced_finalize_forward_album(bot, state: FSMContext, chat_id: int, seq: int):
    await asyncio.sleep(_FORWARD_ALBUM_DEBOUNCE_SEC)
    data = await state.get_data()
    if data.get("broadcast_collect_seq") != seq:
        return
    cur = await state.get_state()
    if cur != AdminBroadcastStates.WAIT_FORWARD.state:
        return
    raw = data.get("broadcast_forward_messages_raw") or []
    if not raw:
        return
    raw_sorted = sorted(raw, key=lambda x: x["message_id"])
    if any(x.get("copy_only") for x in raw_sorted):
        copy_pairs = [(x["from_chat_id"], x["message_id"]) for x in raw_sorted]
        await _broadcast_show_confirm_forward(
            bot, chat_id, state, copy_pairs=copy_pairs
        )
    else:
        media_items = [
            {"type": x["type"], "file_id": x["file_id"]} for x in raw_sorted
        ]
        cap = _merge_forward_caption_from_raw(raw_sorted)
        await _broadcast_show_confirm_forward(
            bot, chat_id, state, media_items=media_items, caption_html=cap
        )


@admin_router.callback_query(F.data == "admin_broadcast_menu")
async def admin_broadcast_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора способа рассылки: переслать сообщение или ручное заполнение."""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    await state.clear()
    text = (
        "📢 <b>Рассылка объявления</b>\n\n"
        "Выберите способ:\n\n"
        "1️⃣ <b>Переслать сообщение</b> — перешлите сообщение или <b>альбом</b> "
        "(несколько фото/видео одним пересланием) из канала или чата; "
        "копия уйдёт всем без пометки «переслано».\n\n"
        "2️⃣ <b>Ручное заполнение</b> — фото, видео или видео как файл (можно несколько), "
        "затем текст. После подтверждения при рассылке показывается прогресс «Отправка N/всего»."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Переслать сообщение", callback_data="admin_broadcast_forward")
    builder.button(text="2️⃣ Ручное заполнение", callback_data="admin_broadcast_manual")
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast_forward")
async def admin_broadcast_forward_mode(callback: CallbackQuery, state: FSMContext):
    """Режим рассылки: ожидание пересланного сообщения."""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    await state.update_data(
        broadcast_mode="forward",
        broadcast_forward_chat_id=callback.message.chat.id,
        broadcast_forward_messages_raw=[],
        broadcast_forward_media_items=None,
        broadcast_forward_copy_pairs=None,
        broadcast_forward_caption=None,
        broadcast_collect_seq=0,
        broadcast_media_group_id=None,
    )
    await state.set_state(AdminBroadcastStates.WAIT_FORWARD)
    text = (
        "📨 <b>Переслать сообщение</b>\n\n"
        "Перешлите одно сообщение или альбом (несколько фото/видео) из канала или чата. "
        "Все части альбома соберутся автоматически. "
        "Копия уйдёт всем пользователям бота (без подписи «переслано»)."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    builder.adjust(1)
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast_manual")
async def admin_broadcast_manual_mode(callback: CallbackQuery, state: FSMContext):
    """Режим рассылки: ручное заполнение — сначала медиа, затем текст."""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    await state.update_data(
        broadcast_mode="manual",
        broadcast_media=[],
        broadcast_text="",
        manual_album_raw=[],
        manual_album_group_id=None,
        manual_album_collect_seq=0,
    )
    await state.set_state(AdminBroadcastStates.MANUAL_MEDIA)
    text = (
        "📷 <b>Шаг 1: Медиа</b>\n\n"
        "Отправьте фото и/или видео (можно несколько). "
        "Для каждого загруженного файла появится кнопка удаления. "
        "Когда медиа готовы — нажмите <b>«Готово с медиа → Текст»</b>."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово с медиа → Текст", callback_data="admin_broadcast_media_done")
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    builder.adjust(1)
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast_cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки и возврат в меню."""
    if not await is_admin(callback.message.chat.id):
        await callback.answer()
        return
    await state.clear()
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(
        callback,
        t("admin.admin_panel", language),
        get_admin_keyboard(),
    )
    await callback.answer("Рассылка отменена")


# Ожидание пересланного сообщения (одно или альбом из нескольких фото/видео)
@admin_router.message(AdminBroadcastStates.WAIT_FORWARD, F.forward_date)
async def admin_broadcast_forward_received(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    # Медиа берём из сообщения в чате с админом (file_id) и шлём как единый альбом.
    # Текст/не-медиа — только copy_message по очереди.
    entry = _forward_entry_from_message(message)

    if not message.media_group_id:
        if entry.get("copy_only"):
            await _broadcast_show_confirm_forward(
                message.bot,
                message.chat.id,
                state,
                copy_pairs=[(entry["from_chat_id"], entry["message_id"])],
            )
        else:
            await _broadcast_show_confirm_forward(
                message.bot,
                message.chat.id,
                state,
                media_items=[
                    {"type": entry["type"], "file_id": entry["file_id"]},
                ],
                caption_html=entry.get("caption_html"),
            )
        return

    data = await state.get_data()
    raw = list(data.get("broadcast_forward_messages_raw") or [])
    existing_mgid = data.get("broadcast_media_group_id")
    if existing_mgid is not None and existing_mgid != message.media_group_id:
        raw = []
    raw.append(entry)
    seq = int(data.get("broadcast_collect_seq") or 0) + 1
    await state.update_data(
        broadcast_forward_messages_raw=raw,
        broadcast_media_group_id=message.media_group_id,
        broadcast_collect_seq=seq,
    )
    asyncio.create_task(
        _debounced_finalize_forward_album(message.bot, state, message.chat.id, seq)
    )


@admin_router.message(AdminBroadcastStates.WAIT_FORWARD)
async def admin_broadcast_forward_not_forwarded(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    await message.answer(
        "⚠️ Нужно именно <b>переслать</b> сообщение (из канала или чата), а не отправить новое.",
        parse_mode="HTML",
    )


def _build_broadcast_media_keyboard(media_list: list):
    """Клавиатура со списком медиа и кнопками удаления."""
    builder = InlineKeyboardBuilder()
    for i, m in enumerate(media_list):
        if m["type"] == "photo":
            label = "📷"
        else:
            label = "🎬"
        builder.button(text=f"{label} Удалить {i + 1}", callback_data=f"admin_broadcast_delete_media:{i}")
    builder.adjust(2)  # по 2 кнопки в ряд
    builder.row(
        InlineKeyboardButton(text="✅ Готово с медиа → Текст", callback_data="admin_broadcast_media_done"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin_broadcast_cancel"),
    )
    return builder.as_markup()


async def _manual_media_merge_album_buffer_and_reply(
    bot, state: FSMContext, chat_id: int, raw: list[dict]
):
    """Слить буфер альбома в broadcast_media и отправить одно итоговое сообщение."""
    if not raw:
        return
    raw_sorted = sorted(raw, key=lambda x: x["message_id"])
    new_items = [{"type": x["type"], "file_id": x["file_id"]} for x in raw_sorted]
    data = await state.get_data()
    media_list = list(data.get("broadcast_media", []))
    media_list.extend(new_items)
    cur_seq = int(data.get("manual_album_collect_seq") or 0)
    await state.update_data(
        broadcast_media=media_list,
        manual_album_raw=None,
        manual_album_group_id=None,
        manual_album_collect_seq=cur_seq + 1,
    )
    added = len(new_items)
    await bot.send_message(
        chat_id,
        f"✅ Добавлено из альбома: <b>{added}</b> шт. Всего медиа: <b>{len(media_list)}</b>. "
        "Отправьте ещё или нажмите «Готово с медиа → Текст».",
        reply_markup=_build_broadcast_media_keyboard(media_list),
        parse_mode="HTML",
    )


async def _debounced_finalize_manual_album(bot, state: FSMContext, chat_id: int, seq: int):
    await asyncio.sleep(_FORWARD_ALBUM_DEBOUNCE_SEC)
    data = await state.get_data()
    if int(data.get("manual_album_collect_seq") or 0) != seq:
        return
    cur = await state.get_state()
    if cur != AdminBroadcastStates.MANUAL_MEDIA.state:
        return
    raw = data.get("manual_album_raw") or []
    if not raw:
        return
    await _manual_media_merge_album_buffer_and_reply(bot, state, chat_id, raw)


async def _append_manual_album_media(
    message: Message, state: FSMContext, mtype: str, file_id: str
):
    """Несколько сообщений с одним media_group_id — один ответ после паузы."""
    data = await state.get_data()
    old_gid = data.get("manual_album_group_id")
    raw = list(data.get("manual_album_raw") or [])
    if old_gid is not None and old_gid != message.media_group_id and raw:
        await _manual_media_merge_album_buffer_and_reply(
            message.bot, state, message.chat.id, raw
        )
        data = await state.get_data()
        raw = list(data.get("manual_album_raw") or [])
    msg_id = message.message_id
    raw = list(data.get("manual_album_raw") or [])
    if any(x["message_id"] == msg_id for x in raw):
        return
    raw.append({"message_id": msg_id, "type": mtype, "file_id": file_id})
    data = await state.get_data()
    prev = int(data.get("manual_album_collect_seq") or 0)
    seq = prev + 1
    await state.update_data(
        manual_album_raw=raw,
        manual_album_group_id=message.media_group_id,
        manual_album_collect_seq=seq,
    )
    asyncio.create_task(
        _debounced_finalize_manual_album(message.bot, state, message.chat.id, seq)
    )


# Шаг 1: медиа (с кнопками удаления)
@admin_router.message(AdminBroadcastStates.MANUAL_MEDIA, F.photo)
async def admin_broadcast_manual_photo(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    if message.media_group_id:
        await _append_manual_album_media(
            message, state, "photo", message.photo[-1].file_id
        )
        return
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    file_id = message.photo[-1].file_id
    media_list.append({"type": "photo", "file_id": file_id})
    await state.update_data(broadcast_media=media_list)
    text = f"✅ Добавлено фото. Всего медиа: {len(media_list)}. Отправьте ещё или нажмите «Готово с медиа → Текст»."
    await message.answer(text, reply_markup=_build_broadcast_media_keyboard(media_list))


@admin_router.message(AdminBroadcastStates.MANUAL_MEDIA, F.video)
async def admin_broadcast_manual_video(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    if message.media_group_id:
        await _append_manual_album_media(message, state, "video", message.video.file_id)
        return
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    file_id = message.video.file_id
    media_list.append({"type": "video", "file_id": file_id})
    await state.update_data(broadcast_media=media_list)
    text = f"✅ Добавлено видео. Всего медиа: {len(media_list)}. Отправьте ещё или нажмите «Готово с медиа → Текст»."
    await message.answer(text, reply_markup=_build_broadcast_media_keyboard(media_list))


@admin_router.message(AdminBroadcastStates.MANUAL_MEDIA, F.document)
async def admin_broadcast_manual_video_document(message: Message, state: FSMContext):
    """Видео, отправленное как файл (документ)."""
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    media_list_prev = data.get("broadcast_media", [])
    mime = (message.document.mime_type or "").lower()
    if not mime.startswith("video/"):
        await message.answer(
            "На этом шаге принимаются фото, видео и видео-файлы. "
            "Другие документы не поддерживаются.",
            reply_markup=_build_broadcast_media_keyboard(media_list_prev) if media_list_prev else None,
        )
        return
    if message.media_group_id:
        await _append_manual_album_media(
            message, state, "video_file", message.document.file_id
        )
        return
    media_list = data.get("broadcast_media", [])
    file_id = message.document.file_id
    media_list.append({"type": "video_file", "file_id": file_id})
    await state.update_data(broadcast_media=media_list)
    text = (
        f"✅ Добавлено видео (файл). Всего медиа: {len(media_list)}. "
        "Отправьте ещё или нажмите «Готово с медиа → Текст»."
    )
    await message.answer(text, reply_markup=_build_broadcast_media_keyboard(media_list))


@admin_router.message(AdminBroadcastStates.MANUAL_MEDIA)
async def admin_broadcast_manual_media_other(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    await message.answer(
        "На этом шаге принимаются фото, видео и видео-файлы. Отправьте медиа или нажмите «Готово с медиа → Текст».",
        reply_markup=_build_broadcast_media_keyboard(media_list) if media_list else None,
    )


@admin_router.callback_query(F.data.startswith("admin_broadcast_delete_media:"))
async def admin_broadcast_delete_media(callback: CallbackQuery, state: FSMContext):
    """Удаление элемента медиа по индексу."""
    if not await is_admin(callback.message.chat.id):
        await callback.answer()
        return
    idx = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    if 0 <= idx < len(media_list):
        media_list.pop(idx)
        await state.update_data(broadcast_media=media_list)
    if media_list:
        text = f"🗑 Удалено. Осталось медиа: {len(media_list)}. Отправьте ещё или нажмите «Готово с медиа → Текст»."
        await callback.message.edit_text(text, reply_markup=_build_broadcast_media_keyboard(media_list))
    else:
        text = "📷 Медиа пусто. Отправьте фото или видео."
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Готово с медиа → Текст", callback_data="admin_broadcast_media_done")
        builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
        builder.adjust(1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer("Удалено")


@admin_router.callback_query(F.data == "admin_broadcast_media_done")
async def admin_broadcast_media_done(callback: CallbackQuery, state: FSMContext):
    """Переход от медиа к вводу текста."""
    if not await is_admin(callback.message.chat.id):
        await callback.answer()
        return
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    if not media_list:
        await callback.answer("Добавьте хотя бы одно фото или видео.", show_alert=True)
        return
    await state.set_state(AdminBroadcastStates.MANUAL_TEXT)
    text = (
        "✏️ <b>Шаг 2: Текст</b>\n\n"
        "Введите текст объявления (подпись к медиа или отдельное сообщение). "
        "Можно нажать «Пропустить», если текст не нужен."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить текст", callback_data="admin_broadcast_skip_text")
    builder.button(text="← Назад к медиа", callback_data="admin_broadcast_back_to_media")
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    builder.adjust(1)
    await safe_edit_message(callback, text, builder.as_markup())
    await callback.answer()


# Шаг 2: текст
@admin_router.message(AdminBroadcastStates.MANUAL_TEXT, F.text)
async def admin_broadcast_manual_text(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    await state.update_data(broadcast_text=message.text or "")
    await state.set_state(AdminBroadcastStates.CONFIRM)
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    text = data.get("broadcast_text", "")
    users = await storage.load_users()
    count = len([k for k in users.keys() if k and str(k).isdigit()])
    preview = f"Медиа: {len(media_list)} шт."
    if text:
        preview += f"\nТекст: «{text[:80]}{'…' if len(text) > 80 else ''}»"
    msg_text = (
        f"📋 <b>Подтверждение рассылки</b>\n\n"
        f"{preview}\n\n"
        f"Будет отправлено <b>{count}</b> пользователям.\n\n"
        "Нажмите «Разослать» или «Отмена»."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Разослать", callback_data="admin_broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    builder.adjust(1)
    await message.answer(msg_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_router.message(AdminBroadcastStates.MANUAL_TEXT)
async def admin_broadcast_manual_text_other(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return
    await message.answer("Введите текст объявления или нажмите «Пропустить текст».")


@admin_router.callback_query(F.data == "admin_broadcast_back_to_media")
async def admin_broadcast_back_to_media(callback: CallbackQuery, state: FSMContext):
    """Возврат к шагу медиа."""
    if not await is_admin(callback.message.chat.id):
        await callback.answer()
        return
    await state.set_state(AdminBroadcastStates.MANUAL_MEDIA)
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    text = (
        "📷 <b>Шаг 1: Медиа</b>\n\n"
        f"Загружено: {len(media_list)} шт. Отправьте ещё фото/видео или нажмите «Готово с медиа → Текст»."
    )
    await safe_edit_message(callback, text, _build_broadcast_media_keyboard(media_list))
    await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast_skip_text")
async def admin_broadcast_skip_text(callback: CallbackQuery, state: FSMContext):
    """Пропуск текста — переход к подтверждению."""
    if not await is_admin(callback.message.chat.id):
        await callback.answer()
        return
    await state.update_data(broadcast_text="")
    await state.set_state(AdminBroadcastStates.CONFIRM)
    data = await state.get_data()
    media_list = data.get("broadcast_media", [])
    text = data.get("broadcast_text", "")
    users = await storage.load_users()
    count = len([k for k in users.keys() if k and str(k).isdigit()])
    preview = f"Медиа: {len(media_list)} шт."
    if text:
        preview += f"\nТекст: «{text[:80]}{'…' if len(text) > 80 else ''}»"
    msg_text = (
        f"📋 <b>Подтверждение рассылки</b>\n\n"
        f"{preview}\n\n"
        f"Будет отправлено <b>{count}</b> пользователям.\n\n"
        "Нажмите «Разослать» или «Отмена»."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Разослать", callback_data="admin_broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    builder.adjust(1)
    await safe_edit_message(callback, msg_text, builder.as_markup())
    await callback.answer()


def _broadcast_should_update_progress(i: int, total: int) -> bool:
    """Частота обновления текста прогресса (не спамить editMessage)."""
    if total <= 1:
        return True
    if total <= 100:
        return True
    if total <= 400:
        return i % 3 == 0 or i == total or i == 1
    return i % 8 == 0 or i == total or i == 1


async def _broadcast_try_progress_edit(
    message: Message, current: int, total: int, failed: int
):
    try:
        fail_line = f"\n⚠️ Ошибок: {failed}" if failed else ""
        await message.edit_text(
            f"⏳ <b>Отправка</b> {current}/{total}{fail_line}\n\nПодождите…",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception as e:
        logger.debug(f"Broadcast progress edit: {e}")


@admin_router.callback_query(F.data == "admin_broadcast_confirm")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    """Выполнение рассылки всем пользователям."""
    if not await is_admin(callback.message.chat.id):
        await callback.answer()
        return
    await callback.answer()
    data = await state.get_data()
    mode = data.get("broadcast_mode")
    users = await storage.load_users()
    uid_list = []
    for uid_key in users.keys():
        if not uid_key or not str(uid_key).isdigit():
            continue
        try:
            uid_list.append(int(uid_key))
        except (ValueError, TypeError):
            continue
    sent = 0
    failed = 0
    admin_chat_id = callback.message.chat.id
    recipients = [uid for uid in uid_list if uid != admin_chat_id]
    total = len(recipients)
    if total == 0:
        await state.clear()
        await safe_edit_message(
            callback,
            "✅ Нет получателей (кроме вас). Рассылка не требуется.",
            get_admin_keyboard(),
        )
        return

    await _broadcast_try_progress_edit(callback.message, 0, total, 0)

    copy_pairs = data.get("broadcast_forward_copy_pairs")
    forward_media = data.get("broadcast_forward_media_items")
    if mode == "forward":
        if not copy_pairs and not forward_media:
            if "broadcast_from_chat_id" in data and "broadcast_message_id" in data:
                copy_pairs = [
                    (data["broadcast_from_chat_id"], data["broadcast_message_id"])
                ]
        if not copy_pairs and not forward_media:
            await state.clear()
            await safe_edit_message(
                callback,
                "⚠️ Нет сообщений для рассылки. Откройте рассылку и перешлите сообщение снова.",
                get_admin_keyboard(),
            )
            return

    for i, uid in enumerate(recipients, start=1):
        try:
            if mode == "forward":
                if forward_media:
                    cap = (data.get("broadcast_forward_caption") or "").strip()
                    await _broadcast_send_media_list_to_user(
                        callback.bot, uid, forward_media, cap
                    )
                else:
                    for from_chat_id, msg_id in copy_pairs:
                        await callback.bot.copy_message(
                            chat_id=uid,
                            from_chat_id=from_chat_id,
                            message_id=msg_id,
                        )
            else:
                media_list = data.get("broadcast_media", [])
                text = data.get("broadcast_text", "")
                await _broadcast_send_manual_to_user(
                    callback.bot, uid, media_list, text
                )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast to {uid} failed: {e}")
        if _broadcast_should_update_progress(i, total):
            await _broadcast_try_progress_edit(callback.message, i, total, failed)
        await asyncio.sleep(0.05)

    await state.clear()
    result_text = f"✅ Рассылка завершена. Успешно: {sent}" + (
        f", ошибок: {failed}" if failed else ""
    )
    await safe_edit_message(callback, result_text, get_admin_keyboard())

@admin_router.callback_query(F.data == "admin_unban_menu")
async def unban_menu_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    banned_users = await storage.load_banned_users()
    
    if not banned_users:
        await callback.answer("📋 Список забаненных пользователей пуст.")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, ban_data in banned_users.items():
        name = f"{ban_data.get('first_name', '')} {ban_data.get('last_name', '')}"
        builder.button(text=f"🔓 {name}", callback_data=f"admin_unban_user:{user_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_banned_list")
    builder.adjust(1)
    
    await safe_edit_message(
        callback,
        "🔓 Выберите пользователя для разбана:",
        builder.as_markup()
    )
    await callback.answer()

# Обработчик кнопки редактирования турниров в админской панели
@admin_router.callback_query(F.data == "admin_edit_tournaments")
async def edit_tournaments_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    # Начинаем с первой страницы
    await show_tournaments_page(callback, page=0)

async def show_tournaments_page(callback: CallbackQuery, page: int = 0):
    """Показывает страницу со списком турниров с пагинацией"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await safe_edit_message(callback, "📋 Нет турниров")
        return
    
    import re
    TOURNAMENTS_PER_PAGE = 5
    
    # Преобразуем в список для пагинации (собранные по слотам — выше)
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
        
        button_text = f"№{tournament_number} | {level} | {location} | {participants_count_label(tournament_data)}"
        builder.button(text=button_text, callback_data=f"edit_tournament:{tournament_id}")
    
    builder.adjust(1)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_tournaments_page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_tournaments_page:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔙 К меню", callback_data="admin_back_to_main"))
    
    text = f"🏆 Выберите турнир:\n\nСтраница {page + 1}/{total_pages} (всего: {total_tournaments})"
    
    await safe_edit_message(
        callback,
        text,
        builder.as_markup()
    )
    await callback.answer()

# Обработчик пагинации турниров
@admin_router.callback_query(F.data.startswith("admin_tournaments_page:"))
async def admin_tournaments_page_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    page = int(callback.data.split(":", 1)[1])
    await show_tournaments_page(callback, page=page)

@admin_router.callback_query(F.data == "admin_clear_all_bans")
async def clear_all_bans_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    keyboard = await get_confirmation_keyboard("clear_all_bans")
    await safe_edit_message(
        callback,
        "⚠️ Вы уверены, что хотите очистить ВЕСЬ список банов?\n\n"
        "Это действие разбанит всех пользователей и очистит историю банов.\n\n"
        "Действие необратимо!",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_confirm_clear_all_bans")
async def confirm_clear_all_bans(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    # Очищаем список банов
    await storage.save_banned_users({})
    
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(callback, t("admin.clear_all_bans_success", language))
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_unban_user:"))
async def unban_user_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    user_id = callback.data.split(':')[1]
    banned_users = await storage.load_banned_users()
    
    if user_id not in banned_users:
        await callback.answer("❌ Пользователь не найден в списке банов")
        return
    
    user_data = banned_users[user_id]
    keyboard = await get_confirmation_keyboard("unban_user", user_id)
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите разбанить пользователя?\n\n"
        f"👤 {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📞 {user_data.get('phone', '')}\n"
        f"🆔 ID: {user_id}\n"
        f"⏰ Забанен: {user_data.get('banned_at', 'Неизвестно')}\n\n"
        "Пользователь сможет снова зарегистрироваться в системе.",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_unban_user:"))
async def confirm_unban_user(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    user_id = callback.data.split(':')[1]
    banned_users = await storage.load_banned_users()
    
    if user_id not in banned_users:
        await callback.answer("❌ Пользователь не найден в списке банов")
        return
    
    # Удаляем пользователя из списка банов
    user_data = banned_users.pop(user_id)
    await storage.save_banned_users(banned_users)
    
    await safe_edit_message(
        callback,
        f"✅ Пользователь {user_data.get('first_name', '')} {user_data.get('last_name', '')} успешно разбанен!\n"
        f"🆔 ID: {user_id}\n\n"
        "Теперь пользователь может снова зарегистрироваться в системе."
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_user_menu")
async def delete_user_menu(callback: CallbackQuery):
    users = await storage.load_users()
    
    if not users:
        await callback.answer("❌ Нет пользователей для удаления")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, user_data in users.items():
        name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}"
        builder.button(text=f"🗑️ {name}", callback_data=f"admin_select_user:{user_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, "👥 Выберите пользователя для удаления:", builder.as_markup())
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_game_menu")
async def delete_game_menu(callback: CallbackQuery):
    games = await storage.load_games()
    
    if not games:
        await callback.answer("❌ Нет игр для удаления")
        return
    
    builder = InlineKeyboardBuilder()
    for game in games[:15]:  # Показываем первые 15 игр
        game_id = game.get('id', '')
        date = game.get('date', 'Неизвестно')
        builder.button(text=f"🎾 {date}", callback_data=f"admin_select_game:{game_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, "🎾 Выберите игру для удаления:", builder.as_markup())
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_offer_menu")
async def delete_offer_menu(callback: CallbackQuery):
    users = await storage.load_users()
    offers_list = []
    
    for user_id, user_data in users.items():
        if 'games' in user_data and user_data['games']:
            for game_offer in user_data['games']:
                if game_offer.get('active', True):
                    offers_list.append({
                        'user_id': user_id,
                        'offer_id': game_offer.get('id'),
                        'user_name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                        'date': game_offer.get('date', 'Неизвестно')
                    })
    
    if not offers_list:
        await callback.answer("❌ Нет активных предложений игр")
        return
    
    builder = InlineKeyboardBuilder()
    for offer in offers_list[:15]:  # Показываем первые 15 предложений
        text = f"📋 {offer['user_name']} - {offer['date']}"
        callback_data = f"admin_select_offer:{offer['user_id']}:{offer['offer_id']}"
        builder.button(text=text, callback_data=callback_data)
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, "📋 Выберите предложение для удаления:", builder.as_markup())
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_vacation_menu")
async def delete_vacation_menu(callback: CallbackQuery):
    users = await storage.load_users()
    vacation_users = []
    
    for user_id, user_data in users.items():
        if user_data.get('vacation_tennis'):
            vacation_users.append({
                'user_id': user_id,
                'user_name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                'start': user_data.get('vacation_start', ''),
                'end': user_data.get('vacation_end', '')
            })
    
    if not vacation_users:
        await callback.answer("❌ Нет пользователей в отпуске")
        return
    
    builder = InlineKeyboardBuilder()
    for user in vacation_users:
        text = f"🏖️ {user['user_name']} ({user['start']} - {user['end']})"
        builder.button(text=text, callback_data=f"admin_select_vacation:{user['user_id']}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, "🏖️ Выберите пользователя для удаления отпуска:", builder.as_markup())
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_subscription_menu")
async def delete_subscription_menu(callback: CallbackQuery):
    users = await storage.load_users()
    sub_users = []
    
    for user_id, user_data in users.items():
        if user_data.get('subscription', {}).get('active'):
            sub_users.append({
                'user_id': user_id,
                'user_name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                'until': user_data['subscription'].get('until', 'Неизвестно')
            })
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if not sub_users:
        await callback.answer(t("admin.no_subscriptions", language))
        return
    
    builder = InlineKeyboardBuilder()
    for user in sub_users:
        text = f"🔔 {user['user_name']} (до {user['until']})"
        builder.button(text=text, callback_data=f"admin_select_subscription:{user['user_id']}")
    
    builder.button(text=t("admin.back_to_main", language), callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, t("admin.select_subscription_to_delete", language), builder.as_markup())
    await callback.answer()

# Обработка выбора конкретного элемента
@admin_router.callback_query(F.data.startswith("admin_select_user:"))
async def select_user(callback: CallbackQuery):
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.user_not_found", language))
        return
    
    user_data = users[user_id]
    
    # Создаем клавиатуру с опциями удаления и бана
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Удалить", callback_data=f"admin_confirm_delete_user:{user_id}")
    builder.button(text="🚫 Забанить", callback_data=f"admin_ban_user:{user_id}")
    builder.button(text="❌ Отмена", callback_data="admin_cancel")
    builder.adjust(2)
    
    await safe_edit_message(
        callback,
        f"⚠️ Выберите действие для пользователя:\n\n"
        f"👤 {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📞 {user_data.get('phone', '')}\n"
        f"🏆 Рейтинг: {user_data.get('rating_points', 0)}\n"
        f"🎮 Игр сыграно: {user_data.get('games_played', 0)}\n"
        f"📋 Активных предложений: {len(user_data.get('games', []))}\n\n"
        "🚫 Забан - удалит пользователя и добавит в черный список",
        builder.as_markup()
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_select_game:"))
async def select_game(callback: CallbackQuery):
    game_id = callback.data.split(':')[1]
    games = await storage.load_games()
    users = await storage.load_users()
    
    game_to_delete = None
    for game in games:
        if game.get('id') == game_id:
            game_to_delete = game
            break
    
    if not game_to_delete:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.game_not_found", language))
        return
    
    player_names = []
    for team in ['team1', 'team2']:
        for player_id in game_to_delete.get('players', {}).get(team, []):
            if player_id in users:
                user = users[player_id]
                player_names.append(f"{user.get('first_name', '')} {user.get('last_name', '')}")
    
    keyboard = await get_confirmation_keyboard("delete_game", game_id)
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить игру?\n\n"
        f"🆔 ID: {game_id}\n"
        f"📅 Дата: {game_to_delete.get('date', 'Неизвестно')}\n"
        f"🎯 Тип: {game_to_delete.get('type', 'Неизвестно')}\n"
        f"📊 Счет: {game_to_delete.get('score', 'Неизвестно')}\n"
        f"👥 Игроки: {', '.join(player_names)}\n\n"
        "Это действие произведет откат рейтингов участников!",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_select_vacation:"))
async def select_vacation(callback: CallbackQuery):
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.user_not_found", language))
        return
    
    user_data = users[user_id]
    keyboard = await get_confirmation_keyboard("delete_vacation", user_id)
    
    vacation_info = "❌ Отпуск не установлен"
    if user_data.get('vacation_tennis'):
        vacation_info = f"✅ В отпуске\n📅 {user_data.get('vacation_start', '')} - {user_data.get('vacation_end', '')}"
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить отпуск пользователя?\n\n"
        f"👤 {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📞 {user_data.get('phone', '')}\n"
        f"🏖️ Статус: {vacation_info}",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_select_subscription:"))
async def select_subscription(callback: CallbackQuery):
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.user_not_found", language))
        return
    
    user_data = users[user_id]
    keyboard = await get_confirmation_keyboard("delete_subscription", user_id)
    
    sub_info = "❌ Подписка не активна"
    if user_data.get('subscription', {}).get('active'):
        sub_info = f"✅ Активна до: {user_data['subscription'].get('until', 'Неизвестно')}"
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить подписку пользователя?\n\n"
        f"👤 {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📞 {user_data.get('phone', '')}\n"
        f"🔔 Подписка: {sub_info}",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_select_offer:"))
async def select_offer(callback: CallbackQuery):
    try:
        parts = callback.data.split(':')
        user_id = parts[1]
        offer_id = parts[2]
    except IndexError:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.id_format_error", language))
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.user_not_found", language))
        return
    
    user_data = users[user_id]
    offer_to_delete = None
    
    for game_offer in user_data.get('games', []):
        if str(game_offer.get('id')) == offer_id:
            offer_to_delete = game_offer
            break
    
    if not offer_to_delete:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.offer_not_found", language))
        return
    
    keyboard = await get_confirmation_keyboard("delete_offer", f"{user_id}:{offer_id}")
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить предложение игры?\n\n"
        f"👤 Пользователь: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"🆔 ID предложения: {offer_id}\n"
        f"🎯 Спорт: {offer_to_delete.get('sport', 'Настольный теннис')}\n"
        f"📅 Дата: {offer_to_delete.get('date', 'Неизвестно')}\n"
        f"⏰ Время: {offer_to_delete.get('time', 'Неизвестно')}\n"
        f"🏙️ Город: {offer_to_delete.get('city', 'Неизвестно')}\n\n"
        "Действие необратимо!",
        keyboard
    )
    await callback.answer()

# Кнопка назад в главное меню
@admin_router.callback_query(F.data == "admin_back_to_main")
async def back_to_main(callback: CallbackQuery):
    language = await get_user_language_async(str(callback.message.chat.id))
    await safe_edit_message(
        callback,
        t("admin.admin_panel", language),
        get_admin_keyboard(language)
    )
    await callback.answer()

# Обработка подтверждения для отдельных действий
@admin_router.callback_query(F.data.startswith("admin_confirm_delete_user:"))
async def confirm_delete_user(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    games = await storage.load_games()
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if user_id not in users:
        await callback.answer(t("admin.user_not_found_in_bans", language))
        return
    
    user_data = users[user_id]
    
    # Удаляем все игры, связанные с пользователем
    new_games = []
    for game in games:
        # Проверяем, участвует ли пользователь в игре
        user_in_game = False
        for team in ['team1', 'team2']:
            if user_id in game.get('players', {}).get(team, []):
                user_in_game = True
                break
        
        if user_in_game:
            # Откатываем рейтинги для всех участников игры
            for player_id, rating_change in game.get('rating_changes', {}).items():
                if player_id in users:
                    users[player_id]['rating_points'] -= rating_change
                    users[player_id]['games_played'] = max(0, users[player_id].get('games_played', 0) - 1)
                    # Уменьшаем счетчик побед если пользователь был в выигравшей команде
                    if (user_id in game.get('players', {}).get('team1', []) and 
                        game.get('score', '').startswith('6')):
                        users[player_id]['games_wins'] = max(0, users[player_id].get('games_wins', 0) - 1)
        else:
            new_games.append(game)
    
    # Удаление фото профиля
    if user_data.get('photo_path'):
        try:
            os.remove(user_data['photo_path'])
        except:
            pass
    
    # Удаление пользователя
    del users[user_id]
    
    await storage.save_users(users)
    await storage.save_games(new_games)
    
    await safe_edit_message(callback, t("admin.user_deleted", language, user_id=user_id))
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_game:"))
async def confirm_delete_game(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(':')[1]
    users = await storage.load_users()
    games = await storage.load_games()
    
    game_to_delete = None
    new_games = []
    for game in games:
        if game.get('id') == game_id:
            game_to_delete = game
        else:
            new_games.append(game)
    
    if not game_to_delete:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.game_not_found", language))
        return
    
    # Откат рейтингов участников
    for player_id, rating_change in game_to_delete.get('rating_changes', {}).items():
        if player_id in users:
            new_rating = users[player_id]['rating_points'] - rating_change
            users[player_id]['rating_points'] = new_rating
            users[player_id]['player_level'] = calculate_level_from_points(
                int(new_rating), 
                users[player_id].get('sport', '🎾Большой теннис')
            )
            users[player_id]['games_played'] = max(0, users[player_id].get('games_played', 0) - 1)
            # Уменьшаем счетчик побед если пользователь был в выигравшей команде
            if (player_id in game_to_delete.get('players', {}).get('team1', []) and 
                game_to_delete.get('score', '').startswith('6')):
                users[player_id]['games_wins'] = max(0, users[player_id].get('games_wins', 0) - 1)
    
    # Удаление игры
    await storage.save_games(new_games)
    await storage.save_users(users)
    
    await safe_edit_message(callback, f"✅ Игра {game_id} успешно удалена! Рейтинги откачены.")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_vacation:"))
async def confirm_delete_vacation(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if user_id not in users:
        await callback.answer(t("admin.user_not_found_in_bans", language))
        return
    
    # Удаляем данные об отпуске
    users[user_id]['vacation_tennis'] = False
    users[user_id].pop('vacation_start', None)
    users[user_id].pop('vacation_end', None)
    users[user_id].pop('vacation_comment', None)
    
    await storage.save_users(users)
    
    await safe_edit_message(callback, t("admin.vacation_deleted", language, user_id=user_id))
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_subscription:"))
async def confirm_delete_subscription(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if user_id not in users:
        await callback.answer(t("admin.user_not_found_in_bans", language))
        return
    
    # Удаляем подписку
    users[user_id].pop('subscription', None)
    
    await storage.save_users(users)
    
    await safe_edit_message(callback, t("admin.subscription_deleted", language, user_id=user_id))
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_offer:"))
async def confirm_delete_offer(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    try:
        user_id, offer_id = callback.data.split(':')[1], callback.data.split(':')[2]
    except:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.id_format_error", language))
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.user_not_found", language))
        return
    
    # Удаляем предложение из списка игр пользователя
    user_games = users[user_id].get('games', [])
    new_games = [game for game in user_games if str(game.get('id')) != offer_id]
    users[user_id]['games'] = new_games
    
    await storage.save_users(users)
    
    await safe_edit_message(callback, f"✅ Предложение {offer_id} пользователя {user_id} успешно удалено!")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_ban_user:"))
async def ban_user_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.user_not_found", language))
        return
    
    user_data = users[user_id]
    
    # Загружаем список забаненных пользователей
    banned_users = await storage.load_banned_users()
    
    # Добавляем пользователя в бан лист
    banned_users[str(user_id)] = {
        'first_name': user_data.get('first_name', ''),
        'last_name': user_data.get('last_name', ''),
        'username': user_data.get('username', ''),
        'phone': user_data.get('phone', ''),
        'banned_by': callback.message.chat.id,
        'banned_at': datetime.now().isoformat()
    }
    await storage.save_banned_users(banned_users)
    
    # Удаляем пользователя (та же логика что и при удалении)
    games = await storage.load_games()
    new_games = []
    for game in games:
        user_in_game = False
        for team in ['team1', 'team2']:
            if user_id in game.get('players', {}).get(team, []):
                user_in_game = True
                break
        
        if user_in_game:
            for player_id, rating_change in game.get('rating_changes', {}).items():
                if player_id in users:
                    new_rating = users[player_id]['rating_points'] - rating_change
                    users[player_id]['rating_points'] = new_rating
                    users[player_id]['player_level'] = calculate_level_from_points(
                        int(new_rating), 
                        users[player_id].get('sport', '🎾Большой теннис')
                    )
                    users[player_id]['games_played'] = max(0, users[player_id].get('games_played', 0) - 1)
                    if (user_id in game.get('players', {}).get('team1', []) and 
                        game.get('score', '').startswith('6')):
                        users[player_id]['games_wins'] = max(0, users[player_id].get('games_wins', 0) - 1)
        else:
            new_games.append(game)
    
    # Удаление фото профиля
    if user_data.get('photo_path'):
        try:
            os.remove(user_data['photo_path'])
        except:
            pass
    
    # Удаление пользователя
    del users[user_id]
    
    await storage.save_users(users)
    await storage.save_games(new_games)
    
    await safe_edit_message(callback, f"✅ Пользователь {user_id} забанен и удален!")
    await callback.answer()


# ==================== УПРАВЛЕНИЕ ИГРАМИ ====================

@admin_router.callback_query(F.data.startswith("admin_tournament_games:"))
async def admin_tournament_games_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки управления играми турнира"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    await state.update_data(viewing_tournament_id=tournament_id)
    
    # Получаем игры турнира
    games = await storage.load_games()
    tournament_games = [g for g in games if g.get('tournament_id') == tournament_id]
    
    if not tournament_games:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад к турниру", callback_data=f"edit_tournament:{tournament_id}")
        await safe_edit_message(callback, "📋 В этом турнире пока нет сыгранных игр.", builder.as_markup())
        await callback.answer()
        return
    
    await show_games_page(callback.message, page=0, callback=callback, tournament_id=tournament_id, state=state)
    await callback.answer()


async def show_games_page(message: Message, page: int = 0, callback: CallbackQuery = None, tournament_id: str = None, state: FSMContext = None):
    """Показывает страницу со списком игр"""
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Фильтруем игры по турниру, если указан tournament_id
    if tournament_id:
        games = [g for g in games if g.get('tournament_id') == tournament_id]
    
    if not games:
        text = "📋 Список игр пуст."
        if callback:
            await safe_edit_message(callback, text)
        else:
            await safe_send_message(message, text)
        return
    
    # Сортируем игры по дате (новые первые)
    games_sorted = sorted(games, key=lambda x: x.get('date', ''), reverse=True)
    
    total_games = len(games_sorted)
    total_pages = (total_games + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE
    
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * GAMES_PER_PAGE
    end_idx = min(start_idx + GAMES_PER_PAGE, total_games)
    
    games_on_page = games_sorted[start_idx:end_idx]
    
    # Заголовок в зависимости от контекста
    if tournament_id:
        tournaments = await storage.load_tournaments()
        tournament_name = tournaments.get(tournament_id, {}).get('name', 'Неизвестный турнир')
        text = f"🏆 <b>Игры турнира: {tournament_name}</b>\n\n"
    else:
        text = f"🎾 <b>Список игр</b>\n\n"
    
    text += f"Страница {page + 1}/{total_pages} (всего игр: {total_games})\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for idx, game in enumerate(games_on_page, start=start_idx + 1):
        game_id = game.get('id', 'Неизвестно')
        game_type = game.get('type', 'single')
        score = game.get('score', 'Нет счета')
        date = game.get('date', '')
        
        # Форматируем дату
        try:
            dt = datetime.fromisoformat(date)
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except:
            date_str = date[:16] if date else "Неизвестно"
        
        # Получаем имена игроков
        team1 = game.get('players', {}).get('team1', [])
        team2 = game.get('players', {}).get('team2', [])
        
        def get_player_name(player_id):
            user = users.get(player_id, {})
            return f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or player_id
        
        if game_type == 'single':
            type_icon = "👤"
            player1 = get_player_name(team1[0]) if team1 else "?"
            player2 = get_player_name(team2[0]) if team2 else "?"
            players_str = f"{player1} vs {player2}"
        elif game_type == 'double':
            type_icon = "👥"
            players_str = "Парная игра"
        else:
            type_icon = "🏆"
            player1 = get_player_name(team1[0]) if team1 else "?"
            player2 = get_player_name(team2[0]) if team2 else "?"
            players_str = f"{player1} vs {player2}"
        
        button_text = f"{type_icon} {date_str} | {score}"
        builder.button(text=button_text, callback_data=f"admin_view_game:{game_id}")
    
    builder.adjust(1)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        callback_data_prev = f"admin_tournament_games_page:{tournament_id}:{page-1}" if tournament_id else f"admin_games_page:{page-1}"
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data_prev))
    if page < total_pages - 1:
        callback_data_next = f"admin_tournament_games_page:{tournament_id}:{page+1}" if tournament_id else f"admin_games_page:{page+1}"
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=callback_data_next))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Кнопка возврата
    if tournament_id:
        builder.row(InlineKeyboardButton(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🔙 К управлению турнирами", callback_data="admin_edit_tournaments"))
    
    if callback:
        await safe_edit_message(callback, text, reply_markup=builder.as_markup())
    else:
        await safe_send_message(message, text, reply_markup=builder.as_markup())


@admin_router.callback_query(F.data.startswith("admin_tournament_games_page:"))
async def admin_tournament_games_page_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик пагинации списка игр турнира"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    parts = callback.data.split(":")
    tournament_id = parts[1]
    page = int(parts[2])
    
    await show_games_page(callback.message, page=page, callback=callback, tournament_id=tournament_id, state=state)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_games_page:"))
async def admin_games_page_handler(callback: CallbackQuery):
    """Обработчик пагинации списка игр"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    page = int(callback.data.split(":", 1)[1])
    await show_games_page(callback.message, page=page, callback=callback)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_view_game:"))
async def admin_view_game_handler(callback: CallbackQuery):
    """Обработчик просмотра информации об игре"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(":", 1)[1]
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    for g in games:
        if g.get('id') == game_id:
            game = g
            break
    
    if not game:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.game_not_found", language))
        return
    
    # Формируем информацию об игре
    game_type = game.get('type', 'single')
    score = game.get('score', 'Нет счета')
    date = game.get('date', '')
    winner_id = game.get('winner_id')
    tournament_id = game.get('tournament_id')
    media = game.get('media_filename')
    
    # Форматируем дату
    try:
        dt = datetime.fromisoformat(date)
        date_str = dt.strftime("%d.%m.%Y в %H:%M")
    except:
        date_str = date[:16] if date else "Неизвестно"
    
    # Получаем информацию об игроках
    team1 = game.get('players', {}).get('team1', [])
    team2 = game.get('players', {}).get('team2', [])
    
    def get_player_info(player_id):
        user = users.get(player_id, {})
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or player_id
        level = user.get('player_level', '?')
        rating = user.get('rating_points', '?')
        return f"{name} ({level}, {rating} pts)"
    
    text = f"<b>🎾 Информация об игре</b>\n\n"
    text += f"🆔 ID: <code>{game_id}</code>\n"
    text += f"📅 Дата: <b>{date_str}</b>\n"
    
    if game_type == 'single':
        text += f"🎮 Тип: <b>Одиночная игра</b>\n\n"
        if team1 and team2:
            text += f"👤 <b>Игрок 1:</b> {get_player_info(team1[0])}\n"
            text += f"👤 <b>Игрок 2:</b> {get_player_info(team2[0])}\n\n"
    elif game_type == 'double':
        text += f"🎮 Тип: <b>Парная игра</b>\n\n"
        text += f"👥 <b>Команда 1:</b>\n"
        for pid in team1:
            text += f"  • {get_player_info(pid)}\n"
        text += f"\n👥 <b>Команда 2:</b>\n"
        for pid in team2:
            text += f"  • {get_player_info(pid)}\n\n"
    else:
        text += f"🎮 Тип: <b>Турнирная игра</b>\n"
        if tournament_id:
            text += f"🏆 Турнир ID: <code>{tournament_id}</code>\n\n"
        if team1 and team2:
            text += f"👤 <b>Игрок 1:</b> {get_player_info(team1[0])}\n"
            text += f"👤 <b>Игрок 2:</b> {get_player_info(team2[0])}\n\n"
    
    text += f"📊 Счет: <b>{score}</b>\n"
    
    if winner_id:
        winner = users.get(winner_id, {})
        winner_name = f"{winner.get('first_name', '')} {winner.get('last_name', '')}".strip() or winner_id
        text += f"🏆 Победитель: <b>{winner_name}</b>\n"
    else:
        text += f"🏆 Победитель: <i>Не определен</i>\n"
    
    if media:
        text += f"📷 Медиа: <b>Есть</b>\n"
    else:
        text += f"📷 Медиа: <i>Нет</i>\n"
    
    # Кнопки редактирования
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить счет", callback_data=f"admin_edit_score:{game_id}")
    builder.button(text="📷 Изменить медиа", callback_data=f"admin_edit_media:{game_id}")
    builder.button(text="🏆 Изменить победителя", callback_data=f"admin_edit_winner:{game_id}")
    builder.button(text="🗑️ Удалить игру", callback_data=f"admin_delete_game:{game_id}")
    builder.button(text="🔙 К списку игр", callback_data="admin_back_to_games")
    
    # Если это турнирная игра, добавляем кнопку возврата к турниру
    if tournament_id:
        builder.button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
    
    builder.adjust(1)
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_back_to_games")
async def admin_back_to_games_handler(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку игр"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    # Проверяем, смотрим ли мы игры конкретного турнира
    data = await state.get_data()
    tournament_id = data.get('viewing_tournament_id')
    
    if tournament_id:
        await show_games_page(callback.message, page=0, callback=callback, tournament_id=tournament_id, state=state)
    else:
        await show_games_page(callback.message, page=0, callback=callback)
    await callback.answer()


# ==================== РЕДАКТИРОВАНИЕ СЧЕТА ====================

@admin_router.callback_query(F.data.startswith("admin_edit_score:"))
async def admin_edit_score_handler(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования счета"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_SCORE)
    
    games = await storage.load_games()
    game = None
    for g in games:
        if g.get('id') == game_id:
            game = g
            break
    
    current_score = game.get('score', 'Не указан') if game else 'Не указан'
    
    language = await get_user_language_async(str(callback.message.chat.id))
    text = (
        t("admin.edit_score_title", language) +
        t("admin.game_id", language, game_id=game_id) + "\n" +
        t("admin.current_score", language, score=current_score) + "\n\n" +
        t("admin.enter_new_score", language)
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("common.back", language), callback_data=f"admin_view_game:{game_id}")
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.message(AdminEditGameStates.EDIT_SCORE, F.text)
async def admin_edit_score_input(message: Message, state: FSMContext):
    """Обработчик ввода нового счета"""
    language = await get_user_language_async(str(message.from_user.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin.no_admin_rights", language), parse_mode="HTML")
        await state.clear()
        return
    
    new_score = message.text.strip()
    data = await state.get_data()
    game_id = data.get('editing_game_id')
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    game_index = None
    for idx, g in enumerate(games):
        if g.get('id') == game_id:
            game = g
            game_index = idx
            break
    
    if not game:
        await message.answer("❌ Игра не найдена", parse_mode="HTML")
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
        games[game_index]['score'] = new_score
        games[game_index]['sets'] = sets
        
        # Пересчитываем победителя по новому счету
        team1_wins = 0
        team2_wins = 0
        
        for s in sets:
            parts = s.split(':')
            score1 = int(parts[0])
            score2 = int(parts[1])
            
            if score1 > score2:
                team1_wins += 1
            elif score2 > score1:
                team2_wins += 1
        
        team1_players = game.get('players', {}).get('team1', [])
        team2_players = game.get('players', {}).get('team2', [])
        
        # Определяем победителя
        winner_id = None
        winner_name = "Не определен"
        
        if team1_wins > team2_wins and team1_players:
            winner_id = team1_players[0]
            games[game_index]['winner_id'] = winner_id
            if winner_id in users:
                winner_name = f"{users[winner_id].get('first_name', '')} {users[winner_id].get('last_name', '')}".strip()
        elif team2_wins > team1_wins and team2_players:
            winner_id = team2_players[0]
            games[game_index]['winner_id'] = winner_id
            if winner_id in users:
                winner_name = f"{users[winner_id].get('first_name', '')} {users[winner_id].get('last_name', '')}".strip()
        
        # Сохраняем изменения в games.json
        await storage.save_games(games)
        
        # Если это турнирная игра, обновляем данные в tournaments.json
        tournament_id = game.get('tournament_id')
        if tournament_id:
            tournaments = await storage.load_tournaments()
            if tournament_id in tournaments:
                tournament = tournaments[tournament_id]
                # Ищем соответствующий матч в турнире
                if 'matches' in tournament:
                    for match in tournament['matches']:
                        # Сопоставляем по ID или по игрокам
                        match_player1 = match.get('player1_id')
                        match_player2 = match.get('player2_id')
                        game_team1 = team1_players[0] if team1_players else None
                        game_team2 = team2_players[0] if team2_players else None
                        
                        # Проверяем, совпадают ли игроки (в любом порядке)
                        if ((match_player1 == game_team1 and match_player2 == game_team2) or
                            (match_player1 == game_team2 and match_player2 == game_team1)):
                            # Обновляем счет, победителя и статус в матче
                            match['score'] = new_score
                            match['winner_id'] = winner_id
                            match['status'] = 'completed'
                            if 'completed_at' not in match:
                                match['completed_at'] = datetime.now().isoformat()
                            logger.info(f"Обновлен матч {match.get('id')} в турнире {tournament_id}")
                            break
                    
                    # Сохраняем изменения в tournaments.json
                    await storage.save_tournaments(tournaments)
                    logger.info(f"Турнир {tournament_id} обновлен")
                    
                    # Пересобираем сетку и продвигаем раунды
                    await tournament_manager._rebuild_next_round(tournament_id)
                    await tournament_manager.advance_tournament_round(tournament_id)
        
        logger.info(f"Счет игры {game_id} изменен на {new_score}, победитель: {winner_id} ({winner_name})")
        
        # Публикуем в телеграм-канал, если это турнирная игра
        if tournament_id:
            try:
                # Подготавливаем данные для публикации в канал
                # Определяем ID игроков
                player1_id = team1_players[0] if team1_players else None
                player2_id = team2_players[0] if team2_players else None
                
                if player1_id and player2_id:
                    # Определяем кто победил
                    winner_side = 'team1' if team1_wins > team2_wins else 'team2'
                    
                    # Формируем данные для канала в формате как в enter_invoice.py
                    channel_data = {
                        'game_type': 'tournament',
                        'score': new_score,
                        'sets': sets,
                        'winner_side': winner_side,
                        'tournament_id': tournament_id,
                        'opponent1': {'telegram_id': player2_id},
                        'current_user_id': player1_id
                    }
                    
                    # Добавляем медиа если есть
                    media_filename = game.get('media_filename')
                    if media_filename:
                        from config.paths import GAMES_PHOTOS_DIR
                        media_path = os.path.join(GAMES_PHOTOS_DIR, media_filename)
                        if os.path.exists(media_path):
                            # Определяем тип медиа по расширению
                            if media_filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                                from aiogram.types import FSInputFile
                                # Отправляем фото как file_id через бот
                                # Но так как у нас только путь к файлу, пропускаем это
                                pass
                    
                    # Отправляем уведомление в канал
                    
                    await send_game_notification_to_channel(
                        message.bot, 
                        channel_data, 
                        users, 
                        player1_id
                    )

                    logger.info(f"Результат турнирной игры {game_id} опубликован в канал")
            except Exception as e:
                logger.error(f"Ошибка при публикации в канал: {e}")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Просмотр игры", callback_data=f"admin_view_game:{game_id}")
        builder.button(text="🔙 К списку игр", callback_data="admin_back_to_games")
        builder.adjust(1)
        
        success_text = (
            f"✅ <b>Счет игры успешно изменен!</b>\n\n"
            f"🆔 ID: <code>{game_id}</code>\n"
            f"📊 Новый счет: <b>{new_score}</b>\n"
            f"🏆 Победитель: <b>{winner_name}</b>\n"
            f"🎯 Счет по сетам: {team1_wins}:{team2_wins}"
        )
        
        # Добавляем информацию о турнире, если игра турнирная
        if tournament_id:
            success_text += f"\n\n🏆 <i>Данные турнира также обновлены и опубликованы в канал</i>"
        
        await message.answer(
            success_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except ValueError as e:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data=f"admin_view_game:{game_id}")
        
        await message.answer(
            "❌ <b>Неверный формат счета!</b>\n\n"
            "Используйте формат: <code>6:4, 6:2</code>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении счета: {e}")
        await message.answer(
            f"❌ <b>Ошибка при изменении счета:</b> {str(e)}",
            parse_mode="HTML"
        )
    
    await state.clear()


# ==================== РЕДАКТИРОВАНИЕ МЕДИА ====================

@admin_router.callback_query(F.data.startswith("admin_edit_media:"))
async def admin_edit_media_handler(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования медиа"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_MEDIA)
    
    games = await storage.load_games()
    game = None
    for g in games:
        if g.get('id') == game_id:
            game = g
            break
    
    current_media = game.get('media_filename', 'Нет') if game else 'Нет'
    
    text = (
        f"📷 <b>Изменение медиафайла игры</b>\n\n"
        f"🆔 ID: <code>{game_id}</code>\n"
        f"📁 Текущий медиафайл: <code>{current_media}</code>\n\n"
        f"Отправьте новое фото или видео для игры.\n"
        f"Или отправьте текст <code>удалить</code> чтобы удалить медиафайл."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=f"admin_view_game:{game_id}")
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@admin_router.message(AdminEditGameStates.EDIT_MEDIA)
async def admin_edit_media_input(message: Message, state: FSMContext):
    """Обработчик изменения медиафайла"""
    language = await get_user_language_async(str(message.from_user.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin.no_admin_rights", language), parse_mode="HTML")
        await state.clear()
        return
    
    data = await state.get_data()
    game_id = data.get('editing_game_id')
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    game_index = None
    for idx, g in enumerate(games):
        if g.get('id') == game_id:
            game = g
            game_index = idx
            break
    
    if not game:
        await message.answer("❌ Игра не найдена", parse_mode="HTML")
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотр игры", callback_data=f"admin_view_game:{game_id}")
    builder.button(text="🔙 К списку игр", callback_data="admin_back_to_games")
    builder.adjust(1)
    
    if message.text and message.text.lower() == 'удалить':
        # Удаляем медиафайл
        old_media = games[game_index].get('media_filename')
        games[game_index]['media_filename'] = None
        await storage.save_games(games)
        
        # Пытаемся удалить файл с диска
        if old_media:
            try:
                from config.paths import GAMES_PHOTOS_DIR
                file_path = os.path.join(GAMES_PHOTOS_DIR, old_media)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Удален медиафайл: {old_media}")
            except Exception as e:
                logger.warning(f"Не удалось удалить медиафайл: {e}")
        
        await message.answer(
            f"✅ <b>Медиафайл игры удален!</b>\n\n"
            f"🆔 ID: <code>{game_id}</code>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    elif message.photo:
        # Сохраняем новое фото
        from utils.media import save_media_file
        photo = message.photo[-1]
        
        try:
            filename = await save_media_file(message.bot, photo.file_id, 'photo')
            games[game_index]['media_filename'] = filename
            await storage.save_games(games)
            logger.info(f"Сохранено новое фото для игры {game_id}: {filename}")
            
            await message.answer_photo(
                photo=photo.file_id,
                caption=f"✅ <b>Новое фото для игры сохранено!</b>\n\n🆔 ID: <code>{game_id}</code>",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения фото: {e}")
            await message.answer(
                f"❌ <b>Ошибка при сохранении фото:</b> {str(e)}",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
    elif message.video:
        # Сохраняем новое видео
        from utils.media import save_media_file
        video = message.video
        
        try:
            filename = await save_media_file(message.bot, video.file_id, 'video')
            games[game_index]['media_filename'] = filename
            await storage.save_games(games)
            logger.info(f"Сохранено новое видео для игры {game_id}: {filename}")
            
            await message.answer_video(
                video=video.file_id,
                caption=f"✅ <b>Новое видео для игры сохранено!</b>\n\n🆔 ID: <code>{game_id}</code>",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения видео: {e}")
            await message.answer(
                f"❌ <b>Ошибка при сохранении видео:</b> {str(e)}",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
    else:
        await message.answer(
            "❌ Отправьте фото, видео или напишите <code>удалить</code>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    
    await state.clear()


# ==================== РЕДАКТИРОВАНИЕ ПОБЕДИТЕЛЯ ====================

@admin_router.callback_query(F.data.startswith("admin_edit_winner:"))
async def admin_edit_winner_handler(callback: CallbackQuery):
    """Начало редактирования победителя"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    for g in games:
        if g.get('id') == game_id:
            game = g
            break
    
    if not game:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.game_not_found", language))
        return
    
    game_type = game.get('type', 'single')
    team1 = game.get('players', {}).get('team1', [])
    team2 = game.get('players', {}).get('team2', [])
    
    def get_team_names(team_ids):
        names = []
        for pid in team_ids:
            user = users.get(pid, {})
            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or pid
            names.append(name)
        return " + ".join(names) if names else "Неизвестно"
    
    team1_name = get_team_names(team1)
    team2_name = get_team_names(team2)
    
    language = await get_user_language_async(str(callback.message.chat.id))
    text = (
        t("admin.edit_winner_title", language) +
        t("admin.game_id", language, game_id=game_id) + "\n" +
        t("admin.game_score", language, score=game.get('score', t("common.not_specified", language))) + "\n\n" +
        t("admin.select_winner", language)
    )
    
    builder = InlineKeyboardBuilder()
    
    if game_type == 'double':
        builder.button(text=t("admin.team1_winner", language, name=team1_name), callback_data=f"admin_set_winner:{game_id}:team1")
        builder.button(text=t("admin.team2_winner", language, name=team2_name), callback_data=f"admin_set_winner:{game_id}:team2")
    else:
        builder.button(text=t("admin.player1_winner", language, name=team1_name), callback_data=f"admin_set_winner:{game_id}:team1")
        builder.button(text=t("admin.player2_winner", language, name=team2_name), callback_data=f"admin_set_winner:{game_id}:team2")
    
    builder.button(text=t("common.back", language), callback_data=f"admin_view_game:{game_id}")
    builder.adjust(1)
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_set_winner:"))
async def admin_set_winner_handler(callback: CallbackQuery):
    """Установка нового победителя"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    parts = callback.data.split(":")
    game_id = parts[1]
    winner_team = parts[2]  # 'team1' или 'team2'
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    game_index = None
    for idx, g in enumerate(games):
        if g.get('id') == game_id:
            game = g
            game_index = idx
            break
    
    if not game:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.game_not_found", language))
        return
    
    # Устанавливаем нового победителя
    if winner_team == 'team1':
        winner_id = game.get('players', {}).get('team1', [None])[0]
    else:
        winner_id = game.get('players', {}).get('team2', [None])[0]
    
    if winner_id:
        games[game_index]['winner_id'] = winner_id
        await storage.save_games(games)
        
        # Получаем имя победителя
        winner_name = "Неизвестно"
        if winner_id in users:
            winner_name = f"{users[winner_id].get('first_name', '')} {users[winner_id].get('last_name', '')}".strip()
        
        # Если это турнирная игра, обновляем данные в tournaments.json
        tournament_id = game.get('tournament_id')
        if tournament_id:
            tournaments = await storage.load_tournaments()
            if tournament_id in tournaments:
                tournament = tournaments[tournament_id]
                # Ищем соответствующий матч в турнире
                if 'matches' in tournament:
                    team1_players = game.get('players', {}).get('team1', [])
                    team2_players = game.get('players', {}).get('team2', [])
                    game_team1 = team1_players[0] if team1_players else None
                    game_team2 = team2_players[0] if team2_players else None
                    
                    for match in tournament['matches']:
                        match_player1 = match.get('player1_id')
                        match_player2 = match.get('player2_id')
                        
                        # Проверяем, совпадают ли игроки (в любом порядке)
                        if ((match_player1 == game_team1 and match_player2 == game_team2) or
                            (match_player1 == game_team2 and match_player2 == game_team1)):
                            # Обновляем победителя и статус в матче
                            match['winner_id'] = winner_id
                            match['status'] = 'completed'
                            if 'completed_at' not in match:
                                match['completed_at'] = datetime.now().isoformat()
                            logger.info(f"Обновлен победитель матча {match.get('id')} в турнире {tournament_id}")
                            break
                    
                    # Сохраняем изменения в tournaments.json
                    await storage.save_tournaments(tournaments)
                    logger.info(f"Турнир {tournament_id} обновлен")
                    
                    # Пересобираем сетку и продвигаем раунды
                    
                    await tournament_manager._rebuild_next_round(tournament_id)
                    await tournament_manager.advance_tournament_round(tournament_id)
                    
                    # Публикуем обновленный результат в телеграм-канал
                    try:
                        # Определяем ID игроков
                        player1_id = team1_players[0] if team1_players else None
                        player2_id = team2_players[0] if team2_players else None
                        
                        if player1_id and player2_id:
                            # Определяем кто победил
                            winner_side = 'team1' if winner_id == player1_id else 'team2'
                            
                            # Формируем данные для канала
                            channel_data = {
                                'game_type': 'tournament',
                                'score': game.get('score', 'Не указан'),
                                'sets': game.get('sets', []),
                                'winner_side': winner_side,
                                'tournament_id': tournament_id,
                                'opponent1': {'telegram_id': player2_id},
                                'current_user_id': player1_id
                            }
                            
                            # Отправляем уведомление в канал  
                            await send_game_notification_to_channel(
                                callback.message.bot, 
                                channel_data, 
                                users, 
                                player1_id
                            )
                            logger.info(f"Обновленный результат турнирной игры {game_id} опубликован в канал")
                    except Exception as e:
                        logger.error(f"Ошибка при публикации в канал: {e}")
        
        logger.info(f"Победитель игры {game_id} изменен на {winner_id} ({winner_name})")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Просмотр игры", callback_data=f"admin_view_game:{game_id}")
        builder.button(text="🔙 К списку игр", callback_data="admin_back_to_games")
        builder.adjust(1)
        
        success_text = (
            f"✅ <b>Победитель игры успешно изменен!</b>\n\n"
            f"🆔 ID: <code>{game_id}</code>\n"
            f"🏆 Новый победитель: <b>{winner_name}</b> (Команда {winner_team[-1]})"
        )
        
        # Добавляем информацию о турнире, если игра турнирная
        if tournament_id:
            success_text += f"\n\n🏆 <i>Данные турнира также обновлены и опубликованы в канал</i>"
        
        try:
            await callback.message.edit_text(
                success_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            await callback.message.answer(
                success_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
    else:
        await callback.answer("❌ Не удалось определить победителя")
    
    await callback.answer()


# ==================== УДАЛЕНИЕ ИГРЫ ====================

@admin_router.callback_query(F.data.startswith("admin_delete_game:"))
async def admin_delete_game_handler(callback: CallbackQuery):
    """Подтверждение удаления игры"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    text = (
        f"⚠️ <b>Удаление игры</b>\n\n"
        f"🆔 ID: <code>{game_id}</code>\n\n"
        f"Вы уверены, что хотите удалить эту игру?\n"
        f"Это действие <b>нельзя отменить</b>!"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"admin_confirm_delete_game:{game_id}")
    builder.button(text="❌ Отмена", callback_data=f"admin_view_game:{game_id}")
    builder.adjust(1)
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_confirm_delete_game:"))
async def admin_confirm_delete_game_handler(callback: CallbackQuery):
    """Подтвержденное удаление игры"""
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.no_admin_rights", language))
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим и удаляем игру
    game_to_delete = None
    new_games = []
    for g in games:
        if g.get('id') == game_id:
            game_to_delete = g
        else:
            new_games.append(g)
    
    if game_to_delete:
        # Удаляем медиафайл если есть
        media_filename = game_to_delete.get('media_filename')
        if media_filename:
            try:
                from config.paths import GAMES_PHOTOS_DIR
                file_path = os.path.join(GAMES_PHOTOS_DIR, media_filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Удален медиафайл: {media_filename}")
            except Exception as e:
                logger.warning(f"Не удалось удалить медиафайл: {e}")
        
        # Если это турнирная игра, обновляем данные в tournaments.json
        tournament_id = game_to_delete.get('tournament_id')
        if tournament_id:
            tournaments = await storage.load_tournaments()
            if tournament_id in tournaments:
                tournament = tournaments[tournament_id]
                # Ищем соответствующий матч в турнире и сбрасываем его
                if 'matches' in tournament:
                    team1_players = game_to_delete.get('players', {}).get('team1', [])
                    team2_players = game_to_delete.get('players', {}).get('team2', [])
                    game_team1 = team1_players[0] if team1_players else None
                    game_team2 = team2_players[0] if team2_players else None
                    
                    for match in tournament['matches']:
                        match_player1 = match.get('player1_id')
                        match_player2 = match.get('player2_id')
                        
                        # Проверяем, совпадают ли игроки (в любом порядке)
                        if ((match_player1 == game_team1 and match_player2 == game_team2) or
                            (match_player1 == game_team2 and match_player2 == game_team1)):
                            # Сбрасываем результат матча
                            match['winner_id'] = None
                            match['score'] = None
                            match['status'] = 'pending'
                            if 'completed_at' in match:
                                del match['completed_at']
                            logger.info(f"Сброшен матч {match.get('id')} в турнире {tournament_id}")
                            break
                    
                    # Сохраняем изменения в tournaments.json
                    await storage.save_tournaments(tournaments)
                    logger.info(f"Турнир {tournament_id} обновлен после удаления игры")
        
        # Сохраняем изменения
        await storage.save_games(new_games)
        logger.info(f"Игра {game_id} успешно удалена")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 К списку игр", callback_data="admin_back_to_games")
        
        success_text = f"✅ <b>Игра успешно удалена!</b>\n\n🆔 ID: <code>{game_id}</code>"
        
        # Добавляем информацию о турнире, если игра была турнирной
        if tournament_id:
            success_text += f"\n\n🏆 <i>Матч в турнире сброшен</i>"
        
        try:
            await callback.message.edit_text(
                success_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            await callback.message.answer(
                success_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
    else:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin.game_not_found", language))
    
    await callback.answer()
