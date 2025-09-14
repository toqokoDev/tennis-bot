from datetime import datetime
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config.paths import BASE_DIR, PHOTOS_DIR
from config.profile import moscow_districts, base_keyboard, cities_data, countries, sport_type
from models.states import EditProfileStates
from utils.bot import show_profile
from utils.media import download_photo_to_path
from services.storage import storage

router = Router()

# Добавляем обработчики для кнопок
@router.callback_query(F.data == "edit_profile")
async def edit_profile_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    profile = await storage.get_user(user_id)
    
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
                InlineKeyboardButton(text="🎾 Вид спорта", callback_data="1edit_sport"),
                InlineKeyboardButton(text="👤 Роль", callback_data="1edit_role")
            ],
            [
                InlineKeyboardButton(text="💰 Стоимость", callback_data="1edit_price"),
                InlineKeyboardButton(text="📊 Уровень", callback_data="1edit_level")
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить профиль", callback_data="1delete_profile")
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
        # Возвращаемся к меню редактирования
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
                    InlineKeyboardButton(text="🎾 Вид спорта", callback_data="1edit_sport"),
                    InlineKeyboardButton(text="👤 Роль", callback_data="1edit_role")
                ],
                [
                    InlineKeyboardButton(text="💰 Стоимость", callback_data="1edit_price"),
                    InlineKeyboardButton(text="📊 Уровень", callback_data="1edit_level")
                ],
                [
                    InlineKeyboardButton(text="🗑️ Удалить профиль", callback_data="1delete_profile")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{user_id}")
                ]
            ]
        )
        
        await callback.message.edit_text(
            "✏️ Выберите, что хотите изменить:",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            "❌ Профиль не найден",
            reply_markup=base_keyboard
        )
    
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
            # Проверяем, редактировал ли пользователь уровень ранее
            if user_data.get('level_edited', False):
                await callback.message.answer("📊 Ваш уровень рассчитывается автоматически на основе игр и не может быть изменен вручную.")
            else:
                await callback.message.answer("📊 Введите ваш уровень (количество очков):")
                await state.set_state(EditProfileStates.LEVEL)
        else:
            await callback.message.answer("❌ Профиль не найден", reply_markup=base_keyboard)
    
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
    sport = callback.data.split("_", 2)[2]
    users = await storage.load_users()
    user_key = str(callback.message.chat.id)
    
    if user_key in users:
        users[user_key]['sport'] = sport
        await storage.save_users(users)
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer("✅ Вид спорта обновлен!")
        await show_profile(callback.message, users[user_key])
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
        try:
            level = int(message.text.strip())
            if level < 0:
                await message.answer("❌ Уровень не может быть отрицательным. Попробуйте еще раз:")
                return
            
            users[user_key]['level'] = level
            users[user_key]['level_edited'] = True  # Помечаем, что пользователь редактировал уровень
            await storage.save_users(users)
            
            await message.answer("✅ Уровень обновлен!")
            await show_profile(message, users[user_key])
        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректное число для уровня:")
            return
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
