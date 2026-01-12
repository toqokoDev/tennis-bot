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
from utils.utils import remove_country_flag
from handlers.profile import calculate_level_from_points
from utils.translations import get_user_language_async, t

admin_edit_router = Router()

# Обработчик для выбора пользователя для редактирования
@admin_edit_router.callback_query(F.data.startswith("admin_edit_profile:"))
async def admin_edit_profile_handler(callback: types.CallbackQuery, state: FSMContext):
    language = await get_user_language_async(str(callback.message.chat.id))
    if not await is_admin(callback.message.chat.id):
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    user_id = callback.data.split(":")[1]
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer(t("admin_edit.user_not_found", language))
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
        InlineKeyboardButton(text=t("admin_edit.buttons.photo", language), callback_data="adminUserProfile_edit_photo"),
        InlineKeyboardButton(text=t("admin_edit.buttons.location", language), callback_data="adminUserProfile_edit_location")
    ])
    
    # Поля в зависимости от конфигурации
    if config.get("has_about_me", True):
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.about_me", language), callback_data="adminUserProfile_edit_comment")])
    
    if config.get("has_payment", True):
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.payment", language), callback_data="adminUserProfile_edit_payment")])
    
    if config.get("has_role", True):
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.role", language), callback_data="adminUserProfile_edit_role")])
    
    if config.get("has_level", True):
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.level", language), callback_data="adminUserProfile_edit_level")])
    
    # Специальные поля для знакомств
    if sport == "🍒Знакомства":
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.dating_goal", language), callback_data="adminUserProfile_edit_dating_goal")])
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.dating_interests", language), callback_data="adminUserProfile_edit_dating_interests")])
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.dating_additional", language), callback_data="adminUserProfile_edit_dating_additional")])
    
    # Специальные поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.meeting_time", language), callback_data="adminUserProfile_edit_meeting_time")])
    
    # Вид спорта (всегда доступен)
    buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.sport", language), callback_data="adminUserProfile_edit_sport")])
    
    # Стоимость (для тренеров)
    if profile.get('role') == 'Тренер':
        buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.price", language), callback_data="adminUserProfile_edit_price")])
    
    # Назад
    buttons.append([InlineKeyboardButton(text=t("admin_edit.buttons.back", language), callback_data="admin_edit_profile")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.edit_text(
            t("admin_edit.edit_profile_title", language,
              first_name=profile.get('first_name', ''),
              last_name=profile.get('last_name', ''),
              user_id=user_id),
            reply_markup=keyboard
        )
    except:
        try:
            await callback.message.delete()
        except:
            pass

        await callback.message.answer(
            t("admin_edit.edit_profile_title", language,
              first_name=profile.get('first_name', ''),
              last_name=profile.get('last_name', ''),
              user_id=user_id),
            reply_markup=keyboard
        )
    await callback.answer()

# Обработчики для редактирования профиля
@admin_edit_router.callback_query(F.data.startswith("adminUserProfile_edit_"))
async def admin_edit_field_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    field = callback.data.split("_", 2)[2]
    
    try:
        await callback.message.delete()
    except:
        pass

    language = await get_user_language_async(str(callback.message.chat.id))
    
    if field == "comment":
        await callback.message.answer(t("admin_edit.enter_comment", language))
        await state.set_state(AdminEditProfileStates.COMMENT)
    elif field == "payment":
        from config.profile import get_payment_types
        payment_types = get_payment_types(language)
        buttons = []
        for payment in payment_types:
            buttons.append([InlineKeyboardButton(text=payment, callback_data=f"adminProfile_edit_payment_{payment}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("admin_edit.select_payment", language), reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.PAYMENT)
    elif field == "photo":
        buttons = [
            [InlineKeyboardButton(text=t("profile_edit.buttons.upload_photo", language), callback_data="adminProfile_edit_photo_upload")],
            [InlineKeyboardButton(text=t("profile_edit.buttons.no_photo", language), callback_data="adminProfile_edit_photo_none")],
            [InlineKeyboardButton(text=t("profile_edit.buttons.from_profile", language), callback_data="adminProfile_edit_photo_profile")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("admin_edit.select_photo", language), reply_markup=keyboard)
    elif field == "location":
        buttons = []
        for country in countries[:5]:
            buttons.append([InlineKeyboardButton(text=f"{country}", callback_data=f"adminProfile_edit_country_{country}")])
        buttons.append([InlineKeyboardButton(text=t("admin_edit.other_country", language), callback_data="adminProfile_edit_other_country")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("admin_edit.select_country", language), reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.COUNTRY)
    elif field == "sport":
        # Создаем клавиатуру для выбора вида спорта
        await callback.message.answer(t("admin_edit.select_sport", language), reply_markup=create_sport_keyboard(pref="adminProfile_edit_sport_", language=language))
        await state.set_state(AdminEditProfileStates.SPORT)
    elif field == "role":
        from config.profile import get_roles
        roles = get_roles(language)
        buttons = []
        for role in roles:
            buttons.append([InlineKeyboardButton(text=role, callback_data=f"adminProfile_edit_role_{role}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("admin_edit.select_role", language), reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.ROLE)
    elif field == "price":
        # Запрос стоимости тренировки
        data = await state.get_data()
        user_id = data.get('admin_edit_user_id')
        
        if not user_id:
            await callback.message.answer(t("admin_edit.user_not_selected", language))
            return
        
        users = await storage.load_users()
        if user_id in users:
            current_price = users[user_id].get('price', t("common.not_specified", language))
            await callback.message.answer(t("admin_edit.enter_price", language, price=current_price))
            await state.set_state(AdminEditProfileStates.TRAINER_PRICE)
        else:
            await callback.message.answer(t("admin_edit.profile_not_found", language))
    elif field == "level":
        # Запрос уровня
        data = await state.get_data()
        user_id = data.get('admin_edit_user_id')
        
        if not user_id:
            await callback.message.answer(t("admin_edit.user_not_selected", language))
            return
        
        users = await storage.load_users()
        if user_id in users:
            current_level = users[user_id].get('level', t("common.not_specified", language))
            level_edited = users[user_id].get('level_edited', False)
            
            if level_edited:
                await callback.message.answer(t("admin_edit.enter_level_edited", language, level=current_level))
            else:
                await callback.message.answer(t("admin_edit.enter_level", language, level=current_level))
            
            await state.set_state(AdminEditProfileStates.LEVEL)
        else:
            await callback.message.answer(t("admin_edit.profile_not_found", language))
    elif field == "dating_goal":
        # Клавиатура для выбора цели знакомства
        from config.profile import get_dating_goals
        goals = get_dating_goals(language)
        buttons = []
        for i, goal in enumerate(goals):
            buttons.append([InlineKeyboardButton(text=goal, callback_data=f"adgoal_{i}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("admin_edit.select_dating_goal", language), reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.DATING_GOAL)
    elif field == "dating_interests":
        # Клавиатура для выбора интересов
        from config.profile import get_dating_interests
        interests = get_dating_interests(language)
        buttons = []
        for i, interest in enumerate(interests):
            buttons.append([InlineKeyboardButton(text=interest, callback_data=f"adint_{i}")])
        buttons.append([InlineKeyboardButton(text=t("admin_edit.finish_interests", language), callback_data="adint_done")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("admin_edit.select_dating_interests", language), reply_markup=keyboard)
        await state.set_state(AdminEditProfileStates.DATING_INTERESTS)
    elif field == "dating_additional":
        await callback.message.answer(t("admin_edit.enter_dating_additional", language))
        await state.set_state(AdminEditProfileStates.DATING_ADDITIONAL)
    elif field == "meeting_time":
        await callback.message.answer(t("admin_edit.enter_meeting_time", language))
        await state.set_state(AdminEditProfileStates.MEETING_TIME)
    
    await callback.answer()

# Обработчик для сохранения нового комментария о себе
@admin_edit_router.message(AdminEditProfileStates.COMMENT, F.text)
async def admin_save_comment_edit(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['profile_comment'] = message.text.strip()
        await storage.save_users(users)
        
        await message.answer(t("admin_edit.comment_updated", language))
        await show_profile(message, users[user_id])
    else:
        await message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

@admin_edit_router.callback_query(AdminEditProfileStates.PAYMENT, F.data.startswith("adminProfile_edit_payment_"))
async def admin_save_payment_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    payment = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not user_id:
        await callback.message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['default_payment'] = payment
        await storage.save_users(users)

        await callback.message.edit_text(t("admin_edit.payment_updated", language))
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer(t("admin_edit.profile_not_found", language))
    
    await callback.answer()
    await state.clear()

# Обработчик для сохранения вида спорта
@admin_edit_router.callback_query(AdminEditProfileStates.SPORT, F.data.startswith("adminProfile_edit_sport_"))
async def admin_save_sport_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    sport = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not user_id:
        await callback.message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['sport'] = sport
        await storage.save_users(users)
        
        await callback.message.edit_text(t("admin_edit.sport_updated", language))
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer(t("admin_edit.profile_not_found", language))
    
    await callback.answer()
    await state.clear()

# Обработчик для сохранения роли
@admin_edit_router.callback_query(AdminEditProfileStates.ROLE, F.data.startswith("adminProfile_edit_role_"))
async def admin_save_role_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    role = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not user_id:
        await callback.message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        from config.profile import get_roles
        roles = get_roles(language)
        trainer_role = roles[1] if len(roles) > 1 else "Тренер"
        player_role = roles[0] if len(roles) > 0 else "Игрок"
        
        if role == trainer_role and users[user_id].get('role') != trainer_role:
            # Если меняем на тренера, запрашиваем цену
            await state.update_data(role=role)
            await callback.message.edit_text(t("admin_edit.enter_trainer_price", language))
            await state.set_state(AdminEditProfileStates.TRAINER_PRICE)
        else:
            # Если меняем на игрока или роль не меняется
            users[user_id]['role'] = role
            if role == player_role:
                users[user_id]['price'] = None  # Сбрасываем цену для игроков
            
            await storage.save_users(users)
            await callback.message.edit_text(t("admin_edit.role_updated", language))
            await show_profile(callback.message, users[user_id])
            await state.clear()
    else:
        await callback.message.answer(t("admin_edit.profile_not_found", language))
        await state.clear()
    
    await callback.answer()

# Обработчик для ввода цены тренера
@admin_edit_router.message(AdminEditProfileStates.TRAINER_PRICE, F.text)
async def admin_save_trainer_price(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    role = data.get('role')
    
    if not user_id or not role:
        await message.answer(t("admin_edit.data_not_found", language))
        await state.clear()
        return
    
    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t("admin_edit.price_invalid", language))
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['role'] = role
        users[user_id]['price'] = price
        await storage.save_users(users)
        
        await message.answer(t("admin_edit.role_price_updated", language))
        await show_profile(message, users[user_id])
    else:
        await message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

# Обработчик для сохранения уровня
@admin_edit_router.message(AdminEditProfileStates.LEVEL, F.text)
async def admin_save_level_edit(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    try:
        rating = int(message.text.strip())
        if rating < 0:
            await message.answer(t("admin_edit.rating_negative", language))
            return
        if rating > 2800:
            await message.answer(t("admin_edit.rating_too_high", language))
            return
    except ValueError:
        await message.answer(t("admin_edit.rating_invalid", language))
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        # Автоматически рассчитываем уровень на основе очков
        sport = users[user_id].get('sport', '🎾Большой теннис')
        calculated_level = calculate_level_from_points(rating, sport)
        
        users[user_id]['rating_points'] = rating
        users[user_id]['player_level'] = calculated_level
        users[user_id]['rating_edited'] = True  # Помечаем, что рейтинг был отредактирован
        await storage.save_users(users)
        
        await message.answer(t("admin_edit.rating_updated", language, level=calculated_level))
        await show_profile(message, users[user_id])
    else:
        await message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

# Обработчики для редактирования местоположения
@admin_edit_router.callback_query(AdminEditProfileStates.COUNTRY, F.data.startswith("adminProfile_edit_country_"))
async def admin_process_country_selection(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    country = callback.data.split("_", 3)[3]
    await state.update_data(country=country)
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    current_city = users[user_id].get('city', '') if user_id in users else ''
    
    await admin_ask_for_city(callback.message, state, country, current_city)
    await callback.answer()

@admin_edit_router.callback_query(AdminEditProfileStates.COUNTRY, F.data == "adminProfile_edit_other_country")
async def admin_process_other_country(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    language = await get_user_language_async(str(callback.message.chat.id))
    await callback.message.edit_text(t("admin_edit.enter_country", language), reply_markup=None)
    await state.set_state(AdminEditProfileStates.COUNTRY_INPUT)
    await callback.answer()

@admin_edit_router.message(AdminEditProfileStates.COUNTRY_INPUT, F.text)
async def admin_process_country_input(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    await state.update_data(country=message.text.strip())
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
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
    
    language = await get_user_language_async(str(message.chat.id))
    cities = cities_data.get(country, [])
    buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"adminProfile_edit_city_{city}")] for city in cities]
    buttons.append([InlineKeyboardButton(text=t("admin_edit.other_city", language), callback_data="adminProfile_edit_other_city")])

    try:
        await message.edit_text(
            t("admin_edit.select_city", language, country=remove_country_flag(country)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            t("admin_edit.select_city", language, country=remove_country_flag(country)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await state.set_state(AdminEditProfileStates.CITY)

@admin_edit_router.callback_query(AdminEditProfileStates.CITY, F.data.startswith("adminProfile_edit_city_"))
async def admin_process_city_selection(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    city = callback.data.split("_", 3)[3]
    await state.update_data(city=city)
    
    if city == "Москва":
        buttons = []
        row = []
        language = await get_user_language_async(str(callback.message.chat.id))
        for i, district in enumerate(moscow_districts):
            row.append(InlineKeyboardButton(text=district, callback_data=f"adminProfile_edit_district_{district}"))
            if (i + 1) % 3 == 0 or i == len(moscow_districts) - 1:
                buttons.append(row)
                row = []
        await callback.message.edit_text(
            t("admin_edit.select_district", language),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await admin_save_location(callback, city, state)
    
    await callback.answer()

@admin_edit_router.callback_query(AdminEditProfileStates.CITY, F.data.startswith("adminProfile_edit_district_"))
async def admin_process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    data = await state.get_data()
    city = data.get('city', '')
    
    district = callback.data.split("_", 3)[3]
    await admin_save_location(callback, city, state, district)
    await callback.answer()

@admin_edit_router.callback_query(AdminEditProfileStates.CITY, F.data == "adminProfile_edit_other_city")
async def admin_process_other_city(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    language = await get_user_language_async(str(callback.message.chat.id))
    await callback.message.edit_text(t("admin_edit.enter_city", language), reply_markup=None)
    await state.set_state(AdminEditProfileStates.CITY_INPUT)
    await callback.answer()

@admin_edit_router.message(AdminEditProfileStates.CITY_INPUT, F.text)
async def admin_process_city_input(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    city = message.text.strip()
    await admin_save_location_message(message, city, state)

async def admin_save_location(callback: types.CallbackQuery, city: str, state: FSMContext, district: str = ''):
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not user_id:
        await callback.message.answer(t("admin_edit.user_not_selected", language))
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
        
        await callback.message.answer(t("admin_edit.location_updated", language))
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

async def admin_save_location_message(message: types.Message, city: str, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    language = await get_user_language_async(str(message.chat.id))
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_id]['country'] = country
        users[user_id]['city'] = city
        await storage.save_users(users)
        
        await message.answer(t("admin_edit.location_updated", language))
        await show_profile(message, users[user_id])
    else:
        await message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

# Обработчики для редактирования фото
@admin_edit_router.callback_query(F.data.startswith("adminProfile_edit_photo_"))
async def admin_edit_photo_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    action = callback.data.split("_", 3)[3]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not user_id:
        await callback.message.answer(t("admin_edit.user_not_selected", language))
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        await callback.answer(t("admin_edit.profile_not_found", language))
        return
    
    try:
        await callback.message.delete()
    except:
        pass

    if action == "upload":
        await callback.message.answer(t("admin_edit.upload_photo", language))
        await state.set_state(AdminEditProfileStates.PHOTO_UPLOAD)
    elif action == "none":
        users[user_id]['photo_path'] = None
        await storage.save_users(users)
        await callback.message.answer(t("admin_edit.photo_deleted", language))
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
                    await callback.message.answer(t("admin_edit.photo_from_profile", language))
                    await show_profile(callback.message, users[user_id])
                else:
                    await callback.message.answer(t("admin_edit.photo_error", language))
            else:
                await callback.message.answer(t("admin_edit.no_photo", language))
        except Exception as e:
            await callback.message.answer(t("admin_edit.photo_error", language))
    
    await callback.answer()

# Обработчик для загрузки нового фото
@admin_edit_router.message(AdminEditProfileStates.PHOTO_UPLOAD, F.photo)
async def admin_save_photo_upload(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id not in users:
        await message.answer(t("admin_edit.profile_not_found", language))
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
            await message.answer(t("admin_edit.photo_updated", language))
            await show_profile(message, users[user_id])
        else:
            await message.answer(t("admin_edit.photo_save_error", language))
    except Exception as e:
        await message.answer(t("admin_edit.photo_save_error", language))
    
    await state.clear()

# Обработчики для редактирования полей знакомств (админ)
@admin_edit_router.callback_query(AdminEditProfileStates.DATING_GOAL, F.data.startswith("adgoal_"))
async def admin_process_dating_goal_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    language = await get_user_language_async(str(callback.message.chat.id))
    goal_index = int(callback.data.split("_")[1])
    from config.profile import get_dating_goals
    goals = get_dating_goals(language)
    goal = goals[goal_index]
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await callback.message.answer(t("admin_edit.user_not_selected", language))
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
        
        await callback.message.answer(t("admin_edit.dating_goal_updated", language))
        await show_profile(callback.message, users[user_id])
    else:
        await callback.message.answer(t("admin_edit.profile_not_found", language))
    
    await callback.answer()
    await state.clear()

@admin_edit_router.callback_query(AdminEditProfileStates.DATING_INTERESTS, F.data.startswith("adint_"))
async def admin_process_dating_interest_edit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    if callback.data == "adint_done":
        # Завершение выбора интересов
        user_data = await state.get_data()
        interests = user_data.get('dating_interests', [])
        user_id = user_data.get('admin_edit_user_id')
        
        language = await get_user_language_async(str(callback.message.chat.id))
        
        if not user_id:
            await callback.message.answer(t("admin_edit.user_not_selected", language))
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
            
            await callback.message.answer(t("admin_edit.interests_updated", language))
            await show_profile(callback.message, users[user_id])
        else:
            await callback.message.answer(t("admin_edit.profile_not_found", language))
        
        await callback.answer()
        await state.clear()
        return
    
    # Обработка выбора интереса
    language = await get_user_language_async(str(callback.message.chat.id))
    interest_index = int(callback.data.split("_")[1])
    from config.profile import get_dating_interests
    interests_list = get_dating_interests(language)
    interest = interests_list[interest_index]
    user_data = await state.get_data()
    interests = user_data.get('dating_interests', [])
    
    if interest in interests:
        interests.remove(interest)
    else:
        interests.append(interest)
    
    await state.update_data(dating_interests=interests)
    
    # Обновляем кнопки
    buttons = []
    for i, interest_text in enumerate(interests_list):
        if interest_text in interests:
            buttons.append([InlineKeyboardButton(text=f"✅ {interest_text}", callback_data=f"adint_{i}")])
        else:
            buttons.append([InlineKeyboardButton(text=interest_text, callback_data=f"adint_{i}")])
    buttons.append([InlineKeyboardButton(text=t("admin_edit.finish_interests", language), callback_data="adint_done")])
    
    await callback.message.edit_text(
        t("admin_edit.select_dating_interests", language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@admin_edit_router.message(AdminEditProfileStates.DATING_ADDITIONAL, F.text)
async def admin_save_dating_additional_edit(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    additional = message.text.strip()
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['dating_additional'] = additional
        await storage.save_users(users)
        
        await message.answer(t("admin_edit.dating_additional_updated", language))
        await show_profile(message, users[user_id])
    else:
        await message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

@admin_edit_router.message(AdminEditProfileStates.MEETING_TIME, F.text)
async def admin_save_meeting_time_edit(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    if not await is_admin(message.from_user.id):
        await message.answer(t("admin_edit.no_admin_rights", language))
        await state.clear()
        return
    
    meeting_time = message.text.strip()
    data = await state.get_data()
    user_id = data.get('admin_edit_user_id')
    
    if not user_id:
        await message.answer(t("admin_edit.user_not_selected", language))
        await state.clear()
        return
    
    users = await storage.load_users()
    
    if user_id in users:
        users[user_id]['meeting_time'] = meeting_time
        await storage.save_users(users)
        
        await message.answer(t("admin_edit.meeting_time_updated", language))
        await show_profile(message, users[user_id])
    else:
        await message.answer(t("admin_edit.profile_not_found", language))
    
    await state.clear()

# Обработчик отмены
@admin_edit_router.callback_query(F.data == "admin_cancel")
async def admin_cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.answer(t("admin_edit.no_admin_rights", language))
        return
    
    language = await get_user_language_async(str(callback.message.chat.id))
    await callback.message.edit_text(t("admin_edit.action_cancelled", language))
    await callback.answer()
