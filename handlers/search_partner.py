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
from config.profile import GENDER_TYPES, PLAYER_LEVELS
from models.states import SearchPartnerStates
from utils.bot import show_profile
from utils.json_data import get_user_profile_from_storage, is_user_registered, load_json, load_users
from utils.ssesion import save_session
from utils.utils import count_users_by_location, count_users_by_filters

router = Router()

cities_data = load_json("cities.json")
sport_types = load_json("sports.json")
countries = list(cities_data.keys())

@router.message(F.text == "🎾 Поиск партнера")
async def handle_search_partner(message: types.Message, state: FSMContext):
    await state.set_state(SearchPartnerStates.SEARCH_TYPE)
    await state.update_data(search_type="partner")
    
    # Сохраняем ID первого сообщения для последующего редактирования
    await state.update_data(first_message_id=message.message_id + 1)
    
    buttons = []
    for country in countries[:5]:
        count = count_users_by_location("partner", country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"partner_search_country_{country}"
        )])
    
    count_other = count_users_by_location("partner") - sum(count_users_by_location("partner", c) for c in countries[:5])
    buttons.append([InlineKeyboardButton(
        text=f"🌎 Другие страны ({count_other})", 
        callback_data="partner_search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад", 
        callback_data="partner_back_to_main"
    )])

    # Отправляем первое сообщение
    sent_message = await message.answer(
        "🌍 Выберите страну для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(SearchPartnerStates.SEARCH_COUNTRY)

@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY, F.data.startswith("partner_search_country_"))
async def process_search_country_partner(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(search_country=country)
    
    data = await state.get_data()
    search_type = data.get('search_type')
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = []
        for city in main_russian_cities:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in main_russian_cities)
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="partner_search_other_city"
        )])
    else:
        cities = cities_data.get(country, [])
        buttons = []
        for city in cities[:5]:
            count = count_users_by_location(search_type, country, city)
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        count_other = count_users_by_location(search_type, country) - sum(count_users_by_location(search_type, country, c) for c in cities[:5])
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="partner_search_other_city"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к странам", 
        callback_data="partner_back_to_countries"
    )])
    
    # Редактируем предыдущее сообщение
    await callback.message.edit_text(
        f"🏙 Выберите город для поиска партнера в {country}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    
    await state.set_state(SearchPartnerStates.SEARCH_CITY)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY, F.data == "partner_search_other_country")
async def process_search_other_country_partner(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌍 Введите название страны для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="partner_back_to_countries")
        ]])
    )
    await state.set_state(SearchPartnerStates.SEARCH_COUNTRY_INPUT)
    await callback.answer()

@router.message(SearchPartnerStates.SEARCH_COUNTRY_INPUT, F.text)
async def process_search_country_input_partner(message: Message, state: FSMContext):
    await state.update_data(search_country=message.text.strip())
    
    # Удаляем предыдущее сообщение и отправляем новое
    data = await state.get_data()
    last_message_id = data.get('last_message_id')
    if last_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
        except:
            pass
    
    sent_message = await message.answer(
        "🏙 Введите название города для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="partner_back_to_countries")
        ]])
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(SearchPartnerStates.SEARCH_CITY_INPUT)
    save_session(message.from_user.id, await state.get_data())

@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY, F.data == "partner_back_to_main")
async def partner_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено")
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_CITY, F.data.startswith("partner_search_city_"))
async def process_search_city_partner(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(search_city=city)
    
    await show_sport_types_partner(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_CITY, F.data == "partner_search_other_city")
async def process_search_other_city_partner(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🏙 Введите название города для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="partner_back_to_countries")
        ]])
    )
    await state.set_state(SearchPartnerStates.SEARCH_CITY_INPUT)
    await callback.answer()

@router.message(SearchPartnerStates.SEARCH_CITY_INPUT, F.text)
async def process_search_city_input_partner(message: Message, state: FSMContext):
    await state.update_data(search_city=message.text.strip())
    
    # Удаляем предыдущее сообщение
    data = await state.get_data()
    last_message_id = data.get('last_message_id')
    if last_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
        except:
            pass
    
    await show_sport_types_partner(message, state, True)
    save_session(message.from_user.id, await state.get_data())

@router.callback_query(SearchPartnerStates.SEARCH_CITY_INPUT, F.data == "partner_back_to_countries")
@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY_INPUT, F.data == "partner_back_to_countries")
@router.callback_query(SearchPartnerStates.SEARCH_CITY, F.data == "partner_back_to_countries")
async def partner_back_to_countries(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    
    buttons = []
    for country in countries[:5]:
        count = count_users_by_location(search_type, country)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"partner_search_country_{country}"
        )])
    
    count_other = count_users_by_location(search_type) - sum(count_users_by_location(search_type, c) for c in countries[:5])
    buttons.append([InlineKeyboardButton(
        text=f"🌎 Другие страны ({count_other})", 
        callback_data="partner_search_other_country"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад", 
        callback_data="partner_back_to_main"
    )])

    await callback.message.edit_text(
        "🌍 Выберите страну для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchPartnerStates.SEARCH_COUNTRY)
    await callback.answer()

async def show_sport_types_partner(message: Union[types.Message, types.CallbackQuery], state: FSMContext, new_mess = False):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    for sport in sport_types:
        builder.add(InlineKeyboardButton(
            text=sport,
            callback_data=f"partner_sport_{sport}"
        ))
    
    builder.adjust(2)
    
    builder.row(InlineKeyboardButton(
        text="🏆 Любой вид спорта",
        callback_data="partner_sport_any"
    ))
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к городам",
        callback_data="partner_back_to_cities"
    ))
    
    if new_mess:
        await message_obj.answer(
            "🏆 Выберите вид спорта:",
            reply_markup=builder.as_markup()
        )
    else:
        await message_obj.edit_text(
            "🏆 Выберите вид спорта:",
            reply_markup=builder.as_markup()
        )
    await state.set_state(SearchPartnerStates.SEARCH_SPORT)

@router.callback_query(SearchPartnerStates.SEARCH_SPORT, F.data.startswith("partner_sport_"))
async def process_sport_selection_partner(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_sport_any":
        await state.update_data(sport_type=None)
    else:
        sport_type = callback.data.split("_", 2)[2]
        await state.update_data(sport_type=sport_type)
    
    await show_gender_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_SPORT, F.data == "partner_back_to_cities")
async def partner_back_to_cities_from_sport(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country = data.get('search_country')
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = []
        for city in main_russian_cities:
            count = count_users_by_location("partner", country, city)
            buttons.append([InlineKeyboardButton(
                text=f"🏙 {city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        count_other = count_users_by_location("partner", country) - sum(count_users_by_location("partner", country, c) for c in main_russian_cities)
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="partner_search_other_city"
        )])
    else:
        cities = cities_data.get(country, [])
        buttons = []
        for city in cities[:5]:
            count = count_users_by_location("partner", country, city)
            buttons.append([InlineKeyboardButton(
                text=f"🏙 {city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        count_other = count_users_by_location("partner", country) - sum(count_users_by_location("partner", country, c) for c in cities[:5])
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({count_other})", 
            callback_data="partner_search_other_city"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к странам", 
        callback_data="partner_back_to_countries"
    )])
    
    await callback.message.edit_text(
        f"🏙 Выберите город для поиска партнера в {country}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchPartnerStates.SEARCH_CITY)
    await callback.answer()

async def show_gender_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    for gender in GENDER_TYPES:
        builder.add(InlineKeyboardButton(
            text=gender,
            callback_data=f"partner_gender_{gender}"
        ))
    
    builder.adjust(2)
    
    builder.row(InlineKeyboardButton(
        text="👥 Любой пол",
        callback_data="partner_gender_any"
    ))
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к виду спорта",
        callback_data="partner_back_to_sport"
    ))
    
    await message_obj.edit_text(
        "👥 Выберите пол партнера:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_GENDER)

@router.callback_query(SearchPartnerStates.SEARCH_GENDER, F.data.startswith("partner_gender_"))
async def process_gender_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_gender_any":
        await state.update_data(gender=None)
    else:
        gender = callback.data.split("_", 2)[2]
        await state.update_data(gender=gender)
    
    await show_level_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_GENDER, F.data == "partner_back_to_sport")
async def partner_back_to_sport_from_gender(callback: types.CallbackQuery, state: FSMContext):
    await show_sport_types_partner(callback.message, state)
    await callback.answer()

async def show_level_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    for level in PLAYER_LEVELS:
        builder.add(InlineKeyboardButton(
            text=level,
            callback_data=f"partner_level_{level}"
        ))
    
    builder.adjust(2)
    
    builder.row(InlineKeyboardButton(
        text="🎯 Любой уровень",
        callback_data="partner_level_any"
    ))
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к полу",
        callback_data="partner_back_to_gender"
    ))
    
    await message_obj.edit_text(
        "🎯 Выберите уровень игры партнера:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_LEVEL)

@router.callback_query(SearchPartnerStates.SEARCH_LEVEL, F.data.startswith("partner_level_"))
async def process_level_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_level_any":
        await state.update_data(level=None)
    else:
        level = callback.data.split("_", 2)[2]
        await state.update_data(level=level)
    
    await perform_partner_search(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_LEVEL, F.data == "partner_back_to_gender")
async def partner_back_to_gender_from_level(callback: types.CallbackQuery, state: FSMContext):
    await show_gender_selection(callback.message, state)
    await callback.answer()

async def perform_partner_search(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    data = await state.get_data()
    country = data.get('search_country')
    city = data.get('search_city')
    sport_type = data.get('sport_type')
    gender = data.get('gender')
    level = data.get('level')
    
    users = load_users()
    current_user_id = str(message_obj.chat.id)
    results = []
    
    for user_id, profile in users.items():
        if user_id == current_user_id:
            continue
            
        if not profile.get('show_in_search', True):
            continue
            
        if profile.get('role') != "Игрок":
            continue
        
        if profile.get('country') != country or profile.get('city') != city:
            continue
        
        if sport_type and profile.get('sport') != sport_type:
            continue
            
        if gender and profile.get('gender') != gender:
            continue
            
        if level and profile.get('player_level') != level:
            continue
            
        results.append((user_id, profile))
    
    if not results:
        sport_text = f" по виду спорта {sport_type}" if sport_type else ""
        gender_text = f", пол: {gender}" if gender else ""
        level_text = f", уровень: {level}" if level else ""
        
        await message_obj.edit_text(
            f"😕 В городе {city} ({country}){sport_text}{gender_text}{level_text} не найдено подходящих партнеров.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="partner_back_to_level")
            ]])
        )
        await state.set_state(SearchPartnerStates.SEARCH_NO_RESULTS)
        return
    
    await state.update_data(search_results=results, current_page=0)
    await show_partner_results_list(message_obj, state, 0)

async def show_partner_results_list(message: types.Message, state: FSMContext, page: int = 0):
    data = await state.get_data()
    results = data.get('search_results', [])
    country = data.get('search_country')
    city = data.get('search_city')
    sport_type = data.get('sport_type')
    gender = data.get('gender')
    level = data.get('level')
    
    if not results:
        await message.edit_text("Результаты поиска не найдены.")
        await state.clear()
        return
    
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
        else:
            name = f"{name} ({profile.get('rating_points', '')})"
            
        builder.add(InlineKeyboardButton(
            text=name,
            callback_data=f"partner_show_profile_{user_id}"
        ))
    
    builder.adjust(1)
    
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton(
            text="⬅️ Предыдущая",
            callback_data=f"partner_page_{page-1}"
        ))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton(
            text="Следующая ➡️",
            callback_data=f"partner_page_{page+1}"
        ))
    
    if pagination_buttons:
        builder.row(*pagination_buttons)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="partner_back_to_level"
    ))
    
    sport_text = f", вид спорта: {sport_type}" if sport_type else ""
    gender_text = f", пол: {gender}" if gender else ""
    level_text = f", уровень: {level}" if level else ""
    
    await message.edit_text(
        f"🔍 Найдено {len(results)} партнеров в городе {city} ({country}){sport_text}{gender_text}{level_text}:\n\n"
        f"Страница {page + 1} из {total_pages}\n\n"
        "Выберите профиль для просмотра:",
        reply_markup=builder.as_markup()
    )
    
    await state.update_data(current_page=page)
    await state.set_state(SearchPartnerStates.SEARCH_RESULTS)

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data.startswith("partner_page_"))
async def handle_page_change_partner(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_", 2)[2])
    await show_partner_results_list(callback.message, state, page)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data.startswith("partner_show_profile_"))
async def handle_show_profile_partner(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_", 3)[3])
    
    profile = get_user_profile_from_storage(user_id)
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Для показа профиля создаем новое сообщение, так как это отдельный экран
    await show_profile(callback.message, profile)
    
    # Добавляем кнопку возврата к результатам
    back_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад к результатам", callback_data="partner_back_to_results")
    ]])
    
    # Редактируем сообщение с профилем, добавляя кнопку возврата
    await callback.message.edit_reply_markup(reply_markup=back_button)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_NO_RESULTS, F.data == "partner_back_to_search_options")
@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data == "partner_back_to_results")
async def handle_back_to_results_partner(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_page = data.get('current_page', 0)
    await show_partner_results_list(callback.message, state, current_page)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data == "partner_back_to_level")
@router.callback_query(SearchPartnerStates.SEARCH_NO_RESULTS, F.data == "partner_back_to_level")
async def partner_back_to_level_from_results(callback: types.CallbackQuery, state: FSMContext):
    await show_level_selection(callback.message, state)
    await callback.answer()
