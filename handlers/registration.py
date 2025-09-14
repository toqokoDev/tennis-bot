from datetime import datetime, timedelta
import re

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config.paths import BASE_DIR, PHOTOS_DIR
from config.profile import moscow_districts, player_levels, base_keyboard, cities_data, sport_type, countries

from models.states import RegistrationStates

from services.channels import send_registration_notification
from utils.admin import is_user_banned
from utils.media import download_photo_to_path
from utils.bot import show_current_data, show_profile
from utils.validate import validate_date, validate_date_range, validate_future_date, validate_price
from services.storage import storage

router = Router()

# ---------- Команды и логика ----------
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = str(message.chat.id)
    
    # Проверяем, забанен ли пользователь
    if await is_user_banned(user_id):
        await message.answer(
            "⛔ Ваш аккаунт заблокирован.\n\n"
            "Вы не можете использовать бота. Если вы считаете, что это ошибка, "
            "свяжитесь с администрацией.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    referral_id = None
    # Проверяем, есть ли параметр в команде start (для ссылок на профили)
    if len(message.text.split()) > 1:
        command_parts = message.text.split()
        if len(command_parts) >= 2:
            start_param = command_parts[1]
            
            if start_param.startswith('ref_'):
                referral_id = start_param.replace('ref_', '')
                
                if referral_id != user_id:
                    await state.update_data(referral_id=referral_id)

            elif start_param.startswith('profile_'):
                profile_user_id = start_param.replace('profile_', '')
                
                # Проверяем, не забанен ли целевой пользователь
                if await is_user_banned(profile_user_id):
                    await message.answer("⛔ Этот профиль недоступен.")
                    return
                
                users = await storage.load_users()
                
                if profile_user_id in users:
                    profile_user = users[profile_user_id]
                    await show_profile(message, profile_user)
                else:
                    await message.answer("Профиль не найден.")
                    
                return
    
    # Загружаем сессию если есть
    session_data = await storage.load_session(user_id)
    
    if session_data:
        await state.set_data(session_data)
    
    if await storage.is_user_registered(user_id):
        profile = await storage.get_user(user_id) or {}
        first_name = profile.get('first_name', message.from_user.first_name or '')
        last_name = profile.get('last_name', message.from_user.last_name or '')
        rating = profile.get('rating_points', 0)
        games_played = profile.get('games_played', 0)
        games_wins = profile.get('games_wins', 0)
        
        greet = (
            f"👋 Здравствуйте, <b>{first_name} {last_name}</b>!\n\n"
            f"🏆 Ваш рейтинг: <b>{rating}</b>\n"
            f"🎾 Сыграно игр: <b>{games_played}</b>\n"
            f"✅ Побед: <b>{games_wins}</b>\n\n"
            f"Вы зарегистрированы в официальном боте @tennis_playbot\n"
            f"Выберите действие из меню ниже:"
        )  

        await message.answer(greet, parse_mode="HTML", reply_markup=base_keyboard)
        await state.clear()
        return

    # Если пользователь не зарегистрирован
    await state.set_state(RegistrationStates.PHONE)
    welcome_text = (
        f"👋 Здравствуйте, <b>{message.from_user.full_name}</b>!\n\n"
        "Вы находитесь в боте @tennis_playbot проекта Tennis-Play.com\n\n"
        "💡 <b>Здесь вы сможете:</b>\n\n"
        "• Найти партнёра по:\n"
        "   🎾 Большому теннису\n"
        "   🏓 Настольному теннису\n"
        "   🏸 Бадминтону\n"
        "   🏖️ Пляжному теннису\n"
        "   🎾 Падл-теннису\n"
        "   🥎 Сквошу\n"
        "   🏆 Пиклболу\n"
        "   ⛳ Гольфу\n"
        "   🏃‍♂️ Бегу\n"
        "   🏋️‍♀️ Фитнесу\n"
        "   🚴 Велоспорту\n"
        "   🍻 По пиву\n"
        "   🍒 Знакомствам\n\n"
        "• Предлагать и находить предложения игр в определенное время и месте.\n"
        "• Участвовать в многодневных турнирах в вашем городе и на вашем корте.\n"
        "• Находить тренеров.\n"
        "• Отслеживать свой рейтинг.\n\n"
        "Для начала пройдите краткую регистрацию.\n\n"
        "Начиная регистрацию, Вы соглашаетесь с <a href='https://tennis-play.com/privacy-bot'>политикой обработки персональных данных</a> "
        "и даёте согласие на <a href='https://tennis-play.com/soglasie'>обработку данных</a>\n\n"
        "<b>Пожалуйста, отправьте номер телефона:</b>"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        ),
        parse_mode="HTML"
    )
    await storage.save_session(user_id, await state.get_data())

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.chat.id
    if not await storage.is_user_registered(user_id):
        await message.answer("❌ Вы еще не зарегистрированы. Введите /start для регистрации.")
        return
    
    profile = await storage.get_user(user_id) or {}
    await show_profile(message, profile)

@router.message(Command("profile_id"))
async def cmd_profile_id(message: types.Message):
    try:
        user_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /profile_id USER_ID")
        return
    
    profile = await storage.get_user(user_id)
    if not profile:
        await message.answer("❌ Пользователь с таким ID не найден.")
        return
    
    await show_profile(message, profile)

@router.message(RegistrationStates.PHONE, (F.contact | F.text))
async def process_phone(message: Message, state: FSMContext):

    phone = None
    phone_pattern = re.compile(r'^\+?\d{10,15}$')

    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        text = message.text.strip()
        if phone_pattern.match(text):
            phone = text

    if not phone:
        await message.answer("❌ Пожалуйста, отправьте корректный номер телефона.")
        return

    await state.update_data(phone=phone)
    
    msg = await message.answer(
        "🎾 Выберите вид спорта:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(prev_msg_id=msg.message_id)

    # Кнопки выбора вида спорта
    buttons = []
    row = []
    for i, sport in enumerate(sport_type):
        row.append(InlineKeyboardButton(text=sport, callback_data=f"sport_{sport}"))
        if (i + 1) % 2 == 0 or i == len(sport_type) - 1:
            buttons.append(row)
            row = []

    await show_current_data(
        message, state,
        "🎾 Выберите вид спорта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.SPORT)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.SPORT, F.data.startswith("sport_"))
async def process_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    sport = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(sport=sport)
    await callback.message.edit_text("📝 Введите ваше имя:", reply_markup=None)
    await state.set_state(RegistrationStates.FIRST_NAME)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.FIRST_NAME, F.text)
async def process_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text.strip())
    await message.answer("📝 Введите вашу фамилию:")
    await state.set_state(RegistrationStates.LAST_NAME)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.LAST_NAME, F.text)
async def process_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text.strip())
    await message.answer("📅 Введите вашу дату рождения в формате ДД.ММ.ГГГГ:")
    await state.set_state(RegistrationStates.BIRTH_DATE)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.BIRTH_DATE, F.text)
async def process_birth_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not await validate_date(date_str):
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return
    
    await state.update_data(birth_date=date_str)
    
    buttons = []
    for country in countries[:5]:
        buttons.append([InlineKeyboardButton(text=f"{country}", callback_data=f"country_{country}")])
    buttons.append([InlineKeyboardButton(text="🌎 Другая страна", callback_data="other_country")])

    await show_current_data(
        message, state,
        "🌍 Выберите страну:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.COUNTRY)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.COUNTRY, F.data.startswith("country_"))
async def process_country_selection(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(country=country)
    await ask_for_city(callback.message, state, country)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.COUNTRY, F.data == "other_country")
async def process_other_country(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌍 Введите название страны:", reply_markup=None)
    await state.set_state(RegistrationStates.COUNTRY_INPUT)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.COUNTRY_INPUT, F.text)
async def process_country_input(message: Message, state: FSMContext):
    await state.update_data(country=message.text.strip())
    await message.answer("🏙 Введите название города:")
    await state.set_state(RegistrationStates.CITY_INPUT)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.CITY_INPUT, F.text)
async def process_city_input(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await ask_for_role(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_city(message: types.Message, state: FSMContext, country: str):
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"city_{city}")] for city in main_russian_cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="other_city")])
    else:
        cities = cities_data.get(country, [])
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"city_{city}")] for city in cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="other_city")])

    await show_current_data(
        message, state,
        f"🏙 Выберите город в стране: {country}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.CITY)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.CITY, F.data.startswith("city_"))
async def process_city_selection(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=1)[1]

    if city == "Москва":
        buttons = [[InlineKeyboardButton(text=district, callback_data=f"district_{district}")] for district in moscow_districts]
        await show_current_data(
            callback.message, state,
            "🏙 Выберите округ Москвы:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await state.update_data(city=city)
        await ask_for_role(callback.message, state)

    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.CITY, F.data.startswith("district_"))
async def process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    district = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(city=district.split("-")[0].strip())
    await state.update_data(district=district.split("-")[1].strip())
    await ask_for_role(callback.message, state)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.CITY, F.data == "other_city")
async def process_other_city(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🏙 Введите название города:", reply_markup=None)
    await state.set_state(RegistrationStates.CITY_INPUT)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

async def ask_for_role(message: types.Message, state: FSMContext):
    buttons = [
        [InlineKeyboardButton(text="🎯 Игрок", callback_data="role_Игрок")],
        [InlineKeyboardButton(text="👨‍🏫 Тренер", callback_data="role_Тренер")]
    ]
    await show_current_data(
        message, state,
        "🎭 Выберите роль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.ROLE)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.ROLE, F.data.startswith("role_"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(role=role)

    if role == "Тренер":
        await callback.message.edit_text("💵 Введите стоимость тренировки (в рублях, только цифры):", reply_markup=None)
        await state.set_state(RegistrationStates.TRAINER_PRICE)
    else:
        # Показываем первую страницу уровней
        await show_levels_page(callback.message, state, page=0)

    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.TRAINER_PRICE, F.text)
async def process_trainer_price(message: types.Message, state: FSMContext):
    price_str = message.text.strip()
    if not await validate_price(price_str):
        await message.answer("❌ Пожалуйста, введите корректную стоимость тренировки (только цифры, больше 0):")
        return
    
    await state.update_data(price=int(price_str))
    
    await show_levels_page(message, state, page=0)
    await state.set_state(RegistrationStates.PLAYER_LEVEL)
    await storage.save_session(message.chat.id, await state.get_data())

async def show_levels_page(message: types.Message, state: FSMContext, page: int = 0):
    """Показывает страницу с уровнями игроков с возможностью пролистывания"""
    levels_list = list(player_levels.keys())
    items_per_page = 3
    total_pages = (len(levels_list) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(levels_list))
    current_levels = levels_list[start_idx:end_idx]
    
    # Формируем текст с описанием текущих уровней
    levels_text = "🏆 *Система уровней теннисистов:*\n\n"
    
    for level in current_levels:
        description = player_levels[level]["desc"]
        levels_text += f"*{level}* - {description}\n\n"
    
    levels_text += f"*Страница {page + 1} из {total_pages}*\n\n👇 *Выберите ваш уровень:*"
    
    # Создаем кнопки для уровней
    buttons = []
    for level in current_levels:
        buttons.append([InlineKeyboardButton(
            text=f"🎾 {level}",
            callback_data=f"level_{level}"
        )])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"levelpage_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"levelpage_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Если сообщение уже существует, редактируем его, иначе отправляем новое
    try:
        await message.edit_text(
            levels_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            levels_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
    await state.set_state(RegistrationStates.PLAYER_LEVEL)
    await state.update_data(level_page=page)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.PLAYER_LEVEL, F.data.startswith("levelpage_"))
async def process_level_page_navigation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка навигации по страницам уровней"""
    page = int(callback.data.split("_", maxsplit=1)[1])
    await show_levels_page(callback.message, state, page)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.PLAYER_LEVEL, F.data.startswith("level_"))
async def process_player_level(callback: types.CallbackQuery, state: FSMContext):
    level = callback.data.split("_", maxsplit=1)[1]
    description = player_levels.get(level, {}).get('desc', '')
    await state.update_data(player_level=level)

    await callback.message.edit_text(
        f"🏆 Ваш уровень: {level}\n\n{description}",
        reply_markup=None
    )
    
    buttons = [
        [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_Мужской")],
        [InlineKeyboardButton(text="👩 Женский", callback_data="gender_Женский")]
    ]
    await show_current_data(
        callback.message, state,
        "👫 Укажите пол:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.GENDER)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.GENDER, F.data.startswith("gender_"))
async def process_gender_selection(callback: types.CallbackQuery, state: FSMContext):
    gender = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(gender=gender)
    
    # Сначала спрашиваем комментарий к анкете
    await callback.message.edit_text("💬 Добавьте комментарий к анкете (или /skip для пропуска):", reply_markup=None)
    await state.set_state(RegistrationStates.PROFILE_COMMENT)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.PROFILE_COMMENT, F.text)
async def process_profile_comment(message: types.Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(profile_comment=message.text.strip())
    
    # Для игроков продолжаем стандартный процесс
    buttons = [
        [InlineKeyboardButton(text="📷 Загрузить фото", callback_data="photo_upload")],
        [InlineKeyboardButton(text="👀 Без фото", callback_data="photo_none")],
        [InlineKeyboardButton(text="Фото из профиля", callback_data="photo_profile")]
    ]
    await show_current_data(
        message, state,
        "📷 Фото профиля:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.PHOTO)
    
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.PHOTO, F.data.startswith("photo_"))
async def process_photo_choice(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split("_", maxsplit=1)[1]

    if choice == "upload":
        await callback.message.edit_text("📷 Отправьте фотографию одним сообщением (из галереи или сделайте снимок):", reply_markup=None)
        return

    if choice == "profile":
        try:
            photos = await callback.message.bot.get_user_profile_photos(callback.message.chat.id, limit=1)
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                ts = int(datetime.now().timestamp())
                filename = f"{callback.message.chat.id}_{ts}.jpg"
                dest_path = PHOTOS_DIR / filename
                ok = await download_photo_to_path(callback.message.bot, file_id, dest_path)
                if ok:
                    rel_path = dest_path.relative_to(BASE_DIR).as_posix()
                    await state.update_data(photo="profile", photo_path=rel_path)
                    await ask_for_vacation_tennis(callback.message, state)
                else:
                    await callback.message.edit_text("❌ Не удалось получить фото профиля. Пожалуйста, загрузите фото вручную:")
                    return
            else:
                await callback.message.edit_text("❌ Фото профиля отсутствует. Пожалуйста, загрузите фото вручную:")
                return
        except Exception:
            await callback.message.edit_text("❌ Не удалось получить фото профиля. Пожалуйста, загрузите фото вручную:")
            return
    elif choice == "none":
        await state.update_data(photo="none", photo_path=None)
        await ask_for_vacation_tennis(callback.message, state)
    else:
        await state.update_data(photo="none", photo_path=None)
        await ask_for_vacation_tennis(callback.message, state)

    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.PHOTO, F.photo)
async def process_photo_upload(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    ts = int(datetime.now().timestamp())
    filename = f"{message.chat.id}_{ts}.jpg"
    dest_path = PHOTOS_DIR / filename
    ok = await download_photo_to_path(message.bot, photo_id, dest_path)
    if ok:
        rel_path = dest_path.relative_to(BASE_DIR).as_posix()
        await state.update_data(photo="uploaded", photo_path=rel_path)
        await ask_for_vacation_tennis(message, state)
    else:
        await message.answer("❌ Не удалось сохранить фото. Попробуйте отправить ещё раз или выберите вариант без фото.")
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_vacation_tennis(message: types.Message, state: FSMContext):
    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data="vacation_yes")],
        [InlineKeyboardButton(text="⏩ Нет", callback_data="vacation_no")]
    ]
    await show_current_data(
        message, state,
        "✈️ Хотите найти партнёра на время отдыха?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.VACATION_TENNIS)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.VACATION_TENNIS, F.data.startswith("vacation_"))
async def process_vacation_tennis(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split("_", maxsplit=1)[1]
    
    if choice == "yes":
        # Сначала спрашиваем страну отдыха
        buttons = []
        for country in countries[:5]:
            buttons.append([InlineKeyboardButton(text=f"{country}", callback_data=f"vacation_country_{country}")])
        buttons.append([InlineKeyboardButton(text="🌎 Другая страна", callback_data="vacation_other_country")])

        await callback.message.edit_text(
            "🌍 Выберите страну отдыха:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(RegistrationStates.VACATION_COUNTRY)
    else:
        await state.update_data(vacation_tennis=False)
        await ask_for_default_payment(callback.message, state)
    
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.VACATION_COUNTRY, F.data.startswith("vacation_country_"))
async def process_vacation_country_selection(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(vacation_country=country)
    await ask_for_vacation_city(callback.message, state, country)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.VACATION_COUNTRY, F.data == "vacation_other_country")
async def process_vacation_other_country(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌍 Введите название страны отдыха:", reply_markup=None)
    await state.set_state(RegistrationStates.VACATION_COUNTRY_INPUT)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_COUNTRY_INPUT, F.text)
async def process_vacation_country_input(message: Message, state: FSMContext):
    await state.update_data(vacation_country=message.text.strip())
    await message.answer("🏙 Введите название города отдыха:")
    await state.set_state(RegistrationStates.VACATION_CITY_INPUT)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_CITY_INPUT, F.text)
async def process_vacation_city_input(message: Message, state: FSMContext):
    await state.update_data(vacation_city=message.text.strip())
    await message.answer("✈️ Введите дату начала отдыха (ДД.ММ.ГГГГ):")
    await state.set_state(RegistrationStates.VACATION_START)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_vacation_city(message: types.Message, state: FSMContext, country: str):
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"vacation_city_{city}")] for city in main_russian_cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="vacation_other_city")])
    else:
        cities = cities_data.get(country, [])
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"vacation_city_{city}")] for city in cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="vacation_other_city")])

    await show_current_data(
        message, state,
        f"🏙 Выберите город отдыха в стране: {country}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.VACATION_CITY)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.VACATION_CITY, F.data.startswith("vacation_city_"))
async def process_vacation_city_selection(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(vacation_city=city)
    await callback.message.edit_text("✈️ Введите дату начала отдыха (ДД.ММ.ГГГГ):", reply_markup=None)
    await state.set_state(RegistrationStates.VACATION_START)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.VACATION_CITY, F.data == "vacation_other_city")
async def process_vacation_other_city(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🏙 Введите название города отдыха:", reply_markup=None)
    await state.set_state(RegistrationStates.VACATION_CITY_INPUT)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_START, F.text)
async def process_vacation_start(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not await validate_date(date_str):
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return
    
    if not await validate_future_date(date_str):
        await message.answer("❌ Дата начала отдыха должна быть в будущем. Пожалуйста, введите корректную дату:")
        return
    
    await state.update_data(vacation_start=date_str, vacation_tennis=True)
    await message.answer("✈️ Введите дату завершения отдыха (ДД.ММ.ГГГГ):")
    await state.set_state(RegistrationStates.VACATION_END)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_END, F.text)
async def process_vacation_end(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not await validate_date(date_str):
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return
    
    user_data = await state.get_data()
    start_date = user_data.get('vacation_start')
    
    if not await validate_date_range(start_date, date_str):
        await message.answer("❌ Дата завершения должна быть после даты начала. Пожалуйста, введите корректную дату:")
        return
    
    await state.update_data(vacation_end=date_str)
    await message.answer("💬 Добавьте комментарий к поездке (необязательно, или /skip для пропуска):")
    await state.set_state(RegistrationStates.VACATION_COMMENT)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_COMMENT, F.text)
async def process_vacation_comment(message: Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(vacation_comment=message.text.strip())
    await ask_for_default_payment(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_default_payment(message: types.Message, state: FSMContext):
    buttons = [
        [InlineKeyboardButton(text="💰 Пополам", callback_data="defaultpay_Пополам")],
        [InlineKeyboardButton(text="💳 Я оплачиваю", callback_data="defaultpay_Я оплачиваю")],
        [InlineKeyboardButton(text="💵 Соперник оплачивает", callback_data="defaultpay_Соперник оплачивает")]
    ]
    await show_current_data(
        message, state,
        "💳 Как вы обычно оплачиваете корт?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.DEFAULT_PAYMENT)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.DEFAULT_PAYMENT, F.data.startswith("defaultpay_"))
async def process_default_payment(callback: types.CallbackQuery, state: FSMContext):
    payment = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(default_payment=payment)
    
    # Спрашиваем, хочет ли пользователь создать игру
    await ask_for_create_game(callback.message, state)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

async def ask_for_create_game(message: types.Message, state: FSMContext):
    """Спрашивает пользователя, хочет ли он создать игру после регистрации"""
    buttons = [
        [InlineKeyboardButton(text="✅ Да, создать игру", callback_data="registerTonew_offer")],
        [InlineKeyboardButton(text="❌ Нет, позже", callback_data="skip_offer")]
    ]
    await show_current_data(
        message, state,
        "🎾 Хотите сразу создать предложение об игре на конкретный день и время?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.CREATE_GAME_OFFER)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.CREATE_GAME_OFFER, F.data == "registerTonew_offer")
async def process_create_game_offer(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь хочет создать игру - завершаем регистрацию и переходим к созданию игры"""
    user_id = callback.message.chat.id
    username = callback.message.chat.username

    user_state = await state.get_data()

    profile = {
        "telegram_id": user_id,
        "username": username,
        "first_name": user_state.get("first_name"),
        "last_name": user_state.get("last_name"),
        "phone": user_state.get("phone"),
        "birth_date": user_state.get("birth_date"),
        "country": user_state.get("country"),
        "city": user_state.get("city"),
        "district": user_state.get("district", ""),
        "role": user_state.get("role", "пользователь"),
        "sport": user_state.get("sport"),
        "gender": user_state.get("gender"),
        "player_level": user_state.get("player_level"),
        "rating_points": player_levels.get(user_state.get("player_level"), {}).get("points", 0),
        "price": user_state.get("price"),
        "photo_path": user_state.get("photo_path"),
        "games_played": 0,
        "games_wins": 0,
        "default_payment": user_state.get("default_payment"),
        "show_in_search": True,
        "profile_comment": user_state.get("profile_comment"),
        "referrals_invited": 0,
        "games": [],
        "created_at": datetime.now().isoformat(timespec="seconds")
    }

    if user_state.get('vacation_tennis', False):
        profile["vacation_tennis"] = True
        profile["vacation_country"] = user_state.get('vacation_country')
        profile["vacation_city"] = user_state.get('vacation_city')
        profile["vacation_start"] = user_state.get('vacation_start')
        profile["vacation_end"] = user_state.get('vacation_end')
        profile["vacation_comment"] = user_state.get('vacation_comment')

    referral_id = user_state.get('referral_id')
    if referral_id and await storage.is_user_registered(referral_id):
        # Обновляем статистику реферера
        referrer_data = await storage.get_user(referral_id) or {}
        referrals_count = referrer_data.get('referrals_invited', 0) + 1
        
        await storage.update_user(referral_id, {
            'referrals_invited': referrals_count
        })
        
        # Проверяем, достиг ли реферер 10 приглашений
        if referrals_count >= 10:
            # Дарим подписку на 1 месяц
            await storage.update_user(referral_id, {
                'active': True,
                'until': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'activated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
            # Уведомляем реферера
            try:
                await callback.message.bot.send_message(
                    referral_id,
                    "🎉 Поздравляем! Вы пригласили 10 друзей и получили бесплатную подписку на 1 месяц!"
                )
            except:
                pass
            
    await storage.save_user(user_id, profile)
    await state.clear()
    await storage.delete_session(user_id)

    # Отправляем уведомление о регистрации
    await send_registration_notification(callback.message, profile)
    
    # Переходим к созданию игры
    await callback.message.edit_text(
        "✅ Регистрация завершена! Теперь вы можете создать предложение об игре.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Предложить игру", callback_data="new_offer")]])
    )
    await callback.answer()

@router.callback_query(RegistrationStates.CREATE_GAME_OFFER, F.data == "skip_offer")
async def process_skip_game_offer(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь не хочет создавать игру - завершаем регистрацию и показываем профиль"""
    user_id = callback.message.chat.id
    username = callback.message.chat.username

    user_state = await state.get_data()

    profile = {
        "telegram_id": user_id,
        "username": username,
        "first_name": user_state.get("first_name"),
        "last_name": user_state.get("last_name"),
        "phone": user_state.get("phone"),
        "birth_date": user_state.get("birth_date"),
        "country": user_state.get("country"),
        "city": user_state.get("city"),
        "district": user_state.get("district", ""),
        "role": user_state.get("role", "пользователь"),
        "sport": user_state.get("sport"),
        "gender": user_state.get("gender"),
        "player_level": user_state.get("player_level"),
        "rating_points": player_levels.get(user_state.get("player_level"), {}).get("points", 0),
        "price": user_state.get("price"),
        "photo_path": user_state.get("photo_path"),
        "games_played": 0,
        "games_wins": 0,
        "default_payment": user_state.get("default_payment"),
        "show_in_search": True,
        "profile_comment": user_state.get("profile_comment"),
        "referrals_invited": 0,
        "games": [],
        "created_at": datetime.now().isoformat(timespec="seconds")
    }

    if user_state.get('vacation_tennis', False):
        profile["vacation_tennis"] = True
        profile["vacation_country"] = user_state.get('vacation_country')
        profile["vacation_city"] = user_state.get('vacation_city')
        profile["vacation_start"] = user_state.get('vacation_start')
        profile["vacation_end"] = user_state.get('vacation_end')
        profile["vacation_comment"] = user_state.get('vacation_comment')

    referral_id = user_state.get('referral_id')
    if referral_id and await storage.is_user_registered(referral_id):
        # Обновляем статистику реферера
        referrer_data = await storage.get_user(referral_id) or {}
        referrals_count = referrer_data.get('referrals_invited', 0) + 1
        
        await storage.update_user(referral_id, {
            'referrals_invited': referrals_count
        })
        
        # Проверяем, достиг ли реферер 10 приглашений
        if referrals_count >= 10:
            await storage.update_user(referral_id, {
                'active': True,
                'until': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'activated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
            # Уведомляем реферера
            try:
                await callback.message.bot.send_message(
                    referral_id,
                    "🎉 Поздравляем! Вы пригласили 10 друзей и получили бесплатную подписку на 1 месяц!"
                )
            except:
                pass

    await storage.save_user(user_id, profile)
    await state.clear()
    await storage.delete_session(user_id)

    # Отправляем уведомление о регистрации
    await send_registration_notification(callback.message, profile)
    
    # Показываем профиль пользователя
    await show_profile(callback.message, profile)
    await callback.answer()
