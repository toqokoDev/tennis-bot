from typing import Union
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import SUBSCRIPTION_PRICE
from config.profile import PRICE_RANGES
from models.states import SearchStates
from utils.admin import is_admin
from utils.bot import show_profile
from utils.json_data import get_user_profile_from_storage, is_user_registered, load_json, load_users
from utils.ssesion import save_session
from utils.utils import count_users_by_location

router = Router()

cities_data = load_json("cities.json")
sport_type = load_json("sports.json")
countries = list(cities_data.keys())

# Интервалы стоимости уроков тренера

@router.message(F.text == "🔍 Еще")
async def handle_more(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🌍 Все игроки", callback_data="all_players"),
        types.InlineKeyboardButton(text="🔍 Поиск тренера", callback_data="find_coach")
    )
    builder.row(
        types.InlineKeyboardButton(text="О нас", callback_data="about"),
        types.InlineKeyboardButton(text="📞 Контакты", callback_data="contacts")
    )
    builder.row(
        types.InlineKeyboardButton(text="🏆 Многодневные турниры", url="https://tennis-play.com/tournaments/"),
        types.InlineKeyboardButton(text="🏆 Турниры выходного дня", url="https://tennis-play.com/tournaments/weekend/")
    )
    builder.row(
        types.InlineKeyboardButton(text="👤 Моя анкета", callback_data="profile"),
        types.InlineKeyboardButton(text="Перейти на сайт", url="https://tennis-play.com/")
    )
    
    await message.answer("Дополнительные опции:", reply_markup=builder.as_markup())

# Обработчики инлайн кнопок
@router.callback_query(F.data == "about")
async def handle_about(callback: types.CallbackQuery):
    about_text = (
        "Tennis-Play - это платформа для организации теннисных турниров и матчей.\n\n"
        "Мы предлагаем:\n"
        "- Удобную систему записи на турниры\n"
        "- Рейтинговую систему\n"
        "- Организацию матчей с игроками своего уровня\n"
        "- Статистику и историю встреч\n\n"
        "Подробнее на нашем сайте: https://tennis-play.com/contacts/"
    )
    await callback.message.edit_text(about_text)
    await callback.answer()

@router.callback_query(F.data == "contacts")
async def handle_contacts(callback: types.CallbackQuery):
    contacts_text = (
        "По всем вопросам работы бота и предложениям пишите на адрес:\n"
        "📧 info@tennis-play.com"
    )
    await callback.message.edit_text(contacts_text)
    await callback.answer()

@router.callback_query(F.data == "all_players")
async def handle_all_players(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.SEARCH_TYPE)
    await state.update_data(search_type="players")
    
    user_id = callback.message.chat.id
    users = load_users()

    if not is_admin(user_id):
        if not users[str(user_id)].get('subscription', {}).get('active', False):
            text = (
                "🔒 <b>Доступ закрыт</b>\n\n"
                "Функция просмотра всех игроков доступна только для пользователей с активной подпиской Tennis-Play PRO.\n\n"
                f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n\n"
                "Перейдите в раздел '💳 Платежи' для оформления подписки."
            )
            
            await callback.message.answer(
                text,
                parse_mode="HTML"
            )

            await state.clear()
            return
    
    buttons = []
    for country in countries[:5]:
        count = count_users_by_location("players", country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    count_other = count_users_by_location("players") - sum(count_users_by_location("players", c) for c in countries[:5])
    buttons.append([InlineKeyboardButton(
        text=f"🌎 Другие страны ({count_other})", 
        callback_data="search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад", 
        callback_data="back_to_main"
    )])

    await callback.message.edit_text(
        "🌍 Выберите страну для поиска игроков:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

@router.callback_query(F.data == "find_coach")
async def handle_find_coach(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.SEARCH_TYPE)
    await state.update_data(search_type="coaches")
    
    buttons = []
    for country in countries[:5]:
        count = count_users_by_location("coaches", country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    count_other = count_users_by_location("coaches") - sum(count_users_by_location("coaches", c) for c in countries[:5])
    buttons.append([InlineKeyboardButton(
        text=f"🌎 Другие страны ({count_other})", 
        callback_data="search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад", 
        callback_data="back_to_main"
    )])

    await callback.message.edit_text(
        "🌍 Выберите страну для поиска тренеров:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data.startswith("search_country_"))
async def process_search_country(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(search_country=country)
    
    data = await state.get_data()
    search_type = data.get('search_type')
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринburg", "Казань"]
        buttons = []
        for city in main_russian_cities:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in main_russian_cities)
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="search_other_city"
        )])
    else:
        cities = cities_data.get(country, [])
        buttons = []
        for city in cities[:5]:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in cities[:5])
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="search_other_city"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к странам", 
        callback_data="back_to_countries"
    )])
    
    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🏙 Выберите город для поиска {search_type_text} в {country}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    
    # Для тренеров добавляем этап выбора вида спорта
    if search_type == "coaches":
        await state.set_state(SearchStates.SEARCH_CITY)
    else:
        await state.set_state(SearchStates.SEARCH_CITY)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data == "search_other_country")
async def process_search_other_country(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🌍 Введите название страны для поиска {search_type_text}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_countries")
        ]])
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY_INPUT)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🌍 Все игроки", callback_data="all_players"),
        types.InlineKeyboardButton(text="🔍 Поиск тренера", callback_data="find_coach")
    )
    builder.row(
        types.InlineKeyboardButton(text="О нас", callback_data="about"),
        types.InlineKeyboardButton(text="📞 Контакты", callback_data="contacts")
    )
    builder.row(
        types.InlineKeyboardButton(text="🏆 Многодневные турниры", url="https://tennis-play.com/tournaments/"),
        types.InlineKeyboardButton(text="🏆 Турниры выходного дня", url="https://tennis-play.com/tournaments/weekend/")
    )
    builder.row(
        types.InlineKeyboardButton(text="👤 Моя анкета", callback_data="profile"),
        types.InlineKeyboardButton(text="Перейти на сайт", url="https://tennis-play.com/")
    )
    
    await callback.message.edit_text("Дополнительные опции:", reply_markup=builder.as_markup())
    await callback.answer()

@router.message(SearchStates.SEARCH_COUNTRY_INPUT, F.text)
async def process_search_country_input(message: Message, state: FSMContext):
    await state.update_data(search_country=message.text.strip())
    
    data = await state.get_data()
    search_type = data.get('search_type')
    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await message.answer(
        f"🏙 Введите название города для поиска {search_type_text}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_countries")
        ]])
    )
    await state.set_state(SearchStates.SEARCH_CITY_INPUT)
    save_session(message.from_user.id, await state.get_data())

@router.callback_query(SearchStates.SEARCH_CITY, F.data.startswith("search_city_"))
async def process_search_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(search_city=city)
    
    data = await state.get_data()
    search_type = data.get('search_type')
    
    # Для тренеров добавляем выбор вида спорта
    if search_type == "coaches":
        await show_sport_types(callback.message, state)
    else:
        await perform_search(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_CITY, F.data == "search_other_city")
async def process_search_other_city(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🏙 Введите название города для поиска {search_type_text}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cities")
        ]])
    )
    await state.set_state(SearchStates.SEARCH_CITY_INPUT)
    await callback.answer()

@router.callback_query(F.data == "back_to_countries")
async def back_to_countries(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    
    buttons = []
    for country in countries[:5]:
        count = count_users_by_location(search_type, country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    count_other = count_users_by_location(search_type) - sum(count_users_by_location(search_type, c) for c in countries[:5])
    buttons.append([InlineKeyboardButton(
        text=f"🌎 Другие страны ({count_other})", 
        callback_data="search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад", 
        callback_data="back_to_main"
    )])

    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🌍 Выберите страну для поиска {search_type_text}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

@router.message(SearchStates.SEARCH_CITY_INPUT, F.text)
async def process_search_city_input(message: Message, state: FSMContext):
    await state.update_data(search_city=message.text.strip())
    
    data = await state.get_data()
    search_type = data.get('search_type')
    
    # Для тренеров добавляем выбор вида спорта
    if search_type == "coaches":
        await show_sport_types(message, state)
    else:
        await perform_search(message, state)
    save_session(message.from_user.id, await state.get_data())

@router.callback_query(SearchStates.SEARCH_CITY_INPUT, F.data == "back_to_countries")
async def back_to_countries_from_input(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    
    buttons = []
    for country in countries[:5]:
        count = count_users_by_location(search_type, country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    count_other = count_users_by_location(search_type) - sum(count_users_by_location(search_type, c) for c in countries[:5])
    buttons.append([InlineKeyboardButton(
        text=f"🌎 Другие страны ({count_other})", 
        callback_data="search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад", 
        callback_data="back_to_main"
    )])

    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🌍 Выберите страну для поиска {search_type_text}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

async def show_sport_types(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message = message.message
    
    builder = InlineKeyboardBuilder()
    
    for sport in sport_type:
        builder.add(InlineKeyboardButton(
            text=sport,
            callback_data=f"sport_{sport}"
        ))
    
    builder.adjust(2)
    
    # Кнопка "Любой вид спорта"
    builder.row(InlineKeyboardButton(
        text="🏆 Любой вид спорта",
        callback_data="sport_any"
    ))
    
    # Кнопка возврата
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к городам",
        callback_data="back_to_cities"
    ))
    
    await message.answer(
        "🏆 Выберите вид спорта:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchStates.SEARCH_SPORT)

@router.callback_query(SearchStates.SEARCH_SPORT, F.data.startswith("sport_"))
async def process_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "sport_any":
        await state.update_data(sport_type=None)
    else:
        sport_type = callback.data.split("_", 1)[1]
        await state.update_data(sport_type=sport_type)
    
    await show_price_ranges(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_SPORT, F.data == "back_to_cities")
async def back_to_cities_from_sport(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country = data.get('search_country')
    search_type = data.get('search_type')
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = []
        for city in main_russian_cities:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"🏙 {city} ({count})", 
                callback_data=f"search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in main_russian_cities)
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="search_other_city"
        )])
    else:
        cities = cities_data.get(country, [])
        buttons = []
        for city in cities[:5]:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"🏙 {city} ({count})", 
                callback_data=f"search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in cities[:5])
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="search_other_city"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к странам", 
        callback_data="back_to_countries"
    )])
    
    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🏙 Выберите город для поиска {search_type_text} в {country}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_CITY)
    await callback.answer()

async def show_price_ranges(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message = message.message
    
    builder = InlineKeyboardBuilder()
    
    for price_range in PRICE_RANGES:
        builder.add(InlineKeyboardButton(
            text=price_range["label"],
            callback_data=f"price_range_{price_range['min']}_{price_range['max']}"
        ))
    
    builder.adjust(2)
    
    # Кнопка "Любая цена"
    builder.row(InlineKeyboardButton(
        text="💵 Любая цена",
        callback_data="price_range_any"
    ))
    
    # Кнопка возврата
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к виду спорта",
        callback_data="back_to_sport"
    ))
    
    await message.answer(
        "💵 Выберите диапазон стоимости урока:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchStates.SEARCH_PRICE_RANGE)

@router.callback_query(SearchStates.SEARCH_PRICE_RANGE, F.data.startswith("price_range_"))
async def process_price_range(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "price_range_any":
        await state.update_data(price_min=None, price_max=None)
    else:
        _, _, min_price, max_price = callback.data.split("_")
        await state.update_data(price_min=int(min_price), price_max=int(max_price))
    
    await perform_search(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_PRICE_RANGE, F.data == "back_to_sport")
async def back_to_sport_from_price(callback: types.CallbackQuery, state: FSMContext):
    await show_sport_types(callback.message, state)
    await callback.answer()

async def perform_search(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message = message.message
    
    data = await state.get_data()
    search_type = data.get('search_type')
    country = data.get('search_country')
    city = data.get('search_city')
    sport_type = data.get('sport_type')
    price_min = data.get('price_min')
    price_max = data.get('price_max')
    
    users = load_users()
    results = []
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
            
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
            
        if profile.get('country') == country and profile.get('city') == city:
            # Для тренеров проверяем вид спорта
            if search_type == "coaches" and sport_type:
                profile_sport = profile.get('sport')
                if not profile_sport or profile_sport != sport_type:
                    continue
            
            # Для тренеров проверяем ценовой диапазон
            if search_type == "coaches" and price_min is not None and price_max is not None:
                lesson_price = profile.get('price')
                if lesson_price and isinstance(lesson_price, (int, float)):
                    if price_min <= lesson_price <= price_max:
                        results.append((user_id, profile))
                else:
                    # Если цена не указана, не включаем в результаты
                    continue
            else:
                results.append((user_id, profile))
    
    if not results:
        search_type_text = "тренеров" if search_type == "coaches" else "игроков"
        sport_text = f" по виду спорта {sport_type}" if sport_type else ""
        price_text = ""
        if search_type == "coaches" and price_min is not None and price_max is not None:
            price_text = f" в ценовом диапазоне {price_min}-{price_max} руб."
        
        await message.answer(
            f"😕 В городе {city} ({country}){sport_text}{price_text} не найдено {search_type_text}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_search_options")
            ]])
        )
        await state.set_state(SearchStates.SEARCH_NO_RESULTS)
        return
    
    await state.update_data(search_results=results, current_page=0)
    await show_search_results_list(message, state, 0)

async def show_search_results_list(message: types.Message, state: FSMContext, page: int = 0):
    data = await state.get_data()
    results = data.get('search_results', [])
    search_type = data.get('search_type')
    country = data.get('search_country')
    city = data.get('search_city')
    sport_type = data.get('sport_type')
    price_min = data.get('price_min')
    price_max = data.get('price_max')
    
    if not results:
        await message.answer("Результаты поиска не найдены.")
        await state.clear()
        return
    
    # Пагинация - показываем по 10 результатов на странице
    results_per_page = 10
    total_pages = (len(results) + results_per_page - 1) // results_per_page
    start_idx = page * results_per_page
    end_idx = min(start_idx + results_per_page, len(results))
    current_results = results[start_idx:end_idx]
    
    builder = InlineKeyboardBuilder()
    
    for user_id, profile in current_results:
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        if not name:
            name = f"Пользователь #{user_id}"
            
        if search_type == "coaches":
            lesson_price = profile.get('price')
            sport = profile.get('sport', '')
            if lesson_price:
                name = f"{name} - {lesson_price} руб."
            if sport:
                name = f"{name} ({sport})"
            level = profile.get('coach_level', '')
        else:
            level = profile.get('player_level', '')
            
        if level:
            name = f"{name} ({level})"
            
        builder.add(InlineKeyboardButton(
            text=name,
            callback_data=f"show_profile_{user_id}"
        ))
    
    builder.adjust(1)
    
    # Кнопки пагинации
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton(
            text="⬅️ Предыдущая",
            callback_data=f"page_{page-1}"
        ))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton(
            text="Следующая ➡️",
            callback_data=f"page_{page+1}"
        ))
    
    if pagination_buttons:
        builder.row(*pagination_buttons)
    
    # Кнопка возврата
    back_callback = "back_to_price_range" if search_type == "coaches" else "back_to_cities"
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=back_callback
    ))
    
    search_type_text = "тренеры" if search_type == "coaches" else "игроки"
    sport_text = f", вид спорта: {sport_type}" if sport_type else ""
    price_text = ""
    if search_type == "coaches" and price_min is not None and price_max is not None:
        price_text = f", цена: {price_min}-{price_max} руб."
    
    await message.answer(
        f"🔍 Найдено {len(results)} {search_type_text} в городе {city} ({country}){sport_text}{price_text}:\n\n"
        f"Страница {page + 1} из {total_pages}\n\n"
        "Выберите профиль для просмотра:",
        reply_markup=builder.as_markup()
    )
    
    await state.update_data(current_page=page)
    await state.set_state(SearchStates.SEARCH_RESULTS)

@router.callback_query(SearchStates.SEARCH_RESULTS, F.data.startswith("page_"))
async def handle_page_change(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[1])
    await show_search_results_list(callback.message, state, page)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_RESULTS, F.data.startswith("show_profile_"))
async def handle_show_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    
    # Получаем профиль пользователя
    profile = get_user_profile_from_storage(user_id)
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Показываем профиль
    await show_profile(callback.message, profile)

    await state.clear()
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_NO_RESULTS, F.data == "back_to_search_options")
@router.callback_query(SearchStates.SEARCH_RESULTS, F.data == "back_to_results")
async def handle_back_to_results(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_page = data.get('current_page', 0)
    await show_search_results_list(callback.message, state, current_page)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_NO_RESULTS, F.data == "back_to_cities")
@router.callback_query(SearchStates.SEARCH_RESULTS, F.data == "back_to_cities")
async def handle_back_to_cities(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country = data.get('search_country')
    search_type = data.get('search_type')
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = []
        for city in main_russian_cities:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"🏙 {city} ({count})", 
                callback_data=f"search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in main_russian_cities)
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="search_other_city"
        )])
    else:
        cities = cities_data.get(country, [])
        buttons = []
        for city in cities[:5]:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"🏙 {city} ({count})", 
                callback_data=f"search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in cities[:5])
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="search_other_city"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к странам", 
        callback_data="back_to_countries"
    )])
    
    search_type_text = "тренеров" if search_type == "coaches" else "игроков"
    
    await callback.message.edit_text(
        f"🏙 Выберите город для поиска {search_type_text} в {country}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_CITY)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_RESULTS, F.data == "back_to_price_range")
async def handle_back_to_price_range(callback: types.CallbackQuery, state: FSMContext):
    await show_price_ranges(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_RESULTS, F.data == "back_to_sport")
async def handle_back_to_sport(callback: types.CallbackQuery, state: FSMContext):
    await show_sport_types(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "profile")
async def handle_my_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_user_registered(user_id):
        await callback.answer("❌ Вы еще не зарегистрированы. Введите /start для регистрации.")
        return
    
    profile = get_user_profile_from_storage(user_id) or {}
    await show_profile(callback.message, profile)
    await callback.answer()
