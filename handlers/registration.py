from datetime import datetime

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
from config.profile import moscow_districts, player_levels, base_keyboard

from models.states import RegistrationStates

from utils.utils import calculate_age
from utils.media import download_photo_to_path
from utils.bot import show_current_data, show_profile
from utils.ssesion import delete_session, load_session, save_session
from utils.validate import validate_date, validate_date_range, validate_future_date, validate_price
from utils.json_data import get_user_profile_from_storage, is_user_registered, load_json, load_users, save_user_to_json


router = Router()

# ---------- Первичные данные ----------
cities_data = load_json("cities.json")
sports = load_json("sports.json")
countries = list(cities_data.keys())

# ---------- Команды и логика ----------
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = str(message.chat.id)
    
    # Проверяем, есть ли параметр в команде start (для ссылок на профили)
    if len(message.text.split()) > 1:
        command_parts = message.text.split()
        if len(command_parts) >= 2:
            start_param = command_parts[1]
            
            # Если это ссылка на профиль (profile_12345)
            if start_param.startswith('profile_'):
                profile_user_id = start_param.replace('profile_', '')
                users = load_users()
                
                if profile_user_id in users:
                    profile_user = users[profile_user_id]
                    
                    await show_profile(message, profile_user)
                else:
                    await message.answer("Профиль не найден.")
                    
                return
    
    # Загружаем сессию если есть
    session_data = load_session(user_id)
    if session_data:
        await state.set_data(session_data)
    
    if is_user_registered(user_id):
        profile = get_user_profile_from_storage(user_id) or {}
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
            f"Вы зарегистрированы в официальном боте tennis-play.com\n"
            f"Выберите действие из меню ниже:"
        )  

        await message.answer(greet, parse_mode="HTML", reply_markup=base_keyboard)
        await state.clear()
        return

    # Если пользователь не зарегистрирован
    await state.set_state(RegistrationStates.PHONE)
    welcome_text = (
        f"👋 Здравствуйте, <b>{message.from_user.full_name}</b>!\n\n"
        "Вы находитесь в официальном боте tennis-play.com\n\n"
        "🎾 Здесь вы можете:\n"
        "• Найти партнёра для тренировок\n"
        "• Найти соперника для матчей\n"
        "• Вносить результаты игр\n"
        "• Отслеживать свой рейтинг\n\n"
        "Для начала пройдите краткую регистрацию. Пожалуйста, отправьте номер телефона:"
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
    save_session(user_id, await state.get_data())

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.chat.id
    if not is_user_registered(user_id):
        await message.answer("❌ Вы еще не зарегистрированы. Введите /start для регистрации.")
        return
    
    profile = get_user_profile_from_storage(user_id) or {}
    await show_profile(message, profile)

@router.message(Command("profile_id"))
async def cmd_profile_id(message: types.Message):
    try:
        user_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /profile_id USER_ID")
        return
    
    profile = get_user_profile_from_storage(user_id)
    if not profile:
        await message.answer("❌ Пользователь с таким ID не найден.")
        return
    
    await show_profile(message, profile)

@router.message(RegistrationStates.PHONE, F.contact)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await message.answer("📝 Введите ваше имя:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegistrationStates.FIRST_NAME)
    save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.FIRST_NAME, F.text)
async def process_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text.strip())
    await message.answer("📝 Введите вашу фамилию:")
    await state.set_state(RegistrationStates.LAST_NAME)
    save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.LAST_NAME, F.text)
async def process_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text.strip())
    await message.answer("📅 Введите вашу дату рождения в формате ДД.ММ.ГГГГ:")
    await state.set_state(RegistrationStates.BIRTH_DATE)
    save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.BIRTH_DATE, F.text)
async def process_birth_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not validate_date(date_str):
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return
    
    age = calculate_age(date_str)
    if age < 12:
        await message.answer("❌ Извините, но наш сервис доступен только для пользователей старше 12 лет.")
        await state.clear()
        return
    elif age > 100:
        await message.answer("❌ Пожалуйста, проверьте дату рождения. Введенный возраст слишком большой.")
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
    save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.COUNTRY, F.data.startswith("country_"))
async def process_country_selection(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(country=country)
    await ask_for_city(callback.message, state, country)
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.callback_query(RegistrationStates.COUNTRY, F.data == "other_country")
async def process_other_country(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌍 Введите название страны:", reply_markup=None)
    await state.set_state(RegistrationStates.COUNTRY_INPUT)
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.message(RegistrationStates.COUNTRY_INPUT, F.text)
async def process_country_input(message: Message, state: FSMContext):
    await state.update_data(country=message.text.strip())
    await message.answer("🏙 Введите название города:")
    await state.set_state(RegistrationStates.CITY_INPUT)
    save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.CITY_INPUT, F.text)
async def process_city_input(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await ask_for_role(message, state)
    save_session(message.chat.id, await state.get_data())

async def ask_for_city(message: types.Message, state: FSMContext, country: str):
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"city_{city}")] for city in main_russian_cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="other_city")])
    else:
        cities = cities_data.get(country, [])
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"city_{city}")] for city in cities[:5]]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="other_city")])

    await show_current_data(
        message, state,
        f"🏙 Выберите город в стране: {country}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.CITY)
    save_session(message.chat.id, await state.get_data())

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
    save_session(callback.from_user.id, await state.get_data())

@router.callback_query(RegistrationStates.CITY, F.data.startswith("district_"))
async def process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    district = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(city=district)
    await ask_for_role(callback.message, state)
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.callback_query(RegistrationStates.CITY, F.data == "other_city")
async def process_other_city(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🏙 Введите название города:", reply_markup=None)
    await state.set_state(RegistrationStates.CITY_INPUT)
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

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
    save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.ROLE, F.data.startswith("role_"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(role=role)

    if role == "Тренер":
        await callback.message.edit_text("💵 Введите стоимость тренировки (в рублях, только цифры):", reply_markup=None)
        await state.set_state(RegistrationStates.TRAINER_PRICE)
    else:
        # Создаем подробное описание всех уровней с Markdown
        levels_text = """*🏆 Система уровней теннисистов:*

*0\.0* \- Новичок без опыта
*0\.5* \- Делает первые шаги
*1\.0* \- Теннисист делает первые шаги
*1\.5* \- Игрок обладает небольшим опытом, совершенствует стабильность ударов
*2\.0* \- Заметны недостатки при выполнении основных ударов\. Укороченный замах
*2\.5* \- Пытается предвидеть направление полета мяча, но чувство корта слабое
*3\.0* \- Хорошо отбивает средние по темпу мячи, но не всегда контролирует силу
*3\.5* \- Может контролировать направление ударов средней сложности
*4\.0* \- Выполняет разнообразные удары, контролирует глубину и направление
*4\.5* \- Разнообразные удары, эффективно использует силу и вращение
*5\.0* \- Прекрасно чувствует мяч, выполняет особенные удары
*5\.5* \- Главное оружие \- мощные удары и стабильность
*6\.0* \- Высокая квалификация
*6\.5* \- Близок к профессиональному уровню
*7\.0* \- Спортсмен мирового класса

👇 *Выберите ваш уровень:*"""
        
        # Создаем кнопки в сетке 5×3
        buttons = []
        levels_list = list(player_levels.keys())
        
        # Разбиваем на строки по 5 кнопок
        for i in range(0, len(levels_list), 5):
            row = []
            for level in levels_list[i:i+5]:
                row.append(InlineKeyboardButton(
                    text=f"🎾 {level}",
                    callback_data=f"level_{level}"
                ))
            buttons.append(row)
        
        await callback.message.edit_text(
            levels_text,
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(RegistrationStates.PLAYER_LEVEL)

    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.message(RegistrationStates.TRAINER_PRICE, F.text)
async def process_trainer_price(message: types.Message, state: FSMContext):
    price_str = message.text.strip()
    if not validate_price(price_str):
        await message.answer("❌ Пожалуйста, введите корректную стоимость тренировки (только цифры, больше 0):")
        return
    
    await state.update_data(price=int(price_str))
    await ask_for_sport(message, state)
    save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.PLAYER_LEVEL, F.data.startswith("level_"))
async def process_player_level(callback: types.CallbackQuery, state: FSMContext):
    level = callback.data.split("_", maxsplit=1)[1]
    description = player_levels.get(level, {}).get('desc', '')
    await state.update_data(player_level=level)

    await callback.message.edit_text(
        f"🏆 Ваш уровень: {level}\n\n{description}",
        reply_markup=None
    )
    await ask_for_sport(callback.message, state)
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

async def ask_for_sport(message: types.Message, state: FSMContext):
    buttons = [[InlineKeyboardButton(text=sport, callback_data=f"sport_{sport}")] for sport in sports[:5]]
    await show_current_data(
        message, state,
        "🎾 Выберите вид спорта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.SPORT)
    save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.SPORT, F.data.startswith("sport_"))
async def process_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    sport = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(sport=sport)

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
    save_session(callback.from_user.id, await state.get_data())

@router.callback_query(RegistrationStates.GENDER, F.data.startswith("gender_"))
async def process_gender_selection(callback: types.CallbackQuery, state: FSMContext):
    gender = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(gender=gender)
    
    user_data = await state.get_data()
    if user_data.get('role') == "Тренер":
        # Для тренеров пропускаем фото и сразу завершаем регистрацию
        await state.update_data(photo="none", photo_path=None, show_in_search=True)
        await finish_registration(callback.message, state)
    else:
        # Для игроков продолжаем стандартный процесс
        buttons = [
            [InlineKeyboardButton(text="📷 Загрузить фото", callback_data="photo_upload")],
            [InlineKeyboardButton(text="👀 Без фото", callback_data="photo_none")],
            [InlineKeyboardButton(text="Фото из профиля", callback_data="photo_profile")]
        ]
        await show_current_data(
            callback.message, state,
            "📷 Фото профиля:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(RegistrationStates.PHOTO)
    
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.callback_query(RegistrationStates.PHOTO, F.data.startswith("photo_"))
async def process_photo_choice(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split("_", maxsplit=1)[1]

    if choice == "upload":
        await callback.message.edit_text("📷 Отправьте фотографию одним сообщением (из галереи или сделайте снимок):", reply_markup=None)
        return

    if choice == "profile":
        try:
            photos = await callback.message.bot.get_user_profile_photos(callback.from_user.id, limit=1)
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                ts = int(datetime.now().timestamp())
                filename = f"{callback.from_user.id}_{ts}.jpg"
                dest_path = PHOTOS_DIR / filename
                ok = await download_photo_to_path(callback.message.bot, file_id, dest_path)
                if ok:
                    rel_path = dest_path.relative_to(BASE_DIR).as_posix()
                    await state.update_data(photo="profile", photo_path=rel_path)
                    await ask_for_show_in_search(callback.message, state)
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
        await ask_for_show_in_search(callback.message, state)
    else:
        await state.update_data(photo="none", photo_path=None)
        await ask_for_show_in_search(callback.message, state)

    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

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
        await ask_for_show_in_search(message, state)
    else:
        await message.answer("❌ Не удалось сохранить фото. Попробуйте отправить ещё раз или выберите вариант без фото.")
    save_session(message.chat.id, await state.get_data())

async def ask_for_show_in_search(message: types.Message, state: FSMContext):
    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data="showsearch_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="showsearch_no")]
    ]
    await show_current_data(
        message, state,
        "🔍 Отображать ваш профиль в поиске партнёров?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.SHOW_IN_SEARCH)
    save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.SHOW_IN_SEARCH, F.data.startswith("showsearch_"))
async def process_show_in_search(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(show_in_search=(choice == "yes"))

    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data="vacation_yes")],
        [InlineKeyboardButton(text="⏩ Нет", callback_data="vacation_no")]
    ]
    await show_current_data(
        callback.message, state,
        "✈️ Хотите найти партнёра по теннису на время отдыха?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.VACATION_TENNIS)
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.callback_query(RegistrationStates.VACATION_TENNIS, F.data.startswith("vacation_"))
async def process_vacation_tennis(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split("_", maxsplit=1)[1]
    
    if choice == "yes":
        await callback.message.edit_text("✈️ Введите дату начала отдыха (ДД.ММ.ГГГГ):", reply_markup=None)
        await state.set_state(RegistrationStates.VACATION_START)
    else:
        await state.update_data(vacation_tennis=False)
        await ask_for_default_payment(callback.message, state)
    
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.message(RegistrationStates.VACATION_START, F.text)
async def process_vacation_start(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not validate_date(date_str):
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return
    
    if not validate_future_date(date_str):
        await message.answer("❌ Дата начала отдыха должна быть в будущем. Пожалуйста, введите корректную дату:")
        return
    
    await state.update_data(vacation_start=date_str, vacation_tennis=True)
    await message.answer("✈️ Введите дату завершения отдыха (ДД.ММ.ГГГГ):")
    await state.set_state(RegistrationStates.VACATION_END)
    save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_END, F.text)
async def process_vacation_end(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if not validate_date(date_str):
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
        return
    
    user_data = await state.get_data()
    start_date = user_data.get('vacation_start')
    
    if not validate_date_range(start_date, date_str):
        await message.answer("❌ Дата завершения должна быть позже даты начала. Пожалуйста, введите корректную дату:")
        return
    
    await state.update_data(vacation_end=date_str)
    await message.answer("💬 Добавьте комментарий к поездке (необязательно, или /skip для пропуска):")
    await state.set_state(RegistrationStates.VACATION_COMMENT)
    save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.VACATION_COMMENT, F.text)
async def process_vacation_comment(message: Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(vacation_comment=message.text.strip())
    await ask_for_default_payment(message, state)
    save_session(message.chat.id, await state.get_data())

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
    save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.DEFAULT_PAYMENT, F.data.startswith("defaultpay_"))
async def process_default_payment(callback: types.CallbackQuery, state: FSMContext):
    payment = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(default_payment=payment)
    
    user_data = await state.get_data()
    if user_data.get('role') == "Тренер":
        # Для тренеров сразу завершаем регистрацию
        await finish_registration(callback.message, state)
    else:
        # Для игроков продолжаем стандартный процесс
        await callback.message.edit_text("💬 Добавьте комментарий к анкете (или /skip для пропуска):", reply_markup=None)
        await state.set_state(RegistrationStates.PROFILE_COMMENT)
    
    await callback.answer()
    save_session(callback.from_user.id, await state.get_data())

@router.message(RegistrationStates.PROFILE_COMMENT, F.text)
async def process_profile_comment(message: types.Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(profile_comment=message.text.strip())

    await finish_registration(message, state)
    
    save_session(message.chat.id, await state.get_data())

async def finish_registration(message: types.Message, state: FSMContext):
    user_id = message.chat.id
    username = message.from_user.username

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
        "show_in_search": user_state.get("show_in_search", True),
        "profile_comment": user_state.get("profile_comment"),
        "games": [],  # Теперь это массив игр
        "created_at": datetime.now().isoformat(timespec="seconds")
    }

    if user_state.get('vacation_tennis', False):
        profile["vacation_tennis"] = True
        profile["vacation_start"] = user_state.get('vacation_start')
        profile["vacation_end"] = user_state.get('vacation_end')
        profile["vacation_comment"] = user_state.get('vacation_comment')

    save_user_to_json(user_id, profile)
    await state.clear()
    delete_session(user_id)

    await show_profile(message, profile)
