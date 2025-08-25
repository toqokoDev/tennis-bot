import json
from config.config import ADMIN_ID
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.storage import storage

async def is_admin(user_id: int) -> bool:
    admin_ids = [int(ADMIN_ID), 1829352344]
    return user_id in admin_ids

async def get_confirmation_keyboard(action: str, target_id: str = None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    callback_data = f"admin_confirm_{action}"
    if target_id:
        callback_data += f":{target_id}"
    builder.button(text="✅ Да", callback_data=callback_data)
    builder.button(text="❌ Нет", callback_data="admin_cancel")
    return builder.as_markup()

async def is_user_banned(user_id: str) -> bool:
    banned_users = await storage.load_banned_users()
    return user_id in banned_users
