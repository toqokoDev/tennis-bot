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

from config.profile import (
    WEEKDAYS, moscow_districts, game_types, payment_types, base_keyboard, cities_data,
    get_sport_config, get_sport_texts, sport_type
)

def get_next_game_step(sport: str, current_step: str) -> str:
    """
    Определяет следующий шаг в создании предложения игры в зависимости от вида спорта
    """
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    # Для встреч (бизнес-завтрак, по пиву) - упрощенный флоу
    if category == "meeting":
        if current_step == "sport":
            return "city"
        elif current_step == "city":
            return "date"
        elif current_step == "date":
            return "time"
        elif current_step == "time":
            return "comment"  # Пропускаем тип игры, оплату, счет
        else:
            return "done"
    
    # Для знакомств - еще более упрощенный флоу
    elif category == "dating":
        if current_step == "sport":
            return "city"
        elif current_step == "city":
            return "comment"  # Пропускаем дату, время, тип игры, оплату, счет
        else:
            return "done"
    
    # Для активных видов спорта без кортов - средний флоу
    elif category == "outdoor_sport":
        if current_step == "sport":
            return "city"
        elif current_step == "city":
            return "date"
        elif current_step == "date":
            return "time"
        elif current_step == "time":
            return "comment"  # Пропускаем тип игры, оплату, счет
        else:
            return "done"
    
    # Для спортивных видов с кортами - полный флоу
    else:  # court_sport
        if current_step == "sport":
            return "city"
        elif current_step == "city":
            return "date"
        elif current_step == "date":
            return "time"
        elif current_step == "time":
            return "type"
        elif current_step == "type":
            return "payment"
        elif current_step == "payment":
            return "competitive"
        elif current_step == "competitive":
            return "comment"
        else:
            return "done"

def get_game_comment_prompt(sport: str) -> str:
    """
    Возвращает подходящий текст для комментария в зависимости от вида спорта
    """
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    if category == "meeting":
        if sport == "☕️Бизнес-завтрак":
            return "💬 Опишите, какие проекты вам интересны для обсуждения или ваше предложение по бизнесу:"
        elif sport == "🍻По пиву":
            return "💬 Опишите, что вы хотели бы посмотреть или обсудить за пивом:"
    elif category == "dating":
        return "💬 Расскажите о себе и что вы ищете:"
    elif category == "outdoor_sport":
        return "💬 Опишите, что вы планируете делать и где встретиться:"
    else:  # court_sport
        return "💬 Добавьте комментарий к игре (или введите /skip для пропуска):"
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
        # Получаем тексты для вида спорта пользователя
        user_profile = await storage.get_user(user_id)
        sport = user_profile.get('sport', '🎾Большой теннис') if user_profile else '🎾Большой теннис'
        texts = get_sport_texts(sport)
        await callback.answer(f"❌ {texts['no_offers_text']}")
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
    
    # Получаем вид спорта
    sport = game.get('sport', '🎾Большой теннис')
    
    # Формируем сообщение с предложением
    response = [
        f"🎾 Предложение #{game['id']} ({current_index + 1}/{len(active_games)})",
        f"🏙 Город: {game.get('city', '—')}"
    ]
    
    # Получаем конфигурацию для вида спорта
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    # Добавляем поля в зависимости от категории вида спорта
    if category == "dating":
        # Для знакомств - только город и комментарий
        pass
    elif category in ["meeting", "outdoor_sport"]:
        # Для встреч и активных видов спорта - добавляем дату и время
        response.append(f"📅 Дата: {game.get('date', '—')}")
        response.append(f"⏰ Время: {game.get('time', '—')}")
    else:  # court_sport
        # Для спортивных видов с кортами - добавляем все поля
        response.append(f"📅 Дата: {game.get('date', '—')}")
        response.append(f"⏰ Время: {game.get('time', '—')}")
        response.append(f"🔍 Тип: {game.get('type', '—')}")
        response.append(f"💳 Оплата: {game.get('payment_type', '—')}")
        response.append(f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}")
        response.append(f"🔄 Повтор: {'Да' if game.get('repeat') else 'Нет'}")
    
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
    
    # Проверяем, есть ли медиафайл
    if game.get('media_filename'):
        from config.paths import GAMES_PHOTOS_DIR
        import os
        media_path = f"{GAMES_PHOTOS_DIR}/{game['media_filename']}"
        if os.path.exists(media_path):
            # Определяем тип медиа
            if game['media_filename'].endswith(('.jpg', '.jpeg', '.png')):
                with open(media_path, 'rb') as photo:
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo,
                        caption="\n".join(response),
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            elif game['media_filename'].endswith(('.mp4', '.mov')):
                with open(media_path, 'rb') as video:
                    await callback.message.delete()
                    await callback.message.answer_video(
                        video,
                        caption="\n".join(response),
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            else:
                try:
                    await callback.message.edit_text("\n".join(response), reply_markup=keyboard, parse_mode='Markdown')
                except:
                    await callback.message.delete()
                    await callback.message.answer("\n".join(response), reply_markup=keyboard, parse_mode='Markdown')
        else:
            try:
                await callback.message.edit_text("\n".join(response), reply_markup=keyboard, parse_mode='Markdown')
            except:
                await callback.message.delete()
                await callback.message.answer("\n".join(response), reply_markup=keyboard, parse_mode='Markdown')
    else:
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
            
            if free_offers_used >= 1:
                text = (
                    "🔒 <b>Доступ закрыт</b>\n\n"
                    "Вы использовали все бесплатные предложения игры (максимум 1).\n\n"
                    "Функция предложения игры доступна только для пользователей с активной подпиской Tennis-Play PRO.\n\n"
                    f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n\n"
                    "Также вы можете получить подписку бесплатно, пригласив 10 друзей.\n"
                    "Ваша персональная ссылка для приглашений доступна в разделе «🔗 Пригласить друга».\n\n"
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
    sport = profile.get('sport', '🎾Большой теннис')
    
    await state.update_data(country=country, city=city, sport=sport)
    
    # Сначала спрашиваем вид спорта
    buttons = []
    for sport_option in sport_type:
        buttons.append([InlineKeyboardButton(text=sport_option, callback_data=f"gamesport_{sport_option}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        "🎾 Выберите вид спорта для игры:",
        reply_markup=keyboard
    )
    await state.set_state(GameOfferStates.GAME_SPORT)
    await callback.answer()

@router.callback_query(GameOfferStates.GAME_SPORT, F.data.startswith("gamesport_"))
async def process_game_sport(callback: types.CallbackQuery, state: FSMContext):
    sport = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(game_sport=sport)
    
    user_data = await state.get_data()
    country = user_data.get('country', '')
    city = user_data.get('city', '')
    
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
    
    # Получаем тексты для вида спорта
    texts = get_sport_texts(sport)
    await callback.message.edit_text(
        f"🏙 {texts['city_prompt']}",
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
                    "Вы использовали все бесплатные предложения игры (максимум 1).\n\n"
                    "Функция предложения игры доступна только для пользователей с активной подпиской Tennis-Play PRO.\n\n"
                    f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n\n"
                    "Также вы можете получить подписку бесплатно, пригласив 10 друзей.\n"
                    "Ваша персональная ссылка для приглашений доступна в разделе «🔗 Пригласить друга».\n\n"
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

    # Получаем тексты для вида спорта пользователя
    sport = user_data.get('sport', '🎾Большой теннис')
    texts = get_sport_texts(sport)
    await show_current_data(
        message, state,
        f"🏙 {texts['city_prompt']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(GameOfferStates.GAME_CITY)
    await storage.save_session(user_id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_CITY, F.data.startswith("gamecity_"))
async def process_game_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(game_city=city)
    
    # Получаем данные о виде спорта
    user_data = await state.get_data()
    sport = user_data.get('game_sport', user_data.get('sport', '🎾Большой теннис'))
    
    # Определяем следующий шаг
    next_step = get_next_game_step(sport, "city")
    
    if next_step == "date":
        # Для спортивных видов и встреч - выбираем дату
        today = datetime.now()

        # список кнопок на 7 дней вперёд
        buttons = []
        row = []

        for i in range(7):
            date = today + timedelta(days=i)
            date_str = date.strftime("%d.%m")
            weekday = WEEKDAYS[date.weekday()]
            text = f"{weekday} ({date_str})"

            row.append(InlineKeyboardButton(text=text, callback_data=f"gamedate_{date_str}"))

            # если в ряду 3 кнопки — перенос строки
            if len(row) == 3:
                buttons.append(row)
                row = []

        # если остались кнопки (например, 7 не делится на 3)
        if row:
            buttons.append(row)

        # добавляем кнопку для ручного ввода
        buttons.append([InlineKeyboardButton(text="📝 Ввести дату вручную", callback_data="gamedate_manual")])

        await show_current_data(
            callback.message, state,
            "📅 Выберите дату игры:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(GameOfferStates.GAME_DATE)
    elif next_step == "comment":
        # Для знакомств - сразу к комментарию
        comment_prompt = get_game_comment_prompt(sport)
        await show_current_data(
            callback.message, state,
            comment_prompt
        )
        await state.set_state(GameOfferStates.GAME_COMMENT)
    
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
    
    # Получаем данные о виде спорта
    user_data = await state.get_data()
    sport = user_data.get('game_sport', user_data.get('sport', '🎾Большой теннис'))
    
    # Определяем следующий шаг
    next_step = get_next_game_step(sport, "time")
    
    if next_step == "type":
        # Для спортивных видов - выбираем тип игры
        buttons = [[InlineKeyboardButton(text=gt, callback_data=f"gametype_{gt}")] for gt in game_types]
        await show_current_data(
            callback.message, state,
            "🎾 Выберите тип игры:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(GameOfferStates.GAME_TYPE)
    elif next_step == "comment":
        # Для встреч и знакомств - сразу к комментарию
        comment_prompt = get_game_comment_prompt(sport)
        await show_current_data(
            callback.message, state,
            comment_prompt
        )
        await state.set_state(GameOfferStates.GAME_COMMENT)
    
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_TYPE, F.data.startswith("gametype_"))
async def process_game_type(callback: types.CallbackQuery, state: FSMContext):
    game_type = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(game_type=game_type)
    
    # Получаем данные о виде спорта
    user_data = await state.get_data()
    sport = user_data.get('game_sport', user_data.get('sport', '🎾Большой теннис'))
    
    # Определяем следующий шаг
    next_step = get_next_game_step(sport, "type")
    
    if next_step == "payment":
        # Для спортивных видов - выбираем тип оплаты
        buttons = [[InlineKeyboardButton(text=pt, callback_data=f"paytype_{pt.split()[1]}")] for pt in payment_types]
        await show_current_data(
            callback.message, state,
            "💳 Выберите тип оплата:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(GameOfferStates.PAYMENT_TYPE)
    elif next_step == "comment":
        # Для встреч - сразу к комментарию
        comment_prompt = get_game_comment_prompt(sport)
        await show_current_data(
            callback.message, state,
            comment_prompt
        )
        await state.set_state(GameOfferStates.GAME_COMMENT)
    
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.PAYMENT_TYPE, F.data.startswith("paytype_"))
async def process_payment_type(callback: types.CallbackQuery, state: FSMContext):
    payment_type = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(payment_type=payment_type)
    
    # Получаем данные о виде спорта
    user_data = await state.get_data()
    sport = user_data.get('game_sport', user_data.get('sport', '🎾Большой теннис'))
    
    # Определяем следующий шаг
    next_step = get_next_game_step(sport, "payment")
    
    if next_step == "competitive":
        # Для спортивных видов - выбираем игру на счет
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
    elif next_step == "comment":
        # Для встреч - сразу к комментарию
        comment_prompt = get_game_comment_prompt(sport)
        await show_current_data(
            callback.message, state,
            comment_prompt
        )
        await state.set_state(GameOfferStates.GAME_COMMENT)
    
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_COMPETITIVE, F.data.startswith("gamecomp_"))
async def process_game_competitive(callback: types.CallbackQuery, state: FSMContext):
    competitive = callback.data.split("_", maxsplit=1)[1] == "yes"
    await state.update_data(game_competitive=competitive)
    
    # Получаем данные о виде спорта
    user_data = await state.get_data()
    sport = user_data.get('game_sport', user_data.get('sport', '🎾Большой теннис'))
    
    # Определяем следующий шаг
    next_step = get_next_game_step(sport, "competitive")
    
    if next_step == "comment":
        # Для спортивных видов - к комментарию
        comment_prompt = get_game_comment_prompt(sport)
        await show_current_data(
            callback.message, state,
            comment_prompt
        )
        await state.set_state(GameOfferStates.GAME_COMMENT)
    
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(GameOfferStates.GAME_COMMENT, F.text)
async def process_game_comment(message: types.Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(game_comment=message.text.strip())
    
    # Переходим к добавлению медиа
    await state.set_state(GameOfferStates.GAME_MEDIA)
    
    # Создаем клавиатуру для медиа
    keyboard_buttons = [
        [InlineKeyboardButton(text="📷 Прикрепить фото", callback_data="game_media:photo")],
        [InlineKeyboardButton(text="🎥 Прикрепить видео", callback_data="game_media:video")],
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data="game_media:skip")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(
        "Хотите прикрепить фото или видео к предложению игры?",
        reply_markup=keyboard
    )
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(GameOfferStates.GAME_MEDIA, F.data.startswith("game_media:"))
async def process_game_media_selection(callback: types.CallbackQuery, state: FSMContext):
    media_type = callback.data.split(":", 1)[1]
    
    if media_type == "skip":
        await state.update_data(game_media_filename=None)
    else:
        await state.update_data(game_media_type=media_type)
        await callback.message.edit_text(
            f"Отправьте {media_type} для предложения игры:"
        )
        await callback.answer()
        return
    
    # Продолжаем создание предложения
    await create_game_offer(callback.message, state)
    await callback.answer()

@router.message(GameOfferStates.GAME_MEDIA, F.photo)
async def process_game_photo(message: types.Message, state: FSMContext):
    from utils.media import save_media_file
    from config.paths import GAMES_PHOTOS_DIR
    
    # Генерируем временный ID для игры
    game_id = f"temp_{message.chat.id}_{int(datetime.now().timestamp())}"
    
    # Сохраняем фото
    photo_id = message.photo[-1].file_id
    filename = await save_media_file(message.bot, photo_id, "photo", game_id)
    
    await state.update_data(game_media_filename=filename)
    await create_game_offer(message, state)

@router.message(GameOfferStates.GAME_MEDIA, F.video)
async def process_game_video(message: types.Message, state: FSMContext):
    from utils.media import save_media_file
    from config.paths import GAMES_PHOTOS_DIR
    
    # Генерируем временный ID для игры
    game_id = f"temp_{message.chat.id}_{int(datetime.now().timestamp())}"
    
    # Сохраняем видео
    video_id = message.video.file_id
    filename = await save_media_file(message.bot, video_id, "video", game_id)
    
    await state.update_data(game_media_filename=filename)
    await create_game_offer(message, state)

async def create_game_offer(message: types.Message, state: FSMContext):
    """Создание предложения игры"""
    user_data = await state.get_data()
    sport = user_data.get('game_sport', user_data.get('sport', '🎾Большой теннис'))
    
    # Создаем базовые данные игры
    game_data = {
        "sport": sport,
        "city": user_data.get('game_city'),
        "comment": user_data.get('game_comment'),
        "media_filename": user_data.get('game_media_filename')
    }
    
    # Получаем конфигурацию для вида спорта
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    # Добавляем поля в зависимости от категории вида спорта
    if category == "dating":
        # Для знакомств - только город и комментарий
        pass
    elif category in ["meeting", "outdoor_sport"]:
        # Для встреч и активных видов спорта - добавляем дату и время
        game_data["date"] = user_data.get('game_date')
        game_data["time"] = user_data.get('game_time')
    else:  # court_sport
        # Для спортивных видов с кортами - добавляем все поля
        game_data["date"] = user_data.get('game_date')
        game_data["time"] = user_data.get('game_time')
        game_data["type"] = user_data.get('game_type')
        game_data["payment_type"] = user_data.get('payment_type')
        game_data["competitive"] = user_data.get('game_competitive')
    
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
    
    # Получаем тексты для вида спорта
    texts = get_sport_texts(sport)
    
    # Формируем информационное сообщение о созданной игре
    response = [
        f"✅ {texts['offer_created']}\n",
        f"🎮 #{game_id}",
        f"🎾 {sport}",
        f"🏙 {game_data.get('city', '—')}"
    ]
    
    # Получаем конфигурацию для вида спорта
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    # Добавляем поля в зависимости от категории вида спорта
    if category == "dating":
        # Для знакомств - только город и комментарий
        pass
    elif category in ["meeting", "outdoor_sport"]:
        # Для встреч и активных видов спорта - добавляем дату и время
        response.append(f"📅 {game_data.get('date', '—')}")
        response.append(f"⏰ {game_data.get('time', '—')}")
    else:  # court_sport
        # Для спортивных видов с кортами - добавляем все поля
        response.append(f"📅 {game_data.get('date', '—')}")
        response.append(f"⏰ {game_data.get('time', '—')}")
        response.append(f"🔍 {game_data.get('type', '—')}")
        response.append(f"💳 {game_data.get('payment_type', '—')}")
        response.append(f"🏆 На счет: {'Да' if game_data.get('competitive') else 'Нет'}")
    
    if game_data.get('comment'):
        response.append(f"💬 {game_data['comment']}")
    
    # Добавляем информацию о статусе подписки
    users = await storage.load_users()
    user_data = users.get(str(message.chat.id), {})
    subscription_active = user_data.get('subscription', {}).get('active', False)
    
    if not subscription_active:
        free_offers_used = user_data.get('free_offers_used', 0)
        remaining_offers = max(0, 1 - free_offers_used)
        response.append(f"\n📊 Бесплатных предложений осталось: {remaining_offers}/1")
        response.append("💳 Оформите подписку для неограниченного создания предложений!")
    else:
        response.append("💎 У вас активна подписка — создавайте игры без ограничений!")
    
    await send_game_offer_to_channel(message.bot, game_data, str(message.chat.id), user_data)
    await message.answer("\n".join(response), reply_markup=base_keyboard)

@router.message(F.text == "📋 Мои предложения")
async def list_my_games(message: types.Message, state: FSMContext):
    user_id = message.chat.id
    games = await get_user_games(user_id)
    
    # Получаем тексты для вида спорта пользователя
    user_profile = await storage.get_user(user_id)
    sport = user_profile.get('sport', '🎾Большой теннис') if user_profile else '🎾Большой теннис'
    texts = get_sport_texts(sport)
    
    if not games:
        await message.answer(f"❌ {texts['no_offers_text']}.")
        return
    
    active_games = [game for game in games if game.get('active', True)]
    
    if not active_games:
        await message.answer(f"❌ {texts['no_offers_text']}.")
        return
    
    # Сохраняем список активных игр в state для навигации
    await state.update_data(active_games=active_games, current_offer_index=0)
    
    # Показываем первое предложение
    game = active_games[0]
    sport = game.get('sport', '🎾Большой теннис')
    
    # Получаем тексты для вида спорта
    texts = get_sport_texts(sport)
    
    response = [
        f"🎾 {texts['offer_prefix']} #{game['id']} (1/{len(active_games)})",
        f"🏙 Город: {game.get('city', '—')}"
    ]
    
    # Получаем конфигурацию для вида спорта
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    # Добавляем поля в зависимости от категории вида спорта
    if category == "dating":
        # Для знакомств - только город и комментарий
        pass
    elif category in ["meeting", "outdoor_sport"]:
        # Для встреч и активных видов спорта - добавляем дату и время
        response.append(f"📅 Дата: {game.get('date', '—')}")
        response.append(f"⏰ Время: {game.get('time', '—')}")
    else:  # court_sport
        # Для спортивных видов с кортами - добавляем все поля
        response.append(f"📅 Дата: {game.get('date', '—')}")
        response.append(f"⏰ Время: {game.get('time', '—')}")
        response.append(f"🔍 Тип: {game.get('type', '—')}")
        response.append(f"💳 Оплата: {game.get('payment_type', '—')}")
        response.append(f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}")
        response.append(f"🔄 Повтор: {'Да' if game.get('repeat') else 'Нет'}")
    
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
    
    # Проверяем, есть ли медиафайл
    if game.get('media_filename'):
        from config.paths import GAMES_PHOTOS_DIR
        import os
        media_path = f"{GAMES_PHOTOS_DIR}/{game['media_filename']}"
        if os.path.exists(media_path):
            # Определяем тип медиа
            if game['media_filename'].endswith(('.jpg', '.jpeg', '.png')):
                with open(media_path, 'rb') as photo:
                    await message.answer_photo(
                        photo,
                        caption="\n".join(response),
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            elif game['media_filename'].endswith(('.mp4', '.mov')):
                with open(media_path, 'rb') as video:
                    await message.answer_video(
                        video,
                        caption="\n".join(response),
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            else:
                await message.answer("\n".join(response), reply_markup=keyboard, parse_mode='Markdown')
        else:
            await message.answer("\n".join(response), reply_markup=keyboard, parse_mode='Markdown')
    else:
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
