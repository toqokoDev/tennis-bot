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
    create_sport_keyboard, get_moscow_districts, cities_data, countries,
    get_sport_config, get_base_keyboard,
    get_tennis_levels, get_table_tennis_levels
)
from models.states import EditProfileStates
from utils.bot import show_profile
from utils.media import download_photo_to_path
from utils.utils import remove_country_flag
from services.storage import storage
from utils.translations import get_user_language_async, t

async def _get_menu_keyboard(user_id: int):
    """Единая точка получения reply keyboard на языке пользователя."""
    language = await get_user_language_async(str(user_id))
    profile = await storage.get_user(user_id) or {}
    sport = profile.get("sport", "🎾Большой теннис")
    return get_base_keyboard(sport, language=language)

async def _get_user_context(user_id: int):
    """Возвращает (language, sport, keyboard) для сообщений."""
    language = await get_user_language_async(str(user_id))
    profile = await storage.get_user(user_id) or {}
    sport = profile.get("sport", "🎾Большой теннис")
    keyboard = get_base_keyboard(sport, language=language)
    return language, sport, keyboard

def calculate_level_from_points(rating_points: int, sport: str) -> str:
    """
    Вычисляет уровень игрока на основе его рейтинговых очков
    
    Args:
        rating_points: Количество рейтинговых очков
        sport: Вид спорта
    
    Returns:
        Строка с уровнем (например, "2.5")
    """
    config = get_sport_config(sport)
    level_type = config.get("level_type", "tennis")
    
    # Выбираем соответствующий словарь уровней (RU-данные нужны только для points)
    if level_type == "table_tennis_rating" or level_type == "table_tennis":
        levels = get_table_tennis_levels("ru")
    else:
        levels = get_tennis_levels("ru")
    
    # Сортируем уровни по очкам
    sorted_levels = sorted(levels.items(), key=lambda x: x[1]["points"])
    
    # Находим подходящий уровень
    for i, (level, data) in enumerate(sorted_levels):
        if rating_points < data["points"]:
            # Если это первый уровень, возвращаем его
            if i == 0:
                return level
            # Иначе возвращаем предыдущий уровень
            return sorted_levels[i - 1][0]
    
    # Если очков больше максимума, возвращаем максимальный уровень
    return sorted_levels[-1][0]

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
        new_profile["role"] = "Игрок"  # по умолчанию (каноническое значение)
    
    if new_config.get("has_level", True) and not new_profile.get("player_level"):
        # Для настольного тенниса используем рейтинг, для остальных - уровень
        if new_sport == "🏓Настольный теннис":
            new_profile["player_level"] = "0.0"  # По умолчанию
        else:
            new_profile["player_level"] = "1.0"  # По умолчанию
        new_profile["rating_points"] = 500  # Базовые очки
    
    if new_config.get("has_payment", True) and not new_profile.get("price"):
        new_profile["price"] = None  # По умолчанию пополам
        new_profile["default_payment"] = "Пополам"
    
    if new_config.get("has_vacation", True):
        # Поля отпуска остаются как есть, если уже заполнены
        pass
    
    # Специальные поля для знакомств
    if new_sport == "🍒Знакомства":
        if not new_profile.get("dating_goal_key") and not new_profile.get("dating_goal"):
            new_profile["dating_goal"] = ""  # пусть заполнит, чтобы не было RU-дефолта в EN
        if not new_profile.get("dating_interests"):
            new_profile["dating_interests"] = []  # Пустой список
        if not new_profile.get("dating_additional"):
            new_profile["dating_additional"] = {}  # Пустой словарь
    
    # Специальные поля для встреч
    if new_sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        if not new_profile.get("meeting_time"):
            new_profile["meeting_time"] = ""  # пусть заполнит
    
    return new_profile

router = Router()

# Добавляем обработчики для кнопок
@router.callback_query(F.data == "edit_profile")
async def edit_profile_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id)
    
    language = await get_user_language_async(str(user_id))
    
    if not profile:
        await callback.answer(t("profile_edit.profile_not_found", language))
        return
    
    # Создаем клавиатуру для редактирования в зависимости от вида спорта
    sport = profile.get("sport", "🎾Большой теннис")
    config = get_sport_config(sport)
    
    buttons = []
    
    # Базовые поля (всегда доступны)
    buttons.append([
        InlineKeyboardButton(text=t("profile_edit.buttons.photo", language), callback_data="1edit_photo"),
        InlineKeyboardButton(text=t("profile_edit.buttons.location", language), callback_data="1edit_location")
    ])
    
    # Поля в зависимости от конфигурации
    if config.get("has_about_me", True):
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.about_me", language), callback_data="1edit_comment")])
    
    if config.get("has_payment", True):
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.payment", language), callback_data="1edit_payment")])
    
    if config.get("has_role", True):
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.role", language), callback_data="1edit_role")])
    
    if config.get("has_level", True):
        # Проверяем, не редактировал ли пользователь уже рейтинг
        if not profile.get('rating_edited', False):
            buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.level", language), callback_data="1edit_level")])
        else:
            buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.level_changed", language), callback_data="1edit_level_disabled")])
    
    # Специальные поля для знакомств
    if sport == "🍒Знакомства":
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.dating_goal", language), callback_data="1edit_dating_goal")])
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.dating_interests", language), callback_data="1edit_dating_interests")])
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.dating_additional", language), callback_data="1edit_dating_additional")])
    
    # Специальные поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.meeting_time", language), callback_data="1edit_meeting_time")])
    
    # Вид спорта (всегда доступен)
    buttons.append([InlineKeyboardButton(text=t("profile_edit.buttons.sport", language), callback_data="1edit_sport")])
    
    # Назад
    buttons.append([InlineKeyboardButton(text=t("common.back", language), callback_data=f"back_to_profile:{user_id}")])
    
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
        language, _, keyboard = await _get_user_context(callback.message.chat.id)
        await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await callback.answer()

# Обработчик для удаления профиля
@router.callback_query(F.data == "1delete_profile")
async def delete_profile_handler(callback: types.CallbackQuery):
    # Создаем клавиатуру с подтверждением удаления
    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("common.confirm", await get_user_language_async(str(callback.message.chat.id))), callback_data="confirm_delete"),
                InlineKeyboardButton(text=t("common.cancel", await get_user_language_async(str(callback.message.chat.id))), callback_data="cancel_delete")
            ]
        ]
    )
    try:
        await callback.message.edit_text(
            t("profile_edit.delete_confirm", await get_user_language_async(str(callback.message.chat.id))),
            reply_markup=confirm_keyboard
        )
    except:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            t("profile_edit.delete_confirm", await get_user_language_async(str(callback.message.chat.id))),
            reply_markup=confirm_keyboard
        )
    
    await callback.answer()

@router.callback_query(F.data == "confirm_delete")
async def confirm_delete_handler(callback: types.CallbackQuery):
    user_id = callback.message.chat.id
    users = await storage.load_users()
    user_key = str(user_id)
    
    language = await get_user_language_async(str(user_id))
    main_inline_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("profile_edit.main_menu", language), callback_data="main_menu")]]
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
            t("profile_edit.deleted", language),
            reply_markup=main_inline_keyboard
        )
    else:
        await callback.message.edit_text(
            t("profile_edit.profile_not_found", language),
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
            t("profile_edit.profile_not_found", await get_user_language_async(str(user_id))),
            reply_markup=await _get_menu_keyboard(user_id)
        )
    
    await callback.answer()

# Обработчики для редактирования профиля
@router.callback_query(F.data.startswith("1edit_"))
async def edit_field_handler(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.replace("1edit_", "")
    user_id = callback.message.chat.id
    language = await get_user_language_async(str(user_id))
    users = await storage.load_users()
    user_key = str(user_id)
    
    try:
        await callback.message.delete()
    except:
        pass

    if field == "comment":
        await callback.message.answer(t("profile_edit.enter_comment", language))
        await state.set_state(EditProfileStates.COMMENT)
    elif field == "payment":
        buttons = [
            [InlineKeyboardButton(text=t("config.payment_types.split", language), callback_data="edit_payment_Пополам")],
            [InlineKeyboardButton(text=t("config.payment_types.i_pay", language), callback_data="edit_payment_Я оплачиваю")],
            # callback_data оставляем как было (обратная совместимость)
            [InlineKeyboardButton(text=t("config.payment_types.opponent_pays", language), callback_data="edit_payment_Соперник оплачиваю")],
            [InlineKeyboardButton(text=t("config.payment_types.loser_pays", language), callback_data="edit_payment_Проигравший оплачивает")],
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("profile_edit.select_payment", language), reply_markup=keyboard)
        await state.set_state(EditProfileStates.PAYMENT)
    elif field == "photo":
        buttons = [
            [InlineKeyboardButton(text=t("profile_edit.photo.upload", language), callback_data="edit_photo_upload")],
            [InlineKeyboardButton(text=t("profile_edit.photo.none", language), callback_data="edit_photo_none")],
            [InlineKeyboardButton(text=t("profile_edit.photo.from_telegram", language), callback_data="edit_photo_profile")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("profile_edit.select_photo", language), reply_markup=keyboard)
    elif field == "location":
        buttons = []
        for country in countries[:5]:
            buttons.append([InlineKeyboardButton(text=f"{country}", callback_data=f"edit_country_{country}")])
        buttons.append([InlineKeyboardButton(text=t("registration.other_country", language), callback_data="edit_other_country")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("profile_edit.select_country", language), reply_markup=keyboard)
        await state.set_state(EditProfileStates.COUNTRY)
    elif field == "sport":
        await callback.message.answer(t("profile_edit.select_sport", language), reply_markup=create_sport_keyboard(pref="edit_sport_", language=language))
        await state.set_state(EditProfileStates.SPORT)
    elif field == "role":
        # Клавиатура для выбора роли
        buttons = [
            [InlineKeyboardButton(text=t("config.roles.player", language), callback_data="edit_role_Игрок")],
            [InlineKeyboardButton(text=t("config.roles.trainer", language), callback_data="edit_role_Тренер")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("profile_edit.select_role", language), reply_markup=keyboard)
        await state.set_state(EditProfileStates.ROLE)
    elif field == "price":
        if user_key not in users:
            await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=await _get_menu_keyboard(user_id))
            await callback.answer()
            return

        role = users[user_key].get('role')
        if role != "Тренер":
            await callback.message.answer(t("profile_edit.price_only_trainer", language))
            await callback.answer()
            return

        await callback.message.answer(t("profile_edit.enter_price", language))
        await state.set_state(EditProfileStates.PRICE)
    elif field == "level":
        # Проверяем, можно ли пользователю редактировать уровень
        if user_key in users:
            user_data = users[user_key]
            
            # Проверяем, не редактировал ли пользователь уже рейтинг
            if user_data.get('rating_edited', False):
                await callback.message.answer(t("profile_edit.rating_already_edited", language), reply_markup=await _get_menu_keyboard(user_id))
                await callback.answer()
                return
            
            sport = user_data.get("sport", "🎾Большой теннис")
            config = get_sport_config(sport)
            
            # Просим пользователя ввести рейтинг
            if config.get("level_type") == "table_tennis":
                await callback.message.answer(t("profile_edit.enter_table_tennis_rating", language))
            else:
                await callback.message.answer(t("profile_edit.enter_rating_points", language))
            
            await state.set_state(EditProfileStates.LEVEL)
        else:
            await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=await _get_menu_keyboard(user_id))
    elif field == "level_disabled":
        await callback.message.answer(t("profile_edit.rating_already_edited", language), reply_markup=await _get_menu_keyboard(user_id))
        await callback.answer()
        return
    elif field == "dating_goal":
        goal_keys = ["relationship", "communication", "friendship", "never_know"]
        buttons = [[InlineKeyboardButton(text=t(f"config.dating_goals.{k}", language), callback_data=f"dgoal_{k}")] for k in goal_keys]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(t("profile_edit.select_dating_goal", language), reply_markup=keyboard)
        await state.set_state(EditProfileStates.DATING_GOAL)
    elif field == "dating_interests":
        interest_keys = ["travel", "music", "cinema", "coffee", "guitar", "skiing", "board_games", "quizzes"]
        buttons = [[InlineKeyboardButton(text=t(f"config.dating_interests.{k}", language), callback_data=f"dint_{k}")] for k in interest_keys]
        buttons.append([InlineKeyboardButton(text=t("common.done", language), callback_data="dint_done")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await state.update_data(dating_interests_keys=[])
        await callback.message.answer(t("profile_edit.select_dating_interests", language), reply_markup=keyboard)
        await state.set_state(EditProfileStates.DATING_INTERESTS)
    elif field == "dating_additional":
        await callback.message.answer(t("profile_edit.enter_dating_additional", language))
        await state.set_state(EditProfileStates.DATING_ADDITIONAL)
    elif field == "meeting_time":
        await callback.message.answer(t("profile_edit.enter_meeting_time", language))
        await state.set_state(EditProfileStates.MEETING_TIME)
    
    await callback.answer()

# Обработчик для сохранения нового комментария о себе
@router.message(EditProfileStates.COMMENT, F.text)
async def save_comment_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    language, sport, keyboard = await _get_user_context(user_id)
    users = await storage.load_users()
    
    user_key = str(user_id)
    
    if user_key in users:
        # Сохраняем новый комментарий
        users[user_key]['profile_comment'] = message.text.strip()
        await storage.save_users(users)
        
        await message.answer(t("profile_edit.comment_updated", language))
        await show_profile(message, users[user_key])
    else:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()

@router.callback_query(EditProfileStates.PAYMENT, F.data.startswith("edit_payment_"))
async def save_payment_edit(callback: types.CallbackQuery):
    payment = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    user_id = callback.message.chat.id
    language, sport, keyboard = await _get_user_context(user_id)
    
    if user_key in users:
        users[user_key]['default_payment'] = payment
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(t("profile_edit.payment_updated", language))
        await show_profile(callback.message, users[user_key])
    else:
        await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
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
        
        language, sport, keyboard = await _get_user_context(callback.message.chat.id)
        await callback.message.answer(t("profile_edit.sport_updated", language))
        await show_profile(callback.message, migrated_profile)
    else:
        language, sport, keyboard = await _get_user_context(callback.message.chat.id)
        await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()
    await callback.answer()

# Обработчик для сохранения роли
@router.callback_query(EditProfileStates.ROLE, F.data.startswith("edit_role_"))
async def save_role_edit(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    language, sport, keyboard = await _get_user_context(callback.message.chat.id)
    
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
            
            await callback.message.answer(t("profile_edit.role_updated_player", language))
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
            
            await callback.message.answer(t("profile_edit.role_updated_trainer_need_price", language))
            await state.set_state(EditProfileStates.PRICE)
            await callback.answer()
            return
    
    else:
        await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()
    await callback.answer()

# Обработчик для сохранения стоимости тренировки
@router.message(EditProfileStates.PRICE, F.text)
async def save_price_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    language, sport, keyboard = await _get_user_context(user_id)
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key in users:
        try:
            price = int(message.text.strip())
            if price < 0:
                await message.answer(t("profile_edit.price_negative", language))
                return
            
            users[user_key]['price'] = price
            await storage.save_users(users)
            
            await message.answer(t("profile_edit.price_updated", language))
            await show_profile(message, users[user_key])
        except ValueError:
            await message.answer(t("profile_edit.price_invalid", language))
            return
    else:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()

# Обработчик для сохранения уровня

@router.message(EditProfileStates.LEVEL, F.text)
async def save_level_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    language, sport, keyboard = await _get_user_context(user_id)
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key in users:
        sport = users[user_key].get("sport", "🎾Большой теннис")
        config = get_sport_config(sport)
        
        try:
            # Пытаемся преобразовать в число для всех видов спорта
            rating = int(message.text.strip())
            if rating < 0:
                await message.answer(t("profile_edit.rating_negative", language))
                return
            if rating > 2800:
                await message.answer(t("profile_edit.rating_too_high", language))
                return
            
            # Автоматически рассчитываем уровень на основе очков
            calculated_level = calculate_level_from_points(rating, sport)
            
            # Сохраняем рейтинг и уровень
            users[user_key]['player_level'] = calculated_level
            users[user_key]['rating_points'] = rating
            users[user_key]['rating_edited'] = True
            await storage.save_users(users)
            
            await message.answer(t("profile_edit.rating_updated", language, level=calculated_level))
            await show_profile(message, users[user_key])
            
        except ValueError:
            # Если не удалось преобразовать в число, используем базовые значения
            calculated_level = calculate_level_from_points(1000, sport)
            users[user_key]['player_level'] = calculated_level
            users[user_key]['rating_points'] = 1000  # Базовый рейтинг
            users[user_key]['rating_edited'] = True
            await storage.save_users(users)
            
            await message.answer(t("profile_edit.rating_updated", language, level=calculated_level))
            await show_profile(message, users[user_key])
    else:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
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
    language = await get_user_language_async(str(callback.message.chat.id))
    await callback.message.edit_text(t("profile_edit.enter_country", language), reply_markup=None)
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
    language = await get_user_language_async(str(message.chat.id))
    data = await state.get_data()
    country = data.get('country', country)
    
    cities = cities_data.get(country, [])
    buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"edit_city_{city}")] for city in cities]
    buttons.append([InlineKeyboardButton(text=t("registration.other_city", language), callback_data="edit_other_city")])

    try:
        await message.edit_text(
            t("profile_edit.select_city", language, country=remove_country_flag(country)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            t("profile_edit.select_city", language, country=remove_country_flag(country)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await state.set_state(EditProfileStates.CITY)

@router.callback_query(EditProfileStates.CITY, F.data.startswith("edit_city_"))
async def process_city_selection(callback: types.CallbackQuery, state: FSMContext):
    language = await get_user_language_async(str(callback.message.chat.id))

    city = callback.data.split("_", 2)[2]
    await state.update_data(city=city)
    
    if city == "Москва":
        buttons = []
        row = []
        moscow_districts = get_moscow_districts(language)
        for i, district in enumerate(moscow_districts):
            row.append(InlineKeyboardButton(text=district, callback_data=f"edit_district_{district}"))
            if (i + 1) % 3 == 0 or i == len(moscow_districts) - 1:
                buttons.append(row)
                row = []
        try:
            await callback.message.edit_text(
            t("admin_edit.select_district", language),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        except:
            await callback.message.answer(
                t("admin_edit.select_district", language),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
    else:
        await save_location(callback, city, state)
    
    await callback.answer()

@router.callback_query(EditProfileStates.CITY, F.data.startswith("edit_district_"))
async def process_district_selection(callback: types.CallbackQuery, state: FSMContext):
    district = callback.data.split("_", 2)[2]
    data = await state.get_data()
    city = data.get('city', '')

    await save_location(callback, city, state, district)
    await callback.answer()

@router.callback_query(EditProfileStates.CITY, F.data == "edit_other_city")
async def process_other_city(callback: types.CallbackQuery, state: FSMContext):
    language = await get_user_language_async(str(callback.message.chat.id))

    await callback.message.edit_text(t("admin_edit.enter_city", language), reply_markup=None)
    await state.set_state(EditProfileStates.CITY_INPUT)
    await callback.answer()

@router.message(EditProfileStates.CITY_INPUT, F.text)
async def process_city_input(message: types.Message, state: FSMContext):
    city = message.text.strip()
    await save_location_message(message, city, state)

async def save_location(callback: types.CallbackQuery, city: str, state: FSMContext, district: str = ''):
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_key]['country'] = country
        users[user_key]['city'] = city
        users[user_key]['district'] = district
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.message.answer(t("profile_edit.location_updated", language))
        await show_profile(callback.message, users[user_key])
    else:
        language, sport, keyboard = await _get_user_context(callback.message.chat.id)
        await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()

async def save_location_message(message: types.Message, city: str, state: FSMContext):
    language, sport, keyboard = await _get_user_context(message.from_user.id)
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    
    if user_key in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_key]['country'] = country
        users[user_key]['city'] = city
        await storage.save_users(users)
        
        await message.answer(t("profile_edit.location_updated", language))
        await show_profile(message, users[user_key])
    else:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()

# Обработчики для редактирования фото
@router.callback_query(F.data.startswith("edit_photo_"))
async def edit_photo_handler(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    language, sport, keyboard = await _get_user_context(callback.message.chat.id)
    
    if user_key not in users:
        await callback.answer(t("profile_edit.profile_not_found", language))
        return
    
    try:
        await callback.message.delete()
    except:
        pass

    if action == "upload":
        await callback.message.answer(t("profile_edit.photo_send_new", language))
        await state.set_state(EditProfileStates.PHOTO_UPLOAD)
    elif action == "none":
        users[user_key]['photo_path'] = None
        await storage.save_users(users)
        await callback.message.answer(t("profile_edit.photo_deleted", language))
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
                    await callback.message.answer(t("profile_edit.photo_set_from_telegram", language))
                    await show_profile(callback.message, users[user_key])
                else:
                    await callback.message.answer(t("profile_edit.photo_set_failed", language))
            else:
                await callback.message.answer(t("profile_edit.telegram_no_photo", language), reply_markup=keyboard)
        except Exception as e:
            await callback.message.answer(t("profile_edit.telegram_photo_error", language), reply_markup=keyboard)
    
    await callback.answer()

# Обработчик для загрузки нового фото
@router.message(EditProfileStates.PHOTO_UPLOAD, F.photo)
async def save_photo_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    language, sport, keyboard = await _get_user_context(user_id)
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key not in users:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
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
            await message.answer(t("profile_edit.photo_updated", language))
            await show_profile(message, users[user_key])
        else:
            await message.answer(t("profile_edit.photo_save_failed", language), reply_markup=keyboard)
    except Exception as e:
        await message.answer(t("profile_edit.photo_save_error", language), reply_markup=keyboard)
    
    await state.clear()

# Обработчики для редактирования полей знакомств
@router.callback_query(EditProfileStates.DATING_GOAL, F.data.startswith("dgoal_"))
async def process_dating_goal_edit(callback: types.CallbackQuery, state: FSMContext):
    language = await get_user_language_async(str(callback.message.chat.id))
    goal_key = callback.data.split("_", 1)[1]
    goal = t(f"config.dating_goals.{goal_key}", language)
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['dating_goal_key'] = goal_key
        users[user_key]['dating_goal'] = goal  # legacy/display fallback
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(t("profile_edit.dating_goal_updated", language))
        await show_profile(callback.message, users[user_key])
    else:
        _, _, keyboard = await _get_user_context(callback.message.chat.id)
        await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await callback.answer()
    await state.clear()

@router.callback_query(EditProfileStates.DATING_INTERESTS, F.data.startswith("dint_"))
async def process_dating_interest_edit(callback: types.CallbackQuery, state: FSMContext):
    language = await get_user_language_async(str(callback.message.chat.id))
    if callback.data == "dint_done":
        # Завершение выбора интересов
        user_data = await state.get_data()
        interests_keys = user_data.get('dating_interests_keys', [])
        
        users = await storage.load_users()
        user_key = str(callback.message.chat.id)
        
        if user_key in users:
            users[user_key]['dating_interests_keys'] = interests_keys
            users[user_key]['dating_interests'] = [t(f"config.dating_interests.{k}", language) for k in interests_keys]  # legacy
            await storage.save_users(users)
            
            try:
                await callback.message.delete()
            except:
                pass
            
            await callback.message.answer(t("profile_edit.dating_interests_updated", language))
            await show_profile(callback.message, users[user_key])
        else:
            _, _, keyboard = await _get_user_context(callback.message.chat.id)
            await callback.message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
        
        await callback.answer()
        await state.clear()
        return
    
    # Обработка выбора интереса
    interest_key = callback.data.split("_", 1)[1]
    user_data = await state.get_data()
    interests_keys = user_data.get('dating_interests_keys', [])
    
    if interest_key in interests_keys:
        interests_keys.remove(interest_key)
    else:
        interests_keys.append(interest_key)
    
    await state.update_data(dating_interests_keys=interests_keys)
    
    # Обновляем кнопки
    interest_keys = ["travel", "music", "cinema", "coffee", "guitar", "skiing", "board_games", "quizzes"]
    buttons = []
    for k in interest_keys:
        interest_text = t(f"config.dating_interests.{k}", language)
        if k in interests_keys:
            buttons.append([InlineKeyboardButton(text=f"✅ {interest_text}", callback_data=f"dint_{k}")])
        else:
            buttons.append([InlineKeyboardButton(text=interest_text, callback_data=f"dint_{k}")])
    buttons.append([InlineKeyboardButton(text=t("common.done", language), callback_data="dint_done")])
    
    await callback.message.edit_text(
        t("profile_edit.select_dating_interests", language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@router.message(EditProfileStates.DATING_ADDITIONAL, F.text)
async def save_dating_additional_edit(message: types.Message, state: FSMContext):
    additional = message.text.strip()
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    language, sport, keyboard = await _get_user_context(message.from_user.id)
    
    if user_key in users:
        users[user_key]['dating_additional'] = additional
        await storage.save_users(users)
        
        await message.answer(t("profile_edit.dating_additional_updated", language))
        await show_profile(message, users[user_key])
    else:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()

@router.message(EditProfileStates.MEETING_TIME, F.text)
async def save_meeting_time_edit(message: types.Message, state: FSMContext):
    meeting_time = message.text.strip()
    users = await storage.load_users()
    user_key = str(message.from_user.id)
    language, sport, keyboard = await _get_user_context(message.from_user.id)
    
    if user_key in users:
        users[user_key]['meeting_time'] = meeting_time
        await storage.save_users(users)
        
        await message.answer(t("profile_edit.meeting_time_updated", language))
        await show_profile(message, users[user_key])
    else:
        await message.answer(t("profile_edit.profile_not_found", language), reply_markup=keyboard)
    
    await state.clear()

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    # Получаем профиль пользователя для определения вида спорта
    user_id = callback.message.chat.id
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    sport = user_data.get('sport', '🎾Большой теннис')
    language = await get_user_language_async(str(user_id))
    
    # Получаем адаптивную клавиатуру
    keyboard = get_base_keyboard(sport, language=language)
    
    try:
        await callback.message.edit_text(
            t("profile_edit.main_menu", language),
            reply_markup=keyboard
        )
    except:
        await callback.message.delete()
        
        await callback.message.answer(
            t("profile_edit.main_menu", language),
            reply_markup=keyboard
        )
    await callback.answer()
