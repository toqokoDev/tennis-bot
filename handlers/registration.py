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
from config.profile import (
    create_sport_keyboard, moscow_districts, player_levels, tennis_levels, table_tennis_levels, 
    base_keyboard, cities_data, sport_type, countries, SPORT_FIELD_CONFIG,
    DATING_GOALS, DATING_INTERESTS, DATING_ADDITIONAL_FIELDS, get_sport_config, get_sport_texts, get_base_keyboard,
    channels_usernames
)

from models.states import RegistrationStates

from services.channels import send_registration_notification
from utils.admin import is_user_banned
from utils.media import download_photo_to_path
from utils.bot import show_current_data, show_profile
from utils.validate import validate_date, validate_date_range, validate_future_date, validate_price
from services.storage import storage
from services.web_api import web_api_client
from services.channels import send_tournament_application_to_channel
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

# ---------- Вспомогательные функции ----------

def get_levels_for_sport(sport: str) -> dict:
    """Получает уровни для выбранного вида спорта"""
    config = get_sport_config(sport)
    level_type = config.get("level_type", "tennis")
    
    if level_type == "table_tennis":
        return table_tennis_levels
    elif level_type == "table_tennis_rating":
        return {}  # Для ввода рейтинга не нужны предустановленные уровни
    else:
        return tennis_levels

def check_profile_completeness(profile: dict, sport: str) -> tuple[bool, list]:
    """
    Проверяет заполненность обязательных полей профиля для выбранного вида спорта
    Возвращает (is_complete, missing_fields)
    """
    config = get_sport_config(sport)
    missing_fields = []
    
    # Базовые поля (всегда обязательные)
    required_basic = ["first_name", "last_name", "birth_date", "country", "city", "gender"]
    for field in required_basic:
        if not profile.get(field):
            missing_fields.append(field)
    
    # Поля в зависимости от конфигурации вида спорта
    if config.get("has_role", True) and not profile.get("role"):
        missing_fields.append("role")
    
    if config.get("has_level", True) and not profile.get("player_level"):
        missing_fields.append("player_level")
    
    if config.get("has_about_me", True) and not profile.get("profile_comment"):
        missing_fields.append("profile_comment")
    
    # Специальные поля для знакомств
    if sport == "🍒Знакомства":
        if not profile.get("dating_goal"):
            missing_fields.append("dating_goal")
        if not profile.get("dating_interests"):
            missing_fields.append("dating_interests")
    
    # Специальные поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        if not profile.get("meeting_time"):
            missing_fields.append("meeting_time")
    
    return len(missing_fields) == 0, missing_fields

def get_missing_fields_text(missing_fields: list, sport: str) -> str:
    """Возвращает текст с описанием недостающих полей"""
    field_names = {
        "first_name": "Имя",
        "last_name": "Фамилия", 
        "birth_date": "Дата рождения",
        "country": "Страна",
        "city": "Город",
        "gender": "Пол",
        "role": "Роль",
        "player_level": "Уровень игры",
        "profile_comment": "О себе",
        "dating_goal": "Цель знакомства",
        "dating_interests": "Интересы",
        "meeting_time": "Время встречи"
    }
    
    missing_text = []
    for field in missing_fields:
        missing_text.append(f"• {field_names.get(field, field)}")
    
    return "\n".join(missing_text)

async def show_registration_success(message: types.Message, profile: dict):
    """Показывает сообщение об успешной регистрации с кнопками"""
    sport = profile.get("sport", "🎾Большой теннис")
    config = get_sport_config(sport)
    texts = get_sport_texts(sport)
    channel_username = channels_usernames.get(sport, "")
    
    # Формируем сообщение
    success_text = f"✅ <b>Регистрация завершена!</b>\n\n"
    success_text += f"Добро пожаловать в сообщество {sport}!\n\n"
    
    if channel_username:
        success_text += f"📢 <b>Подписывайтесь на наш канал с новостями:</b>\n"
        success_text += f"@{channel_username}\n\n"
    
    success_text += "Выберите действие:"
    
    # Создаем кнопки
    buttons = []
    
    # Кнопка "Предложить игру"
    buttons.append([InlineKeyboardButton(
        text=texts.get("offer_button", "🎾 Предложить игру"), 
        callback_data="new_offer"
    )])
    
    # Кнопка "Создать тур" (только для видов спорта с has_vacation=True)
    if config.get("has_vacation", False):
        buttons.append([InlineKeyboardButton(
            text="✈️ Создать тур", 
            callback_data="create_tour"
        )])
    
    # Кнопка "Главное меню"
    buttons.append([InlineKeyboardButton(
        text="🏠 Главное меню", 
        callback_data="main_menu"
    )])
    
    try:
        await message.edit_text(
            success_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            success_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

async def handle_auto_registration(message: types.Message, state: FSMContext, start_param: str):
    user_id = str(message.chat.id)
    
    try:
        # Проверяем, не зарегистрирован ли уже пользователь
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

            # Получаем адаптивную клавиатуру для вида спорта пользователя
            sport = profile.get('sport', '🎾Большой теннис')
            keyboard = get_base_keyboard(sport)

            await message.answer(greet, parse_mode="HTML", reply_markup=keyboard)
            return
        
        # Парсим start_param: формат web_domain_userid
        # Например: web_com_123 или web_by_456
        parts = start_param.replace('web_', '', 1).split('_', 1)
        domain = parts[0] if len(parts) > 1 else 'com'
        web_user_id = parts[1] if len(parts) > 1 else parts[0]
        
        await message.answer(
            "⏳ Получаю ваши данные с сайта...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        web_user_data = await web_api_client.get_user_data(web_user_id, domain)
        
        if not web_user_data:
            await message.answer(
                "❌ Не удалось получить данные с сайта.\n\n"
                f"ID пользователя: {web_user_id}\n\n"
                "Возможные причины:\n"
                "• Пользователь не найден на сайте\n"
                "• Ошибка подключения к API\n"
                "• Неверные настройки API\n\n"
                "Пожалуйста, пройдите обычную регистрацию.\n"
                "<b>Для начала отправьте ваш номер телефона:</b>",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
            await state.set_state(RegistrationStates.PHONE)
            await storage.save_session(message.chat.id, await state.get_data())
            return
        
        params = web_api_client.convert_web_user_to_params(web_user_data)

        if params.get("country", "") == "Белоруссия":
            params["country"] = "Беларусь"
        
        # Скачиваем фото профиля если есть
        photo_path = None
        photo_url_large = web_user_data.get('photo_url_large', '')
        
        if photo_url_large and photo_url_large.strip():
            try:
                # Формируем имя файла и путь
                ts = int(datetime.now().timestamp())
                filename = f"{user_id}_{ts}.jpg"
                dest_path = PHOTOS_DIR / filename
                
                # Скачиваем фото
                if await web_api_client.download_photo(photo_url_large, str(dest_path)):
                    # Сохраняем относительный путь
                    photo_path = dest_path.relative_to(BASE_DIR).as_posix()
            except Exception as e:
                # Если ошибка скачивания - просто логируем и продолжаем без фото
                pass

        profile = {
            "telegram_id": int(user_id),
            "username": message.chat.username,
            "first_name": params.get("fname", ""),
            "last_name": params.get("lname", ""),
            "phone": params.get("phone", ""),
            "birth_date": params.get("bdate", ""),
            "country": next((c for c in countries if params.get("country", "") != "" and params.get("country", "").lower() in c.lower()), params.get("country", "")),
            "city": params["city"],
            "district": params.get("district", "").replace('Москва - ', ''),
            "role": params.get("role", "Игрок"),
            "sport": next((s for s in sport_type if params.get("sport", "") != "" and params.get("sport", "").lower() in s.lower()), sport_type[0]),
            "gender": params.get("gender", "Мужской"),
            "player_level": params.get("level", ""),
            "rating_points": table_tennis_levels[params.get("level", "")].get("points", 0),
            "price": params.get("price", None),
            "photo_path": photo_path,
            "games_played": 0,
            "games_wins": 0,
            "default_payment": params.get("payment", "Пополам"),
            "show_in_search": True,
            "profile_comment": params.get("comment", ""),
            "referrals_invited": 0,
            "games": [],
            "created_at": datetime.now().isoformat(timespec="seconds")
        }
        
        await storage.save_user(user_id, profile)
        
        await send_registration_notification(message, profile)
        
        await show_registration_success(message, profile)
        
    except Exception as e:
        # Если произошла любая ошибка, переключаем на обычную регистрацию
        await message.answer(
            "Пожалуйста, пройдите регистрацию.\n\n"
            "<b>Для начала отправьте ваш номер телефона:</b>",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        await state.set_state(RegistrationStates.PHONE)
        await storage.save_session(message.chat.id, await state.get_data())

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
            
            # Обработка автоматической регистрации через Web API
            if start_param.startswith('web_'):
                await handle_auto_registration(message, state, start_param)
                return
            
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
            elif start_param.startswith('join_tournament_'):
                # Обработка deep-link для участия в турнире из канала
                tournament_id = start_param.replace('join_tournament_', '')
                # Если пользователь еще не зарегистрирован — попросим зарегистрироваться
                if not await storage.is_user_registered(user_id):
                    await message.answer(
                        "❌ Сначала пройдите регистрацию, затем повторите ссылку для участия.")
                    # Продолжим обычный start- flow регистрации ниже
                else:
                    # Регистрируем в турнире (если есть место и не записан)
                    tournaments = await storage.load_tournaments()
                    t = tournaments.get(tournament_id)
                    if not t:
                        await message.answer("❌ Турнир не найден")
                        return
                    participants = t.get('participants', {}) or {}
                    # Проверка мест
                    max_participants = int(t.get('participants_count', 0) or 0)
                    if max_participants and len(participants) >= max_participants:
                        await message.answer("❌ В этом турнире больше нет мест")
                        return
                    if str(user_id) in participants:
                        # Уже участвует — покажем кнопку перехода
                        kb = InlineKeyboardBuilder()
                        kb.button(text="🏆 Открыть турнир", callback_data=f"view_tournament:{tournament_id}")
                        kb.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
                        kb.adjust(1)
                        await message.answer(
                            f"✅ Вы уже участвуете в турнире: {t.get('name', 'Турнир')}",
                            reply_markup=kb.as_markup()
                        )
                        return
                    # Добавляем участника
                    users_all = await storage.load_users()
                    u = users_all.get(str(user_id), {})
                    participants[str(user_id)] = {
                        'name': f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(),
                        'phone': u.get('phone', 'Не указан'),
                        'added_at': datetime.now().isoformat(),
                        'added_by': int(user_id)
                    }
                    t['participants'] = participants
                    tournaments[tournament_id] = t
                    await storage.save_tournaments(tournaments)
                    # Уведомление в канал
                    try:
                        await send_tournament_application_to_channel(message.bot, tournament_id, t, str(user_id), u)
                    except Exception:
                        pass
                    # Ответ пользователю с кнопками
                    kb = InlineKeyboardBuilder()
                    kb.button(text="🏆 Открыть турнир", callback_data=f"view_tournament:{tournament_id}")
                    kb.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
                    kb.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
                    kb.adjust(1)
                    await message.answer(
                        "✅ Вы добавлены в турнир!",
                        reply_markup=kb.as_markup()
                    )
                return
            elif start_param.startswith('view_tournament_'):
                # Обработка deep-link для просмотра турнира из канала
                tournament_id = start_param.replace('view_tournament_', '')
                # Импортируем функцию для показа краткой информации о турнире
                from handlers.tournament import show_tournament_brief_info
                await show_tournament_brief_info(message, tournament_id, user_id)
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

        # Получаем адаптивную клавиатуру для вида спорта пользователя
        sport = profile.get('sport', '🎾Большой теннис')
        keyboard = get_base_keyboard(sport)
        await message.answer(greet, parse_mode="HTML", reply_markup=keyboard)
        await state.clear()
        return

    # Если пользователь не зарегистрирован
    await state.set_state(RegistrationStates.PHONE)
    welcome_text = (
        f"👋 Здравствуйте, <b>{message.from_user.full_name}</b>!\n\n"
        "Вы находитесь в боте @tennis_playbot проекта Tennis-Play.com\n"
        "Для начала пройдите краткую регистрацию.\n\n"
        "Начивая регистрацию, Вы соглашаетесь с <a href='https://tennis-play.com/privacy-bot'>политикой обработки персональных данных</a> "
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

    await message.answer(
        "✅ Номер телефона получен!",
        reply_markup=ReplyKeyboardRemove()
    )

    await show_current_data(
        message, state,
        "🎾 Выберите вид спорта:",
        reply_markup=create_sport_keyboard(pref="sport_")
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
        "🌍 Выберите Вашу страну:",
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
    cities = cities_data.get(country, [])
    buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"city_{city}")] for city in cities]
    buttons.append([InlineKeyboardButton(text="Другой город", callback_data="other_city")])

    await show_current_data(
        message, state,
        f"🏙 Выберите Ваш город в стране: {country}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.CITY)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.CITY, F.data.startswith("city_"))
async def process_city_selection(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", maxsplit=1)[1]

    if city == "Москва":
        buttons = []
        row = []
        for i, district in enumerate(moscow_districts):
            row.append(InlineKeyboardButton(text=district, callback_data=f"district_{district}"))
            if (i + 1) % 3 == 0 or i == len(moscow_districts) - 1:
                buttons.append(row)
                row = []
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
    await state.update_data(city="Москва")
    await state.update_data(district=district.strip())
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
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    if not config.get("has_role", True):
        # Если роль не нужна, переходим к следующему шагу
        await ask_for_gender(message, state)
        return
    
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
        # Переходим к следующему шагу в зависимости от вида спорта
        await ask_for_level_or_gender(callback.message, state)

    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

async def ask_for_gender(message: types.Message, state: FSMContext):
    """Спрашивает пол пользователя"""
    buttons = [
        [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_Мужской")],
        [InlineKeyboardButton(text="👩 Женский", callback_data="gender_Женский")]
    ]
    await show_current_data(
        message, state,
        "👫 Укажите пол:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.GENDER)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_level_or_gender(message: types.Message, state: FSMContext):
    """Определяет следующий шаг после выбора роли"""
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    if config.get("has_level", True):
        # Показываем уровни
        await show_levels_page(message, state, page=0)
    else:
        # Переходим к полу
        await ask_for_gender(message, state)

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
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    levels_dict = get_levels_for_sport(sport)
    
    # Для настольного тенниса показываем специальный интерфейс
    if config.get("level_type") in ["table_tennis", "table_tennis_rating"]:
        await ask_for_table_tennis_rating(message, state)
        return
    
    levels_list = list(levels_dict.keys())
    items_per_page = 3
    total_pages = (len(levels_list) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(levels_list))
    current_levels = levels_list[start_idx:end_idx]
    
    # Формируем текст с описанием текущих уровней
    sport_name = sport.replace("🎾", "").replace("🏓", "").replace("🏸", "").replace("🏖️", "").replace("🥎", "").replace("🏆", "")
    levels_text = f"🏆 *Система уровней {sport_name.lower()}:*\n\n"
    
    for level in current_levels:
        description = levels_dict[level]["desc"]
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

async def ask_for_table_tennis_rating(message: types.Message, state: FSMContext):
    """Спрашивает рейтинг для настольного тенниса"""
    await message.edit_text(
        "🏓 Укажите ваш рейтинг в настольном теннису (цифры):",
        reply_markup=None
    )
    await state.set_state(RegistrationStates.TABLE_TENNIS_RATING)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.PLAYER_LEVEL, F.data.startswith("levelpage_"))
async def process_level_page_navigation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка навигации по страницам уровней"""
    page = int(callback.data.split("_", maxsplit=1)[1])
    await show_levels_page(callback.message, state, page)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.TABLE_TENNIS_RATING, F.text)
async def process_table_tennis_rating(message: types.Message, state: FSMContext):
    """Обрабатывает ввод рейтинга для настольного тенниса"""
    rating = message.text.strip()
    await state.update_data(player_level=rating)
    await ask_for_gender(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.PLAYER_LEVEL, F.data.startswith("level_"))
async def process_player_level(callback: types.CallbackQuery, state: FSMContext):
    level = callback.data.split("_", maxsplit=1)[1]
    user_data = await state.get_data()
    sport = user_data.get("sport")
    levels_dict = get_levels_for_sport(sport)

    await state.update_data(player_level=level)
    
    await ask_for_gender(callback.message, state)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.GENDER, F.data.startswith("gender_"))
async def process_gender_selection(callback: types.CallbackQuery, state: FSMContext):
    gender = callback.data.split("_", maxsplit=1)[1]
    await state.update_data(gender=gender)
    
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    # Определяем следующий шаг в зависимости от вида спорта
    if sport == "🍒Знакомства":
        await ask_for_dating_goals(callback.message, state)
    elif config.get("has_about_me", True):
        await ask_for_profile_comment(callback.message, state)
    elif config.get("has_meeting_time", False):
        await ask_for_meeting_time(callback.message, state)
    else:
        await ask_for_photo(callback.message, state)
    
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

async def ask_for_profile_comment(message: types.Message, state: FSMContext):
    """Спрашивает комментарий к профилю"""
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    # Используем about_me_text если есть, иначе comment_text
    about_me_text = config.get("about_me_text")
    comment_text = config.get("comment_text", "• Комментарий:")
    
    if about_me_text:
        await message.edit_text(f"{about_me_text} (или /skip для пропуска):", reply_markup=None)
    else:
        await message.edit_text(f"{comment_text} (или /skip для пропуска):", reply_markup=None)
    
    await state.set_state(RegistrationStates.PROFILE_COMMENT)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_dating_goals(message: types.Message, state: FSMContext):
    """Спрашивает цели знакомств"""
    buttons = []
    for goal in DATING_GOALS:
        buttons.append([InlineKeyboardButton(text=goal, callback_data=f"dating_goal_{goal}")])
    
    await message.edit_text(
        "💕 Цель знакомства:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.DATING_GOAL)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_photo(message: types.Message, state: FSMContext):
    """Спрашивает фото профиля"""
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

@router.message(RegistrationStates.PROFILE_COMMENT, F.text)
async def process_profile_comment(message: types.Message, state: FSMContext):
    if message.text.strip() != "/skip":
        await state.update_data(profile_comment=message.text.strip())
    
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    # Определяем следующий шаг в зависимости от вида спорта
    if config.get("has_meeting_time", False):
        await ask_for_meeting_time(message, state)
    else:
        await ask_for_photo(message, state)
    
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.DATING_GOAL, F.data.startswith("dating_goal_"))
async def process_dating_goal(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор цели знакомств"""
    goal = callback.data.split("_", maxsplit=2)[2]
    await state.update_data(dating_goal=goal)
    
    if goal == "Свой вариант":
        await callback.message.edit_text("💕 Опишите вашу цель знакомства:", reply_markup=None)
        await state.set_state(RegistrationStates.DATING_GOAL)
        return
    
    await ask_for_dating_interests(callback.message, state)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.DATING_GOAL, F.text)
async def process_dating_goal_text(message: types.Message, state: FSMContext):
    """Обрабатывает текстовый ввод цели знакомств"""
    await state.update_data(dating_goal=message.text.strip())
    await ask_for_dating_interests(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_dating_interests(message: types.Message, state: FSMContext):
    """Спрашивает интересы для знакомств"""
    buttons = []
    for interest in DATING_INTERESTS:
        buttons.append([InlineKeyboardButton(text=interest, callback_data=f"dating_interest_{interest}")])
    
    await message.edit_text(
        "🎯 Ваши интересы (можно выбрать несколько):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(RegistrationStates.DATING_INTERESTS)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.DATING_INTERESTS, F.data.startswith("dating_interest_"))
async def process_dating_interest(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор интересов"""
    interest = callback.data.split("_", maxsplit=2)[2]
    user_data = await state.get_data()
    selected_interests = user_data.get("dating_interests", [])
    
    if interest == "Свой вариант в дополнение":
        await callback.message.edit_text("🎯 Опишите ваши дополнительные интересы:", reply_markup=None)
        await state.set_state(RegistrationStates.DATING_INTERESTS)
        return
    
    if interest in selected_interests:
        selected_interests.remove(interest)
    else:
        selected_interests.append(interest)
    
    await state.update_data(dating_interests=selected_interests)
    
    # Показываем обновленный список
    interests_text = "🎯 Выбранные интересы:\n" + "\n".join([f"• {i}" for i in selected_interests])
    interests_text += "\n\nВыберите еще или нажмите 'Готово' для продолжения:"
    
    buttons = []
    for interest in DATING_INTERESTS:
        text = f"{'✅' if interest in selected_interests else '⬜'} {interest}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"dating_interest_{interest}")])
    buttons.append([InlineKeyboardButton(text="Готово", callback_data="dating_interests_done")])
    
    await callback.message.edit_text(
        interests_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

@router.message(RegistrationStates.DATING_INTERESTS, F.text)
async def process_dating_interest_text(message: types.Message, state: FSMContext):
    """Обрабатывает текстовый ввод интересов"""
    user_data = await state.get_data()
    selected_interests = user_data.get("dating_interests", [])
    selected_interests.append(f"Свой вариант: {message.text.strip()}")
    await state.update_data(dating_interests=selected_interests)
    await ask_for_dating_interests(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

@router.callback_query(RegistrationStates.DATING_INTERESTS, F.data == "dating_interests_done")
async def process_dating_interests_done(callback: types.CallbackQuery, state: FSMContext):
    """Завершает выбор интересов"""
    await ask_for_dating_additional(callback.message, state)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

async def ask_for_dating_additional(message: types.Message, state: FSMContext):
    """Спрашивает дополнительные поля для знакомств"""
    additional_text = "📝 Дополнительная информация (необязательно, можно пропустить):\n\n"
    for field in DATING_ADDITIONAL_FIELDS:
        additional_text += f"• {field}\n"
    additional_text += "\nНапишите информацию по любому из полей или /skip для пропуска:"
    
    await message.edit_text(additional_text, reply_markup=None)
    await state.set_state(RegistrationStates.DATING_ADDITIONAL)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.DATING_ADDITIONAL, F.text)
async def process_dating_additional(message: types.Message, state: FSMContext):
    """Обрабатывает дополнительные поля знакомств"""
    if message.text.strip() != "/skip":
        await state.update_data(dating_additional=message.text.strip())
    
    await ask_for_photo(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_meeting_time(message: types.Message, state: FSMContext):
    """Спрашивает время встречи для бизнес-завтрака и по пиву"""
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    meeting_text = config.get("meeting_time_text", "Напишите место, конкретный день и время или дни недели и временные промежутки, когда вам удобно встретиться.")
    try:
        await message.edit_text(meeting_text)
    except:
        await message.answer(meeting_text)

    await state.set_state(RegistrationStates.MEETING_TIME)
    await storage.save_session(message.chat.id, await state.get_data())

@router.message(RegistrationStates.MEETING_TIME, F.text)
async def process_meeting_time(message: types.Message, state: FSMContext):
    """Обрабатывает время встречи"""
    await state.update_data(meeting_time=message.text.strip())
    await ask_for_photo(message, state)
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
                    await ask_for_next_step_after_photo(callback.message, state)
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
        await ask_for_next_step_after_photo(callback.message, state)
    else:
        await state.update_data(photo="none", photo_path=None)
        await ask_for_next_step_after_photo(callback.message, state)

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
        await ask_for_next_step_after_photo(message, state)
    else:
        await message.answer("❌ Не удалось сохранить фото. Попробуйте отправить ещё раз или выберите вариант без фото.")
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_next_step_after_photo(message: types.Message, state: FSMContext):
    """Определяет следующий шаг после выбора фото"""
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    if config.get("has_payment", True) and sport not in ["☕️Бизнес-завтрак", "🍻По пиву", "🍒Знакомства"]:
        await ask_for_default_payment(message, state)
    else:
        # Завершаем регистрацию для видов спорта без оплаты
        await complete_registration_without_profile(message, state)

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
        await complete_registration_without_profile(callback.message, state)
    
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
    cities = cities_data.get(country, [])
    buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"vacation_city_{city}")] for city in cities]
    buttons.append([InlineKeyboardButton(text="Другой город", callback_data="vacation_o ther_city")])

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
    
    # Автоматически устанавливаем vacation_tennis=True
    await state.update_data(vacation_tennis=True)
    
    # Завершаем регистрацию
    await complete_registration_without_profile(message, state)
    await storage.save_session(message.chat.id, await state.get_data())

async def ask_for_default_payment(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    sport = user_data.get("sport")
    config = get_sport_config(sport)
    
    if not config.get("has_payment", True):
        await complete_registration_without_profile(message, state)
        return
    
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
    
    # Завершаем регистрацию
    await complete_registration_without_profile(callback.message, state)
    await callback.answer()
    await storage.save_session(callback.message.chat.id, await state.get_data())

async def complete_registration_without_profile(message: types.Message, state: FSMContext):
    """Завершает регистрацию без показа анкеты, сначала спрашивает про тур, потом про игру"""
    user_id = message.chat.id
    username = message.chat.username
    
    user_state = await state.get_data()
    profile = await create_user_profile(user_id, username, user_state)
    
    # Обработка реферала
    referral_id = user_state.get('referral_id')
    if referral_id and await storage.is_user_registered(referral_id):
        # Обновляем статистику реферера
        referrer_data = await storage.get_user(referral_id) or {}
        referrals_count = referrer_data.get('referrals_invited', 0) + 1
        
        await storage.update_user(referral_id, {
            'referrals_invited': referrals_count
        })
        
        # Проверяем, достиг ли реферер 5 приглашений
        if referrals_count >= 5:
            # Дарим подписку на 1 месяц
            await storage.update_user(referral_id, {
                'active': True,
                'until': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'activated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
            # Уведомляем реферера
            try:
                await message.bot.send_message(
                    referral_id,
                    "🎉 Поздравляем! Вы пригласили 5 друзей и получили бесплатную подписку на 1 месяц!"
                )
            except:
                pass
    
    # Сохраняем пользователя
    await storage.save_user(user_id, profile)
    await state.clear()
    await storage.delete_session(user_id)
    
    # Отправляем уведомление о регистрации
    await send_registration_notification(message, profile)
    
    # Показываем сообщение об успешной регистрации
    await show_registration_success(message, profile)

async def create_user_profile(user_id: int, username: str, user_state: dict) -> dict:
    """Создает профиль пользователя с учетом вида спорта"""
    # Определяем рейтинговые очки в зависимости от вида спорта
    sport = user_state.get("sport")
    levels_dict = get_levels_for_sport(sport)
    player_level = user_state.get("player_level")
    
    # Для настольного тенниса рейтинг может быть текстовым или числовым
    if sport == "🏓Настольный теннис":
        if player_level and player_level.replace(".", "").isdigit():
            # Если введен числовой рейтинг, используем его как очки
            try:
                rating_points = int(float(player_level))
            except ValueError:
                rating_points = 1000
        else:
            rating_points = 1000  # Базовый рейтинг для текстового рейтинга
    else:
        rating_points = levels_dict.get(player_level, {}).get("points", 0)
    
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
        "role": user_state.get("role", "Игрок"),
        "sport": user_state.get("sport"),
        "gender": user_state.get("gender"),
        "player_level": user_state.get("player_level"),
        "rating_points": rating_points,
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
    
    # Добавляем поля для знакомств
    if sport == "🍒Знакомства":
        profile["dating_goal"] = user_state.get("dating_goal")
        profile["dating_interests"] = user_state.get("dating_interests", [])
        profile["dating_additional"] = user_state.get("dating_additional")
    
    # Добавляем поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        profile["meeting_time"] = user_state.get("meeting_time")
    
    # Поля для тура будут добавлены позже, после регистрации
    return profile

# ---------- Обработчики кнопок после регистрации ----------

@router.callback_query(F.data == "create_tour")
async def process_create_tour_after_registration(callback: types.CallbackQuery):
    """Обрабатывает нажатие кнопки 'Создать тур' после регистрации"""
    # Здесь можно добавить логику создания тура
    await callback.message.answer(
        "✈️ Функция создания тура будет доступна в главном меню.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]])
    )
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def process_main_menu_after_registration(callback: types.CallbackQuery):
    """Обрабатывает нажатие кнопки 'Главное меню' после регистрации"""
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id) or {}
    sport = profile.get('sport', '🎾Большой теннис')
    keyboard = get_base_keyboard(sport)
    
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=keyboard
    )
    await callback.answer()

