from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config.config import ITEMS_PER_PAGE
from config.profile import sport_type
from models.states import BrowseToursStates, CreateTourStates
from services.channels import send_tour_to_channel
from utils.utils import create_user_profile_link, format_tour_date
from utils.validate import validate_future_date
from services.storage import storage

router = Router()

@router.message(F.text == "✈️ Туры")
async def browse_tours_start(message: types.Message, state: FSMContext):
    """Начало просмотра туров - выбор спорта"""
    # Создаем клавиатуру с видами спорта
    keyboard = []

    for sport in sport_type:
        keyboard.append([InlineKeyboardButton(
            text=sport,
            callback_data=f"toursport_{sport}"
        )])
    try:
        await message.edit_text(
            "🎯 Выберите вид спорта для поиска туров:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except:
        await message.answer(
            "🎯 Выберите вид спорта для поиска туров:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    await state.set_state(BrowseToursStates.SELECT_SPORT)
    await state.update_data(page=0)

@router.callback_query(F.data == "tours_back_to_sport")
async def browse_tours_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало просмотра туров - выбор спорта"""
    keyboard = []

    for sport in sport_type:
        keyboard.append([InlineKeyboardButton(
            text=sport,
            callback_data=f"toursport_{sport}"
        )])
    try:
        await callback.message.edit_text(
            "🎯 Выберите вид спорта для поиска туров:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except:
        await callback.message.answer(
            "🎯 Выберите вид спорта для поиска туров:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    await state.set_state(BrowseToursStates.SELECT_SPORT)
    await state.update_data(page=0)

@router.callback_query(BrowseToursStates.SELECT_SPORT, F.data.startswith("toursport_"))
async def select_tour_sport(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора спорта для туров"""
    sport = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(selected_sport=sport)
    
    users = await storage.load_users()
    current_user_id = str(callback.from_user.id)
    
    # Собираем статистику по странам с активными турами (исключая текущего пользователя)
    country_stats = {}
    for user_id, user_data in users.items():
        # Пропускаем текущего пользователя
        if user_id == current_user_id:
            continue
            
        # Проверяем, что у пользователя включен поиск партнера на время отдыха
        # и что выбранный спорт соответствует его профилю
        if (user_data.get('vacation_tennis', False) and 
            user_data.get('sport') == sport):
            country = user_data.get('country', '')
            if country:
                country_stats[country] = country_stats.get(country, 0) + 1
    
    if not country_stats:
        # Предлагаем создать тур с выбранным видом спорта
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🎾 Найти партнера на время отдыха",
                callback_data=f"create_tour"
            )],
            [InlineKeyboardButton(
                text="🔙 Назад к выбору спорта",
                callback_data="tours_back_to_sport"
            )]
        ])
        
        await callback.message.edit_text(
            f"❌ На данный момент нет активных туров по {sport} от других пользователей.",
            reply_markup=keyboard
        )
        return
    
    # Создаем клавиатуру с кнопками стран
    buttons = []
    for country, count in country_stats.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{country} ({count} туров)",
                callback_data=f"tourcountry_{country}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🌍 Выберите страну для просмотра туров по {sport}:",
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
    
    await state.update_data(selected_country=country)
    
    users = await storage.load_users()
    
    # Собираем статистику по городам в выбранной стране для выбранного спорта
    city_stats = {}
    for user_id, user_data in users.items():
        if (user_data.get('country') == country and 
            user_data.get('vacation_tennis', False) and
            user_data.get('sport') == sport):
            city = user_data.get('city', '')
            if city:
                city_stats[city] = city_stats.get(city, 0) + 1
    
    if not city_stats:
        await callback.answer("❌ В этой стране нет активных туров по выбранному виду спорта")
        return
    
    # Создаем клавиатуру с кнопками городов
    buttons = []
    for city, count in city_stats.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"🏙 {city} ({count} туров)",
                callback_data=f"tourcity_{city}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        f"🏙 Выберите город в {country} для {sport}:",
        reply_markup=keyboard
    )
    await state.set_state(BrowseToursStates.SELECT_CITY)
    await callback.answer()

@router.callback_query(BrowseToursStates.SELECT_CITY, F.data.startswith("tourcity_"))
async def select_tour_city(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора города и отображение туров"""
    city = callback.data.split("_", maxsplit=1)[1]
    state_data = await state.get_data()
    country = state_data.get('selected_country')
    sport = state_data.get('selected_sport')
    
    await state.update_data(selected_city=city)
    
    # Получаем все активные туры в выбранном городе и стране для выбранного спорта
    users = await storage.load_users()
    all_tours = []
    
    for user_id, user_data in users.items():
        if (user_data.get('country') == country and 
            user_data.get('city') == city and 
            user_data.get('vacation_tennis', False) and
            user_data.get('sport') == sport):
            
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
        await callback.answer("❌ В этом городе нет активных туров по выбранному виду спорта")
        return
    
    # Сохраняем все туры в state
    await state.update_data(all_tours=all_tours, current_page=0)
    
    # Показываем первую страницу туров
    await show_tours_page(callback.message, state)
    await callback.answer()

async def show_tours_page(message: types.Message, state: FSMContext):
    """Показать страницу с турами"""
    state_data = await state.get_data()
    all_tours = state_data.get('all_tours', [])
    current_page = state_data.get('current_page', 0)
    sport = state_data.get('selected_sport')
    
    if not all_tours:
        await message.answer("❌ Нет туров для отображения")
        return
    
    # Вычисляем индексы для текущей страницы
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_tours = all_tours[start_idx:end_idx]
    
    # Заголовок
    sport_icons = {
        'tennis': '🎾',
        'badminton': '🏸',
        'table_tennis': '🏓'
    }
    sport_icon = sport_icons.get(sport, '🎾')
    
    text = f"{sport_icon} Туры по {sport} в {state_data.get('selected_city')}, {state_data.get('selected_country')}\n\n"
    
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
        user_name = f"{first_name[:1]}. {last_name}" if first_name and last_name else first_name or last_name or 'Неизвестно'
        
        level = user_data.get('player_level', '-')
        
        start_date = await format_tour_date(tour.get('vacation_start', '-'))
        end_date = await format_tour_date(tour.get('vacation_end', '-'))
        
        # Итоговая строка
        tour_info = f"{start_date}-{end_date} | {gender_icon} {user_name} ({level})"
        
        builder.row(InlineKeyboardButton(
            text=tour_info,
            callback_data=f"viewtour_{tour['user_id']}"
        ))
    
    # Кнопки навигации
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="tourpage_prev"))
    if end_idx < len(all_tours):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data="tourpage_next"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Отправляем сообщение
    if message.content_type == 'text':
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
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
    
    if not user_data or not user_data.get('vacation_tennis', False):
        await callback.answer("❌ Тур не найден")
        return
    
    # Формируем детальную информацию
    username = user_data.get("username")
    username_str = f"@{username}" if username else "👤 (без username)"
    
    user_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
    player_level = user_data.get("player_level", "—")
    country = user_data.get("country", "—")
    city = user_data.get("city", "—")
    district = user_data.get('district', None)
    sport = user_data.get('sport', 'теннис')
    
    if district:
        city = f"{city} - {district}"
    
    # Создаем ссылку на профиль
    profile_link = await create_user_profile_link(user_data, user_id)
    
    # Иконка спорта
    sport_icons = {
        'tennis': '🎾',
        'badminton': '🏸',
        'table_tennis': '🏓'
    }
    sport_icon = sport_icons.get(sport, '🎾')
    
    text = (
        f"{sport_icon} Тур пользователя ({sport}):\n\n"
        f"{profile_link}\n"
        f"🏅 Уровень: {player_level}\n"
        f"📍 Место: {country}, {city}\n\n"
        f"📅 Даты поездки:\n"
        f"Начало: {user_data.get('vacation_start', '—')}\n"
        f"Окончание: {user_data.get('vacation_end', '—')}\n\n"
    )
    
    if user_data.get('vacation_comment'):
        text += f"💬 Комментарий: {user_data['vacation_comment']}\n"
    
    # Кнопка для возврата к списку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✉️ Связаться с пользователем", 
                url=f"tg://user?id={user_id}" if user_id.isdigit() else "#"
            )],
            [InlineKeyboardButton(
                text="🔙 Назад к списку", callback_data="back_to_tours_list"
            )]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
    await callback.answer()

@router.callback_query(F.data == "back_to_tours_list")
async def back_to_tours_list(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку туров"""
    await show_tours_page(callback.message, state)
    await callback.answer()

@router.callback_query(F.data.startswith("create_tour"))
async def start_create_tour(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания тура с определенным видом спорта"""    
    try:
        await callback.message.edit_text(
            "📅 Введите дату начала поездки в формате ДД.ММ.ГГГГ:\n"
            "Например: 25.08.2025"
        )
    except:
        try:
            await callback.message.delete()
        except:
            pass

        await callback.message.answer(
            "📅 Введите дату начала поездки в формате ДД.ММ.ГГГГ:\n"
            "Например: 25.08.2025"
        )
    
    await state.set_state(CreateTourStates.ENTER_START_DATE)
    await callback.answer()

@router.message(CreateTourStates.ENTER_START_DATE, F.text)
async def process_start_date(message: types.Message, state: FSMContext):
    """Обработка даты начала поездки"""
    try:
        # Проверяем формат даты
        datetime.strptime(message.text, "%d.%m.%Y")
        
        # Проверяем что дата в будущем
        if not await validate_future_date(message.text):
            await message.answer(
                "❌ Неверный формат даты. "
                "Пожалуйста, введите корректную дату в формате ДД.ММ.ГГГГ:\n"
                "Например: 25.08.2025"
            )
            return
            
        await state.update_data(vacation_start=message.text)
        await message.answer(
            "📅 Введите дату завершения поездки в формате ДД.ММ.ГГГГ:\n"
            "Например: 30.08.2025"
        )
        await state.set_state(CreateTourStates.ENTER_END_DATE)
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:\n"
            "Например: 25.08.2025"
        )

@router.message(CreateTourStates.ENTER_END_DATE, F.text)
async def process_end_date(message: types.Message, state: FSMContext):
    """Обработка даты завершения поездки"""
    try:
        # Проверяем формат даты
        datetime.strptime(message.text, "%d.%m.%Y")
        
        # Проверяем что дата в будущем
        if not await validate_future_date(message.text):
            await message.answer(
                "❌ Неверный формат даты. "
                "Пожалуйста, введите корректную дату в формате ДД.ММ.ГГГГ:\n"
                "Например: 30.08.2025"
            )
            return
        
        state_data = await state.get_data()
        start_date = datetime.strptime(state_data['vacation_start'], "%d.%m.%Y")
        end_date = datetime.strptime(message.text, "%d.%m.%Y")
        
        if end_date <= start_date:
            await message.answer(
                "❌ Дата завершения должна быть позже даты начала. Попробуйте еще раз:"
            )
            return
        
        await state.update_data(vacation_end=message.text)
        await message.answer(
            "💬 Введите комментарий к вашему туру (необязательно):\n\n"
            "Или нажмите /skip чтобы пропустить этот шаг."
        )
        await state.set_state(CreateTourStates.ENTER_COMMENT)
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:\n"
            "Например: 30.08.2025"
        )

@router.message(CreateTourStates.ENTER_COMMENT, F.text == "/skip")
@router.message(CreateTourStates.ENTER_COMMENT, F.text)
async def process_tour_comment(message: types.Message, state: FSMContext):
    """Обработка комментария для тура и сохранение"""
    comment = message.text if message.text != "/skip" else None
    
    state_data = await state.get_data()
    vacation_start = state_data.get('vacation_start')
    vacation_end = state_data.get('vacation_end')
    
    # Загружаем данные пользователей
    users = await storage.load_users()
    user_id = str(message.from_user.id)
    
    if user_id not in users:
        await message.answer("❌ Ошибка: ваш профиль не найден")
        await state.clear()
        return
    
    # Обновляем данные пользователя
    users[user_id]['vacation_tennis'] = True
    users[user_id]['vacation_start'] = vacation_start
    users[user_id]['vacation_end'] = vacation_end
    if comment:
        users[user_id]['vacation_comment'] = comment
    
    # Сохраняем обновленные данные
    await storage.save_users(users)
    await send_tour_to_channel(message.bot, user_id, users[user_id])
    
    await message.answer(
        f"Ваш тур успешно создан! Теперь другие пользователи смогут увидеть его в списке туров.\n\n"
        f"📅 Даты: {vacation_start} - {vacation_end}\n"
        f"💬 Комментарий: {comment if comment else 'Не указан'}"
    )
    
    await state.clear()
