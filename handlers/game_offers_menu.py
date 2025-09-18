from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config.config import ITEMS_PER_PAGE, SUBSCRIPTION_PRICE
from config.profile import create_sport_keyboard, sport_type, get_sport_config
from services.storage import storage
from utils.admin import is_admin
from models.states import BrowseOffersStates, RespondToOfferStates
from utils.utils import create_user_profile_link, get_sort_key

router = Router()

@router.message(F.text == "⏱ Предложение игр")
async def browse_offers_start(message: types.Message, state: FSMContext):
    """Начало просмотра предложенных игр - выбор вида спорта"""
    await message.answer(
        "Выберите вид спорта:",
        reply_markup=create_sport_keyboard(pref="offersport_")
    )
    await state.set_state(BrowseOffersStates.SELECT_SPORT)
    await state.update_data(page=0)

@router.callback_query(BrowseOffersStates.SELECT_SPORT, F.data.startswith("offersport_"))
async def select_offer_sport(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора вида спорта"""
    sport_type_selected = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(selected_sport=sport_type_selected)
    
    users = await storage.load_users()
    current_user_id = str(callback.message.chat.id)
    
    # Собираем статистику по странам для выбранного вида спорта
    country_stats = {}
    for user_id, user_data in users.items():
        if user_data.get('games'):
            for game in user_data['games']:
                if (game.get('active', True) and 
                    game.get('sport') == sport_type_selected and
                    game.get('country')):
                    country = game.get('country')
                    country_stats[country] = country_stats.get(country, 0) + 1
    
    if not country_stats:
        await callback.message.edit_text(
            f"❌ На данный момент нет активных предложений игр в {sport_type_selected} от других пользователей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}")],
                [InlineKeyboardButton(text="🔙 Назад к выбору спорта", callback_data="back_to_sport_selection")]
            ])
        )
        return
    
    # Создаем клавиатуру с кнопками стран
    buttons = []
    
    # Сортируем страны: Россия всегда первая, остальные по убыванию количества предложений
    sorted_countries = sorted(country_stats.items(), key=lambda x: x[1], reverse=True)
    
    # Выделяем Россию и ставим её первой
    russia_count = None
    other_countries = []
    
    for country, count in sorted_countries:
        # Проверяем различные варианты написания России
        if ("🇷🇺" in country and "Россия" in country) or country == "🇷🇺 Россия":
            russia_count = (country, count)
        else:
            other_countries.append((country, count))
    
    # Формируем итоговый список: Россия первая, остальные по убыванию
    final_countries = []
    if russia_count:
        final_countries.append(russia_count)
    final_countries.extend(other_countries)
    
    for country, count in final_countries:
        buttons.append([
            InlineKeyboardButton(
                text=f"{country} ({count} предложений)",
                callback_data=f"offercountry_{country}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}")
    ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Назад к выбору спорта", callback_data="back_to_sport_selection")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🌍 Выберите страну для просмотра предложений {sport_type_selected}:",
        reply_markup=keyboard
    )
    await state.set_state(BrowseOffersStates.SELECT_COUNTRY)
    await callback.answer()

@router.callback_query(BrowseOffersStates.SELECT_COUNTRY, F.data.startswith("offercountry_"))
async def select_offer_country(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора страны"""
    country = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    sport_type_selected = state_data.get('selected_sport')
    
    await state.update_data(selected_country=country)
    
    users = await storage.load_users()
    
    # Собираем статистику по городам в выбранной стране для выбранного вида спорта
    city_stats = {}
    for user_id, user_data in users.items():
        if user_data.get('games'):
            for game in user_data['games']:
                if (game.get('active', True) and 
                    game.get('sport') == sport_type_selected and
                    game.get('country') == country and
                    game.get('city')):
                    city = game.get('city')
                    city_stats[city] = city_stats.get(city, 0) + 1
    
    if not city_stats:
        await callback.message.edit_text(
            f"❌ В {country} нет активных предложений по {sport_type_selected}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к выбору страны", callback_data="back_to_country_selection")]
            ])
        )
        return
    
    # Создаем клавиатуру с кнопками городов
    buttons = []
    for city, count in city_stats.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{city} ({count} предложений)",
                callback_data=f"offercity_{city}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}")
    ])
    # Добавляем кнопку возврата
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад к выбору страны", callback_data="back_to_country_selection")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🏙 Выберите город в {country} для {sport_type_selected}:",
        reply_markup=keyboard
    )
    await state.set_state(BrowseOffersStates.SELECT_CITY)
    await callback.answer()

@router.callback_query(BrowseOffersStates.SELECT_CITY, F.data.startswith("offercity_"))
async def select_offer_city(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора города и отображение предложений"""
    city = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    country = state_data.get('selected_country')
    sport_type_selected = state_data.get('selected_sport')
    
    await state.update_data(selected_city=city)
    
    # Получаем все активные предложения в выбранном городе, стране и виде спорта
    users = await storage.load_users()
    all_offers = []
    
    for user_id, user_data in users.items():
        if user_data.get('games') and user_id != callback.message.chat.id:
            user_name = f"{user_data.get('first_name', 'Неизвестно')[:1]}.{user_data.get('last_name', '')}".strip()
            
            for game in user_data['games']:
                if (game.get('active', True) and 
                    game.get('sport') == sport_type_selected and
                    game.get('country') == country and 
                    game.get('city') == city):
                    
                    offer = {
                        'user_id': user_id,
                        'user_name': user_name,
                        'player_level': user_data.get('player_level'),
                        'gender': user_data.get('gender'),
                        'district': game.get('district'),
                        'game_id': game.get('id'),
                        'country': game.get('country'),
                        'city': game.get('city'),
                        'date': game.get('date'),
                        'time': game.get('time'),
                        'sport_type': game.get('sport'),
                        'game_type': game.get('type'),
                        'payment_type': game.get('payment_type'),
                        'competitive': game.get('competitive'),
                        'repeat': game.get('repeat'),
                        'comment': game.get('comment')
                    }
                    all_offers.append(offer)
    
    if not all_offers:
        await callback.message.edit_text(
            f"❌ В {city} нет активных предложений по {sport_type_selected}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к выбору города", callback_data="back_to_city_selection")]
            ])
        )
        return
    
    all_offers.sort(key=get_sort_key)
    
    # Сохраняем все предложения в state
    await state.update_data(all_offers=all_offers, current_page=0)
    
    # Показываем первую страницу предложений
    await show_offers_page(callback.message, state)
    await callback.answer()

async def show_offers_page(message: types.Message, state: FSMContext):
    """Показать страницу с предложениями"""
    state_data = await state.get_data()
    all_offers = state_data.get('all_offers', [])
    current_page = state_data.get('current_page', 0)
    sport_type_selected = state_data.get('selected_sport')
    city = state_data.get('selected_city')
    
    if not all_offers:
        await message.answer("❌ Нет предложений для отображения")
        return
    
    # Вычисляем индексы для текущей страницы
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_offers = all_offers[start_idx:end_idx]
    
    # Заголовок
    country = state_data.get('selected_country', '')
    text = f"🎾 Предложения {sport_type_selected} в {country}, {city}\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждого предложения на странице
    for i, offer in enumerate(page_offers, start=1):
        # Определяем стикер пола
        gender_icon = "👨" if offer.get('gender', 'male') == 'Мужской' else "👩"
        
        # Имя + уровень
        if offer.get('player_level', '-'):
            user_info = f"{offer['user_name']} ({offer.get('player_level', '-')} lvl)"
        else:
            user_info = f"{offer['user_name']}"
        
        # Дата → только число
        raw_date = offer.get('date')
        day_str = "—"
        if raw_date:
            try:
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                day_str = f"{dt.day}е"
            except ValueError:
                day_str = raw_date[:2] + "е"
        
        # Время
        time = offer.get('time', '-')
        district = '' if offer.get('district', '') == None else offer.get('district', '')
        
        # Получаем информацию о виде спорта для краткого описания
        sport = offer.get('sport', '🎾Большой теннис')
        config = get_sport_config(sport)
        category = config.get("category", "court_sport")
        
        # Итоговая строка
        short_info = f"{day_str} {time} {district} {gender_icon} {user_info}"
        
        builder.row(InlineKeyboardButton(
            text=short_info,
            callback_data=f"viewoffer_{offer['user_id']}_{offer['game_id']}"
        ))
    
    # Кнопки навигации
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="offerpage_prev"))
    if end_idx < len(all_offers):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data="offerpage_next"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Кнопка для предложения новой игры
    builder.row(InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}"))
    
    # Кнопка возврата к выбору города
    builder.row(InlineKeyboardButton(text="🔙 Назад к выбору города", callback_data="back_to_city_selection"))
    
    # Отправляем сообщение
    if message.content_type == 'text':
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("offerpage_"))
async def handle_offer_page_navigation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка навигации по страницам"""
    action = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    current_page = state_data.get('current_page', 0)
    all_offers = state_data.get('all_offers', [])
    
    if action == "prev" and current_page > 0:
        current_page -= 1
    elif action == "next" and (current_page + 1) * ITEMS_PER_PAGE < len(all_offers):
        current_page += 1
    
    await state.update_data(current_page=current_page)
    await show_offers_page(callback.message, state)
    await callback.answer()

@router.callback_query(F.data.startswith("viewoffer_"))
async def view_offer_details(callback: types.CallbackQuery, state: FSMContext):
    """Просмотр деталей конкретного предложения"""
    parts = callback.data.split("_")
    user_id = parts[1]
    game_id = parts[2]
    
    users = await storage.load_users()
    user_data = users.get(user_id)
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден")
        return
    
    # Ищем игру
    game = None
    for g in user_data.get('games', []):
        if str(g.get('id')) == game_id and g.get('active', True):
            game = g
            break
    
    if not game:
        await callback.answer("❌ Предложение не найдено")
        return
    
    # Сохраняем информацию о выбранном предложении для возможного отклика
    await state.update_data(
        selected_offer_user_id=user_id,
        selected_offer_game_id=game_id
    )
    
    # Формируем детальную информацию
    username = user_data.get("username")
    username_str = f"@{username}" if username else "👤 (без username)"

    # Имя + уровень
    user_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
    player_level = user_data.get("player_level", "—")
    
    # Получаем вид спорта из игры и конфигурацию
    sport = game.get('sport', '🎾Большой теннис')
    config = get_sport_config(sport)
    category = config.get("category", "court_sport")
    
    # Формируем текст в зависимости от категории вида спорта
    if category == "dating":
        text = (
            f"{sport}\n"
            f"👤 {user_name} {username_str}\n"
            f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
            f"📅 Дата: {game.get('date', '—')}\n"
            f"⏰ Время: {game.get('time', '—')}\n"
        )
        if game.get('dating_goal'):
            text += f"💕 Цель: {game.get('dating_goal')}\n"
        if game.get('dating_interests'):
            interests = ', '.join(game.get('dating_interests', []))
            text += f"🎯 Интересы: {interests}\n"
        if game.get('dating_additional'):
            text += f"📝 О себе: {game.get('dating_additional')}\n"
    elif category == "meeting":
        if sport == "☕️Бизнес-завтрак":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
        else:  # По пиву
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
    elif category == "outdoor_sport":
        if sport == "⛳Гольф":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
        elif sport == "🏃‍♂️‍➡️Бег":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
        elif sport == "🏋️‍♀️Фитнес":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n" 
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
        elif sport == "🚴Вело":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
        else:
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
            )
    else:  # court_sport
        if sport == "🎾Большой теннис":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        elif sport == "🏓Настольный теннис":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        elif sport == "🏸Бадминтон":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        elif sport == "🏖️Пляжный теннис":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        elif sport == "🎾Падл-теннис":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        elif sport == "🥎Сквош":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        elif sport == "🏆Пиклбол":
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
        else:
            text = (
                f"{sport}\n"
                f"👤 {user_name} {username_str}\n"
                f"🏅 Рейтинг {user_data.get('rating_points', '—')} (Лвл: {player_level})\n"
                f"🌍 {game.get('country', '—')}, {game.get('city', '—')} {game.get('district', '—')}\n"
                f"📊 Сыграно матчей: {user_data.get('games_played', 0)}\n\n"
                f"📅 Дата: {game.get('date', '—')}\n"
                f"⏰ Время: {game.get('time', '—')}\n"
                f"🔍 Тип: {game.get('type', '—')}\n"
                f"💳 Оплата: {game.get('payment_type', '—')}\n"
                f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
            )
    
    if game.get('comment'):
        text += f"💬 Комментарий: {game['comment']}\n"
    
    # Добавляем ID для админа
    if await is_admin(callback.message.chat.id):
        text += f"\n🆔 ID предложения: `{game_id}`"
        text += f"\n🆔 ID пользователя: `{user_id}`"
    
    # Создаем клавиатуру
    keyboard_buttons = []
    
    # Кнопка отклика (только если это не свое предложение)
    if str(callback.message.chat.id) != user_id:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="✅ Откликнуться на предложение", 
                callback_data="respond_to_offer"
            )
        ])
    
    # Кнопка возврата
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="🔙 Назад к списку", 
            callback_data="back_to_offers_list"
        )
    ])
    
    # Кнопка удаления для админа (если это не свое предложение)
    if (await is_admin(callback.message.chat.id)):
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🗑️ Удалить предложение", 
                callback_data=f"admin_select_offer:{user_id}:{game_id}"
            )
        ])
    
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
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            elif game['media_filename'].endswith(('.mp4', '.mov')):
                with open(media_path, 'rb') as video:
                    await callback.message.delete()
                    await callback.message.answer_video(
                        video,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            else:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
        else:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
    
    await callback.answer()

@router.callback_query(F.data == "back_to_offers_list")
async def back_to_offers_list(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку предложений"""
    await show_offers_page(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "respond_to_offer")
async def start_respond_to_offer(callback: types.CallbackQuery, state: FSMContext):
    """Начало процесса отклика на предложение"""
    await callback.message.edit_text(
        "💬 Напишите комментарий к вашему отклику (необязательно):\n\n"
        "Или нажмите /skip чтобы пропустить этот шаг."
    )
    await state.set_state(RespondToOfferStates.ENTER_COMMENT)
    await callback.answer()

@router.message(RespondToOfferStates.ENTER_COMMENT, F.text == "/skip")
@router.message(RespondToOfferStates.ENTER_COMMENT, F.text)
async def process_respond_comment(message: types.Message, state: FSMContext):
    """Обработка комментария для отклика и отправка уведомления"""
    comment = message.text if message.text != "/skip" else "Без комментария"
    
    state_data = await state.get_data()
    target_user_id = state_data.get('selected_offer_user_id')
    game_id = state_data.get('selected_offer_game_id')
    
    if not target_user_id or not game_id:
        await message.answer("❌ Ошибка: информация о предложении не найдена")
        await state.clear()
        return
    
    # Загружаем данные пользователей
    users = await storage.load_users()
    
    # Получаем информацию о текущем пользователе
    current_user = users.get(str(message.chat.id))
    if not current_user:
        await message.answer("❌ Ошибка: ваш профиль не найден")
        await state.clear()
        return
    
    # Получаем информацию о целевом пользователе
    target_user = users.get(target_user_id)
    if not target_user:
        await message.answer("❌ Ошибка: пользователь предложения не найдена")
        await state.clear()
        return
    
    # Находим игру
    game = None
    for g in target_user.get('games', []):
        if str(g.get('id')) == game_id:
            game = g
            break
    
    if not game:
        await message.answer("❌ Ошибка: предложение игры не найдено")
        await state.clear()
        return
    
    # Формируем имя пользователя со ссылкой на профиль
    respondent_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
    respondent_username = current_user.get('username')
    
    profile_link = await create_user_profile_link(current_user, str(message.chat.id))
    
    # Создаем объект отклика
    response_data = {
        'respondent_id': str(message.chat.id),
        'respondent_name': respondent_name,
        'respondent_username': respondent_username,
        'respondent_level': current_user.get('player_level', '—'),
        'game_id': game_id,
        'game_date': game.get('date'),
        'game_time': game.get('time'),
        'sport_type': current_user.get('sport'),
        'comment': comment,
        'response_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'pending'  # pending, accepted, rejected
    }
    
    # Добавляем отклик в данные целевого пользователя
    if 'offer_responses' not in target_user:
        target_user['offer_responses'] = []
    
    target_user['offer_responses'].append(response_data)
    
    # Сохраняем обновленные данные
    users[target_user_id] = target_user
    await storage.save_users(users)
    
    # Формируем сообщение для целевого пользователя
    target_message = (
        f"🎾 Новый отклик на ваше предложение игры в {target_user.get('sport', '—')}!\n\n"
        f"👤 От: {profile_link}\n"
        f"📅 Дата игры: {game.get('date', '—')} {game.get('time', '—')}\n"
        f"💬 Комментарий: {comment}\n"
    )
    
    # Отправляем уведомление целевому пользователю
    try:
        await message.bot.send_message(
            chat_id=target_user_id, 
            text=target_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        await message.answer(
            "✅ Ваш отклик успешно отправлен! Пользователь получил уведомление.\n"
        )
    except Exception as e:
        await message.answer(
            "✅ Ваш отклик сохранен, но не удалось отправить уведомление пользователю. "
            "Возможно, он заблокировал бота."
        )
    
    await state.clear()

@router.callback_query(F.data == "back_to_sport_selection")
async def back_to_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору вида спорта"""
    await callback.message.edit_text(
        "🎯 Выберите вид спорта для просмотра предложений игр:",
        reply_markup=create_sport_keyboard(pref="offersport_")
    )
    await state.set_state(BrowseOffersStates.SELECT_SPORT)
    await callback.answer()

@router.callback_query(F.data == "back_to_country_selection")
async def back_to_country_selection(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору страны"""
    state_data = await state.get_data()
    sport_type_selected = state_data.get('selected_sport')
    
    users = await storage.load_users()
    current_user_id = str(callback.message.chat.id)
    
    # Собираем статистику по странам (исключая текущего пользователя) для выбранного вида спорта
    country_stats = {}
    for user_id, user_data in users.items():
        if user_data.get('games'):
            for game in user_data['games']:
                if (game.get('active', True) and 
                    game.get('sport') == sport_type_selected and
                    game.get('country')):
                    country = game.get('country')
                    country_stats[country] = country_stats.get(country, 0) + 1
    
    if not country_stats:
        await callback.message.edit_text(
            f"❌ На данный момент нет активных предложений игр в {sport_type_selected} от других пользователей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}")],
                [InlineKeyboardButton(text="🔙 Назад к выбору спорта", callback_data="back_to_sport_selection")]
            ])
        )
        return
    
    # Создаем клавиатуру с кнопками стран
    buttons = []
    
    # Сортируем страны: Россия всегда первая, остальные по убыванию количества предложений
    sorted_countries = sorted(country_stats.items(), key=lambda x: x[1], reverse=True)
    
    # Выделяем Россию и ставим её первой
    russia_count = None
    other_countries = []
    
    for country, count in sorted_countries:
        # Проверяем различные варианты написания России
        if ("🇷🇺" in country and "Россия" in country) or country == "🇷🇺 Россия":
            russia_count = (country, count)
        else:
            other_countries.append((country, count))
    
    # Формируем итоговый список: Россия первая, остальные по убыванию
    final_countries = []
    if russia_count:
        final_countries.append(russia_count)
    final_countries.extend(other_countries)
    
    for country, count in final_countries:
        buttons.append([
            InlineKeyboardButton(
                text=f"{country} ({count} предложений)",
                callback_data=f"offercountry_{country}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}")
    ])
    
    # Добавляем кнопку возврата
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад к выбору спорта", callback_data="back_to_sport_selection")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🌍 Выберите страну для просмотра предложений {sport_type_selected}:",
        reply_markup=keyboard
    )
    await state.set_state(BrowseOffersStates.SELECT_COUNTRY)
    await callback.answer()

@router.callback_query(F.data == "back_to_city_selection")
async def back_to_city_selection(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору города"""
    state_data = await state.get_data()
    country = state_data.get('selected_country')
    sport_type_selected = state_data.get('selected_sport')
    
    users = await storage.load_users()
    
    # Собираем статистику по городам в выбранной стране для выбранного вида спорта
    city_stats = {}
    for user_id, user_data in users.items():
        if user_data.get('games'):
            for game in user_data['games']:
                if (game.get('active', True) and 
                    game.get('sport') == sport_type_selected and
                    game.get('country') == country and
                    game.get('city')):
                    city = game.get('city')
                    city_stats[city] = city_stats.get(city, 0) + 1
    
    if not city_stats:
        await callback.message.edit_text(
            f"❌ В {country} нет активных предложений по {sport_type_selected}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к выбору страны", callback_data="back_to_country_selection")]
            ])
        )
        return
    
    # Создаем клавиатуру с кнопками городов
    buttons = []
    for city, count in city_stats.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{city} ({count} предложений)",
                callback_data=f"offercity_{city}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="Предложить игру", callback_data=f"new_offer_{sport_type_selected}")
    ])

    # Добавляем кнопку возврата
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад к выбору страны", callback_data="back_to_country_selection")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🏙 Выберите город в {country} для {sport_type_selected}:",
        reply_markup=keyboard
    )
    await state.set_state(BrowseOffersStates.SELECT_CITY)
    await callback.answer()
