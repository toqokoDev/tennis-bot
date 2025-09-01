from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from datetime import datetime, timedelta
from config.config import SUBSCRIPTION_PRICE
from services.channels import send_game_offer_to_channel
from services.storage import storage
from models.states import GameOfferStates
from utils.admin import is_admin
from utils.bot import show_current_data
from utils.game import get_user_games, save_user_game

from config.profile import moscow_districts, game_types, payment_types, base_keyboard, cities_data
from utils.validate import validate_time, validate_date

router = Router()

# ---------- Обработчики предложений игры ----------
@router.callback_query(F.data == "my_offers")
async def my_offers_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    
    profile = await storage.get_user(user_id)
    
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    active_games = [game for game in profile.get('games', []) if game.get('active', True)]
    
    if not active_games:
        await callback.answer("❌ У вас нет активных предложений")
        return
    
    # Сохраняем список активных игр в state для навигации
    await state.update_data(active_games=active_games, current_offer_index=0)
    
    # Показываем первое предложение
    await show_single_offer(callback, state)
    await callback.answer()

async def show_single_offer(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    user_data = await state.get_data()
    active_games = user_data.get('active_games', [])
    current_index = user_data.get('current_offer_index', 0)
    
    if not active_games:
        await callback.answer("❌ Нет активных предложений")
        return
    
    # Получаем текущее предложение
    game = active_games[current_index]
    
    # Формируем сообщение с предложением
    response = [
        f"🎾 Предложение #{game['id']} ({current_index + 1}/{len(active_games)})",
        f"🏙 Город: {game.get('city', '—')}",
        f"📅 Дата: {game.get('date', '—')}",
        f"⏰ Время: {game.get('time', '—')}",
        f"🔍 Тип: {game.get('type', '—')}",
        f"💳 Оплата: {game.get('payment_type', '—')}",
        f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}",
        f"🔄 Повтор: {'Да' if game.get('repeat') else 'Нет'}"
    ]
    
    if game.get('comment'):
        response.append(f"💬 Комментарий: {game['comment']}")
    
    # Создаем клавиатуру для навигации
    keyboard_buttons = []
    
    # Кнопки навигации (только если больше одного предложения)
    if len(active_games) > 1:
        nav_buttons = []
        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="offer_prev"))
        if current_index < len(active_games) - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data="offer_next"))
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
    
    # Кнопки действий
    action_buttons = [
        InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_offer_{game['id']}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{user_id}")
    ]
    keyboard_buttons.append(action_buttons)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    try:
        if hasattr(callback, 'message'):
            await callback.message.edit_text("\n".join(response), reply_markup=keyboard)
        else:
            await callback.message.delete()
            await callback.answer("\n".join(response), reply_markup=keyboard)
            
    except:
        await callback.message.delete()
        if hasattr(callback, 'message'):
            await callback.message.answer("\n".join(response), reply_markup=keyboard)
        else:
            await callback.answer("\n".join(response), reply_markup=keyboard)

@router.callback_query(F.data == "offer_prev")
async def offer_prev_handler(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    current_index = user_data.get('current_offer_index', 0)
    
    if current_index > 0:
        await state.update_data(current_offer_index=current_index - 1)
        await show_single_offer(callback, state)
    
    await callback.answer()

@router.callback_query(F.data == "offer_next")
async def offer_next_handler(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    active_games = user_data.get('active_games', [])
    current_index = user_data.get('current_offer_index', 0)
    
    if current_index < len(active_games) - 1:
        await state.update_data(current_offer_index=current_index + 1)
        await show_single_offer(callback, state)
    
    await callback.answer()

@router.callback_query(F.data.startswith("delete_offer_"))
async def delete_offer_single_handler(callback: types.CallbackQuery, state: FSMContext):
    game_id = callback.data.split("_", maxsplit=2)[2]
    
    # Клавиатура подтверждения удаления
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"delete_yes_{game_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data="delete_no_single")
            ]
        ]
    )
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        f"❓ Вы уверены, что хотите удалить предложение #{game_id}?",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "delete_no_single")
async def delete_no_single_handler(callback: types.CallbackQuery, state: FSMContext):
    # Возвращаемся к просмотру предложения
    await show_single_offer(callback, state)
    await callback.answer()

@router.callback_query(F.data.startswith("delete_yes_"))
async def delete_yes_handler(callback: types.CallbackQuery, state: FSMContext):
    game_id = callback.data.split("_", maxsplit=2)[2]
    user_id = callback.message.chat.id
    
    # Загружаем пользователей
    users = await storage.load_users()
    user_data = users.get(str(user_id))
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Помечаем игру как неактивную
    for game in user_data.get('games', []):
        if str(game.get('id')) == game_id:
            game['active'] = False
            break
    
    # Сохраняем изменения
    users[str(user_id)] = user_data
    await storage.save_users(users)
    
    # Обновляем данные в state
    user_data = await state.get_data()
    active_games = user_data.get('active_games', [])
    current_index = user_data.get('current_offer_index', 0)
    
    # Удаляем предложение из списка
    active_games = [game for game in active_games if str(game.get('id')) != game_id]
    
    if not active_games:
        # Если предложений больше нет
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer("✅ Предложение успешно удалено! У вас больше нет активных предложений.")
        await state.update_data(active_games=None, current_offer_index=None)
        return
    
    # Корректируем индекс
    if current_index >= len(active_games):
        current_index = len(active_games) - 1
    
    await state.update_data(active_games=active_games, current_offer_index=current_index)
    
    # Показываем обновленное предложение
    await show_single_offer(callback, state)
    await callback.answer()

# Остальной код остается без изменений...

@router.callback_query(F.data == "new_offer")
async def new_offer_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id)
    users = await storage.load_users()
    
    if not profile:
        await callback.answer("❌ Сначала завершите регистрацию")
        return

    # Проверяем подписку и количество бесплатных предложений
    user_data = users.get(str(user_id), {})
    subscription_active = user_data.get('subscription', {}).get('active', False)
    
    if not await is_admin(callback.message.chat.id):
        if not subscription_active:
            # Получаем количество созданных бесплатных предложений
            free_offers_used = user_data.get('free_offers_used', 0)
            
            if free_offers_used >= 2:
                text = (
                    "🔒 <b>Доступ закрыт</b>\n\n"
                    "Вы использовали все бесплатные предложения игры (максимум 2).\n\n"
                    "Функция предложения игры доступна только для пользователей с активной подпиской Tennis-Play PRO.\n\n"
                    f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n\n"
                    "Перейдите в раздел '💳 Платежи' для оформления подписки."
                )
                
                await callback.message.answer(
                    text,
                    parse_mode="HTML"
                )
                await callback.answer()
                return
    
    # Запускаем процесс создания нового предложения
    country = profile.get('country', '')
    city = profile.get('city', '')
    
    await state.update_data(country=country, city=city)
    
    if "Москва" in city:
        buttons = [[InlineKeyboardButton(text=district, callback_data=f"gamecity_{district}")] for district in moscow_districts]
    else:
        cities = cities_data.get(country, [])
        unique_cities = []
        if city:
            unique_cities.append(city)
        for c in cities:
            if c not in unique_cities:
                unique_cities.append(c)
        buttons = [[InlineKeyboardButton(text=f"{c}", callback_data=f"gamecity_{c}")] for c in unique_cities[:5]]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        "🏙 Выберите город для игры:",
        reply_markup=keyboard
    )
    await state.set_state(GameOfferStates.GAME_CITY)
    await callback.answer()
    
@router.message(F.text == "🎾 Предложить игру")
async def offer_game_command(message: types.Message, state: FSMContext):
    user_id = message.chat.id
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    
    if not user_data:
        await message.answer("❌ Сначала зарегистрируйтесь с помощью /start")
        return
    
    # Проверяем подписку и количество бесплатных предложений
    subscription_active = user_data.get('subscription', {}).get('active', False)
    
    if not await is_admin(message.chat.id):
        if not subscription_active:
            # Получаем количество созданных бесплатных предложений
            free_offers_used = user_data.get('free_offers_used', 0)
            
            if free_offers_used >= 2:
                text = (
                    "🔒 <b>Доступ закрыт</b>\n\n"
                    "Вы использовали все бесплатные предложения игры (максимум 2).\n\n"
                    "Функция предложения игры доступна только для пользователей с активной подпиской Tennis-Play PRO.\n\n"
                    f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n\n"
                    "Перейдите в раздел '💳 Платежи' для оформления подписки."
                )
                
                await message.answer(
                    text,
                    parse_mode="HTML"
                )
                return
    
    country = user_data.get('country', '')
    city = user_data.get('city', '')
    
    await state.update_data(country=country, city=city)
    
    if "Москва" in city:
        buttons = [[InlineKeyboardButton(text=district, callback_data=f"gamecity_{district}")] for district in moscow_districts]
    else:
        cities = cities_data.get(country, [])
        unique_cities = []
        if city:
            unique_cities.append(city)
        for c in cities:
            if c not in unique_cities:
                unique_cities.append(c)
        buttons = [[InlineKeyboardButton(text=f"🏙 {c}", callback_data=f"gamecity_{c}")] for c in unique_cities[:5]]

    await show_current_data(
        message, state,
        "🏙 Выберите город для игры:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_CITY)
    await storage.save_session(user_id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_CITY, F.data.startswith("gamecity_"))
async def process_game_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(game_city=city)

    today = datetime.now().strftime('%d.%m.%Y')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')

    buttons = [
        [InlineKeyboardButton(text=f"📅 Сегодня ({today})", callback_data=f"gamedate_{today}")],
        [InlineKeyboardButton(text=f"📅 Завтра ({tomorrow})", callback_data=f"gamedate_{tomorrow}")],
        [InlineKeyboardButton(text="📝 Ввести дату вручную", callback_data="gamedate_manual")]
    ]
    await show_current_data(
        callback.message, state,
        "📅 Выберите дату игры:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_DATE)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_DATE, F.data.startswith("gamedate_"))
async def process_game_date(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "gamedate_manual":
        await show_current_data(
            callback.message, state,
            "📅 Введите дату игры в формате ДД.ММ.ГГГГ (например, 25.12.2025):"
        )
        await state.set_state(GameOfferStates.GAME_DATE_MANUAL)
        await callback.answer()
        return
    
    date = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(game_date=date)

    times = [f"⏰ {hour:02d}:00" for hour in range(7, 24)] + ["⏰ 00:00"]

    buttons = []
    for i in range(0, len(times), 3):
        row = []
        for time in times[i:i+3]:
            time_only = time.split()[1]
            row.append(InlineKeyboardButton(text=time, callback_data=f"gametime_{time_only}"))
        buttons.append(row)

    await show_current_data(
        callback.message, state,
        "⏰ Выберите время игры:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_TIME)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(GameOfferStates.GAME_DATE_MANUAL, F.text)
async def process_game_date_manual(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    
    # Валидация даты
    if not await validate_date(date_text):
        await message.answer("❌ Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ (например, 25.12.2025):")
        return
    
    # Проверка, что дата не в прошлом
    try:
        input_date = datetime.strptime(date_text, '%d.%m.%Y')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if input_date < today:
            await message.answer("❌ Неверный формат даты. Введите корректную дату:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ (например, 25.12.2025):")
        return
    
    await state.update_data(game_date=date_text)

    times = [f"⏰ {hour:02d}:00" for hour in range(7, 24)] + ["⏰ 00:00"]

    buttons = []
    for i in range(0, len(times), 3):
        row = []
        for time in times[i:i+3]:
            time_only = time.split()[1]
            row.append(InlineKeyboardButton(text=time, callback_data=f"gametime_{time_only}"))
        buttons.append(row)

    await show_current_data(
        message, state,
        "⏰ Выберите время игры:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_TIME)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_TIME, F.data.startswith("gametime_"))
async def process_game_time(callback: types.CallbackQuery, state: FSMContext):
    time = callback.data.split("_", maxsplit=1)[1]
    if not await validate_time(time):
        await callback.answer("❌ Неверный формат времени")
        return
    
    await state.update_data(game_time=time)

    buttons = [[InlineKeyboardButton(text=gt, callback_data=f"gametype_{gt}")] for gt in game_types]
    await show_current_data(
        callback.message, state,
        "🎾 Выберите тип игры:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_TYPE)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_TYPE, F.data.startswith("gametype_"))
async def process_game_type(callback: types.CallbackQuery, state: FSMContext):
    game_type = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(game_type=game_type)

    buttons = [[InlineKeyboardButton(text=pt, callback_data=f"paytype_{pt.split()[1]}")] for pt in payment_types]
    await show_current_data(
        callback.message, state,
        "💳 Выберите тип оплата:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.PAYMENT_TYPE)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.PAYMENT_TYPE, F.data.startswith("paytype_"))
async def process_payment_type(callback: types.CallbackQuery, state: FSMContext):
    payment_type = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(payment_type=payment_type)

    buttons = [
        [InlineKeyboardButton(text="🏆 На счёт", callback_data="gamecomp_yes")],
        [InlineKeyboardButton(text="🎾 Не на счёт", callback_data="gamecomp_no")]
    ]
    await show_current_data(
        callback.message, state,
        "🏆 Игра на счёт?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_COMPETITIVE)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_COMPETITIVE, F.data.startswith("gamecomp_"))
async def process_game_competitive(callback: types.CallbackQuery, state: FSMContext):
    competitive = callback.data.split("_", maxsplit=1)[1] == "yes"
    await state.update_data(game_competitive=competitive)

    await show_current_data(
        callback.message, state,
        "💬 Добавьте комментарий к игре (или введите /skip для пропуска):"
    )
    await state.set_state(GameOfferStates.GAME_COMMENT)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(GameOfferStates.GAME_COMMENT, F.text)
async def process_game_comment(message: types.Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(game_comment=message.text.strip())
    
    user_data = await state.get_data()
    
    game_data = {
        "city": user_data.get('game_city'),
        "date": user_data.get('game_date'),
        "time": user_data.get('game_time'),
        "type": user_data.get('game_type'),
        "payment_type": user_data.get('payment_type'),
        "competitive": user_data.get('game_competitive'),
        "comment": user_data.get('game_comment')
    }
    
    # Сохраняем игру
    game_id = await save_user_game(message.chat.id, game_data)
    
    # Обновляем счетчик бесплатных предложений, если нет подписки
    users = await storage.load_users()
    user_id_str = str(message.chat.id)
    
    if user_id_str in users:
        if not users[user_id_str].get('subscription', {}).get('active', False):
            free_offers_used = users[user_id_str].get('free_offers_used', 0)
            users[user_id_str]['free_offers_used'] = free_offers_used + 1
            await storage.save_users(users)
    
    await state.clear()
    await storage.delete_session(message.chat.id)
    
    # Формируем информационное сообщение о созданной игре
    response = [
        "✅ Предложение игры успешно создано!\n\n",
        f"🎾 Предложение #{game_id}",
        f"🏙 Город: {game_data.get('city', '—')}",
        f"📅 Дата: {game_data.get('date', '—')}",
        f"⏰ Время: {game_data.get('time', '—')}",
        f"🔍 Тип: {game_data.get('type', '—')}",
        f"💳 Оплата: {game_data.get('payment_type', '—')}",
        f"🏆 На счет: {'Да' if game_data.get('competitive') else 'Нет'}",
        f"🔄 Повтор: {'Да' if game_data.get('repeat') else 'Нет'}"
    ]
    
    if game_data.get('comment'):
        response.append(f"💬 Комментарий: {game_data['comment']}")
    
    # Добавляем информацию о статусе подписки
    users = await storage.load_users()
    user_data = users.get(str(message.chat.id), {})
    subscription_active = user_data.get('subscription', {}).get('active', False)
    
    if not subscription_active:
        free_offers_used = user_data.get('free_offers_used', 0)
        remaining_offers = max(0, 1 - free_offers_used)
        response.append(f"\n📊 Бесплатных предложений осталось: {remaining_offers}/1")
        response.append("💳 Оформите подписку для неограниченного создания предложений!")
    
    await send_game_offer_to_channel(message.bot, game_data, str(message.chat.id), user_data)
    await message.answer("\n".join(response), reply_markup=base_keyboard)

@router.message(F.text == "📋 Мои предложения")
async def list_my_games(message: types.Message, state: FSMContext):
    user_id = message.chat.id
    games = await get_user_games(user_id)
    
    if not games:
        await message.answer("❌ У вас нет активных предложений игры.")
        return
    
    active_games = [game for game in games if game.get('active', True)]
    
    if not active_games:
        await message.answer("❌ У вас нет активных предложений игры.")
        return
    
    # Сохраняем список активных игр в state для навигации
    await state.update_data(active_games=active_games, current_offer_index=0)
    
    # Показываем первое предложение
    response = []
    game = active_games[0]
    
    response = [
        f"🎾 Предложение #{game['id']} (1/{len(active_games)})",
        f"🏙 Город: {game.get('city', '—')}",
        f"📅 Дата: {game.get('date', '—')}",
        f"⏰ Время: {game.get('time', '—')}",
        f"🔍 Тип: {game.get('type', '—')}",
        f"💳 Оплата: {game.get('payment_type', '—')}",
        f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}",
        f"🔄 Повтор: {'Да' if game.get('repeat') else 'Нет'}"
    ]
    
    if game.get('comment'):
        response.append(f"💬 Комментарий: {game['comment']}")
    
    # Создаем клавиатуру для навигации
    keyboard_buttons = []
    
    # Кнопки навигации (только если больше одного предложения)
    if len(active_games) > 1:
        nav_buttons = []
        if 0 > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="offer_prev"))
        if 0 < len(active_games) - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data="offer_next"))
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
    
    # Кнопки действий
    action_buttons = [
        InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_offer_{game['id']}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{user_id}")
    ]
    keyboard_buttons.append(action_buttons)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer("\n".join(response), reply_markup=keyboard)

@router.callback_query(F.data == "delete_offer")
async def delete_offer_handler(callback: types.CallbackQuery):
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id)
    
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    active_games = [game for game in profile.get('games', []) if game.get('active', True)]
    
    if not active_games:
        await callback.answer("❌ Нет активных предложений для удаления")
        return
    
    # Создаем клавиатуру с кнопками для удаления каждого предложения
    buttons = []
    for game in active_games:
        game_info = f"#{game['id']} - {game.get('date', '?')} {game.get('time', '?')}"
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ Удалить {game_info}", 
                callback_data=f"confirm_delete_{game['id']}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_offers")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        "❌ Выберите предложение для удаления:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_handler(callback: types.CallbackQuery):
    game_id = callback.data.split("_", maxsplit=2)[2]
    user_id = callback.message.chat.id
    
    # Загружаем пользователей
    users = await storage.load_users()
    user_data = users.get(str(user_id))
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Ищем игру для удаления
    game_found = False
    for game in user_data.get('games', []):
        if str(game.get('id')) == game_id and game.get('active', True):
            game_found = True
            break
    
    if not game_found:
        await callback.answer("❌ Предложение не найдено")
        return
    
    # Клавиатура подтверждения удаления
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"delete_yes_{game_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data="delete_no")
            ]
        ]
    )
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        f"❓ Вы уверены, что хотите удалить предложение #{game_id}?",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "delete_no")
async def delete_no_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    
    # Возвращаемся к списку предложений
    await my_offers_handler(callback)
    await callback.answer()

@router.callback_query(F.data == "back_to_offers")
async def back_to_offers_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    
    # Возвращаемся к списку предложений
    await my_offers_handler(callback)
    await callback.answer()
