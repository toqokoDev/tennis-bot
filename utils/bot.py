from config.paths import BASE_DIR
from utils.ssesion import save_session
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from utils.utils import calculate_age

# ---------- Вспомогательная отправка единого "текущего" сообщения ----------
async def show_current_data(message: types.Message, state: FSMContext, text: str,
                            reply_markup=None, parse_mode="HTML"):
    user_data = await state.get_data()
    prev_msg_id = user_data.get('prev_msg_id')
    if prev_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_msg_id)
        except:
            pass

    msg = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await state.update_data(prev_msg_id=msg.message_id)
    save_session(message.from_user.id, await state.get_data())

async def show_profile(message: types.Message, profile: dict):
    caption_lines = []
    
    # Добавляем username
    username = f"@{profile.get('username')}" if profile.get('username') else "—"
    caption_lines.append(f"\n<b>👤 {profile.get('first_name', '')} {profile.get('last_name', '')}</b> ({username})")
    
    if profile.get('birth_date'):
        age = calculate_age(profile['birth_date'])
        if age > 0:
            caption_lines.append(f"🎂 Возраст: {age} лет")
    
    caption_lines.append(f"\n🔎 Роль: {profile.get('role', '—')}")
    
    if profile.get('player_level'):
        caption_lines.append(f"🏆 Уровень: {profile.get('player_level')} ({profile.get('rating_points', 0)} очков)")
    
    if profile.get('price') is not None:
        caption_lines.append(f"💵 Стоимость тренировки: {profile.get('price')} руб")
    
    caption_lines.append(f"\n🌍 Страна: {profile.get('country', '—')}")
    caption_lines.append(f"🏙 Город: {profile.get('city', '—')}")
    caption_lines.append(f"🗂 Вид спорта: {profile.get('sport', '—')}")
    caption_lines.append(f"👫 Пол: {profile.get('gender', '—')}")
    
    # Обязательный вывод статистики игр (даже если 0)
    games_played = profile.get('games_played', 0)
    games_wins = profile.get('games_wins', 0)
    caption_lines.append(f"\n📊 Статистика игр:")
    caption_lines.append(f"• Сыграно: {games_played}")
    caption_lines.append(f"• Побед: {games_wins}")
    
    if games_played > 0:
        percent = int((games_wins / games_played) * 100) if games_played > 0 else 0
        caption_lines.append(f"• Процент побед: {percent}%")
    
    if profile.get('default_payment'):
        caption_lines.append(f"\n💳 Оплата корта: {profile.get('default_payment', '—')}")
    
    if profile.get('vacation_tennis', False):
        caption_lines.append(f"\n✈️ Ищет партнёра на время отдыха:")
        caption_lines.append(f"• С {profile.get('vacation_start', '—')} по {profile.get('vacation_end', '—')}")
        if profile.get('vacation_comment'):
            caption_lines.append(f"• Комментарий: {profile.get('vacation_comment')}")
    
    if profile.get('profile_comment'):
        caption_lines.append(f"\n💬 О себе:\n{profile.get('profile_comment', '—')}")
    
    caption = "\n".join(caption_lines) if caption_lines else "Анкета недоступна."

    # Создаем клавиатуру в зависимости от того, свой это профиль или чужой
    if message.chat.id == profile.get('telegram_id'):
        # Клавиатура для своего профиля
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")],
                [InlineKeyboardButton(text="📋 Мои предложения", callback_data="my_offers")],
                [InlineKeyboardButton(text="🎾 Новое предложение", callback_data="new_offer")],
                [InlineKeyboardButton(text="Моя история игр", callback_data=f"game_history:{message.chat.id}")]
            ]
        )
    else:
        # Клавиатура для чужого профиля
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Просмотреть историю матчей", callback_data=f"game_history:{profile.get('telegram_id')}")]
            ]
        )

    photo_path = profile.get("photo_path")
    if photo_path and (BASE_DIR / photo_path).exists():
        await message.answer_photo(
            FSInputFile(BASE_DIR / photo_path), 
            caption=caption, 
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            caption, 
            parse_mode="HTML",
            reply_markup=keyboard
        )
        