from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config.config import ITEMS_PER_PAGE
from utils.json_data import load_users, load_json
from models.states import BrowseOffersStates

router = Router()

# ---------- Загрузка данных ----------
cities_data = load_json("cities.json")

@router.message(F.text == "⏱ Предложение игр")
async def browse_offers_start(message: types.Message, state: FSMContext):
    """Начало просмотра предложенных игр - выбор страны"""
    users = load_users()
    
    # Собираем статистику по странам
    country_stats = {}
    for user_id, user_data in users.items():
        if user_data.get('games'):
            country = user_data.get('country', '')
            if country:
                active_games = [game for game in user_data['games'] if game.get('active', True)]
                if active_games:
                    country_stats[country] = country_stats.get(country, 0) + len(active_games)
    
    if not country_stats:
        await message.answer("❌ На данный момент нет активных предложений игр.")
        return
    
    # Создаем клавиатуру с кнопками стран
    buttons = []
    for country, count in country_stats.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{country} ({count} предложений)",
                callback_data=f"offercountry_{country}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        "🌍 Выберите страну для просмотра предложений игр:",
        reply_markup=keyboard
    )
    await state.set_state(BrowseOffersStates.SELECT_COUNTRY)
    await state.update_data(page=0)

@router.callback_query(BrowseOffersStates.SELECT_COUNTRY, F.data.startswith("offercountry_"))
async def select_offer_country(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора страны"""
    country = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(selected_country=country)
    
    users = load_users()
    
    # Собираем статистику по городам в выбранной стране
    city_stats = {}
    for user_id, user_data in users.items():
        if user_data.get('country') == country and user_data.get('games'):
            city = user_data.get('city', '')
            if city:
                active_games = [game for game in user_data['games'] if game.get('active', True)]
                if active_games:
                    city_stats[city] = city_stats.get(city, 0) + len(active_games)
    
    if not city_stats:
        await callback.answer("❌ В этой стране нет активных предложений")
        return
    
    # Создаем клавиатуру с кнопками городов
    buttons = []
    for city, count in city_stats.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"🏙 {city} ({count} предложений)",
                callback_data=f"offercity_{city}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🏙 Выберите город в {country}:",
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
    
    await state.update_data(selected_city=city)
    
    # Получаем все активные предложения в выбранном городе и стране
    users = load_users()
    all_offers = []
    
    for user_id, user_data in users.items():
        if (user_data.get('country') == country and 
            user_data.get('city') == city and 
            user_data.get('games')):
            
            user_name = f"{user_data.get('first_name', 'Неизвестно')} {user_data.get('last_name', '')}".strip()
            
            for game in user_data['games']:
                if game.get('active', True):
                    offer = {
                        'user_id': user_id,
                        'user_name': user_name,
                        'game_id': game.get('id'),
                        'city': game.get('city'),
                        'date': game.get('date'),
                        'time': game.get('time'),
                        'game_type': game.get('type'),
                        'payment_type': game.get('payment_type'),
                        'competitive': game.get('competitive'),
                        'repeat': game.get('repeat'),
                        'comment': game.get('comment')
                    }
                    all_offers.append(offer)
    
    if not all_offers:
        await callback.answer("❌ В этом городе нет активных предложений")
        return
    
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
    
    if not all_offers:
        await message.answer("❌ Нет предложений для отображения")
        return
    
    # Вычисляем индексы для текущей страницы
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_offers = all_offers[start_idx:end_idx]
    
    # Создаем сообщение
    text = f"🎾 Предложения игр в {state_data.get('selected_city')}:\n\n"
    
    for i, offer in enumerate(page_offers, start=1):
        text += f"{start_idx + i}. {offer['user_name']}\n"
        text += f"   📅 {offer.get('date', '—')} ⏰ {offer.get('time', '—')}\n"
        text += f"   🎾 {offer.get('game_type', '—')}\n"
        text += "─" * 30 + "\n"
    
    text += f"\nСтраница {current_page + 1}/{(len(all_offers) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE}"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждого предложения на странице
    for i, offer in enumerate(page_offers):
        builder.row(InlineKeyboardButton(
            text=f"🎾 {start_idx + i + 1}. {offer['user_name']}",
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
    builder.row(InlineKeyboardButton(text="🎾 Предложить игру", callback_data="new_offer"))
    
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
async def view_offer_details(callback: types.CallbackQuery):
    """Просмотр деталей конкретного предложения"""
    parts = callback.data.split("_")
    user_id = parts[1]
    game_id = parts[2]
    
    users = load_users()
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
    
    # Формируем детальную информацию
    user_name = f"{user_data.get('first_name', 'Неизвестно')} {user_data.get('last_name', '')}".strip()
    
    text = f"🎾 Детали предложения от {user_name}\n\n"
    text += f"🏙 Город: {game.get('city', '—')}\n"
    text += f"📅 Дата: {game.get('date', '—')}\n"
    text += f"⏰ Время: {game.get('time', '—')}\n"
    text += f"🔍 Тип игры: {game.get('type', '—')}\n"
    text += f"💳 Оплата: {game.get('payment_type', '—')}\n"
    text += f"🏆 На счет: {'Да' if game.get('competitive') else 'Нет'}\n"
    text += f"🔄 Повтор: {'Да' if game.get('repeat') else 'Нет'}\n"
    
    if game.get('comment'):
        text += f"💬 Комментарий: {game['comment']}\n"
    
    # Кнопка для возврата к списку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_offers_list")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "back_to_offers_list")
async def back_to_offers_list(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку предложений"""
    await show_offers_page(callback.message, state)
    await callback.answer()
