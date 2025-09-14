from aiogram import F, Router, types
from config.config import BOT_USERNAME
from services.storage import storage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

router = Router()

@router.callback_query(F.data == "invite_friend")
async def handle_inline_invite_friend(callback: types.CallbackQuery):
    """Обработчик inline кнопки 'Пригласить друга'"""
    user_id = str(callback.message.chat.id)
    
    if not await storage.is_user_registered(user_id):
        await callback.answer("❌ Вы еще не зарегистрированы. Введите /start для регистрации.")
        return
    
    # Получаем информацию о пользователе
    user_data = await storage.get_user(user_id) or {}
    referral_count = user_data.get('referrals_invited', 0)
    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    text = (
        f"👥 <b>Пригласите друзей и получите бесплатную подписку!</b>\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: <b>{referral_count}/10</b>\n\n"
        f"🎁 <b>Как это работает:</b>\n"
        f"• Пригласите 10 друзей в бот\n"
        f"• Каждый друг должен пройти регистрацию\n"
        f"• Получите бесплатную подписку на 1 месяц\n\n"
        f"📎 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"📤 <b>Как делиться:</b>\n"
        f"1. Скопируйте ссылку выше\n"
        f"2. Отправьте друзьям\n"
        f"3. Следите за прогрессом в этом разделе"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", switch_inline_query=f"Присоединяйся к теннисному сообществу!\n\n{referral_link}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ]
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()
