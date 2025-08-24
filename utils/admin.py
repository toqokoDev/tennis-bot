import json
from config.config import ADMIN_ID
from aiogram.utils.keyboard import InlineKeyboardBuilder

def is_admin(user_id: int) -> bool:
    admin_ids = [int(ADMIN_ID), 1829352344]
    return user_id in admin_ids

def load_users():
    try:
        with open('data/users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def load_games():
    try:
        with open('data/games.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_users(users):
    with open('data/users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def save_games(games):
    with open('data/games.json', 'w', encoding='utf-8') as f:
        json.dump(games, f, ensure_ascii=False, indent=2)

def get_confirmation_keyboard(action: str, target_id: str = None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    callback_data = f"admin_confirm_{action}"
    if target_id:
        callback_data += f":{target_id}"
    builder.button(text="✅ Да", callback_data=callback_data)
    builder.button(text="❌ Нет", callback_data="admin_cancel")
    return builder.as_markup()

def load_banned_users():
    try:
        with open('data/banned_users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_banned_users(banned_users):
    with open('data/banned_users.json', 'w', encoding='utf-8') as f:
        json.dump(banned_users, f, ensure_ascii=False, indent=2)
