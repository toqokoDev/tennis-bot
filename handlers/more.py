from typing import Union
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import SUBSCRIPTION_PRICE, BOT_USERNAME
from config.profile import get_price_ranges, cities_data, create_sport_keyboard, sport_type, countries
from models.states import SearchStates
from services.storage import storage
from utils.admin import is_admin
from utils.bot import show_profile
from utils.utils import calculate_age, count_users_by_location, get_top_countries, get_top_cities, remove_country_flag
from utils.translations import get_user_language_async, t

router = Router()

@router.message(F.text.in_([t("menu.more", "ru"), t("menu.more", "en")]))
async def handle_more(message: types.Message):
    language = await get_user_language_async(str(message.chat.id))
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.tours", language), callback_data="tours_main_menu")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.all_players", language), callback_data="all_players"),
        types.InlineKeyboardButton(text=t("more.buttons.find_coach", language), callback_data="find_coach")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.beauty_contest", language), callback_data="beauty_contest")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.about", language), callback_data="about"),
        types.InlineKeyboardButton(text=t("more.buttons.contacts", language), callback_data="contacts")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.multi_day_tournaments", language), url="https://tennis-play.com/tournaments/"),
        types.InlineKeyboardButton(text=t("more.buttons.weekend_tournaments", language), url="https://tennis-play.com/tournaments/weekend/")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.my_profile", language), callback_data="profile"),
        types.InlineKeyboardButton(text=t("more.buttons.go_to_site", language), url="https://tennis-play.com/")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.language_button", language), callback_data="select_language")
    )
    
    await message.answer(t("more.additional_options", language), reply_markup=builder.as_markup())

# Обработчики инлайн кнопок
@router.callback_query(F.data == "about")
async def handle_about(callback: types.CallbackQuery):
    language = await get_user_language_async(str(callback.message.chat.id))
    about_text = t("more.about", language)
    await callback.message.edit_text(about_text)
    await callback.answer()

@router.callback_query(F.data == "contacts")
async def handle_contacts(callback: types.CallbackQuery):
    language = await get_user_language_async(str(callback.message.chat.id))
    contacts_text = t("more.contacts", language)
    await callback.message.edit_text(contacts_text)
    await callback.answer()

@router.callback_query(F.data == "all_players")
async def handle_all_players(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.SEARCH_TYPE)
    await state.update_data(search_type="players")
    
    user_id = callback.message.chat.id
    users = await storage.load_users()

    if not await is_admin(user_id):
        if not users[str(user_id)].get('subscription', {}).get('active', False):
            referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{callback.from_user.id}"
            language = await get_user_language_async(str(user_id))
            text = t("more.all_players_locked", language, 
                    price=SUBSCRIPTION_PRICE,
                    referral_link=referral_link)
            
            await callback.message.answer(
                text,
                parse_mode="HTML"
            )

            await state.clear()
            return
    
    # Показываем выбор вида спорта для игроков
    await show_sport_types_for_players(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "find_coach")
async def handle_find_coach(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.SEARCH_TYPE)
    await state.update_data(search_type="coaches")
    
    # Для тренеров сначала показываем выбор вида спорта
    await show_sport_types(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data.startswith("search_country_"))
async def process_search_country(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(search_country=country)
    
    data = await state.get_data()
    search_type = data.get('search_type')
    
    cities = cities_data.get(country, [])
    buttons = []
    for city in cities:
        count = await count_users_by_location(search_type, country, city)
        buttons.append([InlineKeyboardButton(
            text=f"{city} ({count})", 
            callback_data=f"search_city_{city}"
        )])

    # Получаем количество пользователей в других городах
    other_cities = await get_top_cities(search_type=search_type, country=country, exclude_cities=cities)
    other_cities_count = sum(count for city, count in other_cities)
    
    if other_cities_count > 0:
        language = await get_user_language_async(str(callback.message.chat.id))
        buttons.append([InlineKeyboardButton(
            text=t("more.search.other_cities", language, count=other_cities_count), 
            callback_data="search_other_city"
        )])
    
    language = await get_user_language_async(str(callback.message.chat.id))
    buttons.append([InlineKeyboardButton(
        text=t("more.search.back_to_countries", language),
        callback_data="back_to_countries"
    )])
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if search_type == "coaches":
        text = t("more.search.select_city_for_coaches", language, country=remove_country_flag(country))
    else:
        text = t("more.search.select_city_for_players", language, country=remove_country_flag(country))
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    
    await state.set_state(SearchStates.SEARCH_CITY)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data == "search_other_country")
async def process_search_other_country(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    language = await get_user_language_async(str(callback.message.chat.id))
    
    # Получаем топ-7 стран, исключая основные
    top_countries = await get_top_countries(search_type=search_type, exclude_countries=countries[:5])
    
    buttons = []
    for country, count in top_countries:
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text=t("more.search.back", language), 
        callback_data="back_to_countries"
    )])
    
    if search_type == "coaches":
        text = t("more.search.top_countries_with_coaches", language)
    else:
        text = t("more.search.top_countries_with_players", language)
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    language = await get_user_language_async(str(callback.message.chat.id))
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.tours", language), callback_data="tours_main_menu")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.all_players", language), callback_data="all_players"),
        types.InlineKeyboardButton(text=t("more.buttons.find_coach", language), callback_data="find_coach")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.beauty_contest", language), callback_data="beauty_contest")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.about", language), callback_data="about"),
        types.InlineKeyboardButton(text=t("more.buttons.contacts", language), callback_data="contacts")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.multi_day_tournaments", language), url="https://tennis-play.com/tournaments/"),
        types.InlineKeyboardButton(text=t("more.buttons.weekend_tournaments", language), url="https://tennis-play.com/tournaments/weekend/")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.my_profile", language), callback_data="profile"),
        types.InlineKeyboardButton(text=t("more.buttons.go_to_site", language), url="https://tennis-play.com/")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.language_button", language), callback_data="select_language")
    )
    
    await callback.message.edit_text(t("more.additional_options", language), reply_markup=builder.as_markup())
    await callback.answer()

@router.message(SearchStates.SEARCH_COUNTRY_INPUT, F.text)
async def process_search_country_input(message: Message, state: FSMContext):
    await state.update_data(search_country=message.text.strip())
    
    data = await state.get_data()
    search_type = data.get('search_type')
    language = await get_user_language_async(str(message.chat.id))
    
    if search_type == "coaches":
        text = t("more.search.enter_city_for_coaches", language)
    else:
        text = t("more.search.enter_city_for_players", language)
    
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("more.search.back", language), callback_data="back_to_countries")
        ]])
    )
    await state.set_state(SearchStates.SEARCH_CITY_INPUT)
    await storage.save_session(message.from_user.id, await state.get_data())

@router.callback_query(SearchStates.SEARCH_CITY, F.data.startswith("search_city_"))
async def process_search_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(search_city=city)
    await perform_search(callback.message, state)

    await callback.answer()

@router.callback_query(SearchStates.SEARCH_CITY, F.data == "search_other_city")
async def process_search_other_city(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    country = data.get('search_country')
    language = await get_user_language_async(str(callback.message.chat.id))
    
    # Определяем основные города для исключения
    exclude_cities = cities_data.get(country, [])
    
    # Получаем топ-7 городов в выбранной стране, исключая основные
    top_cities = await get_top_cities(search_type=search_type, country=country, exclude_cities=exclude_cities)
    
    buttons = []
    for city, count in top_cities:
        buttons.append([InlineKeyboardButton(
            text=f"{city} ({count})", 
            callback_data=f"search_city_{city}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text=t("more.search.back", language), 
        callback_data="back_to_cities"
    )])
    
    if search_type == "coaches":
        text = t("more.search.top_cities_with_coaches", language, country=remove_country_flag(country))
    else:
        text = t("more.search.top_cities_with_players", language, country=remove_country_flag(country))
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_RESULTS)
    await callback.answer()

@router.callback_query(F.data == "back_to_countries")
async def back_to_countries(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    
    buttons = []
    for country in countries[:5]:
        count = await count_users_by_location(search_type, country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    # Получаем количество пользователей в других странах
    other_countries = await get_top_countries(search_type=search_type, exclude_countries=countries[:5])
    other_countries_count = sum(count for country, count in other_countries)
    
    language = await get_user_language_async(str(callback.message.chat.id))
    if other_countries_count > 0:
        buttons.append([InlineKeyboardButton(
            text=t("search_partner.other_countries", language, count=other_countries_count), 
            callback_data="search_other_country"
        )])
    
    buttons.append([InlineKeyboardButton(
        text=t("more.search.back", language), 
        callback_data="back_to_main"
    )])
    if search_type == "coaches":
        text = t("more.search.select_country_for_coaches", language)
    else:
        text = t("more.search.select_country_for_players", language)
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

@router.message(SearchStates.SEARCH_CITY_INPUT, F.text)
async def process_search_city_input(message: Message, state: FSMContext):
    await state.update_data(search_city=message.text.strip())
    
    data = await state.get_data()
    search_type = data.get('search_type')
    
    # Для игроков сразу выполняем поиск, для тренеров переходим к выбору цены
    if search_type == "players":
        await perform_search(message, state)
    else:
        await show_price_ranges(message, state)
    await storage.save_session(message.from_user.id, await state.get_data())

@router.callback_query(SearchStates.SEARCH_CITY_INPUT, F.data == "back_to_countries")
async def back_to_countries_from_input(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    
    buttons = []
    for country in countries[:5]:
        count = await count_users_by_location(search_type, country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    counts = []
    for c in countries[:5]:
        counts.append(await count_users_by_location(search_type, c))

    language = await get_user_language_async(str(callback.message.chat.id))
    count_other = await count_users_by_location(search_type) - sum(counts)
    buttons.append([InlineKeyboardButton(
        text=t("search_partner.other_countries", language, count=count_other), 
        callback_data="search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text=t("more.search.back", language), 
        callback_data="back_to_main"
    )])

    language = await get_user_language_async(str(callback.message.chat.id))
    if search_type == "coaches":
        text = t("more.search.select_country_for_coaches", language)
    else:
        text = t("more.search.select_country_for_players", language)
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

async def show_sport_types_for_players(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор вида спорта для игроков"""
    if isinstance(message, types.CallbackQuery):
        message = message.message
    
    language = await get_user_language_async(str(message.chat.id))
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text=t("search_partner.all_sports", language),
        callback_data="players_sport_any"
    ))
    
    sport_keyboard = create_sport_keyboard(pref="players_sport_", language=language)
    for row in sport_keyboard.inline_keyboard:
        builder.row(*row)
    
    builder.row(InlineKeyboardButton(
        text=t("common.back", language),
        callback_data="back_to_main"
    ))

    try:
        await message.edit_text(
            t("more.search.players_select_sport", language),
            reply_markup=builder.as_markup()
        )
    except:
        try:
            await message.delete()
        except:
            await message.answer(
            t("more.search.players_select_sport", language),
            reply_markup=builder.as_markup()
        )
    await state.set_state(SearchStates.SEARCH_SPORT)

async def show_sport_types(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор вида спорта для тренеров"""
    if isinstance(message, types.CallbackQuery):
        message = message.message
    
    language = await get_user_language_async(str(message.chat.id))
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text=t("search_partner.all_sports", language),
        callback_data="sport_any"
    ))
    
    sport_keyboard = create_sport_keyboard(pref="sport_", language=language)
    for row in sport_keyboard.inline_keyboard:
        builder.row(*row)
    
    builder.row(InlineKeyboardButton(
        text=t("common.back", language),
        callback_data="back_to_main"
    ))

    try:
        await message.edit_text(
            t("more.search.coaches_select_sport", language),
            reply_markup=builder.as_markup()
        )
    except:
        try:
            await message.delete()
        except:
            await message.answer(
            t("more.search.coaches_select_sport", language),
            reply_markup=builder.as_markup()
        )
    await state.set_state(SearchStates.SEARCH_SPORT)

@router.callback_query(SearchStates.SEARCH_SPORT, F.data.startswith("players_sport_"))
async def process_players_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора вида спорта для игроков"""
    if callback.data == "players_sport_any":
        await state.update_data(sport_type=None)
    else:
        sport_type = callback.data.split("_", 2)[2]
        await state.update_data(sport_type=sport_type)
    
    # После выбора вида спорта переходим к выбору страны для игроков
    data = await state.get_data()
    buttons = []
    for country in countries[:5]:
        count = await count_users_by_location("players", country, sport_type=data.get('sport_type'))
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"search_country_{country}"
        )])
    
    # Получаем количество пользователей в других странах
    other_countries = await get_top_countries(search_type="players", exclude_countries=countries[:5], sport_type=data.get('sport_type'))
    other_countries_count = sum(count for country, count in other_countries)
    
    if other_countries_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🌎 Другие страны ({other_countries_count})", 
            callback_data="search_other_country"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к виду спорта", 
        callback_data="back_to_players_sport"
    )])

    await callback.message.edit_text(
        "🌍 Выберите страну для поиска игроков:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_COUNTRY)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_SPORT, F.data.startswith("sport_"))
async def process_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора вида спорта для тренеров"""
    if callback.data == "sport_any":
        await state.update_data(sport_type=None)
    else:
        sport_type = callback.data.split("_", 1)[1]
        await state.update_data(sport_type=sport_type)
    
    await show_price_ranges(callback.message, state)
    await callback.answer()

async def show_price_ranges(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message = message.message
    
    builder = InlineKeyboardBuilder()
    language = await get_user_language_async(str(message.chat.id))
    
    builder.row(InlineKeyboardButton(
        text=t("more.search.any_price", language),
        callback_data="price_range_any"
    ))

    for price_range in get_price_ranges(language):
        builder.add(InlineKeyboardButton(
            text=price_range["label"],
            callback_data=f"price_range_{price_range['min']}_{price_range['max']}"
        ))
    
    builder.adjust(1, 2)
    
    # Кнопка возврата
    builder.row(InlineKeyboardButton(
        text=t("common.back", language),
        callback_data="back_to_sport"
    ))
    try:
        await message.edit_text(
            t("more.search.select_price_range", language),
            reply_markup=builder.as_markup()
        )
    except:
        try:
            await message.delete()
        except:
            await message.answer(
                t("more.search.select_price_range", language),
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
    
    # После выбора цены переходим к выбору страны для тренеров
    data = await state.get_data()
    search_type = data.get('search_type')
    
    if search_type == "coaches":
        buttons = []
        for country in countries[:5]:
            count = await count_users_by_location(search_type, country)
            buttons.append([InlineKeyboardButton(
                text=f"{country} ({count})", 
                callback_data=f"search_country_{country}"
            )])
        
        counts = []
        for c in countries[:5]:
            counts.append(await count_users_by_location(search_type, c))

        count_other = await count_users_by_location(search_type) - sum(counts)
        buttons.append([InlineKeyboardButton(
            text=f"🌎 Другие страны ({count_other})", 
            callback_data="search_other_country"
        )])
        
        buttons.append([InlineKeyboardButton(
            text="⬅️ Назад к цене", 
            callback_data="back_to_price_range"
        )])

        await callback.message.edit_text(
            "🌍 Выберите страну для поиска тренеров:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(SearchStates.SEARCH_COUNTRY)
    else:
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
    
    users = await storage.load_users()
    results = []
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
            
        if search_type == "coaches" and profile.get('role') != "Тренер":
            continue
        elif search_type == "players" and profile.get('role') != "Игрок":
            continue
            
        if profile.get('country') == country and profile.get('city') == city:
            # Проверяем вид спорта для игроков и тренеров
            if sport_type:
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
    
    # Сортировка игроков по возрастанию уровня/рейтинга (самые низкие сначала)
    if search_type == "players" and results:
        def sort_key(item):
            _uid, prof = item
            # Настольный теннис сортируем по рейтингу (rating_points)
            if sport_type == "🏓Настольный теннис":
                rating_val = prof.get("rating_points")
                if isinstance(rating_val, (int, float)):
                    return (0, float(rating_val))
                return (1, float("inf"))
            # Остальные виды спорта с уровнем сортируем по player_level (например, 1.0..7.0)
            level_str = prof.get("player_level")
            try:
                return (0, float(str(level_str).replace(",", ".")))
            except Exception:
                rating_val = prof.get("rating_points")
                if isinstance(rating_val, (int, float)):
                    return (0, float(rating_val))
                return (1, float("inf"))

        results.sort(key=sort_key)

    language = await get_user_language_async(str(message.chat.id))
    if not results:
        sport_text = f", вид спорта: {sport_type}" if sport_type else ""
        price_text = ""
        if search_type == "coaches" and price_min is not None and price_max is not None:
            price_text = f", цена: {price_min}-{price_max} руб."
        
        if search_type == "coaches":
            text = t("more.search.no_coaches_found", language, city=city, country=country, sport=sport_text, price=price_text)
        else:
            text = t("more.search.no_players_found", language, city=city, country=country, sport=sport_text, price=price_text)
        
        try:
            await message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=t("more.search.back", language), callback_data="back_to_cities")
                ]])
            )
        except:
            try:
                await message.delete()
            except:
                language = await get_user_language_async(str(message.chat.id))
                if search_type == "coaches":
                    text = t("more.search.no_coaches_found", language, city=city, country=country, sport=sport_text, price=price_text)
                else:
                    text = t("more.search.no_players_found", language, city=city, country=country, sport=sport_text, price=price_text)
                await message.answer(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text=t("more.search.back", language), callback_data="back_to_cities")
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
    
    # Пагинация - показываем по 5 результатов на странице
    results_per_page = 5
    total_pages = (len(results) + results_per_page - 1) // results_per_page
    start_idx = page * results_per_page
    end_idx = min(start_idx + results_per_page, len(results))
    current_results = results[start_idx:end_idx]
    
    builder = InlineKeyboardBuilder()
    
    for user_id, profile in current_results:
        # Если есть фамилия - сокращаем имя, если нет - используем полное имя
        first_name = profile.get('first_name', '')
        last_name = profile.get('last_name', '')
        if last_name:
            name = f"{first_name[0]}. {last_name}".strip()
        else:
            name = first_name.strip()
        
        age = await calculate_age(profile.get('birth_date', '05.05.2000'))
        gender_profile = profile.get('gender', '')
        gender_icon = "👨" if gender_profile == 'Мужской' else "👩" if gender_profile == 'Женский' else '👤'
        
        if profile.get('player_level') and profile.get('rating_points'):
            display_name = f"{profile.get('player_level')} ({profile.get('rating_points')} lvl)"
        else:
            display_name = ""

        if search_type == "coaches":
            lesson_price = profile.get('price')

            name = f"{gender_icon} {name} {age} лет {lesson_price} руб."
        else:
            name = f"{gender_icon} {name} {age} лет {display_name}"
            
        builder.add(InlineKeyboardButton(
            text=name,
            callback_data=f"show_profile_{user_id}"
        ))
    
    builder.adjust(1)
    
    # Кнопки пагинации
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"page_{page-1}"
        ))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton(
            text=" ➡️",
            callback_data=f"page_{page+1}"
        ))
    
    if pagination_buttons:
        builder.row(*pagination_buttons)
    
    language = await get_user_language_async(str(message.chat.id))
    # Кнопка возврата
    back_callback = "back_to_cities"
    builder.row(InlineKeyboardButton(
        text=t("more.search.back", language),
        callback_data=back_callback
    ))
    sport_text = f", вид спорта: {sport_type}" if sport_type else ""
    price_text = ""
    if search_type == "coaches" and price_min is not None and price_max is not None:
        price_text = f", цена: {price_min}-{price_max} руб."
    
    if search_type == "coaches":
        found_text = t("more.search.found_coaches", language, count=len(results), city=city, country=country, sport=sport_text, price=price_text)
    else:
        found_text = t("more.search.found_players", language, count=len(results), city=city, country=country, sport=sport_text, price=price_text)
    
    try:
        await message.edit_text(
            found_text + f"\n{t('common.page', language, page=page + 1, total=total_pages)}\n\n{t('common.select_profile', language)}",
            reply_markup=builder.as_markup()
        )
    except:
        try:
            await message.delete()
        except:
            pass
        language = await get_user_language_async(str(message.chat.id))
        if search_type == "coaches":
            found_text = t("more.search.found_coaches", language, count=len(results), city=city, country=country, sport=sport_text, price=price_text)
        else:
            found_text = t("more.search.found_players", language, count=len(results), city=city, country=country, sport=sport_text, price=price_text)
        await message.answer(
            found_text + f"\n{t('common.page', language, page=page + 1, total=total_pages)}\n\n{t('common.select_profile', language)}",
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
    profile = await storage.get_user(user_id)
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Показываем профиль
    await show_profile(callback.message, profile)

    await state.clear()
    await callback.answer()

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
    
    cities = cities_data.get(country, [])
    buttons = []
    for city in cities:
        count = await count_users_by_location(search_type, country, city)
        buttons.append([InlineKeyboardButton(
            text=f"{city} ({count})", 
            callback_data=f"search_city_{city}"
        )])
    
    # Получаем количество пользователей в других городах
    other_cities = await get_top_cities(search_type=search_type, country=country, exclude_cities=cities)
    other_cities_count = sum(count for city, count in other_cities)
    
    if other_cities_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({other_cities_count})", 
            callback_data="search_other_city"
        )])
    
    language = await get_user_language_async(str(callback.message.chat.id))
    buttons.append([InlineKeyboardButton(
        text=t("more.search.back_to_countries", language), 
        callback_data="back_to_countries"
    )])
    
    if search_type == "coaches":
        text = t("more.search.select_city_for_coaches", language, country=remove_country_flag(country))
    else:
        text = t("more.search.select_city_for_players", language, country=remove_country_flag(country))
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchStates.SEARCH_CITY)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data == "back_to_price_range")
async def handle_back_to_price_range(callback: types.CallbackQuery, state: FSMContext):
    await show_price_ranges(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_COUNTRY, F.data == "back_to_players_sport")
async def handle_back_to_players_sport(callback: types.CallbackQuery, state: FSMContext):
    await show_sport_types_for_players(callback.message, state)
    await callback.answer()

@router.callback_query(SearchStates.SEARCH_RESULTS, F.data == "back_to_sport")
async def handle_back_to_sport(callback: types.CallbackQuery, state: FSMContext):
    await show_sport_types(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "profile")
async def handle_my_profile(callback: types.CallbackQuery):
    user_id = callback.message.chat.id
    if not await storage.is_user_registered(user_id):
        await callback.answer("❌ Вы еще не зарегистрированы. Введите /start для регистрации.")
        return
    
    profile = await storage.get_user(user_id)
    await show_profile(callback.message, profile)
    await callback.answer()

@router.callback_query(F.data == "tours_main_menu")
async def handle_tours_main_menu(callback: types.CallbackQuery, state: FSMContext):
    """Обработка кнопки Туры из меню Еще"""
    from handlers.tours import browse_tours_start_callback
    await browse_tours_start_callback(callback, state)

@router.callback_query(F.data == "select_language")
async def handle_select_language(callback: types.CallbackQuery):
    """Обработка выбора языка"""
    language = await get_user_language_async(str(callback.message.chat.id))
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_language_ru"),
        types.InlineKeyboardButton(text="🇬🇧 English", callback_data="set_language_en")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("common.back", language), callback_data="back_to_main")
    )
    
    await callback.message.edit_text(
        t("more.select_language", language),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("set_language_"))
async def handle_set_language(callback: types.CallbackQuery):
    """Обработка установки языка"""
    language_code = callback.data.split("_")[-1]  # "ru" или "en"
    user_id = callback.message.chat.id
    
    # Обновляем язык пользователя в storage
    await storage.update_user_field(user_id, "language", language_code)
    await storage.set_user_language(str(user_id), language_code)
    
    # Получаем новый язык для отображения сообщения
    new_language = language_code
    
    # Формируем сообщение об успешном изменении языка
    if language_code == "ru":
        success_message = t("more.language_changed", new_language)
    else:
        success_message = t("more.language_changed_en", new_language)
    
    # Возвращаемся в главное меню "Еще"
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.tours", new_language), callback_data="tours_main_menu")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.all_players", new_language), callback_data="all_players"),
        types.InlineKeyboardButton(text=t("more.buttons.find_coach", new_language), callback_data="find_coach")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.beauty_contest", new_language), callback_data="beauty_contest")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.about", new_language), callback_data="about"),
        types.InlineKeyboardButton(text=t("more.buttons.contacts", new_language), callback_data="contacts")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.multi_day_tournaments", new_language), url="https://tennis-play.com/tournaments/"),
        types.InlineKeyboardButton(text=t("more.buttons.weekend_tournaments", new_language), url="https://tennis-play.com/tournaments/weekend/")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.buttons.my_profile", new_language), callback_data="profile"),
        types.InlineKeyboardButton(text=t("more.buttons.go_to_site", new_language), url="https://tennis-play.com/")
    )
    builder.row(
        types.InlineKeyboardButton(text=t("more.language_button", new_language), callback_data="select_language")
    )
    
    await callback.message.edit_text(
        success_message + "\n\n" + t("more.additional_options", new_language),
        reply_markup=builder.as_markup()
    )
    await callback.answer()
