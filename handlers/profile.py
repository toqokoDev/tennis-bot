from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config.paths import BASE_DIR, PHOTOS_DIR
from config.profile import moscow_districts, base_keyboard
from models.states import EditProfileStates
from utils.bot import show_profile
from utils.json_data import get_user_profile_from_storage, load_json, load_users, write_users
from utils.media import download_photo_to_path

router = Router()

# ---------- Первичные данные ----------
cities_data = load_json("cities.json")
countries = list(cities_data.keys())

# Добавляем обработчики для кнопок
@router.callback_query(F.data == "edit_profile")
async def edit_profile_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    profile = get_user_profile_from_storage(user_id)
    
    if not profile:
        await callback.answer("❌ Профиль не найден", reply_markup=base_keyboard)
        return
    
    # Создаем клавиатуру для редактирования
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 О себе", callback_data="1edit_comment"),
                InlineKeyboardButton(text="💳 Оплата", callback_data="1edit_payment")
            ],
            [
                InlineKeyboardButton(text="📷 Фото", callback_data="1edit_photo"),
                InlineKeyboardButton(text="🌍 Страна/Город", callback_data="1edit_location")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{user_id}")
            ]
        ]
    )
    
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("back_to_profile:"))
async def back_to_profile_handler(callback: types.CallbackQuery):
    user_id = callback.data.split(":")[1]
    profile = get_user_profile_from_storage(user_id)
    
    try:
        await callback.message.delete()
    except:
        pass

    if profile:
        await show_profile(callback.message, profile)
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await callback.answer()

# Обработчики для редактирования профиля
@router.callback_query(F.data.startswith("1edit_"))
async def edit_field_handler(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    
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
    
    await callback.answer()

# Обработчик для сохранения нового комментария о себе
@router.message(EditProfileStates.COMMENT, F.text)
async def save_comment_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    users = load_users()
    user_key = str(user_id)
    
    if user_key in users:
        # Сохраняем новый комментарий
        users[user_key]['profile_comment'] = message.text.strip()
        write_users(users)
        
        await message.answer("✅ Комментарий о себе обновлен!")
        await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

@router.callback_query(EditProfileStates.PAYMENT, F.data.startswith("edit_payment_"))
async def save_payment_edit(callback: types.CallbackQuery):
    payment = callback.data.split("_", 2)[2]
    users = load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['default_payment'] = payment
        write_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Тип оплаты обновлен!")
        await show_profile(callback.message, users[user_key])
    else:
        await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await callback.answer()

# Обработчики для редактирования местоположения
@router.callback_query(EditProfileStates.COUNTRY, F.data.startswith("edit_country_"))
async def process_country_selection(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_", 2)[2]
    await state.update_data(country=country)
    
    # Получаем текущие данные пользователя
    users = load_users()
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
    users = load_users()
    user_key = str(message.from_user.id)
    current_city = users[user_key].get('city', '') if user_key in users else ''
    
    data = await state.get_data()
    country = data.get('country', '')
    await ask_for_city(message, state, country, current_city)

async def ask_for_city(message: types.Message, state: FSMContext, country: str, current_city: str = ''):
    data = await state.get_data()
    country = data.get('country', country)
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"edit_city_{city}")] for city in main_russian_cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="edit_other_city")])
    else:
        cities = cities_data.get(country, [])
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"edit_city_{city}")] for city in cities[:5]]
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
    users = load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_key]['country'] = country
        users[user_key]['city'] = city
        write_users(users)
        
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
    users = load_users()
    user_key = str(message.from_user.id)
    
    if user_key in users:
        data = await state.get_data()
        country = data.get('country', '')
        
        users[user_key]['country'] = country
        users[user_key]['city'] = city
        write_users(users)
        
        await message.answer("✅ Страна и город обновлены!")
        await show_profile(message, users[user_key])
    else:
        await message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
    await state.clear()

# Обработчики для редактирования фото
@router.callback_query(F.data.startswith("edit_photo_"))
async def edit_photo_handler(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_", 2)[2]
    users = load_users()
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
        write_users(users)
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
                    write_users(users)
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
    users = load_users()
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
            write_users(users)
            await message.answer("✅ Фото профиля обновлено!")
            await show_profile(message, users[user_key])
        else:
            await message.answer("❌ Не удалось сохранить фото", reply_markup=base_keyboard)
    except Exception as e:
        await message.answer("❌ Ошибка при сохранении фото", reply_markup=base_keyboard)
    
    await state.clear()

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "🏠 Главное меню",
            reply_markup=base_keyboard
        )
    except:
        await callback.message.delete()
        
        await callback.message.answer(
            "🏠 Главное меню",
            reply_markup=base_keyboard
        )
    await callback.answer()
