from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config.paths import BASE_DIR, PHOTOS_DIR
from config.profile import (
    moscow_districts, base_keyboard, cities_data, countries, sport_type,
    get_sport_config, get_sport_texts, get_base_keyboard, tennis_levels, table_tennis_levels,
    DATING_GOALS, DATING_INTERESTS, DATING_ADDITIONAL_FIELDS
)
from models.states import EditProfileStates
from utils.bot import show_profile
from utils.media import download_photo_to_path
from services.storage import storage
from handlers.registration import check_profile_completeness, get_missing_fields_text

async def migrate_profile_data(old_sport: str, new_sport: str, profile: dict) -> dict:
    """
    Мигрирует данные профиля при смене вида спорта
    Заполняет поля, которые нужны для нового вида спорта
    """
    old_config = get_sport_config(old_sport)
    new_config = get_sport_config(new_sport)
    
    # Создаем копию профиля
    new_profile = profile.copy()
    
    # Обновляем вид спорта
    new_profile["sport"] = new_sport
    
    # Заполняем поля, которые нужны для нового вида спорта, но отсутствуют
    if new_config.get("has_role", True) and not new_profile.get("role"):
        new_profile["role"] = "🎯 Игрок"  # По умолчанию игрок
    
    if new_config.get("has_level", True) and not new_profile.get("player_level"):
        # Для настольного тенниса используем рейтинг, для остальных - уровень
        if new_sport == "🏓Настольный теннис":
            new_profile["player_level"] = "0.0"  # По умолчанию
        else:
            new_profile["player_level"] = "1.0"  # По умолчанию
        new_profile["rating_points"] = 500  # Базовые очки
    
    if new_config.get("has_payment", True) and not new_profile.get("price"):
        new_profile["price"] = None  # По умолчанию пополам
        new_profile["default_payment"] = "💰 Пополам"
    
    if new_config.get("has_vacation", True):
        # Поля отпуска остаются как есть, если уже заполнены
        pass
    
    # Специальные поля для знакомств
    if new_sport == "🍒Знакомства":
        if not new_profile.get("dating_goal"):
            new_profile["dating_goal"] = "Общение"  # По умолчанию
        if not new_profile.get("dating_interests"):
            new_profile["dating_interests"] = []  # Пустой список
        if not new_profile.get("dating_additional"):
            new_profile["dating_additional"] = {}  # Пустой словарь
    
    # Специальные поля для встреч
    if new_sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        if not new_profile.get("meeting_time"):
            new_profile["meeting_time"] = "Уточню позже"  # По умолчанию
    
    return new_profile

router = Router()

# Добавляем обработчики для кнопок
@router.callback_query(F.data == "edit_profile")
async def edit_profile_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id)
    
    if not profile:
        await callback.answer("❌ Профиль не найден", reply_markup=base_keyboard)
        return
    
    # Создаем клавиатуру для редактирования в зависимости от вида спорта
    sport = profile.get("sport", "🎾Большой теннис")
    config = get_sport_config(sport)
    
    buttons = []
    
    # Базовые поля (всегда доступны)
    buttons.append([
        InlineKeyboardButton(text="📷 Фото", callback_data="1edit_photo"),
        InlineKeyboardButton(text="🌍 Страна/Город", callback_data="1edit_location")
    ])
    
    # Поля в зависимости от конфигурации
    if config.get("has_about_me", True):
        buttons.append([InlineKeyboardButton(text="💬 О себе", callback_data="1edit_comment")])
    
    if config.get("has_payment", True):
        buttons.append([InlineKeyboardButton(text="💳 Оплата", callback_data="1edit_payment")])
    
    if config.get("has_role", True):
        buttons.append([InlineKeyboardButton(text="👤 Роль", callback_data="1edit_role")])
    
    if config.get("has_level", True):
        buttons.append([InlineKeyboardButton(text="📊 Уровень", callback_data="1edit_level")])
    
    # Специальные поля для знакомств
    if sport == "🍒Знакомства":
        buttons.append([InlineKeyboardButton(text="💕 Цель знакомства", callback_data="1edit_dating_goal")])
        buttons.append([InlineKeyboardButton(text="🎯 Интересы", callback_data="1edit_dating_interests")])
        buttons.append([InlineKeyboardButton(text="📝 Дополнительно", callback_data="1edit_dating_additional")])
    
    # Специальные поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        buttons.append([InlineKeyboardButton(text="⏰ Время встречи", callback_data="1edit_meeting_time")])
    
    # Вид спорта (всегда доступен)
    buttons.append([InlineKeyboardButton(text="🎾 Вид спорта", callback_data="1edit_sport")])
    
    # Назад
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{user_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("back_to_profile:"))
async def back_to_profile_handler(callback: types.CallbackQuery):
    user_id = callback.data.split(":")[1]
    profile = await storage.get_user(user_id)
    
    try:
        await callback.message.delete()
    except:
        pass

    if profile:
        await show_profile(callback.message, profile)
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await callback.answer()

# Обработчик для удаления профиля
@router.callback_query(F.data == "1delete_profile")
async def delete_profile_handler(callback: types.CallbackQuery):
    # Создаем клавиатуру с подтверждением удаления
    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete"),
                InlineKeyboardButton(text="❌ Нет, отмена", callback_data="cancel_delete")
            ]
        ]
    )
    try:
        await callback.message.edit_text(
            "⚠️ Вы уверены, что хотите удалить свой профиль? Это действие нельзя отменить!",
            reply_markup=confirm_keyboard
        )
    except:
        try:
            await callback.message.delete()
        except:
            await callback.message.edit_text(
                "⚠️ Вы уверены, что хотите удалить свой профиль? Это действие нельзя отменить!",
                reply_markup=confirm_keyboard
            )
    
    await callback.answer()

@router.callback_query(F.data == "confirm_delete")
async def confirm_delete_handler(callback: types.CallbackQuery):
    user_id = callback.message.chat.id
    users = await storage.load_users()
    user_key = str(user_id)
    
    main_inline_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
    )
    
    if user_key in users:
        # Удаляем фото профиля, если оно есть
        if 'photo_path' in users[user_key] and users[user_key]['photo_path']:
            try:
                photo_path = BASE_DIR / users[user_key]['photo_path']
                if photo_path.exists():
                    photo_path.unlink()
            except:
                pass
        
        # Удаляем пользователя из хранилища
        del users[user_key]
        await storage.save_users(users)
        
        await callback.message.edit_text(
            "🗑️ Ваш профиль был успешно удален!",
            reply_markup=main_inline_keyboard
        )
    else:
        await callback.message.edit_text(
            "❌ Профиль не найден",
            reply_markup=main_inline_keyboard
        )
    
    await callback.answer()

@router.callback_query(F.data == "cancel_delete")
async def cancel_delete_handler(callback: types.CallbackQuery):
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id)
    
    if profile:
        # Возвращаемся к главной странице профиля
        await show_profile(callback.message, profile)
    else:
        await callback.message.edit_text(
            "❌ Профиль не найден",
            reply_markup=base_keyboard
        )
    
    await callback.answer()

# Обработчики для редактирования профиля
@router.callback_query(F.data.startswith("1edit_"))
async def edit_field_handler(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.replace("1edit_", "")
    
    try:
        await callback.message.delete()
    except:
        pass

    if field == "comment":
        await callback.message.answer("✏️ Введите новый комментарий о себе:")
        await state.set_state(EditProfileStates.COMMENT)
    elif field == "payment":
        buttons = [
            [InlineKeyboardButton(text="💰 Пополам", callback_data="edit_payment_Пополам")],
            [InlineKeyboardButton(text="💳 Я оплачиваю", callback_data="edit_payment_Я оплачиваю")],
            [InlineKeyboardButton(text="💵 Соперник оплачивает", callback_data="edit_payment_Соперник оплачиваю")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("✏️ Выберите тип оплата:", reply_markup=keyboard)
        await state.set_state(EditProfileStates.PAYMENT)
    elif field == "photo":
        buttons = [
            [InlineKeyboardButton(text="📷 Загрузить фото", callback_data="edit_photo_upload")],
            [InlineKeyboardButton(text="👀 Без фото", callback_data="edit_photo_none")],
            [InlineKeyboardButton(text="📸 Из профиля", callback_data="edit_photo_profile")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("✏️ Выберите вариант фото:", reply_markup=keyboard)
    elif field == "location":
        buttons = []
        for country in countries[:5]:
            buttons.append([InlineKeyboardButton(text=f"{country}", callback_data=f"edit_country_{country}")])
        buttons.append([InlineKeyboardButton(text="🌎 Другая страна", callback_data="edit_other_country")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🌍 Выберите страну:", reply_markup=keyboard)
        await state.set_state(EditProfileStates.COUNTRY)
    elif field == "sport":
        # Создаем клавиатуру для выбора вида спорта
        buttons = []
        row = []
        for i, sport in enumerate(sport_type):
            row.append(InlineKeyboardButton(text=sport, callback_data=f"edit_sport_{sport}"))
            if (i + 1) % 2 == 0 or i == len(sport_type) - 1:
                buttons.append(row)
                row = []
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🎾 Выберите вид спорта:", reply_markup=keyboard)
        await state.set_state(EditProfileStates.SPORT)
    elif field == "role":
        # Клавиатура для выбора роли
        buttons = [
            [InlineKeyboardButton(text="🎾 Игрок", callback_data="edit_role_Игрок")],
            [InlineKeyboardButton(text="👨‍🏫 Тренер", callback_data="edit_role_Тренер")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("👤 Выберите вашу роль:", reply_markup=keyboard)
        await state.set_state(EditProfileStates.ROLE)
    elif field == "price":
        if user_key not in users:
            await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
            await callback.answer()
            return

        role = users[user_key].get('role')
        if role != "Тренер":
            await callback.message.answer("❌ Стоимость доступна только для тренеров.")
            await callback.answer()
            return

        await callback.message.answer("💰 Введите стоимость тренировки (в рублях):")
        await state.set_state(EditProfileStates.PRICE)
    elif field == "level":
        # Проверяем, можно ли пользователю редактировать уровень
        users = await storage.load_users()
        user_key = str(callback.message.chat.id)
        
        if user_key in users:
            user_data = users[user_key]
            sport = user_data.get("sport", "🎾Большой теннис")
            config = get_sport_config(sport)
            
            # Просим пользователя ввести рейтинг
            if config.get("level_type") == "table_tennis":
                await callback.message.answer("🏓 Введите ваш рейтинг в настольном теннисе (например: 1500, 2000, 2500):")
            else:
                sport_name = sport.replace('🎾', '').replace('🏓', '').replace('🏸', '').replace('🏖️', '').replace('🥎', '').replace('🏆', '').strip()
                await callback.message.answer(f"📊 Введите ваш рейтинг в {sport_name} (например: 1000, 1500, 2000):")
            
            await state.set_state(EditProfileStates.LEVEL)
        else:
            await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    elif field == "dating_goal":
        # Клавиатура для выбора цели знакомства
        buttons = []
        for goal in DATING_GOALS:
            buttons.append([InlineKeyboardButton(text=goal, callback_data=f"edit_dating_goal_{goal}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("💕 Выберите вашу цель знакомства:", reply_markup=keyboard)
        await state.set_state(EditProfileStates.DATING_GOAL)
    elif field == "dating_interests":
        # Клавиатура для выбора интересов
        buttons = []
        for interest in DATING_INTERESTS:
            buttons.append([InlineKeyboardButton(text=interest, callback_data=f"edit_dating_interest_{interest}")])
        buttons.append([InlineKeyboardButton(text="✅ Завершить выбор", callback_data="edit_dating_interests_done")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🎯 Выберите ваши интересы (можно несколько):", reply_markup=keyboard)
        await state.set_state(EditProfileStates.DATING_INTERESTS)
    elif field == "dating_additional":
        await callback.message.answer("📝 Расскажите о себе дополнительно (работа, образование, рост и т.д.):")
        await state.set_state(EditProfileStates.DATING_ADDITIONAL)
    elif field == "meeting_time":
        await callback.message.answer("⏰ Напишите место, конкретный день и время или дни недели и временные промежутки, когда вам удобно встретиться:")
        await state.set_state(EditProfileStates.MEETING_TIME)
    
    await callback.answer()

# Обработчик для сохранения нового комментария о себе
@router.message(EditProfileStates.COMMENT, F.text)
async def save_comment_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    users = await storage.load_users()
    
    user_key = str(user_id)
    
    if user_key in users:
        # Сохраняем новый комментарий
        users[user_key]['profile_comment'] = message.text.strip()
        await storage.save_users(users)
        
        await message.answer("✅ Комментарий о себе обновлен!")
        await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

@router.callback_query(EditProfileStates.PAYMENT, F.data.startswith("edit_payment_"))
async def save_payment_edit(callback: types.CallbackQuery):
    payment = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['default_payment'] = payment
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Тип оплаты обновлен!")
        await show_profile(callback.message, users[user_key])
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await callback.answer()

# Обработчик для сохранения вида спорта
@router.callback_query(EditProfileStates.SPORT, F.data.startswith("edit_sport_"))
async def save_sport_edit(callback: types.CallbackQuery, state: FSMContext):
    new_sport = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        old_sport = users[user_key].get("sport", "🎾Большой теннис")
        
        # Если вид спорта не изменился, просто возвращаемся к профилю
        if old_sport == new_sport:
            await show_profile(callback.message, users[user_key])
            await state.clear()
            await callback.answer()
            return
        
        # Мигрируем данные профиля
        migrated_profile = await migrate_profile_data(old_sport, new_sport, users[user_key])
        
        # Сохраняем мигрированный профиль
        users[user_key] = migrated_profile
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Вид спорта обновлен!")
        await show_profile(callback.message, migrated_profile)
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()
    await callback.answer()

# Обработчик для сохранения роли
@router.callback_query(EditProfileStates.ROLE, F.data.startswith("edit_role_"))
async def save_role_edit(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['role'] = role
        
        # Если выбрана роль "Игрок" — удаляем стоимость
        if role == "Игрок":
            users[user_key].pop('price', None)
            await storage.save_users(users)
            
            try:
                await callback.message.delete()
            except:
                pass
            
            await callback.message.answer("✅ Роль обновлена! (Стоимость для игроков недоступна)")
            await show_profile(callback.message, users[user_key])
            await state.clear()
            await callback.answer()
            return
        
        # Если выбрана роль "Тренер" — сразу спрашиваем стоимость
        elif role == "Тренер":
            await storage.save_users(users)
            
            try:
                await callback.message.delete()
            except:
                pass
            
            await callback.message.answer("✅ Роль обновлена!\n\n💰 Теперь введите стоимость тренировки (в рублях):")
            await state.set_state(EditProfileStates.PRICE)
            await callback.answer()
            return
    
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()
    await callback.answer()

# Обработчик для сохранения стоимости тренировки
@router.message(EditProfileStates.PRICE, F.text)
async def save_price_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key in users:
        try:
            price = int(message.text.strip())
            if price < 0:
                await message.answer("❌ Стоимость не может быть отрицательной. Попробуйте еще раз:")
                return
            
            users[user_key]['price'] = price
            await storage.save_users(users)
            
            await message.answer("✅ Стоимость тренировки обновлена!")
            await show_profile(message, users[user_key])
        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректное число для стоимости:")
            return
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

# Обработчик для сохранения уровня

@router.message(EditProfileStates.LEVEL, F.text)
async def save_level_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key in users:
        sport = users[user_key].get("sport", "🎾Большой теннис")
        config = get_sport_config(sport)
        
        try:
            # Пытаемся преобразовать в число для всех видов спорта
            rating = int(message.text.strip())
            if rating < 0:
                await message.answer("❌ Рейтинг не может быть отрицательным. Попробуйте еще раз:")
                return
            
            # Сохраняем рейтинг
            users[user_key]['player_level'] = users[user_key].get('player_level', 1)
            users[user_key]['rating_points'] = rating
            users[user_key]['rating_edited'] = True
            await storage.save_users(users)
            
            await message.answer("✅ Рейтинг обновлен!")
            await show_profile(message, users[user_key])
            
        except ValueError:
            # Если не удалось преобразовать в число, сохраняем как текст
            users[user_key]['player_level'] = users[user_key].get('player_level', 1)
            users[user_key]['rating_points'] = 1000  # Базовый рейтинг для текстового рейтинга
            users[user_key]['rating_edited'] = True
            await storage.save_users(users)
            
            await message.answer("✅ Рейтинг обновлен!")
            await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

# Обработчики для редактирования местоположения
@router.callback_query(EditProfileStates.COUNTRY, F.data.startswith("edit_country_"))
async def process_country_selection(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", 2)[2]
    await state.update_data(country=country)
    
    # Получаем текущие данные пользователя
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    current_city = users[user_key].get('city', '') if user_key in users else ''
    
    await ask_for_city(callback.message, state, country, current_city)
    await callback.answer()

@router.callback_query(EditProfileStates.COUNTRY, F.data == "edit_other_country")
async def process_other_country(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌍 Введите название страны:", reply_markup=None)
    await state.set_state(EditProfileStates.COUNTRY_INPUT)
    await callback.answer()

@router.message(EditProfileStates.COUNTRY_INPUT, F.text)
async def process_country_input(message: types.Message, state: FSMContext):
    await state.update_data(country=message.text.strip())
    
    # Получаем текущие данные пользователя
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    current_city = users[user_key].get('city', '') if user_key in users else ''
    
    data = await state.get_data()
    country = data.get('country', '')
    await ask_for_city(message, state, country, current_city)

async def ask_for_city(message: types.Message, state: FSMContext, country: str, current_city: str = ''):
    data = await state.get_data()
    country = data.get('country', country)
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар", "Екатеринбург", "Казань"]
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"edit_city_{city}")] for city in main_russian_cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="edit_other_city")])
    else:
        cities = cities_data.get(country, [])
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"edit_city_{city}")] for city in cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="edit_other_city")])

    await message.edit_text(
        f"🏙 Выберите город в стране: {country}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(EditProfileStates.CITY)

@router.callback_query(EditProfileStates.CITY, F.data.startswith("edit_city_"))
async def process_city_selection(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_", 2)[2]
    
    if city == "Москва":
        buttons = [[InlineKeyboardButton(text=district, callback_data=f"edit_district_{district}")] for district in moscow_districts]
        await callback.message.edit_text(
            "🏙 Выберите округ Москвы:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await save_location(callback, city, state)
    
    await callback.answer()

@router.callback_query(EditProfileStates.CITY, F.data.startswith("edit_district_"))
async def process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    district = callback.data.split("_", 2)[2]
    await save_location(callback, district, state)
    await callback.answer()

@router.callback_query(EditProfileStates.CITY, F.data == "edit_other_city")
async def process_other_city(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🏙 Введите название города:", reply_markup=None)
    await state.set_state(EditProfileStates.CITY_INPUT)
    await callback.answer()

@router.message(EditProfileStates.CITY_INPUT, F.text)
async def process_city_input(message: types.Message, state: FSMContext):
    city = message.text.strip()
    await save_location_message(message, city, state)

async def save_location(callback: types.CallbackQuery, city: str, state: FSMContext):
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_key]['country'] = country
        users[user_key]['city'] = city
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Страна и город обновлены!")
        await show_profile(callback.message, users[user_key])
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

async def save_location_message(message: types.Message, city: str, state: FSMContext):
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    
    if user_key in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_key]['country'] = country
        users[user_key]['city'] = city
        await storage.save_users(users)
        
        await message.answer("✅ Страна и город обновлены!")
        await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

# Обработчики для редактирования фото
@router.callback_query(F.data.startswith("edit_photo_"))
async def edit_photo_handler(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key not in users:
        await callback.answer("❌ Профиль не найден", reply_markup=base_keyboard)
        return
    
    try:
        await callback.message.delete()
    except:
        pass

    if action == "upload":
        await callback.message.answer("📷 Отправьте новое фото профиля:")
        await state.set_state(EditProfileStates.PHOTO_UPLOAD)
    elif action == "none":
        users[user_key]['photo_path'] = None
        await storage.save_users(users)
        await callback.message.answer("✅ Фото профиля удалено!")
        await show_profile(callback.message, users[user_key])
    elif action == "profile":
        # Логика для установки фото из профиля Telegram
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
                    users[user_key]['photo_path'] = rel_path
                    await storage.save_users(users)
                    await callback.message.answer("✅ Фото из профиля установлено!")
                    await show_profile(callback.message, users[user_key])
                else:
                    await callback.message.answer("❌ Не удалось установить фото из профиля")
            else:
                await callback.message.answer("❌ В вашем профиле Telegram нет фото", reply_markup=base_keyboard)
        except Exception as e:
            await callback.message.answer("❌ Ошибка при получении фото из профиля", reply_markup=base_keyboard)
    
    await callback.answer()

# Обработчик для загрузки нового фото
@router.message(EditProfileStates.PHOTO_UPLOAD, F.photo)
async def save_photo_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key not in users:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
        await state.clear()
        return
    
    try:
        photo_id = message.photo[-1].file_id
        ts = int(datetime.now().timestamp())
        filename = f"{message.from_user.id}_{ts}.jpg"
        dest_path = PHOTOS_DIR / filename
        ok = await download_photo_to_path(message.bot, photo_id, dest_path)
        
        if ok:
            rel_path = dest_path.relative_to(BASE_DIR).as_posix()
            users[user_key]['photo_path'] = rel_path
            await storage.save_users(users)
            await message.answer("✅ Фото профиля обновлено!")
            await show_profile(message, users[user_key])
        else:
            await message.answer("❌ Не удалось сохранить фото", reply_markup=base_keyboard)
    except Exception as e:
        await message.answer("❌ Ошибка при сохранении фото", reply_markup=base_keyboard)
    
    await state.clear()

# Обработчики для редактирования полей знакомств
@router.callback_query(EditProfileStates.DATING_GOAL, F.data.startswith("edit_dating_goal_"))
async def process_dating_goal_edit(callback: types.CallbackQuery, state: FSMContext):
    goal = callback.data.split("_", 3)[3]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['dating_goal'] = goal
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Цель знакомства обновлена!")
        await show_profile(callback.message, users[user_key])
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await callback.answer()
    await state.clear()

@router.callback_query(EditProfileStates.DATING_INTERESTS, F.data.startswith("edit_dating_interest_"))
async def process_dating_interest_edit(callback: types.CallbackQuery, state: FSMContext):
    interest = callback.data.split("_", 3)[3]
    user_data = await state.get_data()
    interests = user_data.get('dating_interests', [])
    
    if interest in interests:
        interests.remove(interest)
    else:
        interests.append(interest)
    
    await state.update_data(dating_interests=interests)
    
    # Обновляем кнопки
    buttons = []
    for i in DATING_INTERESTS:
        if i in interests:
            buttons.append([InlineKeyboardButton(text=f"✅ {i}", callback_data=f"edit_dating_interest_{i}")])
        else:
            buttons.append([InlineKeyboardButton(text=i, callback_data=f"edit_dating_interest_{i}")])
    buttons.append([InlineKeyboardButton(text="✅ Завершить выбор", callback_data="edit_dating_interests_done")])
    
    await callback.message.edit_text(
        "🎯 Выберите ваши интересы (можно несколько):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@router.callback_query(EditProfileStates.DATING_INTERESTS, F.data == "edit_dating_interests_done")
async def process_dating_interests_done_edit(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    interests = user_data.get('dating_interests', [])
    
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['dating_interests'] = interests
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Интересы обновлены!")
        await show_profile(callback.message, users[user_key])
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await callback.answer()
    await state.clear()

@router.message(EditProfileStates.DATING_ADDITIONAL, F.text)
async def save_dating_additional_edit(message: types.Message, state: FSMContext):
    additional = message.text.strip()
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    
    if user_key in users:
        users[user_key]['dating_additional'] = additional
        await storage.save_users(users)
        
        await message.answer("✅ Дополнительная информация обновлена!")
        await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

@router.message(EditProfileStates.MEETING_TIME, F.text)
async def save_meeting_time_edit(message: types.Message, state: FSMContext):
    meeting_time = message.text.strip()
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    
    if user_key in users:
        users[user_key]['meeting_time'] = meeting_time
        await storage.save_users(users)
        
        await message.answer("✅ Время встречи обновлено!")
        await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    # Получаем профиль пользователя для определения вида спорта
    user_id = callback.message.chat.id
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    sport = user_data.get('sport', '🎾Большой теннис')
    
    # Получаем адаптивную клавиатуру
    keyboard = get_base_keyboard(sport)
    
    try:
        await callback.message.edit_text(
            "🏠 Главное меню",
            reply_markup=keyboard
        )
    except:
        await callback.message.delete()
        
        await callback.message.answer(
            "🏠 Главное меню",
            reply_markup=keyboard
        )
    await callback.answer()
