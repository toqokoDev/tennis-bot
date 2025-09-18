from calendar import c
from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config.paths import BASE_DIR, PHOTOS_DIR
from config.profile import create_sport_keyboard, moscow_districts, cities_data, countries, sport_type
from models.states import AdminEditProfileStates, RegistrationStates
from services.storage import storage
from utils.admin import is_admin
from utils.bot import show_profile
from utils.media import download_photo_to_path

admin_edit_router = Router()

# Обработчик для выбора пользователя для редактирования
@admin_edit_router.callback_query(F.data.startswith("admin_edit_profile:"))
async def admin_edit_profile_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    user_id = callback.data.split(":")[1]
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Пользователь не найден")
        return
    
    await state.update_data(admin_edit_user_id=user_id)
    
    profile = users[user_id]
    sport = profile.get("sport", "🎾Большой теннис")
    
    # Создаем клавиатуру для редактирования в зависимости от вида спорта
    from config.profile import get_sport_config
    config = get_sport_config(sport)
    
    buttons = []
    
    # Базовые поля (всегда доступны)
    buttons.append([
        InlineKeyboardButton(text="📷 Фото", callback_data="adminUserProfile_edit_photo"),
        InlineKeyboardButton(text="🌍 Страна/Город", callback_data="adminUserProfile_edit_location")
    ])
    
    # Поля в зависимости от конфигурации
    if config.get("has_about_me", True):
        buttons.append([InlineKeyboardButton(text="💬 О себе", callback_data="adminUserProfile_edit_comment")])
    
    if config.get("has_payment", True):
        buttons.append([InlineKeyboardButton(text="💳 Оплата", callback_data="adminUserProfile_edit_payment")])
    
    if config.get("has_role", True):
        buttons.append([InlineKeyboardButton(text="🎭 Роль", callback_data="adminUserProfile_edit_role")])
    
    if config.get("has_level", True):
        buttons.append([InlineKeyboardButton(text="📊 Уровень", callback_data="adminUserProfile_edit_level")])
    
    # Специальные поля для знакомств
    if sport == "🍒Знакомства":
        buttons.append([InlineKeyboardButton(text="💕 Цель знакомства", callback_data="adminUserProfile_edit_dating_goal")])
        buttons.append([InlineKeyboardButton(text="🎯 Интересы", callback_data="adminUserProfile_edit_dating_interests")])
        buttons.append([InlineKeyboardButton(text="📝 Дополнительно", callback_data="adminUserProfile_edit_dating_additional")])
    
    # Специальные поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        buttons.append([InlineKeyboardButton(text="⏰ Время встречи", callback_data="adminUserProfile_edit_meeting_time")])
    
    # Вид спорта (всегда доступен)
    buttons.append([InlineKeyboardButton(text="🎾 Вид спорта", callback_data="adminUserProfile_edit_sport")])
    
    # Стоимость (для тренеров)
    if profile.get('role') == 'Тренер':
        buttons.append([InlineKeyboardButton(text="💰 Стоимость", callback_data="adminUserProfile_edit_price")])
    
    # Назад
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_edit_profile")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.edit_text(
            f"👤 Редактирование профиля:\n"
            f"Имя: {profile.get('first_name', '')} {profile.get('last_name', '')}\n"
            f"ID: {user_id}\n\n"
            "Выберите поле для редактирования:",
            reply_markup=keyboard
        )
    except:
        try:
            await callback.message.delete()
        except:
            pass

        await callback.message.answer(
            f"👤 Редактирование профиля:\n"
            f"Имя: {profile.get('first_name', '')} {profile.get('last_name', '')}\n"
            f"ID: {user_id}\n\n"
            "Выберите поле для редактирования:",
            reply_markup=keyboard
        )
    await callback.answer()

# Обработчики для редактирования профиля
@admin_edit_router.callback_query(F.data.startswith("adminUserProfile_edit_"))
async def admin_edit_field_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    field = callback.data.split("_", 2)[2]
    
    try:
        await callback.message.delete()
    except:
        pass

    if field == "comment":
        await callback.message.answer("✏️ Введите новый комментарий о себе:")
        await state.set_state(AdminEditProfileStates.COMMENT)
    elif field == "payment":
        buttons = [
            [InlineKeyboardButton(text="💰 Пополам", callback_data="adminProfile_edit_payment_Пополам")],
            [InlineKeyboardButton(text="💳 Я оплачиваю", callback_data="adminProfile_edit_payment_Я оплачиваю")],
            [InlineKeyboardButton(text="💵 Соперник оплачивает", callback_data="adminProfile_edit_payment_Соперник оплачиваю")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("✏️ Выберите тип оплата:", reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.PAYMENT)
    elif field == "photo":
        buttons = [
            [InlineKeyboardButton(text="📷 Загрузить фото", callback_data="adminProfile_edit_photo_upload")],
            [InlineKeyboardButton(text="👀 Без фото", callback_data="adminProfile_edit_photo_none")],
            [InlineKeyboardButton(text="📸 Из профиля", callback_data="adminProfile_edit_photo_profile")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("✏️ Выберите вариант фото:", reply_markup=keyboard)
    elif field == "location":
        buttons = []
        for country in countries[:5]:
            buttons.append([InlineKeyboardButton(text=f"{country}", callback_data=f"adminProfile_edit_country_{country}")])
        buttons.append([InlineKeyboardButton(text="🌎 Другая страна", callback_data="adminProfile_edit_other_country")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🌍 Выберите страну:", reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.COUNTRY)
    elif field == "sport":
        # Создаем клавиатуру для выбора вида спорта
        await callback.message.answer("🎾 Выберите вид спорта:", reply_markup=create_sport_keyboard(pref="adminProfile_edit_sport_"))
        await state.set_state(AdminEditProfileStates.SPORT)
    elif field == "role":
        buttons = [
            [InlineKeyboardButton(text="🎯 Игрок", callback_data="adminProfile_edit_role_Игрок")],
            [InlineKeyboardButton(text="👨‍🏫 Тренер", callback_data="adminProfile_edit_role_Тренер")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🎭 Выберите роль:", reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.ROLE)
    elif field == "price":
        # Запрос стоимости тренировки
        data = await state.get_data()
        user_id = data.get('admin_edit_user_id')
        
        if not user_id:
            await callback.message.answer("❌ Пользователь не выбран")
            return
        
        users = await storage.load_users()
        if user_id in users:
            current_price = users[user_id].get('price', 'Не указана')
            await callback.message.answer(f"💰 Текущая стоимость: {current_price} руб.\nВведите новую стоимость тренировки (в рублях):")
            await state.set_state(AdminEditProfileStates.TRAINER_PRICE)
        else:
            await callback.message.answer("❌ Профиль не найден")
    elif field == "level":
        # Запрос уровня
        data = await state.get_data()
        user_id = data.get('admin_edit_user_id')
        
        if not user_id:
            await callback.message.answer("❌ Пользователь не выбран")
            return
        
        users = await storage.load_users()
        if user_id in users:
            current_level = users[user_id].get('level', 'Не указан')
            level_edited = users[user_id].get('level_edited', False)
            
            if level_edited:
                await callback.message.answer(f"📊 Текущий уровень: {current_level}\n⚠️ Пользователь уже редактировал уровень вручную.\nВведите новый уровень (количество очков):")
            else:
                await callback.message.answer(f"📊 Текущий уровень: {current_level}\nВведите новый уровень (количество очков):")
            
            await state.set_state(AdminEditProfileStates.LEVEL)
        else:
            await callback.message.answer("❌ Профиль не найден")
    elif field == "dating_goal":
        # Клавиатура для выбора цели знакомства
        from config.profile import DATING_GOALS
        buttons = []
        for i, goal in enumerate(DATING_GOALS):
            buttons.append([InlineKeyboardButton(text=goal, callback_data=f"adgoal_{i}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("💕 Выберите цель знакомства:", reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.DATING_GOAL)
    elif field == "dating_interests":
        # Клавиатура для выбора интересов
        from config.profile import DATING_INTERESTS
        buttons = []
        for i, interest in enumerate(DATING_INTERESTS):
            buttons.append([InlineKeyboardButton(text=interest, callback_data=f"adint_{i}")])
        buttons.append([InlineKeyboardButton(text="✅ Завершить выбор", callback_data="adint_done")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🎯 Выберите интересы (можно несколько):", reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.DATING_INTERESTS)
    elif field == "dating_additional":
        await callback.message.answer("📝 Расскажите о себе дополнительно (работа, образование, рост и т.д.):")
        await state.set_state(AdminEditProfileStates.DATING_ADDITIONAL)
    elif field == "meeting_time":
        await callback.message.answer("⏰ Напишите место, конкретный день и время или дни недели и временные промежутки, когда удобно встретиться:")
        await state.set_state(AdminEditProfileStates.MEETING_TIME)
    
    await callback.answer()

# Обработчик для сохранения нового комментария о себе
@admin_edit_router.message(AdminEditProfileStates.COMMENT, F.text)
async def admin_save_comment_edit(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Н�т прав администратора")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['profile_comment'] = message.text.strip()
        await storage.save_users(users)
        
        await message.answer("✅ Комментарий о себе обновлен!")
        await show_profile(message, users[user_id])
    else:
        await message.answer("❌ Профиль не найден")
    
    await state.clear()

@admin_edit_router.callback_query(AdminEditProfileStates.PAYMENT, F.data.startswith("adminProfile_edit_payment_"))
async def admin_save_payment_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    payment = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['default_payment'] = payment
        await storage.save_users(users)

        await callback.message.edit_text("✅ Тип оплаты обновлен!")
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer("❌ Профиль не найден")
    
    await callback.answer()
    await state.clear()

# Обработчик для сохранения вида спорта
@admin_edit_router.callback_query(AdminEditProfileStates.SPORT, F.data.startswith("adminProfile_edit_sport_"))
async def admin_save_sport_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    sport = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['sport'] = sport
        await storage.save_users(users)
        
        await callback.message.edit_text("✅ Вид спорта обновлен!")
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer("❌ Профиль не найден")
    
    await callback.answer()
    await state.clear()

# Обработчик для сохранения роли
@admin_edit_router.callback_query(AdminEditProfileStates.ROLE, F.data.startswith("adminProfile_edit_role_"))
async def admin_save_role_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    role = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        if role == "Тренер" and users[user_id].get('role') != "Тренер":
            # Если меняем на тренера, запрашиваем цену
            await state.update_data(role=role)
            await callback.message.edit_text("💵 Введите стоимость тренировки (в рублях, только цифры):")
            await state.set_state(AdminEditProfileStates.TRAINER_PRICE)
        else:
            # Если меняем на игрока или роль не меняется
            users[user_id]['role'] = role
            if role == "Игрок":
                users[user_id]['price'] = None  # Сбрасываем цену для игроков
            
            await storage.save_users(users)
            await callback.message.edit_text("✅ Роль обновлена!")
            await show_profile(callback.message, users[user_id])
            await state.clear()
    else:
        await callback.message.answer("❌ Профиль не найден")
        await state.clear()
    
    await callback.answer()

# Обработчик для ввода цены тренера
@admin_edit_router.message(AdminEditProfileStates.TRAINER_PRICE, F.text)
async def admin_save_trainer_price(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    role = data.get('role')
    
    if not user_id or not role:
        await message.answer("❌ Данные не найдены")
        await state.clear()
        return
    
    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену (положительное число):")
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['role'] = role
        users[user_id]['price'] = price
        await storage.save_users(users)
        
        await message.answer("✅ Роль и цена тренировки обновлены!")
        await show_profile(message, users[user_id])
    else:
        await message.answer("❌ Профиль не найден")
    
    await state.clear()

# Обработчик для сохранения уровня
@admin_edit_router.message(AdminEditProfileStates.LEVEL, F.text)
async def admin_save_level_edit(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    try:
        level = int(message.text.strip())
        if level < 0:
            await message.answer("❌ Уровень не может быть отрицательным. Попробуйте еще раз:")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число для уровня:")
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['level'] = level
        users[user_id]['level_edited'] = True  # Помечаем, что уровень был отредактирован
        await storage.save_users(users)
        
        await message.answer("✅ Уровень обновлен!")
        await show_profile(message, users[user_id])
    else:
        await message.answer("❌ Профиль не найден")
    
    await state.clear()

# Обработчики для редактирования местоположения
@admin_edit_router.callback_query(AdminEditProfileStates.COUNTRY, F.data.startswith("adminProfile_edit_country_"))
async def admin_process_country_selection(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    country = callback.data.split("_", 3)[3]
    await state.update_data(country=country)
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    current_city = users[user_id].get('city', '') if user_id in users else ''
    
    await admin_ask_for_city(callback.message, state, country, current_city)
    await callback.answer()

@admin_edit_router.callback_query(AdminEditProfileStates.COUNTRY, F.data == "adminProfile_edit_other_country")
async def admin_process_other_country(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    await callback.message.edit_text("🌍 Введите название страны:", reply_markup=None)
    await state.set_state(AdminEditProfileStates.COUNTRY_INPUT)
    await callback.answer()

@admin_edit_router.message(AdminEditProfileStates.COUNTRY_INPUT, F.text)
async def admin_process_country_input(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    await state.update_data(country=message.text.strip())
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    current_city = users[user_id].get('city', '') if user_id in users else ''
    
    data = await state.get_data()
    country = data.get('country', '')
    await admin_ask_for_city(message, state, country, current_city)

async def admin_ask_for_city(message: types.Message, state: FSMContext, country: str, current_city: str = ''):
    data = await state.get_data()
    country = data.get('country', country)
    
    cities = cities_data.get(country, [])
    buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"adminProfile_edit_city_{city}")] for city in cities]
    buttons.append([InlineKeyboardButton(text="Другой город", callback_data="adminProfile_edit_other_city")])

    try:
        await message.edit_text(
            f"🏙 Выберите город в стране: {country}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            f"🏙 Выберите город в стране: {country}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await state.set_state(AdminEditProfileStates.CITY)

@admin_edit_router.callback_query(AdminEditProfileStates.CITY, F.data.startswith("adminProfile_edit_city_"))
async def admin_process_city_selection(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    city = callback.data.split("_", 3)[3]
    await state.update_data(city=city)
    
    if city == "Москва":
        buttons = []
        row = []
        for i, district in enumerate(moscow_districts):
            row.append(InlineKeyboardButton(text=district, callback_data=f"adminProfile_edit_district_{district}"))
            if (i + 1) % 3 == 0 or i == len(moscow_districts) - 1:
                buttons.append(row)
                row = []
        await callback.message.edit_text(
            "🏙 Выберите округ Москвы:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await admin_save_location(callback, city, state)
    
    await callback.answer()

@admin_edit_router.callback_query(AdminEditProfileStates.CITY, F.data.startswith("adminProfile_edit_district_"))
async def admin_process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    data = await state.get_data()
    city = data.get('city', '')
    
    district = callback.data.split("_", 3)[3]
    await admin_save_location(callback, city, state, district)
    await callback.answer()

@admin_edit_router.callback_query(AdminEditProfileStates.CITY, F.data == "adminProfile_edit_other_city")
async def admin_process_other_city(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    await callback.message.edit_text("🏙 Введите название города:", reply_markup=None)
    await state.set_state(AdminEditProfileStates.CITY_INPUT)
    await callback.answer()

@admin_edit_router.message(AdminEditProfileStates.CITY_INPUT, F.text)
async def admin_process_city_input(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    city = message.text.strip()
    await admin_save_location_message(message, city, state)

async def admin_save_location(callback: types.CallbackQuery, city: str, state: FSMContext, district: str = ''):
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_id]['country'] = country
        users[user_id]['city'] = city
        users[user_id]['district'] = district
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Страна и город обновлены!")
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer("❌ Профиль не найден")
    
    await state.clear()

async def admin_save_location_message(message: types.Message, city: str, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_id]['country'] = country
        users[user_id]['city'] = city
        await storage.save_users(users)
        
        await message.answer("✅ Страна и город обновлены!")
        await show_profile(message, users[user_id])
    else:
        await message.answer("❌ Профиль не найден")
    
    await state.clear()

# Обработчики для редактирования фото
@admin_edit_router.callback_query(F.data.startswith("adminProfile_edit_photo_"))
async def admin_edit_photo_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    action = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer("❌ Профиль не найден")
        return
    
    try:
        await callback.message.delete()
    except:
        pass

    if action == "upload":
        await callback.message.answer("📷 Отправьте новое фото профиля:")
        await state.set_state(AdminEditProfileStates.PHOTO_UPLOAD)
    elif action == "none":
        users[user_id]['photo_path'] = None
        await storage.save_users(users)
        await callback.message.answer("✅ Фото профиля удалено!")
        await show_profile(callback.message, users[user_id])
    elif action == "profile":
        try:
            photos = await callback.message.bot.get_user_profile_photos(int(user_id), limit=1)
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                ts = int(datetime.now().timestamp())
                filename = f"{user_id}_{ts}.jpg"
                dest_path = PHOTOS_DIR / filename
                ok = await download_photo_to_path(callback.message.bot, file_id, dest_path)
                if ok:
                    rel_path = dest_path.relative_to(BASE_DIR).as_posix()
                    users[user_id]['photo_path'] = rel_path
                    await storage.save_users(users)
                    await callback.message.answer("✅ Фото из профиля установлено!")
                    await show_profile(callback.message, users[user_id])
                else:
                    await callback.message.answer("❌ Не удалось установить фото из профиля")
            else:
                await callback.message.answer("❌ В профиле пользователя нет фото")
        except Exception as e:
            await callback.message.answer("❌ Ошибка при получении фото из профиля")
    
    await callback.answer()

# Обработчик для загрузки нового фото
@admin_edit_router.message(AdminEditProfileStates.PHOTO_UPLOAD, F.photo)
async def admin_save_photo_upload(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        await message.answer("❌ Профиль не найден")
        await state.clear()
        return
    
    try:
        photo_id = message.photo[-1].file_id
        ts = int(datetime.now().timestamp())
        filename = f"{user_id}_{ts}.jpg"
        dest_path = PHOTOS_DIR / filename
        ok = await download_photo_to_path(message.bot, photo_id, dest_path)
        
        if ok:
            rel_path = dest_path.relative_to(BASE_DIR).as_posix()
            users[user_id]['photo_path'] = rel_path
            await storage.save_users(users)
            await message.answer("✅ Фото профиля обновлено!")
            await show_profile(message, users[user_id])
        else:
            await message.answer("❌ Не удалось сохранить фото")
    except Exception as e:
        await message.answer("❌ Ошибка при сохранении фото")
    
    await state.clear()

# Обработчики для редактирования полей знакомств (админ)
@admin_edit_router.callback_query(AdminEditProfileStates.DATING_GOAL, F.data.startswith("adgoal_"))
async def admin_process_dating_goal_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    goal_index = int(callback.data.split("_")[1])
    from config.profile import DATING_GOALS
    goal = DATING_GOALS[goal_index]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer("❌ Пользователь не выбран")
        await callback.answer()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['dating_goal'] = goal
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Цель знакомства обновлена!")
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer("❌ Профиль не найден")
    
    await callback.answer()
    await state.clear()

@admin_edit_router.callback_query(AdminEditProfileStates.DATING_INTERESTS, F.data.startswith("adint_"))
async def admin_process_dating_interest_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    if callback.data == "adint_done":
        # Завершение выбора интересов
        user_data = await state.get_data()
        interests = user_data.get('dating_interests', [])
        user_id = user_data.get('admin_edit_user_id')
        
        if not user_id:
            await callback.message.answer("❌ Пользователь не выбран")
            await callback.answer()
            return
        
        users = await storage.load_users()
        
        if user_id in users:
            users[user_id]['dating_interests'] = interests
            await storage.save_users(users)
            
            try:
                await callback.message.delete()
            except:
                pass
            
            await callback.message.answer("✅ Интересы обновлены!")
            await show_profile(callback.message, users[user_id])
        else:
            await callback.message.answer("❌ Профиль не найден")
        
        await callback.answer()
        await state.clear()
        return
    
    # Обработка выбора интереса
    interest_index = int(callback.data.split("_")[1])
    from config.profile import DATING_INTERESTS
    interest = DATING_INTERESTS[interest_index]
    user_data = await state.get_data()
    interests = user_data.get('dating_interests', [])
    
    if interest in interests:
        interests.remove(interest)
    else:
        interests.append(interest)
    
    await state.update_data(dating_interests=interests)
    
    # Обновляем кнопки
    buttons = []
    for i, interest_text in enumerate(DATING_INTERESTS):
        if interest_text in interests:
            buttons.append([InlineKeyboardButton(text=f"✅ {interest_text}", callback_data=f"adint_{i}")])
        else:
            buttons.append([InlineKeyboardButton(text=interest_text, callback_data=f"adint_{i}")])
    buttons.append([InlineKeyboardButton(text="✅ Завершить выбор", callback_data="adint_done")])
    
    await callback.message.edit_text(
        "🎯 Выберите интересы (можно несколько):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@admin_edit_router.message(AdminEditProfileStates.DATING_ADDITIONAL, F.text)
async def admin_save_dating_additional_edit(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    additional = message.text.strip()
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['dating_additional'] = additional
        await storage.save_users(users)
        
        await message.answer("✅ Дополнительная информация обновлена!")
        await show_profile(message, users[user_id])
    else:
        await message.answer("❌ Профиль не найден")
    
    await state.clear()

@admin_edit_router.message(AdminEditProfileStates.MEETING_TIME, F.text)
async def admin_save_meeting_time_edit(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав администратора")
        await state.clear()
        return
    
    meeting_time = message.text.strip()
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer("❌ Пользователь не выбран")
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['meeting_time'] = meeting_time
        await storage.save_users(users)
        
        await message.answer("✅ Время встречи обновлено!")
        await show_profile(message, users[user_id])
    else:
        await message.answer("❌ Профиль не найден")
    
    await state.clear()

# Обработчик отмены
@admin_edit_router.callback_query(F.data == "admin_cancel")
async def admin_cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await callback.answer()
