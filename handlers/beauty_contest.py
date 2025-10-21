from datetime import datetime
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.more import back_to_main
from models.states import BeautyContestStates
from services.storage import storage
from utils.admin import is_admin
from utils.utils import calculate_age, remove_country_flag
from config.paths import BASE_DIR

router = Router()
# Константы
PROFILES_PER_PAGE = 1  # Показываем по одной анкете за раз

# ============== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==============

async def has_premium(user_id: str) -> bool:
    """Проверка наличия активной премиум подписки у пользователя"""
    users = await storage.load_users()
    user_data = users.get(user_id, {})
    subscription = user_data.get('subscription', {})
    
    if not subscription.get('active', False):
        return False
    
    until_date_str = subscription.get('until')
    if not until_date_str:
        return False
    
    try:
        until_date = datetime.strptime(until_date_str, '%Y-%m-%d')
        return until_date >= datetime.now()
    except ValueError:
        return False

def get_user_votes_info(contest_data: dict, voter_id: str) -> dict:
    """Получить информацию о голосах пользователя"""
    user_votes = contest_data.get("user_votes", {}).get(voter_id, {
        "male_votes": [],  # [user_id1, user_id2, ...]
        "female_votes": []  # [user_id1, user_id2, ...]
    })
    return user_votes

async def can_vote_for_gender(contest_data: dict, voter_id: str, target_gender: str) -> tuple[bool, str]:
    """
    Проверить, может ли пользователь голосовать за этот пол
    Возвращает (can_vote, reason)
    reason может быть: "ok", "no_premium", "max_votes"
    """
    user_votes = get_user_votes_info(contest_data, voter_id)
    is_premium = await has_premium(voter_id)
    
    # Определяем какой массив голосов использовать
    votes_list = user_votes.get("male_votes", []) if target_gender == "Мужской" else user_votes.get("female_votes", [])
    
    # Подсчитываем сколько голосов уже использовано
    current_votes_count = len(votes_list)
    
    # Обычный пользователь: 1 голос за мужчин + 1 за женщин
    # Премиум пользователь: 2 голоса за мужчин + 2 за женщин
    max_votes = 2 if is_premium else 1
    
    if current_votes_count < max_votes:
        return True, "ok"
    elif current_votes_count >= 1 and not is_premium:
        return False, "no_premium"
    else:
        return False, "max_votes"

async def get_votes_status_text(contest_data: dict, voter_id: str) -> str:
    """Получить текст статуса голосов пользователя"""
    user_votes = get_user_votes_info(contest_data, voter_id)
    is_premium = await has_premium(voter_id)
    
    male_votes = user_votes.get("male_votes", [])
    female_votes = user_votes.get("female_votes", [])
    
    # Подсчитываем использованные и доступные голоса
    male_used = len(male_votes)
    female_used = len(female_votes)
    
    max_votes = 2 if is_premium else 1
    
    text = f"🗳 <b>Ваши голоса:</b>\n"
    text += f"• За мужчин: {male_used}/{max_votes} использовано\n"
    
    text += f"• За женщин: {female_used}/{max_votes} использовано\n"
    
    text += "\n"
    
    if is_premium:
        text += "⭐️ <b>Premium активен!</b>\n"
        text += "Вы можете отдать по 2 голоса за каждый пол\n"
    else:
        text += "💡 <b>Подсказка:</b>\n"
        text += "С Premium подпиской вы получите еще по 1 голосу за каждый пол!\n"
    
    return text

# ============== ГЛАВНОЕ МЕНЮ ==============

@router.callback_query(F.data == "beauty_contest")
async def beauty_contest_main_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню конкурса красоты"""
    user_id = str(callback.from_user.id)
    users = await storage.load_users()
    user_data = users.get(user_id)
    
    if not user_data:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Назад к меню", callback_data="back_to_more"))
        try:
            await callback.message.edit_text(
                "❌ Сначала зарегистрируйтесь в боте!",
                reply_markup=builder.as_markup()
            )
        except:
            await callback.message.answer(
                "❌ Сначала зарегистрируйтесь в боте!",
                reply_markup=builder.as_markup()
            )
        await callback.answer()
        return
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    
    # Проверяем, есть ли уже заявка пользователя
    has_application = user_id in applications
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👀 Просмотреть анкеты", callback_data="bc_view_profiles")
    )
    
    if has_application:
        builder.row(
            InlineKeyboardButton(text="❌ Удалить свою заявку", callback_data="bc_delete_application")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="📝 Заявиться на конкурс", callback_data="bc_apply")
        )
    
    # Админские функции
    if await is_admin(int(user_id)):
        builder.row(
            InlineKeyboardButton(text="⚙️ Управление анкетами (Админ)", callback_data="bc_admin_menu")
        )
    
    builder.row(
        InlineKeyboardButton(text="Назад к меню", callback_data="back_to_more")
    )
    
    text = (
        "🌟 <b>Mr & Mrs Tennis Play</b>\n\n"
        "Примите участие в конкурсе Mr & Mrs Tennis Play, чтобы выиграть нашу бесплатную годовую подписку Premium и возможность 1 года бесплатного участия в наших  турнирах для вас и вашего друга!\n\nДля этого нужно просто зарегистрироваться и собирать голоса от других участников бота.\n\n"
        "📊 В конкурсе участвуют:\n"
        f"• Мужчин: {sum(1 for app in applications.values() if app.get('gender') == 'Мужской')}\n"
        f"• Женщин: {sum(1 for app in applications.values() if app.get('gender') == 'Женский')}\n\n"
    )
    
    if has_application:
        user_votes = contest_data.get("votes", {}).get(user_id, {})
        vote_count = len(user_votes)
        text += f"✅ Вы участвуете в конкурсе\n💖 Голосов: {vote_count}\n\n"
    
    # Показываем статус голосов пользователя
    text += await get_votes_status_text(contest_data, user_id) + "\n"
    
    text += f"\n\n<b>Результаты конкурса будут объявлены 15 января 2026 года</b>"
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(BeautyContestStates.MAIN_MENU)
    await callback.answer()

# ============== ПРОСМОТР АНКЕТ ==============

@router.callback_query(F.data == "bc_view_profiles")
async def select_gender(callback: CallbackQuery, state: FSMContext):
    """Выбор пола для просмотра анкет"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👨 Мужчины", callback_data="bc_gender_male"),
        InlineKeyboardButton(text="👩 Женщины", callback_data="bc_gender_female")
    )
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data="beauty_contest")
    )
    
    text = "Выберите пол участников для просмотра:"
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup())
    await state.set_state(BeautyContestStates.SELECT_GENDER)
    await callback.answer()

@router.callback_query(F.data.in_(["bc_gender_male", "bc_gender_female"]))
async def show_profiles_by_gender(callback: CallbackQuery, state: FSMContext):
    """Показ анкет выбранного пола"""
    gender = "Мужской" if callback.data == "bc_gender_male" else "Женский"
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    votes = contest_data.get("votes", {})
    
    # Фильтруем анкеты по полу
    filtered_profiles = {
        uid: app for uid, app in applications.items() 
        if app.get("gender") == gender
    }
    
    if not filtered_profiles:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Назад", callback_data="bc_view_profiles"))
        try:
            await callback.message.edit_text(
                "❌ Нет анкет с таким полом\n\nВыберите другой пол или вернитесь назад.",
                reply_markup=builder.as_markup()
            )
        except:
            await callback.message.answer(
                "❌ Нет анкет с таким полом\n\nВыберите другой пол или вернитесь назад.",
                reply_markup=builder.as_markup()
            )
        await callback.answer()
        return
    
    # Сортируем по количеству голосов
    sorted_profiles = sorted(
        filtered_profiles.items(),
        key=lambda x: len(votes.get(x[0], {})),
        reverse=True
    )
    
    # Сохраняем данные для пагинации
    await state.update_data(
        gender=gender,
        profiles=sorted_profiles,
        current_page=0
    )
    
    await show_profile_page(callback.message, callback.from_user.id, state)
    await state.set_state(BeautyContestStates.VIEW_PROFILES)
    await callback.answer()

async def show_profile_page(message: Message, viewer_id: int, state: FSMContext):
    """Показ страницы с анкетой"""
    data = await state.get_data()
    profiles = data.get("profiles", [])
    current_page = data.get("current_page", 0)
    
    if not profiles or current_page >= len(profiles):
        await message.edit_text(
            "❌ Анкеты закончились",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Назад", callback_data="bc_view_profiles")
            ]])
        )
        return
    
    user_id, profile = profiles[current_page]
    viewer_id_str = str(viewer_id)
    
    # Загружаем данные о голосах
    contest_data = await storage.load_beauty_contest()
    votes = contest_data.get("votes", {})
    profile_votes = votes.get(user_id, {})
    vote_count = len(profile_votes)
    
    # Проверяем, может ли пользователь голосовать за этот пол
    target_gender = profile.get("gender")
    can_vote, reason = await can_vote_for_gender(contest_data, viewer_id_str, target_gender)
    
    # Проверяем, голосовал ли пользователь за этого участника
    user_votes = get_user_votes_info(contest_data, viewer_id_str)
    votes_list = user_votes.get("male_votes", []) if target_gender == "Мужской" else user_votes.get("female_votes", [])
    has_voted_for_this = user_id in votes_list
    
    # Формируем текст анкеты
    age = await calculate_age(profile.get('birth_date', ''))

    text = (
        f"🌟 <b>{profile.get('first_name', '')} {profile.get('last_name', '')}</b>\n\n"
        f"🎂 Возраст: {age} лет\n"
        f"🌍 Страна: {remove_country_flag(profile.get('country', '—'))}\n"
        f"🏙 Город: {profile.get('city', '—')}\n\n"
        f"💖 Голосов: <b>{vote_count}</b>\n\n"
    )
    
    if profile.get('comment'):
        text += f"💬 О себе: {profile.get('comment')}\n\n"
    
    text += f"Анкета {current_page + 1} из {len(profiles)}"
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопки голосования
    if viewer_id_str == user_id:
        # Нельзя голосовать за себя
        builder.row(
            InlineKeyboardButton(text="🚫 Это ваша анкета", callback_data="bc_self_vote")
        )
    elif has_voted_for_this:
        # Уже голосовали за этого участника
        builder.row(
            InlineKeyboardButton(text="💔 Убрать голос", callback_data=f"bc_unvote_{user_id}")
        )
    elif can_vote:
        # Можно голосовать
        builder.row(
            InlineKeyboardButton(text="💖 Проголосовать", callback_data=f"bc_vote_{user_id}")
        )
    else:
        # Голоса закончились
        gender_text = "мужчин" if target_gender == "Мужской" else "женщин"
        builder.row(
            InlineKeyboardButton(text=f"🚫 Голоса за {gender_text} закончились", callback_data="bc_no_votes")
        )
    
    # Навигация
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Предыдущая", callback_data="bc_prev_page"))
    if current_page < len(profiles) - 1:
        nav_buttons.append(InlineKeyboardButton(text="Следующая ▶️", callback_data="bc_next_page"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(
        InlineKeyboardButton(text="Назад к выбору пола", callback_data="bc_view_profiles")
    )
    
    # Пытаемся отправить фото
    photo_path = BASE_DIR / profile['photo_path']
    
    try:
        if photo_path.exists():
            # Удаляем предыдущее сообщение
            try:
                await message.delete()
            except:
                pass
            
            await message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        print(f"Error showing profile: {e}")
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ============== ГОЛОСОВАНИЕ ==============

@router.callback_query(F.data == "bc_self_vote")
async def self_vote_handler(callback: CallbackQuery):
    """Обработка попытки проголосовать за себя"""
    await callback.answer("❌ Нельзя голосовать за себя!", show_alert=True)

@router.callback_query(F.data == "bc_no_votes")
async def no_votes_handler(callback: CallbackQuery):
    """Обработка когда голоса закончились"""
    await callback.answer(
        "❌ У вас закончились голоса за этот пол.\n\n"
        "💡 Оформите Premium подписку, чтобы получить дополнительные голоса!",
        show_alert=True
    )

@router.callback_query(F.data.startswith("bc_vote_"))
async def vote_for_profile(callback: CallbackQuery, state: FSMContext):
    """Голосование за анкету"""
    target_user_id = callback.data.split("_")[2]
    voter_id = str(callback.from_user.id)
    
    # Проверяем, что пользователь не голосует за себя
    if voter_id == target_user_id:
        await callback.answer("❌ Нельзя голосовать за себя!")
        return
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    votes = contest_data.get("votes", {})
    user_votes = contest_data.get("user_votes", {})
    
    # Определяем пол целевого участника
    target_profile = applications.get(target_user_id, {})
    target_gender = target_profile.get("gender")
    
    if not target_gender:
        await callback.answer("❌ Ошибка: не удалось определить пол участника")
        return
    
    # Проверяем, может ли пользователь голосовать за этот пол
    can_vote, reason = await can_vote_for_gender(contest_data, voter_id, target_gender)
    
    if not can_vote:
        if reason == "no_premium":
            gender_text = "мужчин" if target_gender == "Мужской" else "женщин"
            text = (
                f"❌ <b>Голос за {gender_text} уже использован</b>\n\n"
                f"Вы уже использовали свой голос за {gender_text}.\n\n"
                "⭐️ С Premium подпиской вы получите еще один голос за каждый пол!\n\n"
                "Оформите подписку в разделе «💳 Платежи»"
            )
        else:
            text = (
                "❌ <b>Достигнут лимит голосов</b>\n\n"
                "Вы уже использовали все доступные голоса за этот пол."
            )
        
        await callback.answer(text, show_alert=True)
        return
    
    # Инициализируем структуры если нужно
    if voter_id not in user_votes:
        user_votes[voter_id] = {
            "male_votes": [],
            "female_votes": []
        }
    
    # Проверяем, не голосовал ли уже за этого участника
    votes_list_key = "male_votes" if target_gender == "Мужской" else "female_votes"
    if target_user_id in user_votes[voter_id][votes_list_key]:
        await callback.answer("❌ Вы уже голосовали за этого участника!", show_alert=True)
        return
    
    if target_user_id not in votes:
        votes[target_user_id] = {}
    
    # Добавляем голос в общие голоса профиля
    # Создаем уникальный ключ для каждого голоса (voter_id + timestamp)
    vote_key = f"{voter_id}_{datetime.now().timestamp()}"
    votes[target_user_id][vote_key] = {
        "voted_at": datetime.now().isoformat(),
        "voter_id": voter_id,
        "voter_name": f"{callback.from_user.first_name} {callback.from_user.last_name or ''}"
    }
    
    # Добавляем в список проголосовавших за этот пол
    user_votes[voter_id][votes_list_key].append(target_user_id)
    
    contest_data["votes"] = votes
    contest_data["user_votes"] = user_votes
    await storage.save_beauty_contest(contest_data)
    
    await callback.answer("💖 Ваш голос учтён!")
    
    # Обновляем страницу
    await show_profile_page(callback.message, callback.from_user.id, state)

@router.callback_query(F.data.startswith("bc_unvote_"))
async def unvote_for_profile(callback: CallbackQuery, state: FSMContext):
    """Отмена голоса за анкету"""
    target_user_id = callback.data.split("_")[2]
    voter_id = str(callback.from_user.id)
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    votes = contest_data.get("votes", {})
    user_votes = contest_data.get("user_votes", {})
    
    # Определяем пол целевого участника
    target_profile = applications.get(target_user_id, {})
    target_gender = target_profile.get("gender")
    
    # Убираем голос из общих голосов профиля
    if target_user_id in votes:
        # Ищем голос этого пользователя
        votes_to_remove = [key for key, vote_data in votes[target_user_id].items() 
                          if vote_data.get("voter_id") == voter_id]
        
        # Удаляем голос (должен быть только один)
        if votes_to_remove:
            del votes[target_user_id][votes_to_remove[0]]
    
    # Обновляем информацию о голосах пользователя
    if voter_id in user_votes:
        votes_list_key = "male_votes" if target_gender == "Мужской" else "female_votes"
        if target_user_id in user_votes[voter_id].get(votes_list_key, []):
            user_votes[voter_id][votes_list_key].remove(target_user_id)
    
    contest_data["votes"] = votes
    contest_data["user_votes"] = user_votes
    await storage.save_beauty_contest(contest_data)
    
    await callback.answer("💔 Голос убран")
    
    # Обновляем страницу
    await show_profile_page(callback.message, callback.from_user.id, state)

# ============== ПАГИНАЦИЯ ==============

@router.callback_query(F.data == "bc_prev_page")
async def previous_page(callback: CallbackQuery, state: FSMContext):
    """Предыдущая страница"""
    data = await state.get_data()
    current_page = data.get("current_page", 0)
    
    if current_page > 0:
        await state.update_data(current_page=current_page - 1)
        await show_profile_page(callback.message, callback.from_user.id, state)
    
    await callback.answer()

@router.callback_query(F.data == "bc_next_page")
async def next_page(callback: CallbackQuery, state: FSMContext):
    """Следующая страница"""
    data = await state.get_data()
    current_page = data.get("current_page", 0)
    profiles = data.get("profiles", [])
    
    if current_page < len(profiles) - 1:
        await state.update_data(current_page=current_page + 1)
        await show_profile_page(callback.message, callback.from_user.id, state)
    
    await callback.answer()

# ============== ПОДАЧА ЗАЯВКИ ==============

@router.callback_query(F.data == "bc_apply")
async def apply_to_contest(callback: CallbackQuery, state: FSMContext):
    """Подача заявки на конкурс"""
    user_id = str(callback.from_user.id)
    users = await storage.load_users()
    user_data = users.get(user_id)
    
    if not user_data:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Назад", callback_data="beauty_contest"))
        try:
            await callback.message.edit_text(
                "❌ Ошибка получения данных",
                reply_markup=builder.as_markup()
            )
        except:
            await callback.message.answer(
                "❌ Ошибка получения данных",
                reply_markup=builder.as_markup()
            )
        await callback.answer()
        return

    # Проверяем наличие фото
    photo_path = BASE_DIR / user_data['photo_path']
    if not photo_path.exists():
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Назад", callback_data="beauty_contest"))
        try:
            await callback.message.edit_text(
                "❌ <b>Для участия в конкурсе необходимо загрузить фото в профиль!</b>\n\n"
                "Перейдите в раздел '👤 Моя анкета' и загрузите фото.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except:
            await callback.message.answer(
                "❌ <b>Для участия в конкурсе необходимо загрузить фото в профиль!</b>\n\n"
                "Перейдите в раздел '👤 Моя анкета' и загрузите фото.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        await callback.answer()
        return
    
    # Показываем данные для подтверждения
    age = await calculate_age(user_data.get('birth_date', ''))
    
    text = (
        "📝 <b>Подтвердите участие в конкурсе</b>\n\n"
        "Ваша анкета:\n\n"
        f"👤 {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"🎂 Возраст: {age} лет\n"
        f"🌍 Страна: {remove_country_flag(user_data.get('country', '—'))}\n"
        f"🏙 Город: {user_data.get('city', '—')}\n\n"
    )
    
    if user_data.get('comment'):
        text += f"💬 О себе: {user_data.get('comment')}\n\n"
    
    text += "Подтвердите участие в конкурсе красоты:"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="bc_confirm_apply"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="beauty_contest")
    )
    
    try:
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    await state.set_state(BeautyContestStates.CONFIRM_APPLICATION)
    await callback.answer()

@router.callback_query(F.data == "bc_confirm_apply")
async def confirm_application(callback: CallbackQuery, state: FSMContext):
    """Подтверждение заявки"""
    user_id = str(callback.from_user.id)
    users = await storage.load_users()
    user_data = users.get(user_id)
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    
    # Проверяем, нет ли уже заявки
    if user_id in applications:
        await callback.answer("❌ Вы уже участвуете в конкурсе!")
        return
    
    # Добавляем заявку
    applications[user_id] = {
        "first_name": user_data.get('first_name', ''),
        "last_name": user_data.get('last_name', ''),
        "gender": user_data.get('gender', ''),
        "birth_date": user_data.get('birth_date', ''),
        "country": user_data.get('country', ''),
        "city": user_data.get('city', ''),
        "comment": user_data.get('comment', ''),
        "photo_path": user_data.get('photo_path', ''),
        "applied_at": datetime.now().isoformat()
    }
    
    contest_data["applications"] = applications
    await storage.save_beauty_contest(contest_data)
    
    # Возвращаемся в главное меню
    await beauty_contest_main_menu(callback, state)

# ============== УДАЛЕНИЕ ЗАЯВКИ ==============

@router.callback_query(F.data == "bc_delete_application")
async def delete_application_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления заявки"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data="bc_confirm_delete"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="beauty_contest")
    )
    
    text = (
        "❓ <b>Удалить свою заявку?</b>\n\n"
        "Вы уверены, что хотите удалить свою заявку из конкурса красоты?\n"
        "Все голоса за вас будут потеряны."
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(BeautyContestStates.DELETE_APPLICATION)
    await callback.answer()

@router.callback_query(F.data == "bc_confirm_delete")
async def confirm_delete_application(callback: CallbackQuery, state: FSMContext):
    """Удаление заявки пользователя"""
    user_id = str(callback.from_user.id)
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    votes = contest_data.get("votes", {})
    
    # Удаляем заявку
    if user_id in applications:
        del applications[user_id]
    
    # Удаляем голоса за этого пользователя
    if user_id in votes:
        del votes[user_id]
    
    contest_data["applications"] = applications
    contest_data["votes"] = votes
    await storage.save_beauty_contest(contest_data)
    
    await callback.answer()
    
    # Возвращаемся в главное меню с сообщением об успехе
    await beauty_contest_main_menu(callback, state)

# ============== АДМИНСКИЕ ФУНКЦИИ ==============

@router.callback_query(F.data == "bc_admin_menu")
async def admin_menu(callback: CallbackQuery, state: FSMContext):
    """Админское меню управления конкурсом"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    # Загружаем данные конкурса
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить анкету", callback_data="bc_admin_delete")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Сбросить все голоса", callback_data="bc_admin_reset_votes")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Очистить все анкеты", callback_data="bc_admin_clear_all")
    )
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data="beauty_contest")
    )
    
    text = (
        "⚙️ <b>Управление конкурсом красоты</b>\n\n"
        f"📊 Всего анкет: {len(applications)}"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "bc_admin_delete")
async def admin_delete_select(callback: CallbackQuery, state: FSMContext):
    """Выбор анкеты для удаления"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    # Загружаем данные
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    votes = contest_data.get("votes", {})
    
    if not applications:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Назад", callback_data="bc_admin_menu"))
        await callback.message.edit_text(
            "❌ Нет анкет для удаления",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return
    
    # Сортируем по количеству голосов
    sorted_apps = sorted(
        applications.items(),
        key=lambda x: len(votes.get(x[0], {})),
        reverse=True
    )
    
    builder = InlineKeyboardBuilder()
    
    for uid, app in sorted_apps:
        vote_count = len(votes.get(uid, {}))
        button_text = f"{app.get('first_name', '')} {app.get('last_name', '')} ({vote_count} 💖)"
        builder.row(
            InlineKeyboardButton(text=button_text, callback_data=f"bc_admin_del_{uid}")
        )
    
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data="bc_admin_menu")
    )
    
    text = "Выберите анкету для удаления:"
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("bc_admin_del_"))
async def admin_delete_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления анкеты админом"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    target_user_id = callback.data.split("_")[3]
    
    # Загружаем данные
    contest_data = await storage.load_beauty_contest()
    applications = contest_data.get("applications", {})
    votes = contest_data.get("votes", {})
    
    # Удаляем анкету и голоса
    if target_user_id in applications:
        del applications[target_user_id]
    
    if target_user_id in votes:
        del votes[target_user_id]
    
    contest_data["applications"] = applications
    contest_data["votes"] = votes
    await storage.save_beauty_contest(contest_data)
    
    await callback.answer()
    
    # Возвращаемся к списку
    await admin_delete_select(callback, state)

@router.callback_query(F.data == "bc_admin_reset_votes")
async def admin_reset_votes_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение сброса всех голосов"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, сбросить", callback_data="bc_admin_reset_votes_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="bc_admin_menu")
    )
    
    text = (
        "❓ <b>Сбросить все голоса?</b>\n\n"
        "Вы уверены, что хотите сбросить все голоса в конкурсе?\n"
        "Это действие нельзя отменить!"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "bc_admin_reset_votes_confirm")
async def admin_reset_votes(callback: CallbackQuery, state: FSMContext):
    """Сброс всех голосов"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    # Загружаем данные и сбрасываем голоса
    contest_data = await storage.load_beauty_contest()
    contest_data["votes"] = {}
    contest_data["user_votes"] = {}
    await storage.save_beauty_contest(contest_data)
    
    await callback.answer()
    
    # Возвращаемся в админское меню
    await admin_menu(callback, state)

@router.callback_query(F.data == "bc_admin_clear_all")
async def admin_clear_all_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение очистки всех анкет"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, очистить", callback_data="bc_admin_clear_all_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="bc_admin_menu")
    )
    
    text = (
        "❓ <b>Очистить все анкеты?</b>\n\n"
        "Вы уверены, что хотите удалить все анкеты и голоса?\n"
        "Это действие нельзя отменить!"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "bc_admin_clear_all_confirm")
async def admin_clear_all(callback: CallbackQuery, state: FSMContext):
    """Очистка всех анкет и голосов"""
    user_id = int(callback.from_user.id)
    
    if not await is_admin(user_id):
        await callback.answer("❌ Нет доступа")
        return
    
    # Полностью очищаем данные конкурса
    contest_data = {"applications": {}, "votes": {}, "user_votes": {}}
    await storage.save_beauty_contest(contest_data)
    
    await callback.answer()
    
    # Возвращаемся в админское меню
    await admin_menu(callback, state)

# ============== ВОЗВРАТ В МЕНЮ "ЕЩЕ" ==============

@router.callback_query(F.data == "back_to_more")
async def back_to_more(callback: CallbackQuery, state: FSMContext):
    """Возврат в меню 'Еще'"""
    await state.clear()
    
    await back_to_main(callback, state)
