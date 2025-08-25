from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config.paths import BASE_DIR, PHOTOS_DIR
from config.profile import moscow_districts, cities_data, countries
from models.states import AdminEditProfileStates
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
    
    # Создаем клавиатуру для редактирования
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 О себе", callback_data="adminUserProfile_edit_comment"),
                InlineKeyboardButton(text="💳 Оплата", callback_data="adminUserProfile_edit_payment")
            ],
            [
                InlineKeyboardButton(text="📷 Фото", callback_data="adminUserProfile_edit_photo"),
                InlineKeyboardButton(text="🌍 Страна/Город", callback_data="adminUserProfile_edit_location")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin_edit_profile")
            ]
        ]
    )
    
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
    
    await callback.answer()

# Обработчик для сохранения нового комментария о себе
@admin_edit_router.message(AdminEditProfileStates.COMMENT, F.text)
async def admin_save_comment_edit(message: types.Message, state: FSMContext):
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
    
    if country == "Россия":
        main_russian_cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"adminProfile_edit_city_{city}")] for city in main_russian_cities]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="adminProfile_edit_other_city")])
    else:
        cities = cities_data.get(country, [])
        buttons = [[InlineKeyboardButton(text=f"{city}", callback_data=f"adminProfile_edit_city_{city}")] for city in cities[:5]]
        buttons.append([InlineKeyboardButton(text="Другой город", callback_data="adminProfile_edit_other_city")])

    await message.edit_text(
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
    
    if city == "Москва":
        buttons = [[InlineKeyboardButton(text=district, callback_data=f"adminProfile_edit_district_{district}")] for district in moscow_districts]
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
    
    district = callback.data.split("_", 3)[3]
    await admin_save_location(callback, district, state)
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

async def admin_save_location(callback: types.CallbackQuery, city: str, state: FSMContext):
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

# Обработчик отмены
@admin_edit_router.callback_query(F.data == "admin_cancel")
async def admin_cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.message.chat.id):
        await callback.answer("❌ Нет прав администратора")
        return
    
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await callback.answer()
