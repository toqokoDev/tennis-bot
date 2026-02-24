from aiogram import F, Router, types
from config.config import BOT_USERNAME
from services.storage import storage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from utils.translations import get_user_language_async, t

router = Router()

@router.message(F.text.in_([t("menu.invite", "ru"), t("menu.invite", "en")]))
async def invite_friend(message: types.Message):
    """Обработчик inline кнопки 'Пригласить друга'"""
    user_id = str(message.chat.id)
    
    language = await get_user_language_async(user_id)
    
    if not await storage.is_user_registered(user_id):
        await message.answer(t("main.not_registered", language))
        return
    
    # Получаем информацию о пользователе
    user_data = await storage.get_user(user_id) or {}
    referral_count = user_data.get('referrals_invited', 0)
    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    text = t("invite.referral_info", language, 
             referral_count=referral_count,
             referral_link=referral_link)
    
    buttons = [
        [InlineKeyboardButton(text=t("invite.share_button", language), switch_inline_query=f"{t('invite.share_button', language)}\n\n{referral_link}")],
        [InlineKeyboardButton(text=t("invite.back_button", language), callback_data="back_to_main")]
    ]
    
    try:
        await message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
