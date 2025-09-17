from typing import Union
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.profile import (
    GENDER_TYPES, player_levels, cities_data, countries, sport_type,
    get_sport_config
)
from handlers.dating_filters import show_age_range_selection, show_dating_goal_selection, show_distance_selection
from models.states import SearchPartnerStates
from utils.bot import show_profile
from utils.utils import calculate_age, count_users_by_location, get_users_by_location, get_top_countries, get_top_cities
from services.storage import storage

router = Router()

@router.message(F.text == "🎾 Поиск партнера")
async def handle_search_partner(message: types.Message, state: FSMContext):
    await state.set_state(SearchPartnerStates.SEARCH_TYPE)
    await state.update_data(search_type="partner")
    
    # Сохраняем ID первого сообщения для последующего редактирования
    await state.update_data(first_message_id=message.message_id + 1)
    
    # Показываем выбор вида спорта
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку "Любой вид спорта" первой
    builder.row(InlineKeyboardButton(
        text="🎾 Любой вид спорта",
        callback_data="partner_sport_any"
    ))
    
    # Добавляем остальные виды спорта
    for sport in sport_type:  # Пропускаем первый элемент, так как он уже добавлен
        builder.add(InlineKeyboardButton(
            text=sport,
            callback_data=f"partner_sport_{sport}"
        ))
    
    builder.adjust(1, 2)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="partner_back_to_main"
    ))

    # Отправляем первое сообщение
    sent_message = await message.answer(
        "🎾 Выберите вид спорта для поиска партнера:",
        reply_markup=builder.as_markup()
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(SearchPartnerStates.SEARCH_SPORT)

@router.callback_query(SearchPartnerStates.SEARCH_SPORT, F.data.startswith("partner_sport_"))
async def process_search_sport_partner(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_sport_any":
        await state.update_data(sport_type=None)
    else:
        sport_type_val = callback.data.split("_", 2)[2]
        await state.update_data(sport_type=sport_type_val)
    
    data = await state.get_data()
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    buttons = []
    for country in countries[:5]:
        count = await count_users_by_location(search_type, country, sport_type=sport_type_val)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"partner_search_country_{country}"
        )])
    
    # Получаем количество пользователей в других странах
    other_countries = await get_top_countries(search_type=search_type, sport_type=sport_type_val, exclude_countries=countries[:5])
    other_countries_count = sum(count for country, count in other_countries)
    
    if other_countries_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🌎 Другие страны ({other_countries_count})", 
            callback_data="partner_search_other_country"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к виду спорта", 
        callback_data="partner_back_to_sport"
    )])

    # Редактируем предыдущее сообщение
    await callback.message.edit_text(
        "🌍 Выберите страну для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    
    await state.set_state(SearchPartnerStates.SEARCH_COUNTRY)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_SPORT, F.data == "partner_back_to_main")
async def partner_back_to_main_from_sport(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено")
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY, F.data.startswith("partner_search_country_"))
async def process_search_country_partner(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(search_country=country)
    
    data = await state.get_data()
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    # Получаем реальные города с пользователями для выбранной страны
    cities_data_result = await get_users_by_location(
        search_type, 
        country=country, 
        sport_type=sport_type_val, 
        limit=20
    )
    
    buttons = []
    if cities_data_result:
        # Сортируем города по количеству пользователей (по убыванию)
        sorted_cities = sorted(cities_data_result.items(), key=lambda x: x[1], reverse=True)
        
        # Берем топ-5 городов
        for city, count in sorted_cities:
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        # Считаем общее количество для "Других городов"
        other_cities_count = sum(count for city, count in sorted_cities[5:])
        
        if other_cities_count > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🏙 Другие города ({other_cities_count})", 
                callback_data="partner_search_other_city"
            )])
    else:
        # Если нет городов с пользователями, показываем основные города
        if country == "🇷🇺 Россия":
            main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
            for city in main_russian_cities:
                count = await count_users_by_location(search_type, country, city, sport_type_val, )
                buttons.append([InlineKeyboardButton(
                    text=f"{city} ({count})", 
                    callback_data=f"partner_search_city_{city}"
                )])
        else:
            cities = cities_data.get(country, [])
            for city in cities:
                count = await count_users_by_location(search_type, country, city, sport_type_val, )
                buttons.append([InlineKeyboardButton(
                    text=f"{city} ({count})", 
                    callback_data=f"partner_search_city_{city}"
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

@router.callback_query(SearchPartnerStates.SEARCH_CITY, F.data.startswith("partner_search_city_"))
async def process_search_city_partner(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(search_city=city)
    
    # Проверяем, нужно ли показывать выбор округа
    data = await state.get_data()
    country = data.get('search_country')
    
    if country == "🇷🇺 Россия" and city == "Москва":
        # Только для Москвы показываем выбор округа
        await show_district_selection(callback.message, state)
    else:
        await show_gender_selection(callback.message, state)
    await callback.answer()

async def show_district_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    data = await state.get_data()
    city = data.get('search_city')
    
    # Список округов только для Москвы
    moscow_districts = ["ЦАО", "САО", "СВАО", "ВАО", "ЮВАО", "ЮАО", "ЮЗАО", "ЗАО", "СЗАО", "ТиНАО"]
    
    if city != "Москва":
        # Если это не Москва, переходим к выбору пола
        await show_gender_selection(message, state)
        return
    
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку "Любой округ"
    builder.row(InlineKeyboardButton(
        text="🏘️ Любой округ",
        callback_data="partner_district_any"
    ))
    
    # Добавляем округа Москвы
    for district in moscow_districts:
        builder.add(InlineKeyboardButton(
            text=district,
            callback_data=f"partner_district_{district}"
        ))
    
    builder.adjust(3)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к городам",
        callback_data="partner_back_to_cities"
    ))
    
    await message_obj.edit_text(
        f"🏘️ Выберите округ в городе {city}:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_DISTRICT)

@router.callback_query(SearchPartnerStates.SEARCH_DISTRICT, F.data.startswith("partner_district_"))
async def process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_district_any":
        await state.update_data(district=None)
    else:
        district = callback.data.split("_", 2)[2]
        await state.update_data(district=district)
    
    await show_gender_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_DISTRICT, F.data == "partner_back_to_cities")
async def partner_back_to_cities_from_district(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country = data.get('search_country')
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    # Получаем реальные города с пользователями для выбранной страны
    cities_data_result = await get_users_by_location(
        search_type, 
        country=country, 
        sport_type=sport_type_val, 
        limit=20
    )
    
    buttons = []
    if cities_data_result:
        # Сортируем города по количеству пользователей (по убыванию)
        sorted_cities = sorted(cities_data_result.items(), key=lambda x: x[1], reverse=True)
        
        # Берем топ-5 городов
        for city, count in sorted_cities:
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        # Считаем общее количество для "Других городов"
        other_cities_count = sum(count for city, count in sorted_cities[5:])
        
        if other_cities_count > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🏙 Другие города ({other_cities_count})", 
                callback_data="partner_search_other_city"
            )])
    else:
        # Если нет городов с пользователями, показываем основные города
        if country == "🇷🇺 Россия":
            main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
            for city in main_russian_cities:
                count = await count_users_by_location(search_type, country, city, sport_type_val)
                buttons.append([InlineKeyboardButton(
                    text=f"{city} ({count})", 
                    callback_data=f"partner_search_city_{city}"
                )])
        else:
            cities = cities_data.get(country, [])
            for city in cities:
                count = await count_users_by_location(search_type, country, city, sport_type_val)
                buttons.append([InlineKeyboardButton(
                    text=f"{city} ({count})", 
                    callback_data=f"partner_search_city_{city}"
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

async def show_gender_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext, new_mess = False):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="👥 Любой пол",
        callback_data="partner_gender_any"
    ))

    for gender in GENDER_TYPES:
        builder.add(InlineKeyboardButton(
            text=gender,
            callback_data=f"partner_gender_{gender}"
        ))
    
    builder.adjust(1, 2)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к городам",
        callback_data="partner_back_to_cities"
    ))
    
    if new_mess:
        sent_message = await message_obj.answer(
            "👥 Выберите пол партнера:",
        reply_markup=builder.as_markup()
    )
        await state.update_data(last_message_id=sent_message.message_id)
    else:
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
    
    # Проверяем, это знакомства или нет
    data = await state.get_data()
    sport_type_val = data.get('sport_type')
    
    if sport_type_val == "🍒Знакомства":
        await show_age_range_selection(callback.message, state)
    else:
        await show_level_selection(callback.message, state)
    await callback.answer()

async def show_level_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="🎯 Любой уровень",
        callback_data="partner_level_any"
    ))

    for level in player_levels:
        builder.add(InlineKeyboardButton(
            text=level,
            callback_data=f"partner_level_{level}"
        ))
    
    builder.adjust(1, 3)
    
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

async def perform_partner_search(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    data = await state.get_data()
    country = data.get('search_country')
    city = data.get('search_city')
    district = data.get('district')
    sport_type_val = data.get('sport_type')
    gender = data.get('gender')
    level = data.get('level')
    age_range = data.get('age_range')
    dating_goal = data.get('dating_goal')
    distance = data.get('distance')
    
    users = await storage.load_users()
    current_user_id = str(message_obj.chat.id)
    results = []
    
    for user_id, profile in users.items():
        if not profile.get('show_in_search', True):
            continue
        
        # Для знакомств не проверяем роль, для остальных видов спорта проверяем
        if sport_type_val != "🍒Знакомства" and profile.get('role') != "Игрок":
            continue
        
        if profile.get('country') != country or profile.get('city') != city:
            continue
        
        # Фильтрация по округу (если указан)
        if district and profile.get('district') != district:
            continue
        
        # Фильтрация по виду спорта
        if sport_type_val and profile.get('sport') != sport_type_val:
            continue
            
        if gender and profile.get('gender') != gender:
            continue
            
        if level and profile.get('player_level') != level:
            continue
        
        # Фильтрация для знакомств
        if sport_type_val == "🍒Знакомства":
            # Фильтр по возрасту
            if age_range and age_range != "any":
                user_age = await calculate_age(profile.get('birth_date', '01.01.2000'))
                if age_range == "18-25" and not (18 <= user_age <= 25):
                    continue
                elif age_range == "26-35" and not (26 <= user_age <= 35):
                    continue
                elif age_range == "36-45" and not (36 <= user_age <= 45):
                    continue
                elif age_range == "46-55" and not (46 <= user_age <= 55):
                    continue
                elif age_range == "56+" and user_age < 56:
                    continue
            
            # Фильтр по цели знакомств - исправляем маппинг
            if dating_goal and dating_goal != "any":
                profile_goal = profile.get('dating_goal')
                # Преобразуем сокращенные значения обратно в полные
                goal_mapping = {
                    "relationship": "Отношения",
                    "communication": "Общение", 
                    "friendship": "Дружба",
                    "never_know": "Никогда не знаешь, что будет"
                }
                target_goal = goal_mapping.get(dating_goal, dating_goal)
                if profile_goal != target_goal:
                    continue
            
        results.append((user_id, profile))
    
    if not results:
        sport_text = f" по виду спорта {sport_type_val}" if sport_type_val else ""
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

# Обработчики для фильтров знакомств
@router.callback_query(SearchPartnerStates.SEARCH_AGE_RANGE, F.data.startswith("partner_age_"))
async def process_age_range_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_age_any":
        await state.update_data(age_range=None)
    else:
        age_range = callback.data.split("_", 2)[2]
        await state.update_data(age_range=age_range)
    
    await show_dating_goal_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_AGE_RANGE, F.data == "partner_back_to_gender")
async def partner_back_to_gender_from_age(callback: types.CallbackQuery, state: FSMContext):
    await show_gender_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_DATING_GOAL, F.data.startswith("partner_dating_goal_"))
async def process_dating_goal_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_dating_goal_any":
        await state.update_data(dating_goal=None)
    else:
        dating_goal = callback.data.split("_", 3)[3]
        await state.update_data(dating_goal=dating_goal)
    
    await show_distance_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_DATING_GOAL, F.data == "partner_back_to_age")
async def partner_back_to_age_from_dating_goal(callback: types.CallbackQuery, state: FSMContext):
    await show_age_range_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_DISTANCE, F.data.startswith("partner_distance_"))
async def process_distance_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "partner_distance_any":
        await state.update_data(distance=None)
    else:
        distance = int(callback.data.split("_", 2)[2])
        await state.update_data(distance=distance)
    
    # Переходим к поиску
    await perform_partner_search(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_DISTANCE, F.data == "partner_back_to_dating_goal")
async def partner_back_to_dating_goal_from_distance(callback: types.CallbackQuery, state: FSMContext):
    await show_dating_goal_selection(callback.message, state)
    await callback.answer()

# Обработчики кнопок "Назад"
@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY, F.data == "partner_back_to_sport")
async def partner_back_to_sport_from_country(callback: types.CallbackQuery, state: FSMContext):
    # Показываем выбор вида спорта
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку "Любой вид спорта" первой
    builder.row(InlineKeyboardButton(
        text="🎾 Любой вид спорта",
        callback_data="partner_sport_any"
    ))
    
    # Добавляем остальные виды спорта
    for sport in sport_type:
        builder.add(InlineKeyboardButton(
            text=sport,
            callback_data=f"partner_sport_{sport}"
        ))
    
    builder.adjust(1, 2)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="partner_back_to_main"
    ))

    await callback.message.edit_text(
        "🎾 Выберите вид спорта для поиска партнера:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_SPORT)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_CITY, F.data == "partner_back_to_countries")
async def partner_back_to_countries_from_city(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    buttons = []
    for country in countries[:5]:
        count = await count_users_by_location(search_type, country, sport_type=sport_type_val)
        buttons.append([InlineKeyboardButton(
            text=f"{country} ({count})", 
            callback_data=f"partner_search_country_{country}"
        )])
    
    # Получаем количество пользователей в других странах
    other_countries = await get_top_countries(search_type=search_type, sport_type=sport_type_val, exclude_countries=countries[:5])
    other_countries_count = sum(count for country, count in other_countries)
    
    if other_countries_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🌎 Другие страны ({other_countries_count})", 
            callback_data="partner_search_other_country"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к виду спорта", 
        callback_data="partner_back_to_sport"
    )])
    
    await callback.message.edit_text(
        "🌍 Выберите страну для поиска партнера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(SearchPartnerStates.SEARCH_COUNTRY)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_GENDER, F.data == "partner_back_to_cities")
async def partner_back_to_cities_from_gender(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country = data.get('search_country')
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    # Получаем реальные города с пользователями для выбранной страны
    cities_data_result = await get_users_by_location(
        search_type, 
        country=country, 
        sport_type=sport_type_val, 
        limit=20
    )
    
    buttons = []
    if cities_data_result:
        # Сортируем города по количеству пользователей (по убыванию)
        sorted_cities = sorted(cities_data_result.items(), key=lambda x: x[1], reverse=True)
        
        # Берем топ-5 городов
        for city, count in sorted_cities:
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
        
        # Считаем общее количество для "Других городов"
        other_cities_count = sum(count for city, count in sorted_cities[5:])
        
        if other_cities_count > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🏙 Другие города ({other_cities_count})", 
                callback_data="partner_search_other_city"
            )])
    else:
        # Если нет городов с пользователями, показываем основные города
        if country == "🇷🇺 Россия":
            main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
            for city in main_russian_cities:
                count = await count_users_by_location(search_type, country, city, sport_type_val)
                buttons.append([InlineKeyboardButton(
                    text=f"{city} ({count})", 
                    callback_data=f"partner_search_city_{city}"
                )])
        else:
            cities = cities_data.get(country, [])
            for city in cities:
                count = await count_users_by_location(search_type, country, city, sport_type_val)
                buttons.append([InlineKeyboardButton(
                    text=f"{city} ({count})", 
                    callback_data=f"partner_search_city_{city}"
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

@router.callback_query(SearchPartnerStates.SEARCH_LEVEL, F.data == "partner_back_to_gender")
async def partner_back_to_gender_from_level(callback: types.CallbackQuery, state: FSMContext):
    await show_gender_selection(callback.message, state)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data == "partner_back_to_level")
@router.callback_query(SearchPartnerStates.SEARCH_NO_RESULTS, F.data == "partner_back_to_level")
async def partner_back_to_level_from_results(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sport_type_val = data.get('sport_type')
    
    if sport_type_val == "🍒Знакомства":
        await show_age_range_selection(callback.message, state)
    else:
        await show_level_selection(callback.message, state)
    await callback.answer()

# Обработчик для "Других стран"
@router.callback_query(SearchPartnerStates.SEARCH_COUNTRY, F.data == "partner_search_other_country")
async def process_search_other_country_partner(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    # Получаем топ-7 стран, исключая основные
    top_countries = await get_top_countries(search_type=search_type, sport_type=sport_type_val, exclude_countries=countries[:5])
    
    if not top_countries:
        await callback.answer("❌ Нет стран с пользователями")
        return
    
    builder = InlineKeyboardBuilder()
    
    for country, count in top_countries:
        builder.add(InlineKeyboardButton(
            text=f"{country} ({count})",
            callback_data=f"partner_search_country_{country}"
        ))
    
    builder.adjust(1)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="partner_back_to_countries"
    ))

    await callback.message.edit_text(
        "🌍 Топ стран с пользователями:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_OTHER_COUNTRIES)
    await callback.answer()

# Обработчик для "Других городов"
@router.callback_query(SearchPartnerStates.SEARCH_CITY, F.data == "partner_search_other_city")
async def process_search_other_city_partner(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    search_type = data.get('search_type')
    country = data.get('search_country')
    sport_type_val = data.get('sport_type')
    
    # Определяем основные города для исключения
    if country == "🇷🇺 Россия":
        exclude_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
    else:
        exclude_cities = cities_data.get(country, [])
    
    # Получаем топ-7 городов в выбранной стране, исключая основные
    top_cities = await get_top_cities(search_type=search_type, country=country, sport_type=sport_type_val, exclude_cities=exclude_cities)
    
    if not top_cities:
        await callback.answer("❌ Нет городов с пользователями")
        return
    
    builder = InlineKeyboardBuilder()
    
    for city, count in top_cities:
        builder.add(InlineKeyboardButton(
            text=f"{city} ({count})",
            callback_data=f"partner_search_city_{city}"
        ))
    
    builder.adjust(1)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="partner_back_to_cities"
    ))
    
    await callback.message.edit_text(
        f"🏙 Топ городов в {country}:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_OTHER_CITIES)
    await callback.answer()

# Обработчик для выбора города из "Других городов"
@router.callback_query(SearchPartnerStates.SEARCH_OTHER_CITIES, F.data.startswith("partner_search_city_"))
async def process_other_city_selection(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(search_city=city)
    await show_gender_selection(callback.message, state)
    await callback.answer()

# Обработчик для возврата к городам из "Других городов"
@router.callback_query(SearchPartnerStates.SEARCH_OTHER_CITIES, F.data == "partner_back_to_cities")
async def back_to_cities_from_other(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country = data.get('search_country')
    search_type = data.get('search_type')
    sport_type_val = data.get('sport_type')
    
    buttons = []
    
    # Показываем основные города
    if country == "🇷🇺 Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
        for city in main_russian_cities:
            count = await count_users_by_location(search_type, country, city, sport_type_val)
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
    else:
        cities = cities_data.get(country, [])
        for city in cities:
            count = await count_users_by_location(search_type, country, city, sport_type_val)
            buttons.append([InlineKeyboardButton(
                text=f"{city} ({count})", 
                callback_data=f"partner_search_city_{city}"
            )])
    
    # Добавляем кнопку "Другие города"
    if country == "🇷🇺 Россия":
        exclude_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
    else:
        exclude_cities = cities_data.get(country, [])
    
    other_cities = await get_top_cities(search_type=search_type, country=country, sport_type=sport_type_val, exclude_cities=exclude_cities)
    other_cities_count = sum(count for city, count in other_cities)
    
    if other_cities_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🏙 Другие города ({other_cities_count})", 
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

async def show_partner_results_list(message: types.Message, state: FSMContext, page: int = 0):
    data = await state.get_data()
    results = data.get('search_results', [])
    country = data.get('search_country')
    city = data.get('search_city')
    sport_type_val = data.get('sport_type')
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
        name = f"{profile.get('first_name', '')[0]}. {profile.get('last_name', '')}".strip()
        age = await calculate_age(profile.get('birth_date', '05.05.2000'))
        gender_profile = profile.get('gender', '')
        user_district = profile.get('district', '')
        player_level = profile.get('player_level', '')
        rating_points = profile.get('rating_points', '')
        
        gender_icon = "👨" if gender_profile == 'Мужской' else "👩" if gender_profile == 'Женский' else '👤'
        district_text = f"{user_district}" if user_district else ""
        
        # Формируем основную информацию
        display_name = f"{gender_icon} {name} {district_text} ({age} лет)"
        
        # Добавляем уровень и рейтинг только если они есть
        if player_level and rating_points:
            display_name += f" | {player_level} ({rating_points})"
        elif player_level:
            display_name += f" | {player_level}"
            
        builder.add(InlineKeyboardButton(
            text=display_name,
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
    
    sport_text = f", вид спорта: {sport_type_val}" if sport_type_val else ""
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

# Обработчики для отображения профилей
@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data.startswith("partner_show_profile_"))
async def handle_show_profile_partner(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_", 3)[3])
    
    profile = await storage.get_user(user_id)
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Показываем краткую информацию о профиле
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    age = await calculate_age(profile.get('birth_date', '01.01.2000'))
    gender = profile.get('gender', '')
    city = profile.get('city', '')
    country = profile.get('country', '')
    sport = profile.get('sport', '')
    level = profile.get('player_level', '')
    rating = profile.get('rating_points', '')
    
    # Формируем краткую информацию
    profile_text = f"👤 **{name}**\n"
    profile_text += f"🎂 Возраст: {age} лет\n"
    profile_text += f"👫 Пол: {gender}\n"
    profile_text += f"📍 Местоположение: {city}, {country}\n"
    profile_text += f"🎾 Вид спорта: {sport}\n"
    
    if level and level.strip():
        profile_text += f"🎯 Уровень: {level}"
        if rating and rating.strip():
            profile_text += f" ({rating} очков)"
        profile_text += "\n"
    
    # Добавляем дополнительную информацию для знакомств
    if sport == "🍒Знакомства":
        dating_goal = profile.get('dating_goal', '')
        if dating_goal:
            profile_text += f"💕 Цель знакомств: {dating_goal}\n"
        
        interests = profile.get('dating_interests', [])
        if interests:
            profile_text += f"🎨 Интересы: {', '.join(interests)}\n"
    
    # Добавляем информацию о встрече для бизнес-завтраков и по пиву
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        meeting_time = profile.get('meeting_time', '')
        if meeting_time:
            profile_text += f"⏰ Время встречи: {meeting_time}\n"
    
    profile_text += f"\n💬 {profile.get('about_me', 'Информация не указана')}"
    
    # Создаем кнопки
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="👁️ Полный профиль",
        callback_data=f"partner_full_profile_{user_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="💬 Написать сообщение",
        callback_data=f"partner_message_{user_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="⬅️ Назад к результатам",
        callback_data="partner_back_to_results"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data.startswith("partner_full_profile_"))
async def handle_full_profile_partner(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_", 3)[3])
    
    profile = await storage.get_user(user_id)
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Показываем полный профиль
    await show_profile(callback.message, profile)
    
    # Добавляем кнопку возврата
    back_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад к краткому профилю", callback_data=f"partner_show_profile_{user_id}")
    ]])
    
    await callback.message.edit_reply_markup(reply_markup=back_button)
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data.startswith("partner_message_"))
async def handle_message_partner(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_", 3)[3])
    
    profile = await storage.get_user(user_id)
    if not profile:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Здесь можно добавить логику отправки сообщения
    # Пока просто показываем информацию о том, как связаться
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    
    await callback.message.edit_text(
        f"💬 Для связи с {name} используйте Telegram: @{profile.get('username', 'пользователь не указал username')}\n\n"
        f"Или попросите администратора связать вас с этим пользователем.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад к профилю", callback_data=f"partner_show_profile_{user_id}")
        ]])
    )
    await callback.answer()

@router.callback_query(SearchPartnerStates.SEARCH_RESULTS, F.data == "partner_back_to_results")
async def handle_back_to_results_partner(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_page = data.get('current_page', 0)
    await show_partner_results_list(callback.message, state, current_page)
    await callback.answer()
