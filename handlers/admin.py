from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
import os
import logging

from services.storage import storage
from utils.admin import get_confirmation_keyboard, is_admin

admin_router = Router()
logger = logging.getLogger(__name__)

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    """
    Безопасное редактирование сообщения с обработкой ошибок
    """
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
            return True
        except Exception as e2:
            logger.error(f"Не удалось отправить новое сообщение: {e2}")
            return False

async def safe_send_message(message: Message, text: str, reply_markup=None):
    """
    Безопасная отправка сообщения
    """
    try:
        await message.answer(text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение: {e}")
        return False

# Команда для работы с турнирами
@admin_router.message(Command("tournaments"))
async def tournaments_cmd(message: Message):
    if not await is_admin(message.from_user.id):
        await safe_send_message(message, "❌ У вас нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await safe_send_message(message, "📋 Список турниров пуст.")
        return
    
    text = "🏆 Активные турниры:\n\n"
    for tournament_id, tournament_data in tournaments.items():
        # Формируем информацию о турнире
        location = f"{tournament_data.get('city', 'Не указан')}"
        if tournament_data.get('district'):
            location += f" ({tournament_data['district']})"
        location += f", {tournament_data.get('country', 'Не указана')}"
        
        text += f"🏆 {tournament_data.get('name', 'Без названия')}\n"
        text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
        text += f"🌍 Место: {location}\n"
        text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
        text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
        text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
        text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
        text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
        text += f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
        text += f"📋 В списке города: {'Да' if tournament_data.get('show_in_list', False) else 'Нет'}\n"
        text += f"🔒 Скрыть сетку: {'Да' if tournament_data.get('hide_bracket', False) else 'Нет'}\n"
        if tournament_data.get('comment'):
            text += f"💬 Комментарий: {tournament_data['comment']}\n"
        text += f"🆔 ID: {tournament_id}\n"
        text += "─" * 30 + "\n"
    
    # Добавляем кнопки для управления турнирами
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Создать турнир", callback_data="admin_create_tournament")
    builder.button(text="🗑️ Удалить турнир", callback_data="admin_delete_tournament_menu")
    builder.adjust(1)
    
    await safe_send_message(message, text, builder.as_markup())

# Меню просмотра заявок
@admin_router.callback_query(F.data == "admin_view_applications")
async def view_applications_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    await safe_edit_message(callback, "📋 Система заявок отключена.")
    await callback.answer()

# Меню принятия заявки
@admin_router.callback_query(F.data == "admin_accept_application_menu")
async def accept_application_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    await safe_edit_message(callback, "📋 Система заявок отключена.")
    await callback.answer()

# Обработчик принятия заявки
@admin_router.callback_query(F.data.startswith("admin_accept_application:"))
async def accept_application_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    await safe_edit_message(callback, "📋 Система заявок отключена.")
    await callback.answer()

# Меню отклонения заявки
@admin_router.callback_query(F.data == "admin_reject_application_menu")
async def reject_application_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    await safe_edit_message(callback, "📋 Система заявок отключена.")
    await callback.answer()

# Обработчик отклонения заявки
@admin_router.callback_query(F.data.startswith("admin_reject_application:"))
async def reject_application_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    await safe_edit_message(callback, "📋 Система заявок отключена.")
    await callback.answer()

# Меню удаления турнира
@admin_router.callback_query(F.data == "admin_delete_tournament_menu")
async def delete_tournament_menu(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await callback.answer("📋 Нет активных турниров")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        text = f"🗑️ {tournament_data.get('name', 'Без названия')} ({tournament_data.get('date', '')})"
        builder.button(text=text, callback_data=f"admin_delete_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_tournaments")
    builder.adjust(1)
    
    await safe_edit_message(callback, "🗑️ Выберите турнир для удаления:", builder.as_markup())
    await callback.answer()

# Обработчик удаления турнира
@admin_router.callback_query(F.data.startswith("admin_delete_tournament:"))
async def delete_tournament_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Создаем клавиатуру подтверждения
    keyboard = await get_confirmation_keyboard("delete_tournament", tournament_id)
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить турнир?\n\n"
        f"🎯 Название: {tournament_data.get('name', 'Без названия')}\n"
        f"📅 Дата: {tournament_data.get('date', 'Неизвестно')}\n"
        f"📍 Место: {tournament_data.get('location', 'Неизвестно')}\n"
        f"👥 Участников: {len(tournament_data.get('participants', {}))}\n\n"
        "Это действие удалит все данные о турнире!",
        keyboard
    )
    await callback.answer()

# Подтверждение удаления турнира
@admin_router.callback_query(F.data.startswith("admin_confirm_delete_tournament:"))
async def confirm_delete_tournament(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Удаляем турнир
    del tournaments[tournament_id]
    await storage.save_tournaments(tournaments)
    
    await safe_edit_message(
        callback,
        f"✅ Турнир удален!\n\n"
        f"🎯 Название: {tournament_data.get('name', 'Без названия')}\n"
        f"📅 Дата: {tournament_data.get('date', 'Неизвестно')}\n\n"
        f"Все данные о турнире удалены из системы."
    )
    await callback.answer()

# Кнопка назад к турнирам
@admin_router.callback_query(F.data == "admin_back_to_tournaments")
async def back_to_tournaments(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await safe_edit_message(callback, "📋 Список турниров пуст.")
        return
    
    text = "🏆 Активные турниры:\n\n"
    for tournament_id, tournament_data in tournaments.items():
        text += f"🎯 {tournament_data.get('name', 'Без названия')}\n"
        text += f"📅 Дата: {tournament_data.get('date', 'Не указана')}\n"
        text += f"📍 Место: {tournament_data.get('location', 'Не указано')}\n"
        text += f"👥 Участников: {len(tournament_data.get('participants', {}))}\n"
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
        await safe_send_message(message, "❌ У вас нет прав администратора")
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
        await safe_send_message(message, "❌ У вас нет прав администратора")
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
    await safe_edit_message(callback, "❌ Действие отменено")
    await callback.answer()

# Клавиатура админской панели
def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Забаненные пользователи", callback_data="admin_banned_list")
    builder.button(text="🏆 Турниры", callback_data="admin_tournaments")
    builder.button(text="➕ Создать турнир", callback_data="admin_create_tournament")
    builder.button(text="✏️ Редактировать турниры", callback_data="admin_edit_tournaments")
    builder.button(text="👥 Участники турниров", callback_data="admin_view_tournament_participants")
    builder.adjust(1)
    return builder.as_markup()

# Обработчик кнопки создания турнира в админской панели
@admin_router.callback_query(F.data == "admin_create_tournament")
async def admin_create_tournament_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки создания турнира в админской панели"""
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Перенаправляем на обработчик создания турнира из tournament.py
    from handlers.tournament import create_tournament_callback
    await create_tournament_callback(callback, state)

# Обработчик кнопки участников турниров в админской панели
@admin_router.callback_query(F.data == "admin_view_tournament_participants")
async def admin_view_tournament_participants_handler(callback: CallbackQuery):
    """Обработчик кнопки просмотра участников турниров в админской панели"""
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await safe_edit_message(callback, "📋 Нет турниров для просмотра")
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
    
    await safe_edit_message(
        callback,
        "👥 Просмотр участников турниров\n\n"
        "Выберите турнир для просмотра участников:",
        builder.as_markup()
    )
    await callback.answer()

# Обработчик кнопки турниров в админской панели
@admin_router.callback_query(F.data == "admin_tournaments")
async def tournaments_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await safe_edit_message(callback, "📋 Список турниров пуст.")
        return
    
    text = "🏆 Активные турниры:\n\n"
    for tournament_id, tournament_data in tournaments.items():
        # Формируем информацию о турнире
        location = f"{tournament_data.get('city', 'Не указан')}"
        if tournament_data.get('district'):
            location += f" ({tournament_data['district']})"
        location += f", {tournament_data.get('country', 'Не указана')}"
        
        text += f"🏆 {tournament_data.get('name', 'Без названия')}\n"
        text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
        text += f"🌍 Место: {location}\n"
        text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
        text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
        text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
        text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
        text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
        text += f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
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
        await safe_send_message(message, "❌ У вас нет прав администратора")
        return
    
    await safe_send_message(
        message,
        "👨‍💼 Админская панель:\n\n"
        "Доступные действия:",
        get_admin_keyboard()
    )

# Обработчики кнопок админской панели - меню выбора
@admin_router.callback_query(F.data == "admin_banned_list")
async def banned_list_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
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

@admin_router.callback_query(F.data == "admin_unban_menu")
async def unban_menu_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
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
        await callback.answer("❌ Нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await safe_edit_message(callback, "📋 Нет турниров для редактирования")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        builder.button(text=f"🏆 {name} ({city})", callback_data=f"edit_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(
        callback,
        "🏆 Редактирование турниров\n\n"
        "Выберите турнир для редактирования:",
        builder.as_markup()
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_clear_all_bans")
async def clear_all_bans_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
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
        await callback.answer("❌ Нет прав администратора")
        return
    
    # Очищаем список банов
    await storage.save_banned_users({})
    
    await safe_edit_message(callback, "✅ Все баны успешно очищены!")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_unban_user:"))
async def unban_user_handler(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
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
        await callback.answer("❌ Нет прав администратора")
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
    
    if not sub_users:
        await callback.answer("❌ Нет активных подписок")
        return
    
    builder = InlineKeyboardBuilder()
    for user in sub_users:
        text = f"🔔 {user['user_name']} (до {user['until']})"
        builder.button(text=text, callback_data=f"admin_select_subscription:{user['user_id']}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await safe_edit_message(callback, "🔔 Выберите пользователя для удаления подписки:", builder.as_markup())
    await callback.answer()

# Обработка выбора конкретного элемента
@admin_router.callback_query(F.data.startswith("admin_select_user:"))
async def select_user(callback: CallbackQuery):
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
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
        await callback.answer("❌ Игра не найдена")
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
        await callback.answer("❌ Пользователь не найден")
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
        await callback.answer("❌ Пользователь не найден")
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
        await callback.answer("❌ Ошибка формата ID")
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    user_data = users[user_id]
    offer_to_delete = None
    
    for game_offer in user_data.get('games', []):
        if str(game_offer.get('id')) == offer_id:
            offer_to_delete = game_offer
            break
    
    if not offer_to_delete:
        await callback.answer("❌ Предложение не найдено")
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
    await safe_edit_message(
        callback,
        "👨‍💼 Админская панель:\n\n"
        "Доступные действия:",
        get_admin_keyboard()
    )
    await callback.answer()

# Обработка подтверждения для отдельных действий
@admin_router.callback_query(F.data.startswith("admin_confirm_delete_user:"))
async def confirm_delete_user(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав")
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    games = await storage.load_games()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
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
    
    await safe_edit_message(callback, f"✅ Пользователь {user_id} успешно удален! Все связанные игры также удалены.")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_game:"))
async def confirm_delete_game(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав")
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
        await callback.answer("❌ Игра не найдена")
        return
    
    # Откат рейтингов участников
    for player_id, rating_change in game_to_delete.get('rating_changes', {}).items():
        if player_id in users:
            users[player_id]['rating_points'] -= rating_change
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
        await callback.answer("❌ Нет прав")
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Удаляем данные об отпуске
    users[user_id]['vacation_tennis'] = False
    users[user_id].pop('vacation_start', None)
    users[user_id].pop('vacation_end', None)
    users[user_id].pop('vacation_comment', None)
    
    await storage.save_users(users)
    
    await safe_edit_message(callback, f"✅ Отпуск пользователя {user_id} успешно удален!")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_subscription:"))
async def confirm_delete_subscription(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав")
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Удаляем подписку
    users[user_id].pop('subscription', None)
    
    await storage.save_users(users)
    
    await safe_edit_message(callback, f"✅ Подписка пользователя {user_id} успешно удалена!")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_offer:"))
async def confirm_delete_offer(callback: CallbackQuery):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав")
        return
    
    try:
        user_id, offer_id = callback.data.split(':')[1], callback.data.split(':')[2]
    except:
        await callback.answer("❌ Ошибка формата ID")
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
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
        await callback.answer("❌ Нет прав администратора")
        return
    
    user_id = callback.data.split(':')[1]
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
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
                    users[player_id]['rating_points'] -= rating_change
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
