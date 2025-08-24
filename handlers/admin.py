from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os
import logging

from utils.admin import get_confirmation_keyboard, is_admin, load_banned_users, load_games, save_banned_users, save_games, save_users
from utils.json_data import load_users

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

# Команда удаления всех пользователей
@admin_router.message(Command("delete_all_users"))
async def delete_all_users_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await safe_send_message(message, "❌ У вас нет прав администратора")
        return
    
    keyboard = get_confirmation_keyboard("delete_all_users")
    await safe_send_message(
        message,
        "⚠️ Вы уверены, что хотите удалить ВСЕХ пользователей?\n"
        "Это действие удалит:\n"
        "• Все аккаунты пользователей\n"
        "• Все связанные игры\n"
        "• Фотографии профилей\n"
        "• Произведет откат рейтингов\n\n"
        "Дейтие необратимо!",
        keyboard
    )

# Команда удаления всех игр
@admin_router.message(Command("delete_all_games"))
async def delete_all_games_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await safe_send_message(message, "❌ У вас нет прав администратора")
        return
    
    keyboard = get_confirmation_keyboard("delete_all_games")
    await safe_send_message(
        message,
        "⚠️ Вы уверены, что хотите удалить ВСЕ игры?\n"
        "Это действие:\n"
        "• Удалит все записи о играх\n"
        "• Произведет откат рейтингов игроков\n\n"
        "Действие необратимо!",
        keyboard
    )

# Команда удаления всех предложений игр
@admin_router.message(Command("delete_all_offers"))
async def delete_all_offers_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await safe_send_message(message, "❌ У вас нет прав администратора")
        return
    
    keyboard = get_confirmation_keyboard("delete_all_offers")
    await safe_send_message(
        message,
        "⚠️ Вы уверены, что хотите удалить ВСЕ предложения игр?\n"
        "Это действие удалит все активные предложения игр у пользователей.\n\n"
        "Действие необратимо!",
        keyboard
    )

# Обработка подтверждения удаления всех пользователей
@admin_router.callback_query(F.data == "admin_confirm_delete_all_users")
async def confirm_delete_all_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    users = load_users()
    games = load_games()
    
    # Откат рейтингов и удаление фото
    for user_id, user_data in users.items():
        # Удаление фото профиля
        if user_data.get('photo_path'):
            try:
                os.remove(user_data['photo_path'])
            except:
                pass
    
    # Удаление всех пользователей
    users.clear()
    save_users(users)
    
    # Удаление всех игр
    games.clear()
    save_games(games)
    
    await safe_edit_message(callback, "✅ Все пользователи и игры успешно удалены!")
    await callback.answer()

# Обработка подтверждения удаления всех игр
@admin_router.callback_query(F.data == "admin_confirm_delete_all_games")
async def confirm_delete_all_games(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    users = load_users()
    games = load_games()
    
    # Откат рейтингов
    for game in games:
        for player_id, rating_change in game.get('rating_changes', {}).items():
            if player_id in users:
                users[player_id]['rating_points'] -= rating_change
                # Обновляем статистику игр
                users[player_id]['games_played'] = users[player_id].get('games_played', 0) - 1
                # Обновляем статистику побед
                if users[player_id].get('games_wins', 0) > 0:
                    users[player_id]['games_wins'] -= 1
    
    # Удаление всех игр
    games.clear()
    save_games(games)
    save_users(users)
    
    await safe_edit_message(callback, "✅ Все игры удалены, рейтинги откачены!")
    await callback.answer()

# Обработка подтверждения удаления всех предложений
@admin_router.callback_query(F.data == "admin_confirm_delete_all_offers")
async def confirm_delete_all_offers(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    users = load_users()
    
    # Удаление всех предложений игр у пользователей
    for user_id, user_data in users.items():
        if 'games' in user_data and user_data['games']:
            user_data['games'] = []
    
    save_users(users)
    
    await safe_edit_message(callback, "✅ Все предложения игр успешно удалены!")
    await callback.answer()

# Отмена действия
@admin_router.callback_query(F.data == "admin_cancel")
async def cancel_action(callback: CallbackQuery):
    await safe_edit_message(callback, "❌ Действие отменено")
    await callback.answer()

# Клавиатура админской панели
def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Удалить ВСЕХ пользователей", callback_data="admin_delete_all_users")
    builder.button(text="⚠️ Удалить ВСЕ игры", callback_data="admin_delete_all_games")
    builder.button(text="⚠️ Удалить ВСЕ предложения", callback_data="admin_delete_all_offers")
    builder.adjust(2)
    return builder.as_markup()

# Команда админской панели
@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await safe_send_message(message, "❌ У вас нет прав администратора")
        return
    
    await safe_send_message(
        message,
        "👨‍💼 Админская панель:\n\n"
        "Доступные действия:",
        get_admin_keyboard()
    )

# Обработчики кнопок админской панели - меню выбора
@admin_router.callback_query(F.data == "admin_delete_user_menu")
async def delete_user_menu(callback: CallbackQuery):
    users = load_users()
    
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
    games = load_games()
    
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
    users = load_users()
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
    users = load_users()
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
    users = load_users()
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
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    user_data = users[user_id]
    keyboard = get_confirmation_keyboard("delete_user", user_id)
    
    await safe_edit_message(
        callback,
        f"⚠️ Вы уверены, что хотите удалить пользователя?\n\n"
        f"👤 {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📞 {user_data.get('phone', '')}\n"
        f"🏆 Рейтинг: {user_data.get('rating_points', 0)}\n"
        f"🎮 Игр сыграно: {user_data.get('games_played', 0)}\n"
        f"📋 Активных предложений: {len(user_data.get('games', []))}\n\n"
        "Это действие также удалит все его игры и фотографии!",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_select_game:"))
async def select_game(callback: CallbackQuery):
    game_id = callback.data.split(':')[1]
    games = load_games()
    users = load_users()
    
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
    
    keyboard = get_confirmation_keyboard("delete_game", game_id)
    
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
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    user_data = users[user_id]
    keyboard = get_confirmation_keyboard("delete_vacation", user_id)
    
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
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    user_data = users[user_id]
    keyboard = get_confirmation_keyboard("delete_subscription", user_id)
    
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
    
    users = load_users()
    
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
    
    keyboard = get_confirmation_keyboard("delete_offer", f"{user_id}:{offer_id}")
    
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
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    user_id = callback.data.split(':')[1]
    users = load_users()
    games = load_games()
    
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
    
    save_users(users)
    save_games(new_games)
    
    await safe_edit_message(callback, f"✅ Пользователь {user_id} успешно удален! Все связанные игры также удалены.")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_game:"))
async def confirm_delete_game(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    game_id = callback.data.split(':')[1]
    users = load_users()
    games = load_games()
    
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
    save_games(new_games)
    save_users(users)
    
    await safe_edit_message(callback, f"✅ Игра {game_id} успешно удалена! Рейтинги откачены.")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_vacation:"))
async def confirm_delete_vacation(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    user_id = callback.data.split(':')[1]
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Удаляем данные об отпуске
    users[user_id]['vacation_tennis'] = False
    users[user_id].pop('vacation_start', None)
    users[user_id].pop('vacation_end', None)
    users[user_id].pop('vacation_comment', None)
    
    save_users(users)
    
    await safe_edit_message(callback, f"✅ Отпуск пользователя {user_id} успешно удален!")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_subscription:"))
async def confirm_delete_subscription(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    user_id = callback.data.split(':')[1]
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Удаляем подписку
    users[user_id].pop('subscription', None)
    
    save_users(users)
    
    await safe_edit_message(callback, f"✅ Подписка пользователя {user_id} успешно удалена!")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_confirm_delete_offer:"))
async def confirm_delete_offer(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    try:
        user_id, offer_id = callback.data.split(':')[1], callback.data.split(':')[2]
    except:
        await callback.answer("❌ Ошибка формата ID")
        return
    
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Удаляем предложение из списка игр пользователя
    user_games = users[user_id].get('games', [])
    new_games = [game for game in user_games if str(game.get('id')) != offer_id]
    users[user_id]['games'] = new_games
    
    save_users(users)
    
    await safe_edit_message(callback, f"✅ Предложение {offer_id} пользователя {user_id} успешно удалено!")
    await callback.answer()

# Обработчики для кнопок массового удаления из админской панели
@admin_router.callback_query(F.data == "admin_delete_all_users")
async def delete_all_users_callback(callback: CallbackQuery):
    keyboard = get_confirmation_keyboard("delete_all_users")
    await safe_edit_message(
        callback,
        "⚠️ Вы уверены, что хотите удалить ВСЕХ пользователей?\n"
        "Это действие удалит:\n"
        "• Все аккаунты пользователей\n"
        "• Все связанные игры\n"
        "• Фотографии профиля\n"
        "• Произведет откат рейтингов\n\n"
        "Действие необратимо!",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_all_games")
async def delete_all_games_callback(callback: CallbackQuery):
    keyboard = get_confirmation_keyboard("delete_all_games")
    await safe_edit_message(
        callback,
        "⚠️ Вы уверены, что хотите удалить ВСЕ игры?\n"
        "Это действие:\n"
        "• Удалит все записи о играх\n"
        "• Произведет откат рейтингов игроков\n\n"
        "Действие необратимо!",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_delete_all_offers")
async def delete_all_offers_callback(callback: CallbackQuery):
    keyboard = get_confirmation_keyboard("delete_all_offers")
    await safe_edit_message(
        callback,
        "⚠️ Вы уверены, что хотите удалить ВСЕ предложения игр?\n"
        "Это действие удалит все активные предложения игр у пользователей.\n\n"
        "Действие необратимо!",
        keyboard
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_ban_user:"))
async def ban_user_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    user_id = callback.data.split(':')[1]
    users = load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    user_data = users[user_id]
    
    # Загружаем список забаненных пользователей
    banned_users = load_banned_users()
    
    # Добавляем пользователя в бан лист
    banned_users[str(user_id)] = {
        'first_name': user_data.get('first_name', ''),
        'last_name': user_data.get('last_name', ''),
        'username': user_data.get('username', ''),
        'phone': user_data.get('phone', ''),
        'banned_by': callback.from_user.id,
        'banned_at': datetime.now().isoformat()
    }
    save_banned_users(banned_users)
    
    # Удаляем пользователя (та же логика что и при удалении)
    games = load_games()
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
    
    save_users(users)
    save_games(new_games)
    
    await safe_edit_message(callback, f"✅ Пользователь {user_id} забанен и удален!")
    await callback.answer()
