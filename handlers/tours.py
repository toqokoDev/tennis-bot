from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config.config import ITEMS_PER_PAGE
from config.profile import create_sport_keyboard, sport_type, countries, cities_data, get_sport_config, get_country_translation, get_city_translation, get_sport_translation
from models.states import BrowseToursStates, CreateTourStates
from services.channels import send_tour_to_channel
from utils.utils import create_user_profile_link, format_tour_date, remove_country_flag
from utils.validate import validate_future_date, validate_date, validate_date_range
from services.storage import storage
from utils.translations import get_user_language_async, t

router = Router()

@router.message(F.text.in_([t("menu.tours", "ru"), t("menu.tours", "en")]))
async def browse_tours_start(message: types.Message, state: FSMContext):
    """Начало просмотра туров - выбор спорта"""
    builder = InlineKeyboardBuilder()

    language = await get_user_language_async(str(message.chat.id))
    
    builder.row(InlineKeyboardButton(
        text=t("tours.offer_tour", language),
        callback_data="create_tour_from_menu"
    ))
    
    builder.row(InlineKeyboardButton(
        text=t("tours.any_sport", language),
        callback_data="toursport_any"
    ))
    
    sport_keyboard = create_sport_keyboard(pref="toursport_", language=language)
    for row in sport_keyboard.inline_keyboard:
        builder.row(*row)

    try:
        await message.edit_text(
            t("tours.select_sport", language),
            reply_markup=builder.as_markup()
        )
    except:
        await message.answer(
            t("tours.select_sport", language),
            reply_markup=builder.as_markup()
        )
    await state.set_state(BrowseToursStates.SELECT_SPORT)
    await state.update_data(page=0)

@router.callback_query(F.data == "tours_back_to_sport")
async def browse_tours_start_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало просмотра туров - выбор спорта"""
    builder = InlineKeyboardBuilder()

    language = await get_user_language_async(str(callback.message.chat.id))
    
    builder.row(InlineKeyboardButton(
        text=t("tours.offer_tour", language),
        callback_data="create_tour_from_menu"
    ))

    builder.row(InlineKeyboardButton(
        text=t("tours.any_sport_short", language),
        callback_data="toursport_any"
    ))
    
    sport_keyboard = create_sport_keyboard(pref="toursport_", language=language)
    for row in sport_keyboard.inline_keyboard:
        builder.row(*row)

    try:
        await callback.message.edit_text(
            t("tours.select_sport", language),
            reply_markup=builder.as_markup()
        )
    except:
        await callback.message.answer(
            t("tours.select_sport", language),
            reply_markup=builder.as_markup()
        )
    await state.set_state(BrowseToursStates.SELECT_SPORT)
    await state.update_data(page=0)
    await callback.answer()

@router.callback_query(BrowseToursStates.SELECT_SPORT, F.data.startswith("toursport_"))
async def select_tour_sport(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора спорта для туров"""
    sport = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(selected_sport=sport)
    
    language = await get_user_language_async(str(callback.message.chat.id))

    # Создаем клавиатуру с кнопками всех стран
    buttons = []
    buttons.append([InlineKeyboardButton(
        text=t("tours.offer_tour", language),
        callback_data="create_tour_from_menu"
    )])
    for country in countries:
        buttons.append([
            InlineKeyboardButton(
                text=get_country_translation(country, language),
                callback_data=f"tourcountry_{country}"
            )
        ])
    buttons.append([InlineKeyboardButton(text=t("registration.other_country", language), callback_data="tourcountry_other")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        t("tours.select_country", language),
        reply_markup=keyboard
    )
    await state.set_state(BrowseToursStates.SELECT_COUNTRY)
    await callback.answer()

@router.callback_query(BrowseToursStates.SELECT_COUNTRY, F.data.startswith("tourcountry_"))
async def select_tour_country(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора страны для туров"""
    country = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    sport = state_data.get('selected_sport')

    language = await get_user_language_async(str(callback.message.chat.id))
    
    await state.update_data(selected_country=country)
    
    if country == "other":
        await callback.message.edit_text(t("registration.enter_country", language), reply_markup=None)
        await state.set_state(BrowseToursStates.ENTER_COUNTRY)
        await callback.answer()
        return
    
    users = await storage.load_users()

    # Собираем статистику по городам в выбранной стране для выбранного спорта
    city_stats = {}
    for user_id, user_data in users.items():
        if (user_data.get('vacation_country') == country and 
            user_data.get('vacation_tennis', False) and
            (user_data.get('sport') == sport or sport=="any")):
            city = user_data.get('vacation_city', '')
            if city:
                city_stats[city] = city_stats.get(city, 0) + 1
    
    # Создаем клавиатуру с кнопками городов
    buttons = []
    buttons.append([InlineKeyboardButton(
        text=t("tours.offer_tour", language),
        callback_data="create_tour_from_menu"
    )])
    
    # Если есть туры в этой стране, показываем города с турами
    if city_stats:
        for city, count in city_stats.items():
            buttons.append([
                InlineKeyboardButton(
                    text=f"{get_city_translation(city, language)} ({count})",
                    callback_data=f"tourcity_{city}"
                )
            ])
    else:
        main_cities = cities_data.get(country, [])
        
        for city in main_cities[:5]:  # Показываем первые 5 городов
            buttons.append([
                InlineKeyboardButton(
                    text=f"{get_city_translation(city, language)} (0)",
                    callback_data=f"tourcity_{city}"
                )
            ])
    
    buttons.append([InlineKeyboardButton(text=t("registration.other_city", language), callback_data="tourcity_other")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        t("admin_edit.select_city", language, country=get_country_translation(country, language)),
        reply_markup=keyboard
    )
    
    await state.set_state(BrowseToursStates.SELECT_CITY)
    await callback.answer()

@router.message(BrowseToursStates.ENTER_COUNTRY, F.text)
async def process_tour_country_input(message: types.Message, state: FSMContext):
    """Обработка ввода названия страны для просмотра туров"""
    country = message.text.strip()
    await state.update_data(selected_country=country)
    
    # Переходим к выбору города
    await select_tour_country_from_input(message, state, country)

async def select_tour_country_from_input(message: types.Message, state: FSMContext, country: str):
    """Обработка выбора города после ввода страны"""
    state_data = await state.get_data()
    sport = state_data.get('selected_sport')
    
    language = await get_user_language_async(str(message.chat.id))
    users = await storage.load_users()

    # Собираем статистику по городам в выбранной стране для выбранного спорта
    city_stats = {}
    for user_id, user_data in users.items():
        if (user_data.get('vacation_country') == country and 
            user_data.get('vacation_tennis', False) and
            (user_data.get('sport') == sport or sport=="any")):
            city = user_data.get('vacation_city', '')
            if city:
                city_stats[city] = city_stats.get(city, 0) + 1
    
    # Создаем клавиатуру с кнопками городов
    buttons = []
    buttons.append([InlineKeyboardButton(
        text=t("tours.offer_tour", language),
        callback_data="create_tour_from_menu"
    )])
    
    # Если есть туры в этой стране, показываем города с турами
    if city_stats:
        for city, count in city_stats.items():
            buttons.append([
                InlineKeyboardButton(
                    text=f"{get_city_translation(city, language)} ({count})",
                    callback_data=f"tourcity_{city}"
                )
            ])
    else:
        # Если нет туров, показываем основные города страны
        main_cities = cities_data.get(country, [])
        for city in main_cities[:5]:  # Показываем первые 5 городов
            buttons.append([
                InlineKeyboardButton(
                    text=f"{get_city_translation(city, language)} (0)",
                    callback_data=f"tourcity_{city}"
                )
            ])
    
    buttons.append([InlineKeyboardButton(text=t("registration.other_city", language), callback_data="tourcity_other")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        t("admin_edit.select_city", language, country=get_country_translation(country, language)),
        reply_markup=keyboard
    )
    
    await state.set_state(BrowseToursStates.SELECT_CITY)

@router.callback_query(BrowseToursStates.SELECT_CITY, F.data.startswith("tourcity_"))
async def select_tour_city(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора города и отображение туров"""
    city = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    country = state_data.get('selected_country')
    sport = state_data.get('selected_sport')
    
    language = await get_user_language_async(str(callback.message.chat.id))

    await state.update_data(selected_city=city)
    
    if city == "other":
        await callback.message.edit_text(t("admin_edit.enter_city", language, country=country), reply_markup=None)
        await state.set_state(BrowseToursStates.ENTER_CITY)
        await callback.answer()
        return
    
    # Получаем все активные туры в выбранном городе и стране для выбранного спорта
    users = await storage.load_users()
    all_tours = []
    
    for user_id, user_data in users.items():
        if (user_data.get('vacation_country') == country and 
            user_data.get('vacation_city') == city and 
            user_data.get('vacation_tennis', False) and
            (user_data.get('sport') == sport or sport=="any")):
            
            tour = {
                'user_id': user_id,
                'user_data': user_data,
                'gender': user_data.get('gender'),
                'vacation_start': user_data.get('vacation_start'),
                'vacation_end': user_data.get('vacation_end'),
                'vacation_comment': user_data.get('vacation_comment'),
                'sport': user_data.get('sport')
            }
            all_tours.append(tour)
    
    if not all_tours:
        await callback.answer(t("tours.not_found_tour", language))
        return
    
    # Сохраняем все туры в state
    await state.update_data(all_tours=all_tours, current_page=0)
    
    # Показываем первую страницу туров
    await show_tours_page(callback.message, state)
    await callback.answer()

@router.message(BrowseToursStates.ENTER_CITY, F.text)
async def process_tour_city_input(message: types.Message, state: FSMContext):
    """Обработка ввода названия города для просмотра туров"""
    city = message.text.strip()
    await state.update_data(selected_city=city)
    
    # Получаем все активные туры в выбранном городе и стране для выбранного спорта
    state_data = await state.get_data()
    country = state_data.get('selected_country')
    sport = state_data.get('selected_sport')

    language = await get_user_language_async(str(message.chat.id))
    
    users = await storage.load_users()
    all_tours = []
    
    for user_id, user_data in users.items():
        if (user_data.get('vacation_country') == country and 
            user_data.get('vacation_city') == city and 
            user_data.get('vacation_tennis', False) and
            (user_data.get('sport') == sport or sport=="any")):
            
            tour = {
                'user_id': user_id,
                'user_data': user_data,
                'gender': user_data.get('gender'),
                'vacation_start': user_data.get('vacation_start'),
                'vacation_end': user_data.get('vacation_end'),
                'vacation_comment': user_data.get('vacation_comment'),
                'sport': user_data.get('sport')
            }
            all_tours.append(tour)
    
    if not all_tours:
        await message.answer(t("tours.not_found_tour", language))
        return
    
    # Сохраняем все туры в state
    await state.update_data(all_tours=all_tours, current_page=0)
    
    # Показываем первую страницу туров
    await show_tours_page(message, state)

async def show_tours_page(message: types.Message, state: FSMContext):
    """Показать страницу с турами"""
    state_data = await state.get_data()
    all_tours = state_data.get('all_tours', [])
    current_page = state_data.get('current_page', 0)
    sport = state_data.get('selected_sport')
    
    language = await get_user_language_async(str(message.chat.id))

    if not all_tours:
        await message.answer(t("tours.not_found_tour", language))
        return
    
    # Вычисляем индексы для текущей страницы
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_tours = all_tours[start_idx:end_idx]

    sport_text = t("tours.any_sport_text", language) if sport == "any" else get_sport_translation(sport, language)

    text = f"🔎 {t('tours.find_tours', language, sport_text=sport_text)} {get_city_translation(state_data.get('selected_city'), language)}, {get_country_translation(state_data.get('selected_country'), language)}\n\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждого тура на странице
    for i, tour in enumerate(page_tours, start=1):
        user_data = tour['user_data']
        
        # Смайлик гендера
        gender = user_data.get('gender', '')
        gender_icon = "👨" if gender == 'Мужской' else "👩" if gender == 'Женский' else '👤'
        
        # Имя сокращено до первой буквы + фамилия
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        user_name = f"{first_name[:1]}. {last_name}" if first_name and last_name else first_name or last_name or t("common.not_specified", language)
        
        level = user_data.get('player_level', '-')

        start_date = await format_tour_date(tour.get('vacation_start', '-'))
        end_date = await format_tour_date(tour.get('vacation_end', '-'))
        
        # Итоговая строка
        tour_info = f"{start_date}-{end_date} | {gender_icon} {user_name} ({level})"
        
        builder.row(InlineKeyboardButton(
            text=tour_info,
            callback_data=f"viewtour_{tour['user_id']}"
        ))
    
    builder.row(InlineKeyboardButton(
        text=t("tours.offer_tour", language),
        callback_data="create_tour_from_menu"
    ))
    
    # Кнопки навигации
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton(text=t("common.back", language), callback_data="tourpage_prev"))
    if end_idx < len(all_tours):
        nav_buttons.append(InlineKeyboardButton(text=t("common.next", language), callback_data="tourpage_next"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Отправляем сообщение
    if message.content_type == 'text':
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        try:
            await message.delete()
        except:
            pass
        await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("tourpage_"))
async def handle_tour_page_navigation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка навигации по страницам туров"""
    action = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    current_page = state_data.get('current_page', 0)
    all_tours = state_data.get('all_tours', [])
    
    if action == "prev" and current_page > 0:
        current_page -= 1
    elif action == "next" and (current_page + 1) * ITEMS_PER_PAGE < len(all_tours):
        current_page += 1
    
    await state.update_data(current_page=current_page)
    await show_tours_page(callback.message, state)
    await callback.answer()

@router.callback_query(F.data.startswith("viewtour_"))
async def view_tour_details(callback: types.CallbackQuery, state: FSMContext):
    """Просмотр деталей конкретного тура"""
    user_id = callback.data.split("_", maxsplit=1)[1]
    
    users = await storage.load_users()
    user_data = users.get(user_id)

    language = await get_user_language_async(str(user_id))
    
    if not user_data or not user_data.get('vacation_tennis', False):
        await callback.answer(t("tours.not_tour", language))
        return
    
    country = user_data.get("vacation_country", "—")
    city = user_data.get("vacation_city", "—")
    district = user_data.get('district', None)
    
    if district:
        city = f"{city} - {district}"
    
    # Создаем ссылку на профиль
    profile_link = await create_user_profile_link(user_data, user_id)
    
    country_display = get_country_translation(country, language) if country and country != "—" else country
    city_display = get_city_translation(city, language) if city and city != "—" else city
    text = (
        f"🔎 {t('tours.user_tour', language)}:\n\n"
        f"{profile_link}\n"
        f"📍 {t('tours.place', language)}: {country_display}, {city_display}\n\n"
        f"📅 {t('tours.travel_dates', language)}:\n"
        f"{t('tours.start', language)}: {user_data.get('vacation_start', '—')}\n"
        f"{t('tours.end', language)}: {user_data.get('vacation_end', '—')}\n\n"
    )
    
    if user_data.get('vacation_comment'):
        text += f"{t('tours.comment', language)}: {user_data['vacation_comment']}\n"
    
    # Кнопка для возврата к списку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=t("common.contact_user", language), 
                url=f"tg://user?id={user_id}" if user_id.isdigit() else "#"
            )],
            [InlineKeyboardButton(
                text=t("common.back_to_list", language), callback_data="back_to_tours_list"
            )]
            ,
            [InlineKeyboardButton(
                text=t("tours.offer_tour", language), callback_data="create_tour_from_menu"
            )]
        ]
    )
    
    # Проверяем наличие фото
    photo_path = user_data.get('photo_path')
    if photo_path:
        # Если есть фото, удаляем старое сообщение и отправляем новое с фото
        try:
            await callback.message.delete()
        except:
            pass
        
        try:
            photo = FSInputFile(photo_path)
            await callback.message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            # Если не удалось отправить фото, отправляем текстом
            await callback.message.answer(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        # Если фото нет, просто редактируем
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
    
    await callback.answer()

@router.callback_query(F.data == "back_to_tours_list")
async def back_to_tours_list(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку туров"""
    language = await get_user_language_async(str(callback.message.chat.id))

    # Сначала пытаемся редактировать существующее сообщение
    try:
        await show_tours_page(callback.message, state)
    except Exception as e:
        # Если не удалось редактировать (например, сообщение с фото), удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        # Отправляем новое сообщение со списком туров
        state_data = await state.get_data()
        all_tours = state_data.get('all_tours', [])
        current_page = state_data.get('current_page', 0)
        sport = state_data.get('selected_sport')
        
        if not all_tours:
            await callback.message.answer(t("tours.not_found_tour", language))
            await callback.answer()
            return
        
        # Вычисляем индексы для текущей страницы
        start_idx = current_page * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_tours = all_tours[start_idx:end_idx]
        
        sport_text = t("tours.any_sport_text", language) if sport == "any" else get_sport_translation(sport, language)

        text = f"🔎 {t('tours.find_tours', language, sport_text=sport_text)} {get_city_translation(state_data.get('selected_city'), language)}, {get_country_translation(state_data.get('selected_country'), language)}\n\n"
    
        # Создаем клавиатуру
        builder = InlineKeyboardBuilder()
        
        # Кнопки для каждого тура на странице
        for i, tour in enumerate(page_tours, start=1):
            user_data = tour['user_data']
            
            # Смайлик гендера
            gender = user_data.get('gender', '')
            gender_icon = "👨" if gender == 'Мужской' else "👩" if gender == 'Женский' else '👤'
            
            # Имя сокращено до первой буквы + фамилия
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            user_name = f"{first_name[:1]}. {last_name}" if first_name and last_name else first_name or last_name or t("common.not_specified", language)
            
            level = user_data.get('player_level', '-')

            start_date = await format_tour_date(tour.get('vacation_start', '-'))
            end_date = await format_tour_date(tour.get('vacation_end', '-'))
            
            # Итоговая строка
            tour_info = f"{start_date}-{end_date} | {gender_icon} {user_name} ({level})"
            
            builder.row(InlineKeyboardButton(
                text=tour_info,
                callback_data=f"viewtour_{tour['user_id']}"
            ))
        
        builder.row(InlineKeyboardButton(
            text=t("tours.offer_tour", language),
            callback_data="create_tour_from_menu"
        ))
        
        # Кнопки навигации
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton(text=t("common.back", language), callback_data="tourpage_prev"))
        if end_idx < len(all_tours):
            nav_buttons.append(InlineKeyboardButton(text=t("common.next", language), callback_data="tourpage_next"))
    
        if nav_buttons:
            builder.row(*nav_buttons)
        
        await callback.message.answer(text, reply_markup=builder.as_markup())
    
    await callback.answer()

@router.callback_query(F.data == "create_tour_from_menu")
async def start_create_tour_from_menu(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания тура из главного меню туров"""
    # Получаем профиль пользователя для проверки вида спорта
    user_id = callback.from_user.id
    user_data = await storage.get_user(user_id) or {}
    sport = user_data.get('sport', '🎾Большой теннис')
    config = get_sport_config(sport)

    language = await get_user_language_async(str(user_id))
    
    # Проверяем, поддерживает ли вид спорта туры
    if not config.get("has_vacation", True):
        await callback.message.edit_text(t("tours.sport_dont_supports", language, sport=sport))
        await callback.answer()
        return
    
    # Создаем клавиатуру с кнопками стран
    buttons = []
    for country in countries[:5]:
        buttons.append([InlineKeyboardButton(text=get_country_translation(country, language), callback_data=f"create_tour_country_{country}")])
    buttons.append([InlineKeyboardButton(text=t("registration.other_country", language), callback_data="create_tour_other_country")])

    try:
        await callback.message.edit_text(
            t("registration.select_vacation_country", language),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await callback.message.answer(
            t("registration.select_vacation_country", language),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
    await state.set_state(CreateTourStates.SELECT_COUNTRY)
    await callback.answer()

@router.callback_query(F.data.startswith("createTour"))
async def start_create_tour(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания тура с выбором страны"""
    # Получаем профиль пользователя для проверки вида спорта
    user_id = callback.from_user.id
    user_data = await storage.get_user(user_id) or {}
    sport = user_data.get('sport', '🎾Большой теннис')
    config = get_sport_config(sport)

    language = await get_user_language_async(str(user_id))
    
    # Проверяем, поддерживает ли вид спорта туры
    if not config.get("has_vacation", True):
        await callback.message.edit_text(t("tours.sport_dont_supports", language, sport=sport))
        await callback.answer()
        return
    
    # Создаем клавиатуру с кнопками стран
    buttons = []
    for country in countries[:5]:
        buttons.append([InlineKeyboardButton(text=get_country_translation(country, language), callback_data=f"create_tour_country_{country}")])
    buttons.append([InlineKeyboardButton(text=t("registration.other_country", language), callback_data="create_tour_other_country")])

    try:
        await callback.message.edit_text(
            t("registration.select_vacation_country", language),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await callback.message.answer(
            t("registration.select_vacation_country", language),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
    await state.set_state(CreateTourStates.SELECT_COUNTRY)
    await callback.answer()

@router.callback_query(CreateTourStates.SELECT_COUNTRY, F.data.startswith("create_tour_country_"))
async def process_create_tour_country_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора страны для создания тура"""
    country = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(vacation_country=country)
    await ask_for_create_tour_city(callback.message, state, country)
    await callback.answer()

@router.callback_query(CreateTourStates.SELECT_COUNTRY, F.data == "create_tour_other_country")
async def process_create_tour_other_country(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора другой страны для создания тура"""
    language = await get_user_language_async(str(callback.from_user.id))
    
    await callback.message.edit_text(t("registration.enter_vacation_country", language), reply_markup=None)
    await state.set_state(CreateTourStates.ENTER_COUNTRY)
    await callback.answer()

@router.message(CreateTourStates.ENTER_COUNTRY, F.text)
async def process_create_tour_country_input(message: Message, state: FSMContext):
    """Обработка ввода названия страны для создания тура"""
    await state.update_data(vacation_country=message.text.strip())
    language = await get_user_language_async(str(message.chat.id))

    await message.answer(t("registration.enter_vacation_city", language))
    await state.set_state(CreateTourStates.ENTER_CITY)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_create_tour_city(message: types.Message, state: FSMContext, country: str):
    """Запрос города для создания тура"""
    language = await get_user_language_async(str(message.chat.id))

    cities = cities_data.get(country, [])
    buttons = [[InlineKeyboardButton(text=get_city_translation(city, language), callback_data=f"create_tour_city_{city}")] for city in cities[:5]]
    buttons.append([InlineKeyboardButton(text=t("registration.other_city", language), callback_data="create_tour_other_city")])
    
    try:
        await message.edit_text(
            t("registration.select_vacation_city", language, country=get_country_translation(country, language)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            t("registration.select_vacation_city", language, country=get_country_translation(country, language)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
    await state.set_state(CreateTourStates.SELECT_CITY)

@router.callback_query(CreateTourStates.SELECT_CITY, F.data.startswith("create_tour_city_"))
async def process_create_tour_city_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора города для создания тура"""
    city = callback.data.split("_", maxsplit=3)[3]
    await state.update_data(vacation_city=city)

    language = await get_user_language_async(str(callback.message.chat.id))

    await callback.message.edit_text(
        t("registration.enter_vacation_start", language),
        reply_markup=None
    )
    await state.set_state(CreateTourStates.ENTER_START_DATE)
    await callback.answer()

@router.callback_query(CreateTourStates.SELECT_CITY, F.data == "create_tour_other_city")
async def process_create_tour_other_city(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора другого города для создания тура"""
    language = await get_user_language_async(str(callback.message.chat.id))

    await callback.message.edit_text(t("registration.enter_vacation_city", language), reply_markup=None)
    await state.set_state(CreateTourStates.ENTER_CITY)
    await callback.answer()

@router.message(CreateTourStates.ENTER_CITY, F.text)
async def process_create_tour_city_input(message: Message, state: FSMContext):
    """Обработка ввода названия города для создания тура"""
    language = await get_user_language_async(str(message.chat.id))

    await state.update_data(vacation_city=message.text.strip())
    await message.answer(
        t("registration.enter_vacation_start", language)
    )
    await state.set_state(CreateTourStates.ENTER_START_DATE)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(CreateTourStates.ENTER_START_DATE, F.text)
async def process_start_date(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))

    """Обработка даты начала поездки"""
    try:
        # Проверяем формат даты
        datetime.strptime(message.text, "%d.%m.%Y")
        
        # Проверяем что дата в будущем
        if not await validate_future_date(message.text):
            await message.answer(
                t("registration.invalid_vacation_start", language)
            )
            return
            
        await state.update_data(vacation_start=message.text)
        await message.answer(
            t("registration.enter_vacation_end", language)
        )
        await state.set_state(CreateTourStates.ENTER_END_DATE)
    except ValueError:
        await message.answer(
            t("registration.invalid_vacation_start", language)
        )

@router.message(CreateTourStates.ENTER_END_DATE, F.text)
async def process_end_date(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))

    """Обработка даты завершения поездки"""
    try:
        # Проверяем формат даты
        datetime.strptime(message.text, "%d.%m.%Y")
        
        # Проверяем что дата в будущем
        if not await validate_future_date(message.text):
            await message.answer(
                t("registration.invalid_vacation_end", language)
            )
            return
        
        state_data = await state.get_data()
        start_date = datetime.strptime(state_data['vacation_start'], "%d.%m.%Y")
        end_date = datetime.strptime(message.text, "%d.%m.%Y")
        
        if end_date <= start_date:
            await message.answer(
                t("registration.invalid_vacation_end", language)
            )
            return
        
        await state.update_data(vacation_end=message.text)
        await message.answer(
            t("registration.enter_vacation_comment", language)
        )
        await state.set_state(CreateTourStates.ENTER_COMMENT)
    except ValueError:
        await message.answer(
            t("registration.invalid_vacation_end", language)
        )

@router.message(CreateTourStates.ENTER_COMMENT, F.text == "/skip")
@router.message(CreateTourStates.ENTER_COMMENT, F.text)
async def process_tour_comment(message: types.Message, state: FSMContext):
    """Обработка комментария для тура и сохранение"""
    comment = message.text if message.text != "/skip" else None

    language = await get_user_language_async(str(message.chat.id))
    
    state_data = await state.get_data()
    vacation_start = state_data.get('vacation_start')
    vacation_end = state_data.get('vacation_end')
    vacation_country = state_data.get('vacation_country')
    vacation_city = state_data.get('vacation_city')
    
    # Загружаем данные пользователей
    users = await storage.load_users()
    user_id = str(message.from_user.id)
    
    if user_id not in users:
        await message.answer(t("main.profile_not_found", language))
        await state.clear()
        return
    
    # Обновляем данные пользователя
    users[user_id]['vacation_tennis'] = True
    users[user_id]['vacation_start'] = vacation_start
    users[user_id]['vacation_end'] = vacation_end
    users[user_id]['vacation_country'] = vacation_country
    users[user_id]['vacation_city'] = vacation_city
    if comment:
        users[user_id]['vacation_comment'] = comment
    
    # Сохраняем обновленные данные
    await storage.save_users(users)
    await send_tour_to_channel(message.bot, user_id, users[user_id])
    
    await message.answer(
        f"{t('tours.tour_successfully_created', language)}"
        f"📍 {t('tours.place', language)}: {get_country_translation(vacation_country, language)}, {get_city_translation(vacation_city, language)}\n"
        f"📅 {t('tours.travel_dates', language)}: {vacation_start} - {vacation_end}\n"
        f"💬 {t('tours.comment', language)}: {comment if comment else '-'}"
    )
    
    await state.clear()
