from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from datetime import datetime

from services.storage import storage
from models.states import CreateTournamentStates, EditTournamentStates, ViewTournamentsStates, AdminEditGameStates
from utils.admin import is_admin
from config.profile import sport_type, cities_data, create_sport_keyboard
from config.tournament_config import (
    TOURNAMENT_TYPES, GENDERS, CATEGORIES, AGE_GROUPS, 
    DURATIONS, YES_NO_OPTIONS, DISTRICTS_MOSCOW, MIN_PARTICIPANTS
)
from utils.tournament_brackets import create_tournament_bracket, Player, format_bracket_text
from utils.bracket_image_generator import create_bracket_image
from utils.tournament_manager import tournament_manager
from utils.tournament_notifications import TournamentNotifications
import io

router = Router()
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения состояния пагинации
tournament_pages = {}
my_tournaments_pages = {}
my_applications_pages = {}

# Глобальная переменная для хранения данных создаваемого турнира
tournament_data = {}

# Списки для выбора (используем данные из конфигурации)
SPORTS = sport_type
COUNTRIES = list(cities_data.keys())

# Получаем города для каждой страны из конфигурации
def get_cities_for_country(country):
    """Получить список городов для страны"""
    cities = cities_data.get(country, [])
    return cities + ["Другое"] if cities else ["Другое"]

# Обработчик создания турнира (только для админов)
@router.callback_query(F.data == "admin_create_tournament")
async def create_tournament_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик создания турнира (только админы)"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    # Очищаем данные предыдущего создания
    global tournament_data
    tournament_data = {}
    
    # Начинаем с выбора вида спорта
    await state.set_state(CreateTournamentStates.SPORT)
    
    await callback.message.edit_text(
        "🏆 Создание турнира\n\n"
        "📋 Шаг 1/13: Выберите вид спорта",
        reply_markup=create_sport_keyboard(pref="tournament_sport:")
    )
    await callback.answer()

# Обработчик выбора вида спорта
@router.callback_query(F.data.startswith("tournament_sport:"))
async def select_sport(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора вида спорта"""
    sport = callback.data.split(":", 1)[1]
    tournament_data["sport"] = sport
    
    await state.set_state(CreateTournamentStates.COUNTRY)
    
    builder = InlineKeyboardBuilder()
    for country in COUNTRIES:
        builder.button(text=country, callback_data=f"tournament_country:{country}")
    builder.adjust(2)
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 2/13: Выберите страну\n"
        f"✅ Вид спорта: {sport}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора страны
@router.callback_query(F.data.startswith("tournament_country:"))
async def select_country(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора страны"""
    country = callback.data.split(":", 1)[1]
    tournament_data["country"] = country
    
    if country == "Другое":
        await state.set_state(CreateTournamentStates.COUNTRY_INPUT)
        await callback.message.edit_text(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 2/13: Введите название страны\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {country}\n\n"
            f"Введите название страны:",
            reply_markup=None
        )
    else:
        await state.set_state(CreateTournamentStates.CITY)
        
        # Выбираем список городов в зависимости от страны
        cities = get_cities_for_country(country)
        
        builder = InlineKeyboardBuilder()
        for city in cities:
            builder.button(text=city, callback_data=f"tournament_city:{city}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 3/13: Выберите город\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {country}",
            reply_markup=builder.as_markup()
        )
    
    await callback.answer()

# Обработчик ввода страны вручную
@router.message(CreateTournamentStates.COUNTRY_INPUT)
async def input_country(message: Message, state: FSMContext):
    """Обработчик ввода страны вручную"""
    country = message.text.strip()
    tournament_data["country"] = country
    
    await state.set_state(CreateTournamentStates.CITY)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Ввести город вручную", callback_data="tournament_city_input")
    
    await message.answer(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 3/13: Выберите город\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {country}\n\n"
        f"Выберите способ выбора города:",
        reply_markup=builder.as_markup()
    )

# Обработчик кнопки ввода города вручную
@router.callback_query(F.data == "tournament_city_input")
async def tournament_city_input(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки ввода города вручную"""
    await state.set_state(CreateTournamentStates.CITY_INPUT)
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 3/13: Введите название города\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n\n"
        f"Введите название города:",
        reply_markup=None
    )
    await callback.answer()

# Обработчик выбора города
@router.callback_query(F.data.startswith("tournament_city:"))
async def select_city(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города"""
    city = callback.data.split(":", 1)[1]
    tournament_data["city"] = city
    
    if city == "Другое":
        await state.set_state(CreateTournamentStates.CITY_INPUT)
        await callback.message.edit_text(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 3/13: Введите название города\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {city}\n\n"
            f"Введите название города:",
            reply_markup=None
        )
    else:
        # Проверяем, нужно ли выбирать район (только для Москвы)
        if city == "Москва":
            await state.set_state(CreateTournamentStates.DISTRICT)
            
            builder = InlineKeyboardBuilder()
            for district in DISTRICTS_MOSCOW:
                builder.button(text=district, callback_data=f"tournament_district:{district}")
            builder.adjust(2)
            
            await callback.message.edit_text(
                f"🏆 Создание турнира\n\n"
                f"📋 Шаг 4/13: Выберите часть города\n"
                f"✅ Вид спорта: {tournament_data['sport']}\n"
                f"✅ Страна: {tournament_data['country']}\n"
                f"✅ Город: {city}",
                reply_markup=builder.as_markup()
            )
        else:
            # Пропускаем выбор района
            await state.set_state(CreateTournamentStates.TYPE)
            
            builder = InlineKeyboardBuilder()
            for t_type in TOURNAMENT_TYPES:
                builder.button(text=t_type, callback_data=f"tournament_type:{t_type}")
            builder.adjust(1)
            
            await callback.message.edit_text(
                f"🏆 Создание турнира\n\n"
                f"📋 Шаг 4/13: Выберите тип турнира\n"
                f"✅ Вид спорта: {tournament_data['sport']}\n"
                f"✅ Страна: {tournament_data['country']}\n"
                f"✅ Город: {city}",
                reply_markup=builder.as_markup()
            )
    
    await callback.answer()

# Обработчик ввода города вручную
@router.message(CreateTournamentStates.CITY_INPUT)
async def input_city(message: Message, state: FSMContext):
    """Обработчик ввода города вручную"""
    city = message.text.strip()
    tournament_data["city"] = city
    
    # Проверяем, нужно ли выбирать район (только для Москвы)
    if city == "Москва":
        await state.set_state(CreateTournamentStates.DISTRICT)
        
        builder = InlineKeyboardBuilder()
        for district in DISTRICTS_MOSCOW:
            builder.button(text=district, callback_data=f"tournament_district:{district}")
        builder.adjust(2)
        
        await message.answer(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 4/13: Выберите часть города\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {city}\n\n"
            f"Выберите часть города:",
            reply_markup=builder.as_markup()
        )
    else:
        # Пропускаем выбор района
        await state.set_state(CreateTournamentStates.TYPE)
        
        builder = InlineKeyboardBuilder()
        for t_type in TOURNAMENT_TYPES:
            builder.button(text=t_type, callback_data=f"tournament_type:{t_type}")
        builder.adjust(1)
        
        await message.answer(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг 4/13: Выберите тип турнира\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {city}\n\n"
            f"Выберите тип турнира:",
            reply_markup=builder.as_markup()
        )

# Обработчик выбора района
@router.callback_query(F.data.startswith("tournament_district:"))
async def select_district(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора района"""
    district = callback.data.split(":", 1)[1]
    tournament_data["district"] = district
    
    await state.set_state(CreateTournamentStates.TYPE)
    
    builder = InlineKeyboardBuilder()
    for t_type in TOURNAMENT_TYPES:
        builder.button(text=t_type, callback_data=f"tournament_type:{t_type}")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг 5/13: Выберите тип турнира\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"✅ Район: {district}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора типа турнира
@router.callback_query(F.data.startswith("tournament_type:"))
async def select_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа турнира"""
    t_type = callback.data.split(":", 1)[1]
    tournament_data["type"] = t_type
    
    await state.set_state(CreateTournamentStates.GENDER)
    
    builder = InlineKeyboardBuilder()
    for gender in GENDERS:
        builder.button(text=gender, callback_data=f"tournament_gender:{gender}")
    builder.adjust(2)
    
    step = "5" if "district" not in tournament_data else "6"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите пол участников\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {t_type}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора пола
@router.callback_query(F.data.startswith("tournament_gender:"))
async def select_gender(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора пола участников"""
    gender = callback.data.split(":", 1)[1]
    tournament_data["gender"] = gender
    
    await state.set_state(CreateTournamentStates.CATEGORY)
    
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        builder.button(text=category, callback_data=f"tournament_category:{category}")
    builder.adjust(2)
    
    step = "6" if "district" not in tournament_data else "7"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите категорию\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {gender}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора категории
@router.callback_query(F.data.startswith("tournament_category:"))
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора категории"""
    category = callback.data.split(":", 1)[1]
    tournament_data["category"] = category
    
    await state.set_state(CreateTournamentStates.AGE_GROUP)
    
    builder = InlineKeyboardBuilder()
    for age_group in AGE_GROUPS:
        builder.button(text=age_group, callback_data=f"tournament_age_group:{age_group}")
    builder.adjust(2)
    
    step = "7" if "district" not in tournament_data else "8"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите возрастную группу\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {category}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора возрастной группы
@router.callback_query(F.data.startswith("tournament_age_group:"))
async def select_age_group(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора возрастной группы"""
    age_group = callback.data.split(":", 1)[1]
    tournament_data["age_group"] = age_group
    
    await state.set_state(CreateTournamentStates.DURATION)
    
    builder = InlineKeyboardBuilder()
    for duration in DURATIONS:
        builder.button(text=duration, callback_data=f"tournament_duration:{duration}")
    builder.adjust(1)
    
    step = "8" if "district" not in tournament_data else "9"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Выберите продолжительность\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {age_group}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора продолжительности
@router.callback_query(F.data.startswith("tournament_duration:"))
async def select_duration(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора продолжительности"""
    duration = callback.data.split(":", 1)[1]
    tournament_data["duration"] = duration
    
    await state.set_state(CreateTournamentStates.PARTICIPANTS_COUNT)
    
    step = "9" if "district" not in tournament_data else "10"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Введите количество участников\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {tournament_data['age_group']}\n"
        f"✅ Продолжительность: {duration}\n\n"
        f"Введите количество участников (число):",
        reply_markup=None
    )
    await callback.answer()

# Обработчик ввода количества участников
@router.message(CreateTournamentStates.PARTICIPANTS_COUNT)
async def input_participants_count(message: Message, state: FSMContext):
    """Обработчик ввода количества участников"""
    try:
        count = int(message.text.strip())
        if count <= 0:
            await message.answer("❌ Количество участников должно быть больше 0. Попробуйте еще раз:")
            return
        
        tournament_data["participants_count"] = count
        
        await state.set_state(CreateTournamentStates.SHOW_IN_LIST)
        
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            builder.button(text=option, callback_data=f"tournament_show_in_list:{option}")
        builder.adjust(2)
        
        step = "10" if "district" not in tournament_data else "11"
        
        await message.answer(
            f"🏆 Создание турнира\n\n"
            f"📋 Шаг {step}/13: Отображать в общем списке турниров города?\n"
            f"✅ Вид спорта: {tournament_data['sport']}\n"
            f"✅ Страна: {tournament_data['country']}\n"
            f"✅ Город: {tournament_data['city']}\n"
            f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
            f"✅ Тип: {tournament_data['type']}\n"
            f"✅ Пол: {tournament_data['gender']}\n"
            f"✅ Категория: {tournament_data['category']}\n"
            f"✅ Возраст: {tournament_data['age_group']}\n"
            f"✅ Продолжительность: {tournament_data['duration']}\n"
            f"✅ Участников: {count}\n\n"
            f"Отображать турнир в общем списке турниров города?",
            reply_markup=builder.as_markup()
        )
    except ValueError:
        await message.answer("❌ Введите корректное число. Попробуйте еще раз:")

# Обработчик выбора отображения в списке
@router.callback_query(F.data.startswith("tournament_show_in_list:"))
async def select_show_in_list(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора отображения в списке"""
    show_in_list = callback.data.split(":", 1)[1]
    tournament_data["show_in_list"] = show_in_list == "Да"
    
    await state.set_state(CreateTournamentStates.HIDE_BRACKET)
    
    builder = InlineKeyboardBuilder()
    for option in YES_NO_OPTIONS:
        builder.button(text=option, callback_data=f"tournament_hide_bracket:{option}")
    builder.adjust(2)
    
    step = "11" if "district" not in tournament_data else "12"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Скрывать турнирную сетку?\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {tournament_data['age_group']}\n"
        f"✅ Продолжительность: {tournament_data['duration']}\n"
        f"✅ Участников: {tournament_data['participants_count']}\n"
        f"✅ В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n\n"
        f"Скрывать турнирную сетку от участников?",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора скрытия сетки
@router.callback_query(F.data.startswith("tournament_hide_bracket:"))
async def select_hide_bracket(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора скрытия турнирной сетки"""
    hide_bracket = callback.data.split(":", 1)[1]
    tournament_data["hide_bracket"] = hide_bracket == "Да"
    
    await state.set_state(CreateTournamentStates.COMMENT)
    
    step = "12" if "district" not in tournament_data else "13"
    
    await callback.message.edit_text(
        f"🏆 Создание турнира\n\n"
        f"📋 Шаг {step}/13: Введите комментарий к турниру\n"
        f"✅ Вид спорта: {tournament_data['sport']}\n"
        f"✅ Страна: {tournament_data['country']}\n"
        f"✅ Город: {tournament_data['city']}\n"
        f"{f'✅ Район: {tournament_data['district']}\n' if 'district' in tournament_data else ''}"
        f"✅ Тип: {tournament_data['type']}\n"
        f"✅ Пол: {tournament_data['gender']}\n"
        f"✅ Категория: {tournament_data['category']}\n"
        f"✅ Возраст: {tournament_data['age_group']}\n"
        f"✅ Продолжительность: {tournament_data['duration']}\n"
        f"✅ Участников: {tournament_data['participants_count']}\n"
        f"✅ В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n"
        f"✅ Скрыть сетку: {'Да' if tournament_data['hide_bracket'] else 'Нет'}\n\n"
        f"Введите комментарий к турниру (или отправьте '-' чтобы пропустить):",
        reply_markup=None
    )
    await callback.answer()

# Обработчик ввода комментария
@router.message(CreateTournamentStates.COMMENT)
async def input_comment(message: Message, state: FSMContext):
    """Обработчик ввода комментария"""
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    tournament_data["comment"] = comment
    
    await state.set_state(CreateTournamentStates.CONFIRM)
    
    # Формируем итоговую информацию
    location = f"{tournament_data['city']}"
    if "district" in tournament_data:
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data['country']}"
    
    text = f"🏆 Создание турнира\n\n"
    text += f"📋 Подтверждение данных:\n\n"
    text += f"🏓 Вид спорта: {tournament_data['sport']}\n"
    text += f"🌍 Место: {location}\n"
    text += f"⚔️ Тип: {tournament_data['type']}\n"
    text += f"👥 Пол: {tournament_data['gender']}\n"
    text += f"🏆 Категория: {tournament_data['category']}\n"
    text += f"👶 Возраст: {tournament_data['age_group']}\n"
    text += f"⏱️ Продолжительность: {tournament_data['duration']}\n"
    text += f"👥 Участников: {tournament_data['participants_count']}\n"
    text += f"📋 В списке города: {'Да' if tournament_data['show_in_list'] else 'Нет'}\n"
    text += f"🔒 Скрыть сетку: {'Да' if tournament_data['hide_bracket'] else 'Нет'}\n"
    if tournament_data['comment']:
        text += f"💬 Комментарий: {tournament_data['comment']}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать турнир", callback_data="tournament_confirm_create")
    builder.button(text="❌ Отменить", callback_data="tournament_cancel_create")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Обработчик подтверждения создания турнира
@router.callback_query(F.data == "tournament_confirm_create")
async def confirm_create_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения создания турнира"""
    try:
        # Загружаем существующие турниры
        tournaments = await storage.load_tournaments()
        
        # Создаем ID турнира
        tournament_id = f"tournament_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Формируем название турнира
        name = f"{tournament_data['sport']} - {tournament_data['category']}"
        
        # Формируем описание
        location = f"{tournament_data['city']}"
        if "district" in tournament_data:
            location += f" ({tournament_data['district']})"
        location += f", {tournament_data['country']}"
        
        description = f"Турнир по {tournament_data['sport'].lower()}\n"
        description += f"Место: {location}\n"
        description += f"Тип: {tournament_data['type']}\n"
        description += f"Пол: {tournament_data['gender']}\n"
        description += f"Категория: {tournament_data['category']}\n"
        description += f"Возраст: {tournament_data['age_group']}\n"
        description += f"Продолжительность: {tournament_data['duration']}\n"
        description += f"Участников: {tournament_data['participants_count']}"
        
        if tournament_data['comment']:
            description += f"\n\nКомментарий: {tournament_data['comment']}"
        
        # Создаем турнир
        tournaments[tournament_id] = {
            'name': name,
            'description': description,
            'sport': tournament_data['sport'],
            'country': tournament_data['country'],
            'city': tournament_data['city'],
            'district': tournament_data.get('district', ''),
            'type': tournament_data['type'],
            'gender': tournament_data['gender'],
            'category': tournament_data['category'],
            'age_group': tournament_data['age_group'],
            'duration': tournament_data['duration'],
            'participants_count': tournament_data['participants_count'],
            'show_in_list': tournament_data['show_in_list'],
            'hide_bracket': tournament_data['hide_bracket'],
            'comment': tournament_data['comment'],
            'created_at': datetime.now().isoformat(),
            'created_by': callback.from_user.id,
            'participants': {},
            'status': 'active',
            'rules': 'Стандартные правила турнира',
            'prize_fund': 'Будет определен позже'
        }
        
        # Сохраняем турниры
        await storage.save_tournaments(tournaments)
        
        # Очищаем состояние
        await state.clear()
        
        await callback.message.edit_text(
            f"✅ Турнир успешно создан!\n\n"
            f"🏆 Название: {name}\n"
            f"🆔 ID: {tournament_id}\n"
            f"📍 Место: {location}\n"
            f"👥 Участников: {tournament_data['participants_count']}\n\n"
            f"Турнир добавлен в систему и готов к приему заявок."
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка создания турнира: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при создании турнира. Попробуйте еще раз."
        )
        await callback.answer()

# Обработчик отмены создания турнира
@router.callback_query(F.data == "tournament_cancel_create")
async def cancel_create_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены создания турнира"""
    await state.clear()
    
    await callback.message.edit_text(
        "❌ Создание турнира отменено.\n\n"
        "Для создания нового турнира используйте команду /create_tournament"
    )
    await callback.answer()

# Команда для просмотра турниров
@router.message(F.text == "🏆 Турниры")
@router.message(Command("tournaments"))
async def tournaments_main(message: Message, state: FSMContext):
    """Главное меню турниров"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    text = (
        f"🏆 Турниры\n\n"
        f"Сейчас проходит: {len(active_tournaments)} активных турниров\n"
        f"Участвуйте в соревнованиях и покажите свои навыки!\n\n"
        f"📋 Вы можете просмотреть список доступных турниров, "
        f"подать заявку на участие или посмотреть свои текущие турниры."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть список", callback_data="view_tournaments_start")
    builder.button(text="📝 Мои заявки", callback_data="my_applications_list:0")
    builder.button(text="🎯 Мои турниры", callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Начало просмотра турниров - выбор вида спорта
@router.callback_query(F.data == "view_tournaments_start")
async def view_tournaments_start(callback: CallbackQuery, state: FSMContext):
    """Начало просмотра турниров - выбор вида спорта"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    if not active_tournaments:
        await callback.message.edit_text("🏆 На данный момент нет активных турниров.")
        await callback.answer()
        return
    
    # Получаем уникальные виды спорта из активных турниров
    sports_in_tournaments = set()
    for tournament_data in active_tournaments.values():
        sport = tournament_data.get('sport')
        if sport:
            sports_in_tournaments.add(sport)
    
    if not sports_in_tournaments:
        await callback.message.edit_text("🏆 На данный момент нет активных турниров.")
        await callback.answer()
        return
    
    await state.set_state(ViewTournamentsStates.SELECT_SPORT)
    
    builder = InlineKeyboardBuilder()
    for sport in sorted(sports_in_tournaments):
        builder.button(text=sport, callback_data=f"view_tournament_sport:{sport}")
    builder.adjust(2)
    
    await callback.message.edit_text(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 1/3: Выберите вид спорта\n\n"
        f"Доступные виды спорта:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора вида спорта для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_sport:"))
async def select_sport_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора вида спорта для просмотра турниров"""
    sport = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    # Фильтруем турниры по выбранному виду спорта
    sport_tournaments = {k: v for k, v in active_tournaments.items() if v.get('sport') == sport}
    
    if not sport_tournaments:
        await callback.message.edit_text(f"🏆 Нет активных турниров по {sport}")
        await callback.answer()
        return
    
    # Получаем уникальные страны из турниров этого вида спорта
    countries_in_tournaments = set()
    for tournament_data in sport_tournaments.values():
        country = tournament_data.get('country')
        if country:
            countries_in_tournaments.add(country)
    
    await state.set_state(ViewTournamentsStates.SELECT_COUNTRY)
    await state.update_data(selected_sport=sport)
    
    builder = InlineKeyboardBuilder()
    for country in sorted(countries_in_tournaments):
        builder.button(text=country, callback_data=f"view_tournament_country:{country}")
    builder.adjust(2)
    
    await callback.message.edit_text(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 2/3: Выберите страну\n"
        f"✅ Вид спорта: {sport}\n\n"
        f"Доступные страны:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора страны для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_country:"))
async def select_country_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора страны для просмотра турниров"""
    country = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    # Фильтруем турниры по виду спорта и стране
    filtered_tournaments = {k: v for k, v in active_tournaments.items() 
                          if v.get('sport') == sport and v.get('country') == country}
    
    if not filtered_tournaments:
        await callback.message.edit_text(f"🏆 Нет активных турниров по {sport} в {country}")
        await callback.answer()
        return
    
    # Получаем уникальные города из отфильтрованных турниров
    cities_in_tournaments = set()
    for tournament_data in filtered_tournaments.values():
        city = tournament_data.get('city')
        if city:
            cities_in_tournaments.add(city)
    
    await state.set_state(ViewTournamentsStates.SELECT_CITY)
    await state.update_data(selected_country=country)
    
    builder = InlineKeyboardBuilder()
    for city in sorted(cities_in_tournaments):
        builder.button(text=city, callback_data=f"view_tournament_city:{city}")
    builder.adjust(2)
    
    await callback.message.edit_text(
        f"🏆 Просмотр турниров\n\n"
        f"📋 Шаг 3/3: Выберите город\n"
        f"✅ Вид спорта: {sport}\n"
        f"✅ Страна: {country}\n\n"
        f"Доступные города:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора города для просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_city:"))
async def select_city_for_view(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города для просмотра турниров"""
    city = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    # Фильтруем турниры по виду спорта, стране и городу
    filtered_tournaments = {k: v for k, v in active_tournaments.items() 
                          if (v.get('sport') == sport and 
                              v.get('country') == country and 
                              v.get('city') == city)}
    
    if not filtered_tournaments:
        await callback.message.edit_text(f"🏆 Нет активных турниров по {sport} в {city}, {country}")
        await callback.answer()
        return
    
    # Показываем список турниров
    await show_tournaments_list(callback, filtered_tournaments, sport, country, city)
    await callback.answer()

# Функция для показа списка турниров
async def show_tournaments_list(callback: CallbackQuery, tournaments: dict, sport: str, country: str, city: str):
    """Показывает список турниров"""
    if not tournaments:
        await callback.message.edit_text(f"🏆 Нет активных турниров по {sport} в {city}, {country}")
        return
    
    # Преобразуем в список для пагинации
    tournament_list = list(tournaments.items())
    total_tournaments = len(tournament_list)
    
    text = f"🏆 Турниры по {sport}\n"
    text += f"📍 {city}, {country}\n\n"
    text += f"Найдено турниров: {total_tournaments}\n\n"
    
    # Показываем первый турнир
    tournament_id, tournament_data = tournament_list[0]
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text += f"🏆 Турнир 1/{total_tournaments}\n\n"
    text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"🌍 Место: {location}\n"
    text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"💬 Комментарий: {tournament_data['comment']}\n"
    
    # Проверяем, подал ли пользователь уже заявку на этот турнир
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    
    existing_application = None
    for app_id, app_data in applications.items():
        if (app_data.get('user_id') == user_id and 
            app_data.get('tournament_id') == tournament_id):
            existing_application = app_data
            break
    
    # Проверяем, зарегистрирован ли пользователь уже в турнире
    is_registered = str(user_id) in tournament_data.get('participants', {})
    
    if existing_application:
        text += f"\n📋 Статус заявки: {'⏳ Ожидает рассмотрения' if existing_application.get('status') == 'pending' else '✅ Принята' if existing_application.get('status') == 'accepted' else '❌ Отклонена'}\n"
    elif is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации (если турниров больше одного)
    if total_tournaments > 1:
        builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournament_prev:0")
        builder.button(text="Следующий ➡️", callback_data=f"view_tournament_next:0")
    
    # Кнопка участия (только если пользователь еще не подал заявку и не зарегистрирован)
    if not existing_application and not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка истории игр (для всех пользователей)
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    
    # Кнопка турнирной сетки (для всех пользователей)
    builder.button(text="🏆 Турнирная сетка", callback_data=f"tournament_bracket:{tournament_id}")
    
    builder.button(text="🔙 Назад к выбору города", callback_data=f"view_tournament_country:{country}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_tournaments > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    if not existing_application and not is_registered:
        builder.adjust(1)  # Кнопка участия в отдельном ряду
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# Обработчики пагинации для новой системы просмотра турниров
@router.callback_query(F.data.startswith("view_tournament_prev:"))
async def view_tournament_prev(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Предыдущий' в просмотре турниров"""
    page = int(callback.data.split(':')[1])
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    # Фильтруем турниры по виду спорта и стране
    filtered_tournaments = {k: v for k, v in active_tournaments.items() 
                          if v.get('sport') == sport and v.get('country') == country}
    
    if not filtered_tournaments:
        await callback.answer("❌ Нет турниров для отображения")
        return
    
    # Получаем список городов
    cities_in_tournaments = set()
    for tournament_data in filtered_tournaments.values():
        city = tournament_data.get('city')
        if city:
            cities_in_tournaments.add(city)
    
    # Находим текущий город из контекста сообщения
    current_city = None
    for city in cities_in_tournaments:
        if city in callback.message.text:
            current_city = city
            break
    
    if not current_city:
        await callback.answer("❌ Не удалось определить текущий город")
        return
    
    # Фильтруем по городу
    city_tournaments = {k: v for k, v in filtered_tournaments.items() if v.get('city') == current_city}
    
    # Вычисляем предыдущую страницу
    tournament_list = list(city_tournaments.items())
    total_tournaments = len(tournament_list)
    
    if total_tournaments <= 1:
        await callback.answer("❌ Это первый турнир")
        return
    
    prev_page = (page - 1) % total_tournaments
    if prev_page < 0:
        prev_page = total_tournaments - 1
    
    # Показываем предыдущий турнир
    tournament_id, tournament_data = tournament_list[prev_page]
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 Турниры по {sport}\n"
    text += f"📍 {current_city}, {country}\n\n"
    text += f"Найдено турниров: {total_tournaments}\n\n"
    text += f"🏆 Турнир {prev_page + 1}/{total_tournaments}\n\n"
    text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"🌍 Место: {location}\n"
    text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"💬 Комментарий: {tournament_data['comment']}\n"
    
    # Проверяем статус заявки
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    
    existing_application = None
    for app_id, app_data in applications.items():
        if (app_data.get('user_id') == user_id and 
            app_data.get('tournament_id') == tournament_id):
            existing_application = app_data
            break
    
    is_registered = str(user_id) in tournament_data.get('participants', {})
    
    if existing_application:
        text += f"\n📋 Статус заявки: {'⏳ Ожидает рассмотрения' if existing_application.get('status') == 'pending' else '✅ Принята' if existing_application.get('status') == 'accepted' else '❌ Отклонена'}\n"
    elif is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if total_tournaments > 1:
        builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournament_prev:{prev_page}")
        builder.button(text="Следующий ➡️", callback_data=f"view_tournament_next:{prev_page}")
    
    if not existing_application and not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка истории игр (для всех пользователей)
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    
    # Кнопка турнирной сетки (для всех пользователей)
    builder.button(text="🏆 Турнирная сетка", callback_data=f"tournament_bracket:{tournament_id}")
    
    builder.button(text="🔙 Назад к выбору города", callback_data=f"view_tournament_country:{country}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    if total_tournaments > 1:
        builder.adjust(2)
    if not existing_application and not is_registered:
        builder.adjust(1)
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("view_tournament_next:"))
async def view_tournament_next(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Следующий' в просмотре турниров"""
    page = int(callback.data.split(':')[1])
    
    data = await state.get_data()
    sport = data.get('selected_sport')
    country = data.get('selected_country')
    
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    # Фильтруем турниры по виду спорта и стране
    filtered_tournaments = {k: v for k, v in active_tournaments.items() 
                          if v.get('sport') == sport and v.get('country') == country}
    
    if not filtered_tournaments:
        await callback.answer("❌ Нет турниров для отображения")
        return
    
    # Получаем список городов
    cities_in_tournaments = set()
    for tournament_data in filtered_tournaments.values():
        city = tournament_data.get('city')
        if city:
            cities_in_tournaments.add(city)
    
    # Находим текущий город из контекста сообщения
    current_city = None
    for city in cities_in_tournaments:
        if city in callback.message.text:
            current_city = city
            break
    
    if not current_city:
        await callback.answer("❌ Не удалось определить текущий город")
        return
    
    # Фильтруем по городу
    city_tournaments = {k: v for k, v in filtered_tournaments.items() if v.get('city') == current_city}
    
    # Вычисляем следующую страницу
    tournament_list = list(city_tournaments.items())
    total_tournaments = len(tournament_list)
    
    if total_tournaments <= 1:
        await callback.answer("❌ Это последний турнир")
        return
    
    next_page = (page + 1) % total_tournaments
    
    # Показываем следующий турнир
    tournament_id, tournament_data = tournament_list[next_page]
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 Турниры по {sport}\n"
    text += f"📍 {current_city}, {country}\n\n"
    text += f"Найдено турниров: {total_tournaments}\n\n"
    text += f"🏆 Турнир {next_page + 1}/{total_tournaments}\n\n"
    text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"🌍 Место: {location}\n"
    text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"👥 Участников: {len(tournament_data.get('participants', {}))}/{tournament_data.get('participants_count', 'Не указано')}\n"
    
    if tournament_data.get('comment'):
        text += f"💬 Комментарий: {tournament_data['comment']}\n"
    
    # Проверяем статус заявки
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    
    existing_application = None
    for app_id, app_data in applications.items():
        if (app_data.get('user_id') == user_id and 
            app_data.get('tournament_id') == tournament_id):
            existing_application = app_data
            break
    
    is_registered = str(user_id) in tournament_data.get('participants', {})
    
    if existing_application:
        text += f"\n📋 Статус заявки: {'⏳ Ожидает рассмотрения' if existing_application.get('status') == 'pending' else '✅ Принята' if existing_application.get('status') == 'accepted' else '❌ Отклонена'}\n"
    elif is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if total_tournaments > 1:
        builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournament_prev:{next_page}")
        builder.button(text="Следующий ➡️", callback_data=f"view_tournament_next:{next_page}")
    
    if not existing_application and not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    # Кнопка истории игр (для всех пользователей)
    builder.button(text="📊 История игр", callback_data=f"tournament_games_history:{tournament_id}")
    
    # Кнопка турнирной сетки (для всех пользователей)
    builder.button(text="🏆 Турнирная сетка", callback_data=f"tournament_bracket:{tournament_id}")
    
    builder.button(text="🔙 Назад к выбору города", callback_data=f"view_tournament_country:{country}")
    builder.button(text="🏠 Главное меню", callback_data="tournaments_main_menu")
    
    if total_tournaments > 1:
        builder.adjust(2)
    if not existing_application and not is_registered:
        builder.adjust(1)
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик кнопки "Участвовать"
@router.callback_query(F.data.startswith("apply_tournament:"))
async def apply_tournament_handler(callback: CallbackQuery):
    """Обработчик подачи заявки на турнир"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Проверяем, не подал ли пользователь уже заявку
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    
    # Ищем существующую заявку этого пользователя на этот турнир
    existing_application = None
    for app_id, app_data in applications.items():
        if (app_data.get('user_id') == user_id and 
            app_data.get('tournament_id') == tournament_id):
            existing_application = app_data
            break
    
    if existing_application:
        await callback.answer("⚠️ Вы уже подали заявку на этот турнир")
        return
    
    # Проверяем, не зарегистрирован ли пользователь уже в турнире
    if str(user_id) in tournament_data.get('participants', {}):
        await callback.answer("✅ Вы уже зарегистрированы в этом турнире")
        return
    
    # Загружаем данные пользователя
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    
    if not user_data:
        await callback.answer("❌ Сначала зарегистрируйтесь в системе")
        return
    
    # Создаем заявку
    application_id = f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
    
    applications[application_id] = {
        'user_id': user_id,
        'user_name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
        'phone': user_data.get('phone', 'Не указан'),
        'tournament_id': tournament_id,
        'tournament_name': tournament_data.get('name', 'Без названия'),
        'applied_at': datetime.now().isoformat(),
        'status': 'pending'
    }
    
    # Сохраняем заявку
    await storage.save_tournament_applications(applications)
    
    await callback.message.edit_text(
        f"✅ Заявка успешно подана!\n\n"
        f"👤 Ваши данные:\n"
        f"Имя: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"Телефон: {user_data.get('phone', 'Не указан')}\n\n"
        f"⏳ Заявка отправлена на рассмотрение администратору.\n"
        f"Вы получите уведомление о решении."
    )
    
    # Добавляем кнопку для возврата к списку турниров
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Вернуться к списку турниров", callback_data="view_tournaments_start")
    builder.button(text="📝 Мои заявки", callback_data="my_applications_list:0")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    builder.adjust(1)
    
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

# Просмотр своих заявок с пагинацией
@router.callback_query(F.data.startswith("my_applications_list:"))
async def my_applications_list(callback: CallbackQuery):
    """Показывает заявки пользователя с пагинацией по одной заявке на страницу"""
    page = int(callback.data.split(':')[1])
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Получаем все заявки пользователя
    user_applications = []
    for app_id, app_data in applications.items():
        if app_data.get('user_id') == user_id:
            user_applications.append(app_data)
    
    if not user_applications:
        await callback.message.edit_text("📋 У вас нет активных заявок на турниры.")
        await callback.answer()
        return
    
    # Сохраняем список заявок для пагинации
    my_applications_pages[callback.from_user.id] = user_applications
    
    # Вычисляем общее количество страниц
    total_pages = len(user_applications)
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Получаем заявку для текущей страницы
    application = user_applications[page]
    
    # Получаем данные турнира для дополнительной информации
    tournament_data = tournaments.get(application['tournament_id'], {})
    
    # Формируем текст для текущей заявки
    text = f"📋 Ваша заявка {page + 1}/{total_pages}\n\n"
    
    text += f"📅 Подана: {datetime.fromisoformat(application['applied_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    # Статус заявки
    status_emoji = "⏳" if application.get('status') == 'pending' else "✅" if application.get('status') == 'accepted' else "❌"
    status_text = "ожидает рассмотрения" if application.get('status') == 'pending' else "принята" if application.get('status') == 'accepted' else "отклонена"
    text += f"📊 Статус: {status_emoji} {status_text}\n"
    
    if application.get('status') == 'accepted' and application.get('accepted_at'):
        text += f"✅ Подтверждена: {datetime.fromisoformat(application['accepted_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    if application.get('status') == 'rejected' and application.get('rejected_reason'):
        text += f"📝 Причина отказа: {application.get('rejected_reason')}\n"
    
    # Информация о пользователе из заявки
    text += f"\n👤 Ваши данные в заявке:\n"
    text += f"Имя: {application.get('user_name', 'Не указано')}\n"
    text += f"Телефон: {application.get('phone', 'Не указан')}\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            builder.button(text="⬅️ Предыдущая", callback_data=f"my_applications_list:{page-1}")
        if page < total_pages - 1:
            builder.button(text="Следующая ➡️", callback_data=f"my_applications_list:{page+1}")
    
    # Кнопка для просмотра турнира (если турнир существует)
    if tournament_data:
        builder.button(text="👀 Посмотреть турнир", callback_data=f"view_tournament:{application['tournament_id']}")
    
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_start")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_pages > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    if tournament_data:
        builder.adjust(1)  # Кнопка просмотра турнира
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Просмотр турнира из заявки
@router.callback_query(F.data.startswith("view_tournament:"))
async def view_tournament_from_application(callback: CallbackQuery):
    """Показывает турнир из заявки"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Находим индекс турнира в списке активных турниров
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    tournament_ids = list(active_tournaments.keys())
    
    if tournament_id not in tournament_ids:
        await callback.answer("❌ Турнир больше не активен")
        return
    
    page = tournament_ids.index(tournament_id)
    
    # Переходим к просмотру турнира через новую систему
    await callback.answer("❌ Функция временно недоступна. Используйте главное меню турниров.")

# Просмотр своих турниров с пагинацией
@router.callback_query(F.data.startswith("my_tournaments_list:"))
async def my_tournaments_list(callback: CallbackQuery):
    """Показывает турниры пользователя с пагинацией"""
    page = int(callback.data.split(':')[1])
    user_id = callback.from_user.id
    tournaments = await storage.load_tournaments()
    
    # Получаем все турниры пользователя
    user_tournaments = []
    for tournament_id, tournament_data in tournaments.items():
        if str(user_id) in tournament_data.get('participants', {}):
            user_tournaments.append((tournament_id, tournament_data))
    
    if not user_tournaments:
        await callback.message.edit_text("🎾 Вы пока не участвуете ни в одном турнире.")
        await callback.answer()
        return
    
    # Сохраняем список турниров для пагинации
    my_tournaments_pages[callback.from_user.id] = user_tournaments
    
    # Вычисляем общее количество страниц
    total_pages = len(user_tournaments)
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Получаем турнир для текущей страницы
    tournament_id, tournament_data = user_tournaments[page]
    participant_data = tournament_data['participants'][str(user_id)]
    
    # Формируем текст для текущего турнира
    text = f"🏆 Ваш турнир {page + 1}/{total_pages}\n\n"
    text += f"📋 Название: {tournament_data.get('name', 'Без названия')}\n"
    text += f"🏙️ Город: {tournament_data.get('city', 'Не указан')}\n"
    text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"👥 Участников: {len(tournament_data.get('participants', {}))}\n"
    text += f"📊 Статус: {tournament_data.get('status', 'Не указан')}\n\n"
    
    if tournament_data.get('description'):
        text += f"📝 Описание: {tournament_data.get('description')}\n\n"
    
    if tournament_data.get('rules'):
        text += f"📋 Правила: {tournament_data.get('rules')}\n\n"
    
    if tournament_data.get('prize_fund'):
        text += f"💰 Призовой фонд: {tournament_data.get('prize_fund')}\n\n"
    
    # Информация о регистрации
    if participant_data.get('accepted_at'):
        text += f"✅ Подтверждено: {datetime.fromisoformat(participant_data['accepted_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    if participant_data.get('applied_at'):
        text += f"📅 Заявка подана: {datetime.fromisoformat(participant_data['applied_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            builder.button(text="⬅️ Предыдущий", callback_data=f"my_tournaments_list:{page-1}")
        if page < total_pages - 1:
            builder.button(text="Следующий ➡️", callback_data=f"my_tournaments_list:{page+1}")
    
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_start")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_pages > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Команда просмотра заявок на турниры (только для админов)
@router.message(Command("view_tournament_applications"))
async def view_tournament_applications_command(message: Message, state: FSMContext):
    """Команда для просмотра заявок на турниры (только админы)"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Фильтруем только ожидающие заявки
    pending_applications = {k: v for k, v in applications.items() if v.get('status') == 'pending'}
    
    if not pending_applications:
        await message.answer("📋 Нет заявок на рассмотрение")
        return
    
    text = "📋 Заявки на турниры (ожидают рассмотрения)\n\n"
    
    for app_id, app_data in pending_applications.items():
        tournament_id = app_data.get('tournament_id')
        tournament_data = tournaments.get(tournament_id, {})
        
        text += f"🆔 Заявка: {app_id}\n"
        text += f"👤 Пользователь: {app_data.get('user_name', 'Не указано')}\n"
        text += f"📞 Телефон: {app_data.get('phone', 'Не указан')}\n"
        text += f"🏆 Турнир: {tournament_data.get('name', 'Неизвестный турнир')}\n"
        text += f"📅 Подана: {datetime.fromisoformat(app_data['applied_at']).strftime('%d.%m.%Y %H:%M')}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять заявку", callback_data="admin_accept_application_menu")
    builder.button(text="❌ Отклонить заявку", callback_data="admin_reject_application_menu")
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Обработчик меню принятия заявки
@router.callback_query(F.data == "admin_accept_application_menu")
async def admin_accept_application_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора заявки для принятия"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Фильтруем только ожидающие заявки
    pending_applications = {k: v for k, v in applications.items() if v.get('status') == 'pending'}
    
    if not pending_applications:
        await callback.message.edit_text("📋 Нет заявок на рассмотрение")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for app_id, app_data in pending_applications.items():
        tournament_id = app_data.get('tournament_id')
        tournament_data = tournaments.get(tournament_id, {})
        tournament_name = tournament_data.get('name', 'Неизвестный турнир')
        user_name = app_data.get('user_name', 'Не указано')
        
        builder.button(
            text=f"✅ {user_name} - {tournament_name}", 
            callback_data=f"admin_accept_application:{app_id}"
        )
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "✅ Принятие заявки на турнир\n\n"
        "Выберите заявку для принятия:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик принятия заявки
@router.callback_query(F.data.startswith("admin_accept_application:"))
async def admin_accept_application(callback: CallbackQuery, state: FSMContext):
    """Принятие заявки на турнир"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    app_id = callback.data.split(":", 1)[1]
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    if app_id not in applications:
        await callback.answer("❌ Заявка не найдена")
        return
    
    app_data = applications[app_id]
    tournament_id = app_data.get('tournament_id')
    user_id = app_data.get('user_id')
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    # Проверяем, не добавлен ли уже этот пользователь
    if str(user_id) in participants:
        await callback.answer("❌ Пользователь уже участвует в турнире")
        return
    
    # Загружаем данные пользователя
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден в системе")
        return
    
    # Обновляем статус заявки
    applications[app_id]['status'] = 'accepted'
    applications[app_id]['accepted_at'] = datetime.now().isoformat()
    applications[app_id]['accepted_by'] = callback.from_user.id
    await storage.save_tournament_applications(applications)
    
    # Добавляем участника в турнир
    participants[str(user_id)] = {
        'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
        'phone': user_data.get('phone', 'Не указан'),
        'added_at': datetime.now().isoformat(),
        'added_by': callback.from_user.id,
        'application_id': app_id
    }
    
    tournament_data['participants'] = participants
    await storage.save_tournaments(tournaments)
    
    # Проверяем, готов ли турнир к запуску
    tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
    
    success_message = f"✅ Заявка принята!\n\n"
    success_message += f"👤 Пользователь: {app_data.get('user_name', 'Не указано')}\n"
    success_message += f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
    success_message += f"📅 Принята: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    
    if tournament_ready and tournament_data.get('status') == 'active':
        # Запускаем турнир
        tournament_started = await tournament_manager.start_tournament(tournament_id)
        
        if tournament_started:
            success_message += f"🎉 *Турнир автоматически запущен!*\n\n"
            success_message += f"🏆 Набрано минимальное количество участников\n"
            success_message += f"⚔️ Матчи распределены и отправлены участникам\n\n"
            
            # Отправляем уведомления участникам
            try:
                from main import bot  # Импортируем бота
                notifications = TournamentNotifications(bot)
                await notifications.notify_tournament_started(tournament_id, tournament_data)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомлений о начале турнира: {e}")
    else:
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
        current_count = len(participants)
        success_message += f"📊 Участников: {current_count}/{min_participants}\n"
        success_message += f"⏳ Дождитесь набора минимального количества участников\n"
    
    # Отправляем уведомление пользователю
    try:
        from main import bot
        await bot.send_message(
            user_id,
            f"🎉 Ваша заявка принята!\n\n"
            f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
            f"📅 Принята: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Добро пожаловать в турнир!"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 К заявкам", callback_data="admin_accept_application_menu")
    builder.button(text="🔙 Главное меню", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(
        success_message,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )
    await callback.answer()

# Обработчик меню отклонения заявки
@router.callback_query(F.data == "admin_reject_application_menu")
async def admin_reject_application_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора заявки для отклонения"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Фильтруем только ожидающие заявки
    pending_applications = {k: v for k, v in applications.items() if v.get('status') == 'pending'}
    
    if not pending_applications:
        await callback.message.edit_text("📋 Нет заявок на рассмотрение")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for app_id, app_data in pending_applications.items():
        tournament_id = app_data.get('tournament_id')
        tournament_data = tournaments.get(tournament_id, {})
        tournament_name = tournament_data.get('name', 'Неизвестный турнир')
        user_name = app_data.get('user_name', 'Не указано')
        
        builder.button(
            text=f"❌ {user_name} - {tournament_name}", 
            callback_data=f"admin_reject_application:{app_id}"
        )
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "❌ Отклонение заявки на турнир\n\n"
        "Выберите заявку для отклонения:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик отклонения заявки
@router.callback_query(F.data.startswith("admin_reject_application:"))
async def admin_reject_application(callback: CallbackQuery, state: FSMContext):
    """Отклонение заявки на турнир"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    app_id = callback.data.split(":", 1)[1]
    
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    if app_id not in applications:
        await callback.answer("❌ Заявка не найдена")
        return
    
    app_data = applications[app_id]
    tournament_id = app_data.get('tournament_id')
    user_id = app_data.get('user_id')
    
    tournament_data = tournaments.get(tournament_id, {})
    
    # Обновляем статус заявки
    applications[app_id]['status'] = 'rejected'
    applications[app_id]['rejected_at'] = datetime.now().isoformat()
    applications[app_id]['rejected_by'] = callback.from_user.id
    applications[app_id]['rejected_reason'] = 'Отклонено администратором'
    await storage.save_tournament_applications(applications)
    
    # Отправляем уведомление пользователю
    try:
        from main import bot
        await bot.send_message(
            user_id,
            f"❌ Ваша заявка отклонена\n\n"
            f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
            f"📅 Отклонена: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"📝 Причина: Отклонено администратором\n\n"
            f"Вы можете подать заявку на другой турнир."
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 К заявкам", callback_data="admin_reject_application_menu")
    builder.button(text="🔙 Главное меню", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"❌ Заявка отклонена!\n\n"
        f"👤 Пользователь: {app_data.get('user_name', 'Не указано')}\n"
        f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
        f"📅 Отклонена: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Пользователь получил уведомление об отклонении.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Команда просмотра участников турниров (только для админов)
@router.message(Command("view_tournament_participants"))
async def view_tournament_participants_command(message: Message, state: FSMContext):
    """Команда для просмотра участников турниров (только админы)"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await message.answer("📋 Нет турниров для просмотра")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        participants_count = len(tournament_data.get('participants', {}))
        builder.button(text=f"🏆 {name} ({city}) - {participants_count} участников", 
                      callback_data=f"admin_view_participants:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await message.answer(
        "👥 Просмотр участников турниров\n\n"
        "Выберите турнир для просмотра участников:",
        reply_markup=builder.as_markup()
    )

# Команда редактирования турниров (только для админов)
@router.message(Command("edit_tournaments"))
async def edit_tournaments_command(message: Message, state: FSMContext):
    """Команда для редактирования турниров (только админы)"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await message.answer("📋 Нет турниров для редактирования")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        builder.button(text=f"🏆 {name} ({city})", callback_data=f"edit_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await message.answer(
        "🏆 Редактирование турниров\n\n"
        "Выберите турнир для редактирования:",
        reply_markup=builder.as_markup()
    )

# Обработчик просмотра участников турнира (для админа)
@router.callback_query(F.data.startswith("admin_view_participants:"))
async def admin_view_tournament_participants(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра участников турнира для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"👥 Участники турнира\n\n"
    text += f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
    text += f"📍 Место: {location}\n"
    text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"👥 Всего участников: {len(participants)}/{tournament_data.get('participants_count', 'Не указано')}\n\n"
    
    if participants:
        text += "📋 Список участников:\n"
        for i, (user_id, participant_data) in enumerate(participants.items(), 1):
            name = participant_data.get('name', 'Неизвестно')
            phone = participant_data.get('phone', 'Не указан')
            added_at = participant_data.get('added_at', '')
            
            # Форматируем дату добавления
            if added_at:
                try:
                    added_date = datetime.fromisoformat(added_at)
                    added_str = added_date.strftime('%d.%m.%Y %H:%M')
                except:
                    added_str = added_at
            else:
                added_str = 'Не указано'
            
            text += f"{i}. {name}\n"
            text += f"   📞 Телефон: {phone}\n"
            text += f"   🆔 ID: {user_id}\n"
            text += f"   📅 Добавлен: {added_str}\n\n"
    else:
        text += "📋 Участников пока нет\n"
    
    builder = InlineKeyboardBuilder()
    
    if participants:
        builder.button(text="🗑️ Удалить участника", callback_data=f"admin_remove_participant_menu:{tournament_id}")
    
    builder.button(text="➕ Добавить участника", callback_data=f"admin_add_participant:{tournament_id}")
    builder.button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
    builder.button(text="🏠 Главное меню", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик просмотра истории игр турнира
@router.callback_query(F.data.startswith("tournament_games_history:"))
async def tournament_games_history(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра истории игр турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id)
    
    if not tournament_data:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Загружаем игры
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Фильтруем игры турнира
    tournament_games = []
    for game in games:
        if game.get('tournament_id') == tournament_id:
            tournament_games.append(game)
    
    if not tournament_games:
        await callback.message.edit_text(
            f"🏆 История игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
            "📊 Пока нет сыгранных игр в этом турнире.",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"view_tournament_city:{tournament_data.get('city', 'Не указан')}")
            .as_markup()
        )
        await callback.answer()
        return
    
    # Сортируем игры по дате (новые сначала)
    tournament_games.sort(key=lambda x: x['date'], reverse=True)
    
    # Формируем краткую информацию об играх
    history_text = f"🏆 История игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
    history_text += f"📊 Всего игр: {len(tournament_games)}\n\n"
    
    for i, game in enumerate(tournament_games[:10], 1):  # Показываем последние 10 игр
        game_date = datetime.fromisoformat(game['date'])
        formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
        
        # Определяем победителя
        team1_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
        team2_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
        
        if team1_wins > team2_wins:
            winner_id = game['players']['team1'][0]
            loser_id = game['players']['team2'][0]
        else:
            winner_id = game['players']['team2'][0]
            loser_id = game['players']['team1'][0]
        
        winner = users.get(winner_id, {})
        loser = users.get(loser_id, {})
        
        winner_name = f"{winner.get('first_name', '')} {winner.get('last_name', '')}".strip()
        loser_name = f"{loser.get('first_name', '')} {loser.get('last_name', '')}".strip()
        
        history_text += f"{i}. 📅 {formatted_date}\n"
        history_text += f"   🥇 {winner_name} победил {loser_name}\n"
        history_text += f"   📊 Счет: {game['score']}\n\n"
    
    if len(tournament_games) > 10:
        history_text += f"... и еще {len(tournament_games) - 10} игр\n\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопка для админа - подробный просмотр
    if await is_admin(callback.from_user.id):
        builder.button(text="🔧 Подробный просмотр (Админ)", callback_data=f"admin_tournament_games:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data=f"view_tournament_city:{tournament_data.get('city', 'Не указан')}")
    
    await callback.message.edit_text(history_text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик подробного просмотра игр турнира для админа
@router.callback_query(F.data.startswith("admin_tournament_games:"))
async def admin_tournament_games(callback: CallbackQuery, state: FSMContext):
    """Обработчик подробного просмотра игр турнира для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id)
    
    if not tournament_data:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Загружаем игры
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Фильтруем игры турнира
    tournament_games = []
    for game in games:
        if game.get('tournament_id') == tournament_id:
            tournament_games.append(game)
    
    if not tournament_games:
        await callback.message.edit_text(
            f"🏆 Подробная история игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
            "📊 Пока нет сыгранных игр в этом турнире.",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"tournament_games_history:{tournament_id}")
            .as_markup()
        )
        await callback.answer()
        return
    
    # Сортируем игры по дате (новые сначала)
    tournament_games.sort(key=lambda x: x['date'], reverse=True)
    
    # Формируем подробную информацию об играх
    history_text = f"🏆 Подробная история игр турнира \"{tournament_data.get('name', 'Неизвестный турнир')}\"\n\n"
    history_text += f"📊 Всего игр: {len(tournament_games)}\n\n"
    
    for i, game in enumerate(tournament_games, 1):
        game_date = datetime.fromisoformat(game['date'])
        formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
        
        # Определяем победителя
        team1_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
        team2_wins = sum(1 for set_score in game['sets'] 
                        if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
        
        if team1_wins > team2_wins:
            winner_id = game['players']['team1'][0]
            loser_id = game['players']['team2'][0]
        else:
            winner_id = game['players']['team2'][0]
            loser_id = game['players']['team1'][0]
        
        winner = users.get(winner_id, {})
        loser = users.get(loser_id, {})
        
        winner_name = f"{winner.get('first_name', '')} {winner.get('last_name', '')}".strip()
        loser_name = f"{loser.get('first_name', '')} {loser.get('last_name', '')}".strip()
        
        history_text += f"{i}. 📅 {formatted_date}\n"
        history_text += f"   🥇 {winner_name} победил {loser_name}\n"
        history_text += f"   📊 Счет: {game['score']}\n"
        history_text += f"   🆔 ID игры: {game['id']}\n"
        
        if game.get('media_filename'):
            history_text += f"   📷 Есть медиафайл\n"
        
        history_text += "\n"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждой игры (редактирование)
    for i, game in enumerate(tournament_games[:5], 1):  # Показываем первые 5 игр
        builder.button(text=f"✏️ Игра {i}", callback_data=f"admin_edit_game:{game['id']}")
    
    if len(tournament_games) > 5:
        builder.button(text="📄 Показать еще", callback_data=f"admin_tournament_games_more:{tournament_id}:5")
    
    builder.button(text="🔙 Назад", callback_data=f"tournament_games_history:{tournament_id}")
    
    await callback.message.edit_text(history_text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик редактирования игры админом
@router.callback_query(F.data.startswith("admin_edit_game:"))
async def admin_edit_game(callback: CallbackQuery, state: FSMContext):
    """Обработчик редактирования игры админом"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await callback.answer("❌ Игра не найдена")
        return
    
    # Получаем информацию об игроках
    player1_id = game['players']['team1'][0]
    player2_id = game['players']['team2'][0]
    
    player1 = users.get(player1_id, {})
    player2 = users.get(player2_id, {})
    
    player1_name = f"{player1.get('first_name', '')} {player1.get('last_name', '')}".strip()
    player2_name = f"{player2.get('first_name', '')} {player2.get('last_name', '')}".strip()
    
    # Определяем текущего победителя
    team1_wins = sum(1 for set_score in game['sets'] 
                    if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
    team2_wins = sum(1 for set_score in game['sets'] 
                    if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
    
    if team1_wins > team2_wins:
        current_winner = player1_name
    else:
        current_winner = player2_name
    
    game_date = datetime.fromisoformat(game['date'])
    formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
    
    # Формируем информацию об игре
    game_text = f"🔧 Редактирование игры (Админ)\n\n"
    game_text += f"🆔 ID игры: {game_id}\n"
    game_text += f"📅 Дата: {formatted_date}\n"
    game_text += f"👤 Игрок 1: {player1_name}\n"
    game_text += f"👤 Игрок 2: {player2_name}\n"
    game_text += f"📊 Текущий счет: {game['score']}\n"
    game_text += f"🥇 Текущий победитель: {current_winner}\n"
    
    if game.get('media_filename'):
        game_text += f"📷 Медиафайл: {game['media_filename']}\n"
    
    # Создаем клавиатуру для редактирования
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить счет", callback_data=f"admin_edit_game_score:{game_id}")
    builder.button(text="📷 Изменить медиа", callback_data=f"admin_edit_game_media:{game_id}")
    builder.button(text="🔄 Изменить победителя", callback_data=f"admin_edit_game_winner:{game_id}")
    builder.button(text="🗑️ Удалить игру", callback_data=f"admin_delete_game:{game_id}")
    builder.button(text="🔙 Назад", callback_data=f"admin_tournament_games:{game.get('tournament_id', '')}")
    builder.adjust(1)
    
    await callback.message.edit_text(game_text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик изменения счета игры
@router.callback_query(F.data.startswith("admin_edit_game_score:"))
async def admin_edit_game_score(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения счета игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_SCORE)
    
    await callback.message.edit_text(
        f"✏️ Изменение счета игры {game_id}\n\n"
        "Введите новый счет в формате:\n"
        "6:4, 6:2 (для нескольких сетов)\n"
        "или\n"
        "6:4 (для одного сета)\n\n"
        "Примеры:\n"
        "• 6:4, 6:2\n"
        "• 7:5, 6:4, 6:2\n"
        "• 6:0",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик изменения медиафайла игры
@router.callback_query(F.data.startswith("admin_edit_game_media:"))
async def admin_edit_game_media(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения медиафайла игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_MEDIA)
    
    await callback.message.edit_text(
        f"📷 Изменение медиафайла игры {game_id}\n\n"
        "Отправьте новое фото или видео для игры.\n"
        "Или отправьте 'удалить' чтобы удалить медиафайл.",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик изменения победителя игры
@router.callback_query(F.data.startswith("admin_edit_game_winner:"))
async def admin_edit_game_winner(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения победителя игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await callback.answer("❌ Игра не найдена")
        return
    
    # Получаем информацию об игроках
    player1_id = game['players']['team1'][0]
    player2_id = game['players']['team2'][0]
    
    player1 = users.get(player1_id, {})
    player2 = users.get(player2_id, {})
    
    player1_name = f"{player1.get('first_name', '')} {player1.get('last_name', '')}".strip()
    player2_name = f"{player2.get('first_name', '')} {player2.get('last_name', '')}".strip()
    
    await state.update_data(editing_game_id=game_id)
    await state.set_state(AdminEditGameStates.EDIT_WINNER)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🥇 {player1_name}", callback_data=f"admin_set_winner:{game_id}:team1")
    builder.button(text=f"🥇 {player2_name}", callback_data=f"admin_set_winner:{game_id}:team2")
    builder.button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🔄 Изменение победителя игры {game_id}\n\n"
        f"Текущий счет: {game['score']}\n\n"
        "Выберите нового победителя:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик ввода нового счета
@router.message(AdminEditGameStates.EDIT_SCORE)
async def admin_edit_score_input(message: Message, state: FSMContext):
    """Обработчик ввода нового счета игры"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        await state.clear()
        return
    
    new_score = message.text.strip()
    data = await state.get_data()
    game_id = data.get('editing_game_id')
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await message.answer("❌ Игра не найдена")
        await state.clear()
        return
    
    # Парсим новый счет
    try:
        sets = [s.strip() for s in new_score.split(',')]
        for s in sets:
            parts = s.split(':')
            if len(parts) != 2:
                raise ValueError("Неверный формат счета")
            int(parts[0])
            int(parts[1])
        
        # Обновляем игру
        game['score'] = new_score
        game['sets'] = sets
        
        # Сохраняем изменения
        await storage.save_games(games)
        
        await message.answer(
            f"✅ Счет игры {game_id} успешно изменен на: {new_score}",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат счета. Используйте формат: 6:4, 6:2",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    
    await state.clear()

# Обработчик изменения медиафайла
@router.message(AdminEditGameStates.EDIT_MEDIA)
async def admin_edit_media_input(message: Message, state: FSMContext):
    """Обработчик изменения медиафайла игры"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        await state.clear()
        return
    
    data = await state.get_data()
    game_id = data.get('editing_game_id')
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await message.answer("❌ Игра не найдена")
        await state.clear()
        return
    
    if message.text and message.text.lower() == 'удалить':
        # Удаляем медиафайл
        game['media_filename'] = None
        await storage.save_games(games)
        await message.answer(
            f"✅ Медиафайл игры {game_id} удален",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    elif message.photo:
        # Сохраняем новое фото
        photo_id = message.photo[-1].file_id
        # Здесь можно добавить сохранение фото на диск
        await message.answer(
            f"✅ Новое фото для игры {game_id} получено\n"
            f"ID фото: {photo_id}",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    elif message.video:
        # Сохраняем новое видео
        video_id = message.video.file_id
        await message.answer(
            f"✅ Новое видео для игры {game_id} получено\n"
            f"ID видео: {video_id}",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    else:
        await message.answer(
            "❌ Отправьте фото, видео или напишите 'удалить'",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=f"admin_edit_game:{game_id}")
            .as_markup()
        )
    
    await state.clear()

# Обработчик установки нового победителя
@router.callback_query(F.data.startswith("admin_set_winner:"))
async def admin_set_winner(callback: CallbackQuery, state: FSMContext):
    """Обработчик установки нового победителя игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    parts = callback.data.split(":")
    game_id = parts[1]
    winner_team = parts[2]
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим игру
    game = None
    for g in games:
        if g['id'] == game_id:
            game = g
            break
    
    if not game:
        await callback.answer("❌ Игра не найдена")
        return
    
    # Обновляем счет так, чтобы выбранная команда стала победителем
    if winner_team == "team1":
        # Команда 1 должна выиграть больше сетов
        new_sets = ["6:4", "6:2"]  # Простой пример
    else:
        # Команда 2 должна выиграть больше сетов
        new_sets = ["4:6", "2:6"]  # Простой пример
    
    game['sets'] = new_sets
    game['score'] = ", ".join(new_sets)
    
    # Сохраняем изменения
    await storage.save_games(games)
    
    await callback.message.edit_text(
        f"✅ Победитель игры {game_id} изменен\n"
        f"Новый счет: {game['score']}",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 К редактированию", callback_data=f"admin_edit_game:{game_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик удаления игры
@router.callback_query(F.data.startswith("admin_delete_game:"))
async def admin_delete_game(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления игры"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    game_id = callback.data.split(":", 1)[1]
    
    # Загружаем игры
    games = await storage.load_games()
    
    # Находим и удаляем игру
    games = [g for g in games if g['id'] != game_id]
    
    # Сохраняем изменения
    await storage.save_games(games)
    
    await callback.message.edit_text(
        f"✅ Игра {game_id} удалена",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 К списку игр", callback_data=f"admin_tournament_games:{callback.data.split(':')[1] if ':' in callback.data else ''}")
        .as_markup()
    )
    await callback.answer()

# Обработчик выбора турнира для редактирования
@router.callback_query(F.data.startswith("edit_tournament:"))
async def select_tournament_for_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора турнира для редактирования"""
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Сохраняем ID турнира в состоянии
    await state.update_data(editing_tournament_id=tournament_id)
    
    # Формируем информацию о турнире
    location = f"{tournament_data.get('city', 'Не указан')}"
    if tournament_data.get('district'):
        location += f" ({tournament_data['district']})"
    location += f", {tournament_data.get('country', 'Не указана')}"
    
    text = f"🏆 Редактирование турнира\n\n"
    text += f"📋 Информация о турнире:\n\n"
    text += f"🏓 Вид спорта: {tournament_data.get('sport', 'Не указан')}\n"
    text += f"🌍 Место: {location}\n"
    text += f"⚔️ Тип: {tournament_data.get('type', 'Не указан')}\n"
    text += f"👥 Пол: {tournament_data.get('gender', 'Не указан')}\n"
    text += f"🏆 Категория: {tournament_data.get('category', 'Не указана')}\n"
    text += f"👶 Возраст: {tournament_data.get('age_group', 'Не указан')}\n"
    text += f"⏱️ Продолжительность: {tournament_data.get('duration', 'Не указана')}\n"
    text += f"👥 Участников: {tournament_data.get('participants_count', 'Не указано')}\n"
    text += f"📋 В списке города: {'Да' if tournament_data.get('show_in_list', False) else 'Нет'}\n"
    text += f"🔒 Скрыть сетку: {'Да' if tournament_data.get('hide_bracket', False) else 'Нет'}\n"
    if tournament_data.get('comment'):
        text += f"💬 Комментарий: {tournament_data['comment']}\n"
    
    # Показываем участников
    participants = tournament_data.get('participants', {})
    if participants:
        text += f"\n👥 Участники ({len(participants)}):\n"
        for user_id, participant_data in participants.items():
            text += f"• {participant_data.get('name', 'Неизвестно')} (ID: {user_id})\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать поля", callback_data="edit_tournament_fields")
    builder.button(text="👥 Управление участниками", callback_data="manage_tournament_participants")
    builder.button(text="🗑️ Удалить турнир", callback_data=f"delete_tournament_confirm:{tournament_id}")
    builder.button(text="🔙 Назад", callback_data="edit_tournaments_back")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик редактирования полей турнира
@router.callback_query(F.data == "edit_tournament_fields")
async def edit_tournament_fields(callback: CallbackQuery, state: FSMContext):
    """Обработчик редактирования полей турнира"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏓 Вид спорта", callback_data="edit_field:sport")
    builder.button(text="🌍 Страна", callback_data="edit_field:country")
    builder.button(text="🏙️ Город", callback_data="edit_field:city")
    builder.button(text="📍 Район", callback_data="edit_field:district")
    builder.button(text="⚔️ Тип", callback_data="edit_field:type")
    builder.button(text="👥 Пол", callback_data="edit_field:gender")
    builder.button(text="🏆 Категория", callback_data="edit_field:category")
    builder.button(text="👶 Возраст", callback_data="edit_field:age_group")
    builder.button(text="⏱️ Продолжительность", callback_data="edit_field:duration")
    builder.button(text="👥 Количество участников", callback_data="edit_field:participants_count")
    builder.button(text="📋 Показывать в списке", callback_data="edit_field:show_in_list")
    builder.button(text="🔒 Скрыть сетку", callback_data="edit_field:hide_bracket")
    builder.button(text="💬 Комментарий", callback_data="edit_field:comment")
    builder.button(text="🔙 Назад", callback_data="edit_tournament_back")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "✏️ Редактирование полей турнира\n\n"
        "Выберите поле для редактирования:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик выбора поля для редактирования
@router.callback_query(F.data.startswith("edit_field:"))
async def select_field_to_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора поля для редактирования"""
    field = callback.data.split(":", 1)[1]
    
    # Сохраняем поле в состоянии
    await state.update_data(editing_field=field)
    
    tournaments = await storage.load_tournaments()
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    tournament_data = tournaments[tournament_id]
    
    if field == "sport":
        builder = InlineKeyboardBuilder()
        for sport in SPORTS:
            selected = "✅" if sport == tournament_data.get('sport') else ""
            builder.button(text=f"{selected} {sport}", callback_data=f"update_field:{sport}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"🏓 Редактирование: Вид спорта\n\n"
            f"Текущее значение: {tournament_data.get('sport', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "country":
        builder = InlineKeyboardBuilder()
        for country in COUNTRIES:
            selected = "✅" if country == tournament_data.get('country') else ""
            builder.button(text=f"{selected} {country}", callback_data=f"update_field:{country}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"🌍 Редактирование: Страна\n\n"
            f"Текущее значение: {tournament_data.get('country', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "city":
        current_country = tournament_data.get('country', '🇷🇺 Россия')
        cities = get_cities_for_country(current_country)
        
        builder = InlineKeyboardBuilder()
        for city in cities:
            selected = "✅" if city == tournament_data.get('city') else ""
            builder.button(text=f"{selected} {city}", callback_data=f"update_field:{city}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"🏙️ Редактирование: Город\n\n"
            f"Текущее значение: {tournament_data.get('city', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "district":
        if tournament_data.get('city') == "Москва":
            builder = InlineKeyboardBuilder()
            for district in DISTRICTS_MOSCOW:
                selected = "✅" if district == tournament_data.get('district') else ""
                builder.button(text=f"{selected} {district}", callback_data=f"update_field:{district}")
            builder.adjust(2)
            
            await callback.message.edit_text(
                f"📍 Редактирование: Район\n\n"
                f"Текущее значение: {tournament_data.get('district', 'Не указан')}\n\n"
                f"Выберите новое значение:",
                reply_markup=builder.as_markup()
            )
        else:
            await callback.message.edit_text(
                f"📍 Редактирование: Район\n\n"
                f"Для города {tournament_data.get('city', 'Не указан')} выбор района недоступен.\n"
                f"Район можно выбрать только для Москвы.",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_fields").as_markup()
            )
    
    elif field == "type":
        builder = InlineKeyboardBuilder()
        for t_type in TOURNAMENT_TYPES:
            selected = "✅" if t_type == tournament_data.get('type') else ""
            builder.button(text=f"{selected} {t_type}", callback_data=f"update_field:{t_type}")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"⚔️ Редактирование: Тип турнира\n\n"
            f"Текущее значение: {tournament_data.get('type', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "gender":
        builder = InlineKeyboardBuilder()
        for gender in GENDERS:
            selected = "✅" if gender == tournament_data.get('gender') else ""
            builder.button(text=f"{selected} {gender}", callback_data=f"update_field:{gender}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"👥 Редактирование: Пол участников\n\n"
            f"Текущее значение: {tournament_data.get('gender', 'Не указан')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "category":
        builder = InlineKeyboardBuilder()
        for category in CATEGORIES:
            selected = "✅" if category == tournament_data.get('category') else ""
            builder.button(text=f"{selected} {category}", callback_data=f"update_field:{category}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"🏆 Редактирование: Категория\n\n"
            f"Текущее значение: {tournament_data.get('category', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "age_group":
        builder = InlineKeyboardBuilder()
        for age_group in AGE_GROUPS:
            selected = "✅" if age_group == tournament_data.get('age_group') else ""
            builder.button(text=f"{selected} {age_group}", callback_data=f"update_field:{age_group}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"👶 Редактирование: Возрастная группа\n\n"
            f"Текущее значение: {tournament_data.get('age_group', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "duration":
        builder = InlineKeyboardBuilder()
        for duration in DURATIONS:
            selected = "✅" if duration == tournament_data.get('duration') else ""
            builder.button(text=f"{selected} {duration}", callback_data=f"update_field:{duration}")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"⏱️ Редактирование: Продолжительность\n\n"
            f"Текущее значение: {tournament_data.get('duration', 'Не указана')}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "participants_count":
        await callback.message.edit_text(
            f"👥 Редактирование: Количество участников\n\n"
            f"Текущее значение: {tournament_data.get('participants_count', 'Не указано')}\n\n"
            f"Введите новое количество участников (число):",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_fields").as_markup()
        )
        await state.set_state(EditTournamentStates.EDIT_PARTICIPANTS_COUNT)
    
    elif field == "show_in_list":
        current_value = tournament_data.get('show_in_list', False)
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            selected = "✅" if (option == "Да" and current_value) or (option == "Нет" and not current_value) else ""
            builder.button(text=f"{selected} {option}", callback_data=f"update_field:{option}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"📋 Редактирование: Показывать в списке города\n\n"
            f"Текущее значение: {'Да' if current_value else 'Нет'}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "hide_bracket":
        current_value = tournament_data.get('hide_bracket', False)
        builder = InlineKeyboardBuilder()
        for option in YES_NO_OPTIONS:
            selected = "✅" if (option == "Да" and current_value) or (option == "Нет" and not current_value) else ""
            builder.button(text=f"{selected} {option}", callback_data=f"update_field:{option}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"🔒 Редактирование: Скрыть турнирную сетку\n\n"
            f"Текущее значение: {'Да' if current_value else 'Нет'}\n\n"
            f"Выберите новое значение:",
            reply_markup=builder.as_markup()
        )
    
    elif field == "comment":
        await callback.message.edit_text(
            f"💬 Редактирование: Комментарий\n\n"
            f"Текущее значение: {tournament_data.get('comment', 'Нет комментария')}\n\n"
            f"Введите новый комментарий (или отправьте '-' чтобы удалить):",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="edit_tournament_fields").as_markup()
        )
        await state.set_state(EditTournamentStates.EDIT_COMMENT)
    
    await callback.answer()

# Обработчик обновления поля
@router.callback_query(F.data.startswith("update_field:"))
async def update_tournament_field(callback: CallbackQuery, state: FSMContext):
    """Обработчик обновления поля турнира"""
    new_value = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    field = data.get('editing_field')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    # Обновляем поле
    if field == "show_in_list":
        tournament_data[field] = new_value == "Да"
    elif field == "hide_bracket":
        tournament_data[field] = new_value == "Да"
    else:
        tournament_data[field] = new_value
    
    # Сохраняем изменения
    await storage.save_tournaments(tournaments)
    
    await callback.message.edit_text(
        f"✅ Поле '{field}' успешно обновлено!\n\n"
        f"Новое значение: {new_value}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="✏️ Редактировать еще", callback_data="edit_tournament_fields")
        .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        .adjust(1)
        .as_markup()
    )
    await callback.answer()

# Обработчик ввода количества участников
@router.message(EditTournamentStates.EDIT_PARTICIPANTS_COUNT)
async def edit_participants_count(message: Message, state: FSMContext):
    """Обработчик ввода количества участников"""
    try:
        count = int(message.text.strip())
        if count <= 0:
            await message.answer("❌ Количество участников должно быть больше 0. Попробуйте еще раз:")
            return
        
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id')
        
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        tournament_data['participants_count'] = count
        
        await storage.save_tournaments(tournaments)
        
        await message.answer(
            f"✅ Количество участников обновлено!\n\n"
            f"Новое значение: {count}\n\n"
            f"Выберите действие:",
            reply_markup=InlineKeyboardBuilder()
            .button(text="✏️ Редактировать еще", callback_data="edit_tournament_fields")
            .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
            .adjust(1)
            .as_markup()
        )
        
    except ValueError:
        await message.answer("❌ Введите корректное число. Попробуйте еще раз:")

# Обработчик ввода комментария
@router.message(EditTournamentStates.EDIT_COMMENT)
async def edit_comment(message: Message, state: FSMContext):
    """Обработчик ввода комментария"""
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    tournament_data['comment'] = comment
    
    await storage.save_tournaments(tournaments)
    
    await message.answer(
        f"✅ Комментарий обновлен!\n\n"
        f"Новое значение: {comment if comment else 'Нет комментария'}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="✏️ Редактировать еще", callback_data="edit_tournament_fields")
        .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        .adjust(1)
        .as_markup()
    )

# Обработчик управления участниками
@router.callback_query(F.data == "manage_tournament_participants")
async def manage_tournament_participants(callback: CallbackQuery, state: FSMContext):
    """Обработчик управления участниками турнира"""
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    text = f"👥 Управление участниками турнира\n\n"
    text += f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
    text += f"👥 Участников: {len(participants)}/{tournament_data.get('participants_count', 'Не указано')}\n\n"
    
    if participants:
        text += "📋 Список участников:\n"
        for user_id, participant_data in participants.items():
            text += f"• {participant_data.get('name', 'Неизвестно')} (ID: {user_id})\n"
    else:
        text += "📋 Участников пока нет\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить участника", callback_data="add_tournament_participant")
    if participants:
        builder.button(text="➖ Удалить участника", callback_data="remove_tournament_participant")
    builder.button(text="🔙 Назад", callback_data=f"edit_tournament:{tournament_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик добавления участника
@router.callback_query(F.data == "add_tournament_participant")
async def add_tournament_participant(callback: CallbackQuery, state: FSMContext):
    """Обработчик добавления участника в турнир"""
    await state.set_state(EditTournamentStates.ADD_PARTICIPANT)
    
    await callback.message.edit_text(
        "➕ Добавление участника в турнир\n\n"
        "Введите ID пользователя для добавления в турнир:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад", callback_data="manage_tournament_participants")
        .as_markup()
    )
    await callback.answer()

# Обработчик ввода ID участника
@router.message(EditTournamentStates.ADD_PARTICIPANT)
async def input_participant_id(message: Message, state: FSMContext):
    """Обработчик ввода ID участника"""
    try:
        user_id = int(message.text.strip())
        
        # Проверяем, существует ли пользователь
        users = await storage.load_users()
        if str(user_id) not in users:
            data = await state.get_data()
            tournament_id = data.get('editing_tournament_id') or data.get('admin_editing_tournament_id')
            
            # Определяем режим работы (обычный или админский)
            is_admin_mode = 'admin_editing_tournament_id' in data
            
            if is_admin_mode:
                back_callback = f"admin_view_participants:{tournament_id}"
            else:
                back_callback = "manage_tournament_participants"
            
            await message.answer(
                "❌ Пользователь с таким ID не найден в системе.\n\n"
                "Попробуйте еще раз или нажмите 'Назад':",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data=back_callback)
                .as_markup()
            )
            return
        
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id') or data.get('admin_editing_tournament_id')
        
        # Определяем режим работы (обычный или админский)
        is_admin_mode = 'admin_editing_tournament_id' in data
        
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments[tournament_id]
        participants = tournament_data.get('participants', {})
        
        # Проверяем, не добавлен ли уже этот пользователь
        if str(user_id) in participants:
            if is_admin_mode:
                back_callback = f"admin_view_participants:{tournament_id}"
            else:
                back_callback = "manage_tournament_participants"
            
            await message.answer(
                "❌ Этот пользователь уже участвует в турнире.\n\n"
                "Попробуйте еще раз или нажмите 'Назад':",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 Назад", callback_data=back_callback)
                .as_markup()
            )
            return
        
        # Добавляем участника
        user_data = users[str(user_id)]
        participants[str(user_id)] = {
            'name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
            'phone': user_data.get('phone', 'Не указан'),
            'added_at': datetime.now().isoformat(),
            'added_by': message.from_user.id
        }
        
        tournament_data['participants'] = participants
        await storage.save_tournaments(tournaments)
        
        # Проверяем, готов ли турнир к запуску
        tournament_ready = await tournament_manager.check_tournament_readiness(tournament_id)
        
        success_message = f"✅ Участник успешно добавлен в турнир!\n\n"
        success_message += f"👤 Имя: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        success_message += f"🆔 ID: {user_id}\n"
        success_message += f"📞 Телефон: {user_data.get('phone', 'Не указан')}\n\n"
        
        if tournament_ready and tournament_data.get('status') == 'active':
            # Запускаем турнир
            tournament_started = await tournament_manager.start_tournament(tournament_id)
            
            if tournament_started:
                success_message += f"🎉 *Турнир автоматически запущен!*\n\n"
                success_message += f"🏆 Набрано минимальное количество участников\n"
                success_message += f"⚔️ Матчи распределены и отправлены участникам\n\n"
                
                # Отправляем уведомления участникам
                try:
                    from main import bot  # Импортируем бота
                    notifications = TournamentNotifications(bot)
                    await notifications.notify_tournament_started(tournament_id, tournament_data)
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомлений о начале турнира: {e}")
            else:
                success_message += f"⚠️ Не удалось автоматически запустить турнир\n"
        else:
            tournament_type = tournament_data.get('type', 'Олимпийская система')
            min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
            current_count = len(participants)
            success_message += f"📊 Участников: {current_count}/{min_participants}\n"
            success_message += f"⏳ Дождитесь набора минимального количества участников\n"
        
        # Формируем кнопки в зависимости от режима
        builder = InlineKeyboardBuilder()
        if is_admin_mode:
            builder.button(text="➕ Добавить еще", callback_data=f"admin_add_participant:{tournament_id}")
            builder.button(text="👥 К участникам", callback_data=f"admin_view_participants:{tournament_id}")
            builder.button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
        else:
            builder.button(text="➕ Добавить еще", callback_data="add_tournament_participant")
            builder.button(text="👥 Управление участниками", callback_data="manage_tournament_participants")
            builder.button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        
        builder.adjust(1)
        
        await message.answer(
            success_message,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
        
    except ValueError:
        data = await state.get_data()
        tournament_id = data.get('editing_tournament_id') or data.get('admin_editing_tournament_id')
        
        # Определяем режим работы (обычный или админский)
        is_admin_mode = 'admin_editing_tournament_id' in data
        
        if is_admin_mode:
            back_callback = f"admin_view_participants:{tournament_id}"
        else:
            back_callback = "manage_tournament_participants"
        
        await message.answer(
            "❌ Введите корректный ID пользователя (число).\n\n"
            "Попробуйте еще раз или нажмите 'Назад':",
            reply_markup=InlineKeyboardBuilder()
            .button(text="🔙 Назад", callback_data=back_callback)
            .as_markup()
        )

# Обработчик удаления участника
@router.callback_query(F.data == "remove_tournament_participant")
async def remove_tournament_participant(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления участника из турнира"""
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if not participants:
        await callback.answer("❌ В турнире нет участников для удаления")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, participant_data in participants.items():
        name = participant_data.get('name', 'Неизвестно')
        builder.button(text=f"➖ {name} (ID: {user_id})", callback_data=f"remove_participant:{user_id}")
    
    builder.button(text="🔙 Назад", callback_data="manage_tournament_participants")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "➖ Удаление участника из турнира\n\n"
        "Выберите участника для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик подтверждения удаления участника
@router.callback_query(F.data.startswith("remove_participant:"))
async def confirm_remove_participant(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления участника"""
    user_id = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if user_id not in participants:
        await callback.answer("❌ Участник не найден")
        return
    
    participant_data = participants[user_id]
    
    # Удаляем участника
    del participants[user_id]
    tournament_data['participants'] = participants
    await storage.save_tournaments(tournaments)
    
    await callback.message.edit_text(
        f"✅ Участник успешно удален из турнира!\n\n"
        f"👤 Имя: {participant_data.get('name', 'Неизвестно')}\n"
        f"🆔 ID: {user_id}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="➖ Удалить еще", callback_data="remove_tournament_participant")
        .button(text="👥 Управление участниками", callback_data="manage_tournament_participants")
        .button(text="🔙 К турниру", callback_data=f"edit_tournament:{tournament_id}")
        .adjust(1)
        .as_markup()
    )
    await callback.answer()

# Обработчик подтверждения удаления турнира
@router.callback_query(F.data.startswith("delete_tournament_confirm:"))
async def confirm_delete_tournament(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"delete_tournament_yes:{tournament_id}")
    builder.button(text="❌ Нет, отменить", callback_data=f"edit_tournament:{tournament_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить турнир?\n\n"
        f"🏆 Название: {tournament_data.get('name', 'Без названия')}\n"
        f"📍 Место: {tournament_data.get('city', 'Не указан')}\n"
        f"👥 Участников: {len(tournament_data.get('participants', {}))}\n\n"
        f"Это действие необратимо!",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик удаления турнира
@router.callback_query(F.data.startswith("delete_tournament_yes:"))
async def delete_tournament_yes(callback: CallbackQuery, state: FSMContext):
    """Обработчик удаления турнира"""
    tournament_id = callback.data.split(":", 1)[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    
    # Удаляем турнир
    del tournaments[tournament_id]
    await storage.save_tournaments(tournaments)
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ Турнир успешно удален!\n\n"
        f"🏆 Название: {tournament_data.get('name', 'Без названия')}\n"
        f"📍 Место: {tournament_data.get('city', 'Не указан')}\n\n"
        f"Все данные о турнире удалены из системы."
    )
    await callback.answer()

# Обработчик меню удаления участника (для админа)
@router.callback_query(F.data.startswith("admin_remove_participant_menu:"))
async def admin_remove_participant_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления участника для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if not participants:
        await callback.answer("❌ В турнире нет участников для удаления")
        return
    
    builder = InlineKeyboardBuilder()
    for user_id, participant_data in participants.items():
        name = participant_data.get('name', 'Неизвестно')
        builder.button(text=f"🗑️ {name} (ID: {user_id})", callback_data=f"admin_remove_participant:{tournament_id}:{user_id}")
    
    builder.button(text="🔙 Назад к участникам", callback_data=f"admin_view_participants:{tournament_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "🗑️ Удаление участника из турнира\n\n"
        "Выберите участника для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчик удаления участника (для админа)
@router.callback_query(F.data.startswith("admin_remove_participant:"))
async def admin_remove_participant(callback: CallbackQuery, state: FSMContext):
    """Удаление участника из турнира для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    parts = callback.data.split(":")
    tournament_id = parts[1]
    user_id = parts[2]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments[tournament_id]
    participants = tournament_data.get('participants', {})
    
    if user_id not in participants:
        await callback.answer("❌ Участник не найден")
        return
    
    participant_data = participants[user_id]
    
    # Удаляем участника
    del participants[user_id]
    tournament_data['participants'] = participants
    await storage.save_tournaments(tournaments)
    
    await callback.message.edit_text(
        f"✅ Участник успешно удален из турнира!\n\n"
        f"👤 Имя: {participant_data.get('name', 'Неизвестно')}\n"
        f"🆔 ID: {user_id}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🗑️ Удалить еще", callback_data=f"admin_remove_participant_menu:{tournament_id}")
        .button(text="👥 К участникам", callback_data=f"admin_view_participants:{tournament_id}")
        .button(text="🔙 К списку турниров", callback_data="admin_back_to_tournament_list")
        .adjust(1)
        .as_markup()
    )
    await callback.answer()

# Обработчик добавления участника (для админа)
@router.callback_query(F.data.startswith("admin_add_participant:"))
async def admin_add_participant(callback: CallbackQuery, state: FSMContext):
    """Добавление участника в турнир для админа"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора")
        return
    
    tournament_id = callback.data.split(":", 1)[1]
    
    # Сохраняем ID турнира в состоянии
    await state.update_data(admin_editing_tournament_id=tournament_id)
    await state.set_state(EditTournamentStates.ADD_PARTICIPANT)
    
    await callback.message.edit_text(
        "➕ Добавление участника в турнир\n\n"
        "Введите ID пользователя для добавления в турнир:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="🔙 Назад к участникам", callback_data=f"admin_view_participants:{tournament_id}")
        .as_markup()
    )
    await callback.answer()

# Обработчик возврата к списку турниров (для админа)
@router.callback_query(F.data == "admin_back_to_tournament_list")
async def admin_back_to_tournament_list(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку турниров для админа"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await callback.message.edit_text("📋 Нет турниров для просмотра")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        participants_count = len(tournament_data.get('participants', {}))
        builder.button(text=f"🏆 {name} ({city}) - {participants_count} участников", 
                      callback_data=f"admin_view_participants:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "👥 Просмотр участников турниров\n\n"
        "Выберите турнир для просмотра участников:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработчики навигации
@router.callback_query(F.data == "edit_tournaments_back")
async def edit_tournaments_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку турниров для редактирования"""
    tournaments = await storage.load_tournaments()
    
    if not tournaments:
        await callback.message.edit_text("📋 Нет турниров для редактирования")
        return
    
    builder = InlineKeyboardBuilder()
    for tournament_id, tournament_data in tournaments.items():
        name = tournament_data.get('name', 'Без названия')
        city = tournament_data.get('city', 'Не указан')
        builder.button(text=f"🏆 {name} ({city})", callback_data=f"edit_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "🏆 Редактирование турниров\n\n"
        "Выберите турнир для редактирования:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "edit_tournament_back")
async def edit_tournament_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к турниру"""
    data = await state.get_data()
    tournament_id = data.get('editing_tournament_id')
    
    if tournament_id:
        await select_tournament_for_edit(callback, state)
    else:
        await edit_tournaments_back(callback, state)

# Возврат в главное меню турниров
@router.callback_query(F.data == "tournaments_main_menu")
async def tournaments_main_menu(callback: CallbackQuery):
    """Возврат в главное меню турниров"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    text = (
        f"🏆 Турниры\n\n"
        f"Сейчас проходит: {len(active_tournaments)} активных турниров\n"
        f"Участвуйте в соревнованиях и покажите свои навыки!\n\n"
        f"📋 Вы можете просмотреть список доступных турниров, "
        f"подать заявку на участие или посмотреть свои текущие турниры."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть список", callback_data="view_tournaments_start")
    builder.button(text="📝 Мои заявки", callback_data="my_applications_list:0")
    builder.button(text="🎯 Мои турниры", callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# Обработчик отображения турнирной сетки
@router.callback_query(F.data.startswith("tournament_bracket:"))
async def tournament_bracket(callback: CallbackQuery, state: FSMContext):
    """Обработчик отображения турнирной сетки"""
    tournament_id = callback.data.split(":")[1]
    
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id, {})
    
    if not tournament_data:
        await callback.message.edit_text("❌ Турнир не найден")
        await callback.answer()
        return
    
    participants = tournament_data.get('participants', {})
    tournament_type = tournament_data.get('type', 'Олимпийская система')
    
    # Проверяем минимальное количество участников
    min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
    current_participants = len(participants)
    
    if current_participants < min_participants:
        await callback.message.edit_text(
            f"❌ Недостаточно участников для отображения сетки!\n\n"
            f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
            f"⚔️ Тип: {tournament_type}\n"
            f"👥 Текущих участников: {current_participants}\n"
            f"📊 Минимум требуется: {min_participants}\n\n"
            f"Дождитесь набора минимального количества участников.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад к турниру", callback_data=f"view_tournament:{tournament_id}")]]
            )
        )
        await callback.answer()
        return
    
    # Создаем список игроков для сетки
    players = []
    users = await storage.load_users()
    
    for user_id, participant_data in participants.items():
        user_data = users.get(user_id, {})
        player = Player(
            id=user_id,
            name=participant_data.get('name', user_data.get('first_name', 'Неизвестно')),
            photo_url=user_data.get('photo_path'),
            initial=None
        )
        players.append(player)
    
    # Создаем турнирную сетку
    try:
        bracket = create_tournament_bracket(players, tournament_type)
        
        # Создаем изображение сетки
        bracket_image = create_bracket_image(bracket)
        
        # Конвертируем изображение в байты
        img_byte_arr = io.BytesIO()
        bracket_image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        # Создаем BufferedInputFile для aiogram
        photo_file = BufferedInputFile(
            file=img_byte_arr.getvalue(),
            filename="tournament_bracket.png"
        )
        
        # Отправляем изображение
        await callback.message.answer_photo(
            photo=photo_file,
            caption=f"🏆 Турнирная сетка\n\n"
                   f"📋 Турнир: {tournament_data.get('name', 'Без названия')}\n"
                   f"⚔️ Тип: {tournament_type}\n"
                   f"👥 Участников: {current_participants}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад к турниру", callback_data=f"view_tournament:{tournament_id}")]]
            )
        )
        
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка создания турнирной сетки: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка создания турнирной сетки\n\n"
            f"Попробуйте позже или обратитесь к администратору.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад к турниру", callback_data=f"view_tournament:{tournament_id}")]]
            )
        )
    
    await callback.answer()

