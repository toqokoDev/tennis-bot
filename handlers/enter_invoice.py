from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import copy
import os
import glob
from typing import List, Optional, Union
from datetime import datetime

from config.config import SUBSCRIPTION_PRICE, BOT_USERNAME
from config.paths import GAMES_PHOTOS_DIR
from models.states import AddScoreState
from services.channels import send_game_notification_to_channel
from services.storage import storage
from utils.tournament_manager import tournament_manager
from utils.admin import is_admin
from utils.media import save_media_file
from utils.utils import calculate_age, calculate_new_ratings, create_user_profile_link, search_users
from handlers.profile import calculate_level_from_points
from utils.translations import get_user_language_async, t

def format_rating(rating: float) -> str:
    """Форматирует рейтинг, убирая лишние нули после запятой"""
    if rating == int(rating):
        return str(int(rating))
    return f"{rating:.1f}".rstrip('0').rstrip('.')

router = Router()


# ID последнего сообщения для редактирования
last_message_ids = {}

# Создание inline клавиатуры для выбора пользователей
async def create_users_inline_keyboard(users_list: List[tuple], action: str, page: int = 0, has_more: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    users_per_page = 8
    
    start_idx = page * users_per_page
    end_idx = min(start_idx + users_per_page, len(users_list))
    
    for user_id, user_data in users_list[start_idx:end_idx]:
        # Если есть фамилия - сокращаем имя, если нет - используем полное имя
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        if last_name:
            name = f"{first_name[0]}. {last_name}".strip()
        else:
            name = first_name.strip()
        
        age = await calculate_age(user_data.get('birth_date', '05.05.2000'))
        gender_profile = user_data.get('gender', '')
        gender_icon = "👨" if gender_profile == 'Мужской' else "👩" if gender_profile == 'Женский' else '👤'
        
        if user_data.get('player_level') and user_data.get('rating_points'):
            display_name = f"{user_data.get('player_level')} ({user_data.get('rating_points')} lvl)"
        else:
            display_name = ""
        year = "лет" if language == "ru" else "years"
        btn_text = f"{gender_icon} {name} {age} {year} {display_name}"

        builder.button(text=btn_text, callback_data=f"{action}:{user_id}")
    
    builder.adjust(1)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text=t("common.back", language=language), callback_data=f"nav:{action}:{page-1}"))
    if has_more and end_idx < len(users_list):
        nav_buttons.append(InlineKeyboardButton(text=t("common.next", language=language), callback_data=f"nav:{action}:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text=t("common.back", language=language), callback_data="back"))
    
    return builder.as_markup()

# Создание inline клавиатуры для выбора типа игры
async def create_game_type_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("enter_invoice.single_game", language=language), callback_data="game_type:single")
    builder.button(text=t("enter_invoice.double_game", language=language), callback_data="game_type:double")
    builder.button(text=t("enter_invoice.tournament_game", language=language), callback_data="game_type:tournament")
    builder.button(text=t("enter_invoice.back", language=language), callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

# Создание inline клавиатуры для выбора счета супертайбрейка
def create_supertiebreak_keyboard(set_number: int = 3, language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Левая колонка: победа первого игрока (10:0 до 10:8, потом 11:9 до 20:18)
    left_scores = ["10:0", "10:1", "10:2", "10:3", "10:4", "10:5", "10:6", "10:7", "10:8"]
    right_scores = ["0:10", "1:10", "2:10", "3:10", "4:10", "5:10", "6:10", "7:10", "8:10"]
    
    # Добавляем кнопки в две колонки
    for left_score, right_score in zip(left_scores, right_scores):
        builder.row(
            InlineKeyboardButton(text=left_score, callback_data=f"set_score:{set_number}_{left_score}"),
            InlineKeyboardButton(text=right_score, callback_data=f"set_score:{set_number}_{right_score}")
        )
    
    # Добавляем счета с разницей в 2 (11:9, 12:10, и т.д.)
    extra_scores = [
        ("11:9", "9:11"), ("12:10", "10:12"), ("13:11", "11:13"), 
        ("14:12", "12:14"), ("15:13", "13:15"), ("16:14", "14:16"),
        ("17:15", "15:17"), ("18:16", "16:18"), ("19:17", "17:19"), ("20:18", "18:20")
    ]
    
    for left_score, right_score in extra_scores:
        builder.row(
            InlineKeyboardButton(text=left_score, callback_data=f"set_score:{set_number}_{left_score}"),
            InlineKeyboardButton(text=right_score, callback_data=f"set_score:{set_number}_{right_score}")
        )
    
    builder.row(InlineKeyboardButton(text=t("common.back_to_regular", language=language), callback_data=f"back_to_normal_set:{set_number}"))
    builder.row(InlineKeyboardButton(text=t("common.back", language=language), callback_data="back"))
    
    return builder.as_markup()

# Создание inline клавиатуры для выбора счета сета
def create_set_score_keyboard(set_number: int = 1, language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Левая колонка: победа первого игрока
    left_scores = ["6:0", "6:1", "6:2", "6:3", "6:4", "7:5", "7:6"]
    
    # Правая колонка: победа второго игрока
    right_scores = ["0:6", "1:6", "2:6", "3:6", "4:6", "5:7", "6:7"]
    
    # Добавляем кнопки в две колонки
    for left_score, right_score in zip(left_scores, right_scores):
        builder.row(
            InlineKeyboardButton(text=left_score, callback_data=f"set_score:{set_number}_{left_score}"),
            InlineKeyboardButton(text=right_score, callback_data=f"set_score:{set_number}_{right_score}")
        )
    
    # На 3-ем сете добавляем супертайбрейк для всех типов игр
    if set_number == 3:
        builder.row(
            InlineKeyboardButton(text=t("enter_invoice.super_tie_button", language=language), callback_data=f"supertiebreak:{set_number}")
        )
    
    # Кнопки навигации
    if set_number > 1:
        builder.row(
            InlineKeyboardButton(text=t("enter_invoice.previous_set_button", language=language), callback_data=f"prev_set:{set_number-1}"),
            InlineKeyboardButton(text=t("enter_invoice.next_set_button", language=language), callback_data=f"next_set:{set_number+1}")
        )
    else:
        builder.row(InlineKeyboardButton(text=t("enter_invoice.next_set_button", language=language), callback_data=f"next_set:{set_number+1}"))
    
    builder.row(InlineKeyboardButton(text=t("enter_invoice.complete_entry_button", language=language), callback_data="finish_score"))
    builder.row(InlineKeyboardButton(text=t("enter_invoice.back", language=language), callback_data="back"))
    
    return builder.as_markup()

# Сохранение ID сообщения для редактирования
def save_message_id(user_id: int, message_id: int):
    last_message_ids[user_id] = message_id

# Получение сохраненного ID сообщения
def get_message_id(user_id: int) -> Optional[int]:
    return last_message_ids.get(user_id)

# Удаление предыдущего сообщения и отправка нового
async def delete_and_send_new_message(message: types.Message, text: str, keyboard: InlineKeyboardMarkup = None, parse_mode: str = None):
    try:
        await message.delete()
    except:
        pass
    
    new_msg = await message.answer(text, reply_markup=keyboard, parse_mode=parse_mode)
    save_message_id(message.chat.id, new_msg.message_id)
    return new_msg

# Редактирование сообщения с медиа
async def edit_media_message(callback: types.CallbackQuery, text: str, keyboard: InlineKeyboardMarkup, media_data: dict = None):
    try:
        if media_data:
            # Если есть медиа, удаляем старое сообщение и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass
            
            if 'photo_id' in media_data:
                new_msg = await callback.message.answer_photo(
                    media_data['photo_id'],
                    caption=text,
                    reply_markup=keyboard, 
                    parse_mode="Markdown"
                )
            elif 'video_id' in media_data:
                new_msg = await callback.message.answer_video(
                    media_data['video_id'],
                    caption=text,
                    reply_markup=keyboard, 
                    parse_mode="Markdown"
                )
            else:
                new_msg = await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            # Если нет медиа, редактируем текст
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            new_msg = callback.message
    except Exception as e:
        # Если не удалось отредактировать, отправляем новое сообщение
        try:
            await callback.message.delete()
        except:
            pass
        new_msg = await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    
    save_message_id(callback.message.chat.id, new_msg.message_id)
    return new_msg

@router.message(F.text.in_([t("menu.enter_score", "ru"), t("menu.enter_score", "en")]))
async def handle_add_score(message: types.Message, state: FSMContext):
    # Проверяем наличие активной подписки
    user_id = message.chat.id
    users = await storage.load_users()
    language = await get_user_language_async(str(message.chat.id))
    
    if not await is_admin(user_id):
        if not users[str(user_id)].get('subscription', {}).get('active', False):
            # Показываем сообщение о необходимости подписки
            referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
            text = t("enter_invoice.enter_invoice_locked", language, price=SUBSCRIPTION_PRICE, referral_link=referral_link)
            
            await message.answer(
                text,
                parse_mode="HTML"
            )
            return
    
    # Если подписка активна, продолжаем процесс
    await state.set_state(AddScoreState.selecting_game_type)
    
    keyboard = await create_game_type_keyboard(language=language)
    msg = await message.answer(t("enter_invoice.select_game_type", language=language), reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("game_type:"))
async def handle_game_type_selection(callback: types.CallbackQuery, state: FSMContext):
    game_type = callback.data.split(":")[1]
    
    await state.update_data(game_type=game_type)
    
    if game_type == "single":
        await state.set_state(AddScoreState.searching_opponent)
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.message.edit_text(
            t("enter_invoice.search_opponent_prompt", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        
    elif game_type == "double":
        await state.set_state(AddScoreState.selecting_partner)
        language = await get_user_language_async(str(callback.message.chat.id))
        await callback.message.edit_text(
            t("enter_invoice.search_partner_prompt", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
    
    elif game_type == "tournament":
        # Tournament logic moved to handlers.tournament_score
        from handlers.tournament_score import create_tournament_keyboard
        await state.set_state(AddScoreState.selecting_tournament)
        current_user_id = str(callback.message.chat.id)
        keyboard = await create_tournament_keyboard(current_user_id)
        await callback.message.edit_text(
            t("enter_invoice.select_tournament", await get_user_language_async(str(callback.message.chat.id))),
            reply_markup=keyboard
        )
    
    await callback.answer()

@router.message(AddScoreState.searching_opponent)
async def handle_opponent_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    language = await get_user_language_async(current_user_id)

    matching_users = await search_users(search_query, exclude_ids=[current_user_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
        )
        msg = await message.answer(
            t("enter_invoice.users_not_found", language=language),
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(opponent_search=search_query)
    await state.set_state(AddScoreState.selecting_opponent)
    
    keyboard = await create_users_inline_keyboard(matching_users, "select_opponent", language=language)
    msg = await message.answer(t("enter_invoice.select_opponent", language=language), reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.message(AddScoreState.selecting_partner)
async def handle_partner_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id])
    
    if not matching_users:
        language = await get_user_language_async(str(message.chat.id))
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
        )
        msg = await message.answer(
            t("enter_invoice.users_not_found", language=language),
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(partner_search=search_query)
    await state.set_state(AddScoreState.searching_partner)
    
    language = await get_user_language_async(str(message.chat.id))
    keyboard = await create_users_inline_keyboard(matching_users, "select_partner", language=language)
    msg = await message.answer(t("enter_invoice.select_partner", language=language), reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("select_partner:"))
async def handle_partner_selection(callback: types.CallbackQuery, state: FSMContext):
    partner_id = callback.data.split(":")[1]
    users = await storage.load_users()
    language = await get_user_language_async(str(callback.message.chat.id))

    if partner_id not in users:
        await callback.answer(t("enter_invoice.user_not_found", language=language))
        return
    
    selected_partner = users[partner_id]
    selected_partner['telegram_id'] = partner_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    partner_sport = selected_partner.get('sport', '')
    
    if current_user_sport != partner_sport:
        await callback.message.edit_text(
            t("enter_invoice.sport_mismatch", language, current=current_user_sport, other=partner_sport),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        await callback.answer(t("enter_invoice.sports_not_match", language=language))
        return
    
    await state.update_data(partner=selected_partner)
    await state.set_state(AddScoreState.searching_opponent1)
    
    await callback.message.edit_text(
        t("enter_invoice.search_opponent1_prompt", language=language),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
        )
    )
    await callback.answer()

@router.message(AddScoreState.searching_opponent1)
async def handle_opponent1_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    data = await state.get_data()
    partner_id = data.get('partner', {}).get('telegram_id')
    language = await get_user_language_async(str(message.chat.id))
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
        )
        msg = await message.answer(
            t("enter_invoice.users_not_found", language=language),
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(opponent1_search=search_query)
    await state.set_state(AddScoreState.selecting_opponent1)
    
    keyboard = await create_users_inline_keyboard(matching_users, "select_opponent1", language=language)
    msg = await message.answer(t("enter_invoice.select_opponent", language=language), reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("select_opponent1:"))
async def handle_opponent1_selection(callback: types.CallbackQuery, state: FSMContext):
    opponent_id = callback.data.split(":")[1]
    users = await storage.load_users()
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if opponent_id not in users:
        await callback.answer(t("enter_invoice.opponent_not_found", language=language))
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    opponent_sport = selected_opponent.get('sport', '')
    
    
    if current_user_sport != opponent_sport:
        await callback.message.edit_text(
            t("enter_invoice.sport_mismatch", language, current=current_user_sport, other=opponent_sport),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        await callback.answer(t("enter_invoice.sports_not_match", language=language))
        return
    
    await state.update_data(opponent1=selected_opponent)
    await state.set_state(AddScoreState.searching_opponent2)
    
    await callback.message.edit_text(
        t("enter_invoice.search_opponent2_prompt", language=language),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
        )
    )
    await callback.answer()

@router.message(AddScoreState.searching_opponent2)
async def handle_opponent2_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    language = await get_user_language_async(str(message.chat.id))
    data = await state.get_data()
    partner_id = data.get('partner', {}).get('telegram_id')
    opponent1_id = data.get('opponent1', {}).get('telegram_id')
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id, opponent1_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
        )
        msg = await message.answer(
            t("enter_invoice.users_not_found", language=language),
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(opponent2_search=search_query)
    await state.set_state(AddScoreState.selecting_opponent2)

    keyboard = await create_users_inline_keyboard(matching_users, "select_opponent2", language=language)
    msg = await message.answer(t("enter_invoice.select_opponent2", language=language), reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("select_opponent2:"))
async def handle_opponent2_selection(callback: types.CallbackQuery, state: FSMContext):
    opponent_id = callback.data.split(":")[1]
    users = await storage.load_users()
    language = await get_user_language_async(str(callback.message.chat.id))

    if opponent_id not in users:
        await callback.answer(t("enter_invoice.opponent_not_found", language=language))
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    opponent_sport = selected_opponent.get('sport', '')
    
    if current_user_sport != opponent_sport:
        await callback.message.edit_text(
            t("enter_invoice.sport_mismatch", language, current=current_user_sport, other=opponent_sport),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        await callback.answer(t("enter_invoice.sports_not_match", language=language))
        return
    
    await state.update_data(opponent2=selected_opponent)
    await state.set_state(AddScoreState.selecting_set_score)
    
    data = await state.get_data()
    partner = data.get('partner')
    opponent1 = data.get('opponent1')
    opponent2 = selected_opponent
    
    keyboard = create_set_score_keyboard(1, language=language)

    await callback.message.edit_text(
        t("enter_invoice.pairs_formed", 
          language, 
          team1_player1=await create_user_profile_link(current_user, current_user.get('telegram_id'), additional=False), 
          team1_player2=await create_user_profile_link(partner, partner.get('telegram_id'), additional=False), 
          team2_player1=await create_user_profile_link(opponent1, opponent1.get('telegram_id'), additional=False), 
          team2_player2=await create_user_profile_link(opponent2, opponent2.get('telegram_id'), additional=False), 
          team1_avg=(current_user.get('rating_points', 0) + partner.get('rating_points', 0)) / 2, 
          team2_avg=(opponent1.get('rating_points', 0) + opponent2.get('rating_points', 0)) / 2
        ),
        reply_markup=keyboard, 
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("select_opponent:"))
async def handle_single_opponent_selection(callback: types.CallbackQuery, state: FSMContext):
    opponent_id = callback.data.split(":")[1]
    users = await storage.load_users()
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if opponent_id not in users:
        await callback.answer(t("enter_invoice.opponent_not_found", language=language))
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    opponent_sport = selected_opponent.get('sport', '')
    
    if current_user_sport != opponent_sport:
        await callback.message.edit_text(
            t("enter_invoice.sport_mismatch", language, current=current_user_sport, other=opponent_sport),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        await callback.answer(t("enter_invoice.sports_not_match", language=language))
        return
    
    await state.update_data(opponent1=selected_opponent)
    await state.set_state(AddScoreState.selecting_set_score)
    
    opponent = selected_opponent
    
    keyboard = create_set_score_keyboard(1, language=language)
    
    await callback.message.edit_text( 
        t("enter_invoice.search_opponent", 
          language, 
          opponent_link=await create_user_profile_link(opponent, opponent.get('telegram_id', ''), additional=False), 
          user_score=current_user.get('rating_points', 0)
        ),
        reply_markup=keyboard, 
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("set_score:"))
async def handle_set_score_selection(callback: types.CallbackQuery, state: FSMContext):
    set_number_str, score = callback.data.replace("set_score:", "").split("_")
    set_number = int(set_number_str)
    data = await state.get_data()
    sets = data.get('sets', [])
    language = await get_user_language_async(str(callback.message.chat.id))
    
    # Проверяем, был ли выбран супертайбрейк
    supertiebreak_set = data.get('supertiebreak_set')
    
    # Если это супертайбрейк, просто используем счет как есть
    if supertiebreak_set == set_number:
        await state.update_data(supertiebreak_set=None)
    
    # Обновляем или добавляем счет сета
    if len(sets) >= set_number:
        sets[set_number - 1] = score
    else:
        sets.append(score)
    
    await state.update_data(sets=sets)
    
    # Проверяем, завершена ли игра
    team1_wins = sum(1 for s in sets if int(s.split(':')[0]) > int(s.split(':')[1]))
    team2_wins = sum(1 for s in sets if int(s.split(':')[0]) < int(s.split(':')[1]))
    
    if team1_wins >= 2 or team2_wins >= 2:
        # Игра завершена
        await process_completed_game(callback, state)
    else:
        # Предлагаем добавить еще сет
        await state.set_state(AddScoreState.adding_another_set)
        builder = InlineKeyboardBuilder()
        builder.button(text=t("enter_invoice.add_another_set_button", language=language), callback_data="add_another_set:yes")
        builder.button(text=t("enter_invoice.complete_input_button", language=language), callback_data="add_another_set:no")
        builder.button(text=t("enter_invoice.back", language=language), callback_data="back")
        builder.adjust(1)
        
        sets_ = "Сет" if language == "ru" else "Set"

        sets_text = "\n".join([f"{sets_} {i+1}: {s}" for i, s in enumerate(sets)])
        
        await callback.message.edit_text(
            t("enter_invoice.current_score", language, score=sets_text),
            reply_markup=builder.as_markup()
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("add_another_set:"))
async def handle_add_another_set(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    language = await get_user_language_async(str(callback.message.chat.id))

    if action == "yes":
        data = await state.get_data()
        sets = data.get('sets', [])
        next_set_number = len(sets) + 1
        
        await state.set_state(AddScoreState.selecting_set_score)
        keyboard = create_set_score_keyboard(next_set_number, language=language)
        
        await callback.message.edit_text(
            t("enter_invoice.select_score", language, next_set_number=next_set_number),
            reply_markup=keyboard
        )
    else:
        await process_completed_game(callback, state)
    
    await callback.answer()

@router.callback_query(F.data.startswith(("prev_set:", "next_set:")))
async def handle_navigate_sets(callback: types.CallbackQuery, state: FSMContext):
    action_, set_number_str = callback.data.split(":")
    set_number = int(set_number_str)

    language = await get_user_language_async(str(callback.message.chat.id))
    
    await state.set_state(AddScoreState.selecting_set_score)
    keyboard = create_set_score_keyboard(set_number, language=language)
    
    await callback.message.edit_text(
        t("enter_invoice.select_score", language, next_set_number=set_number),
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("supertiebreak:"))
async def handle_supertiebreak_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора супертайбрейка для 3-его сета в турнирной игре"""
    set_number = int(callback.data.split(":")[1])
    language = await get_user_language_async(str(callback.message.chat.id))

    # Сохраняем выбор супертайбрейка
    await state.update_data(supertiebreak_set=set_number)
    
    # Показываем клавиатуру выбора счета супертайбрейка
    keyboard = create_supertiebreak_keyboard(set_number, language=language)
    
    await callback.message.edit_text(
        t("enter_invoice.super_tiebreak", language=language),
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("back_to_normal_set:"))
async def handle_back_to_normal_set(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к обычному выбору счета сета"""
    set_number = int(callback.data.split(":")[1])
    
    language = await get_user_language_async(str(callback.message.chat.id))

    # Очищаем данные о супертайбрейке
    data = await state.get_data()
    if 'supertiebreak_set' in data:
        await state.update_data(supertiebreak_set=None)
    
    keyboard = create_set_score_keyboard(set_number, language=language)
    
    await callback.message.edit_text(
        t("enter_invoice.select_score", language, next_set_number=set_number),
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "finish_score")
async def handle_finish_score(callback: types.CallbackQuery, state: FSMContext):
    await process_completed_game(callback, state)
    await callback.answer()

async def process_completed_game(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sets = data.get('sets', [])
    language = await get_user_language_async(str(callback.message.chat.id))
    
    if not sets:
        await callback.answer(t("enter_invoice.score_not_entered", language=language))
        return
    
    # Рассчитываем общую разницу геймов
    total_game_diff = 0
    for set_score in sets:
        games1, games2 = map(int, set_score.split(':'))
        total_game_diff += abs(games1 - games2)
    
    # Определяем победителя
    team1_wins = sum(1 for s in sets if int(s.split(':')[0]) > int(s.split(':')[1]))
    team2_wins = sum(1 for s in sets if int(s.split(':')[0]) < int(s.split(':')[1]))
    
    if team1_wins > team2_wins:
        winner_side = "team1"
    else:
        winner_side = "team2"
    
    score_text = ", ".join(sets)
    
    await state.update_data(
        score=score_text,
        sets=sets,
        game_difference=total_game_diff,
        winner_side=winner_side
    )
    
    await state.set_state(AddScoreState.adding_media)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=t("common.add_photo", language=language), callback_data="media:photo")
    builder.button(text=t("common.add_video", language=language), callback_data="media:video")
    builder.button(text=t("common.skip", language=language), callback_data="media:skip")
    builder.button(text=t("common.back", language=language), callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text(
        t("enter_invoice.attach_media_to_result", language=language),
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("media:"))
async def handle_media_selection(callback: types.CallbackQuery, state: FSMContext):
    media_type = callback.data.split(":")[1]
    language = await get_user_language_async(str(callback.message.chat.id))

    if media_type == "skip":
        await confirm_score(callback, state)
    elif media_type == "photo":
        await callback.message.edit_text(
            t("common.send_photo", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
    elif media_type == "video":
        await callback.message.edit_text(
            t("common.send_video", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
    
    await callback.answer()

# Обработка фото
@router.message(AddScoreState.adding_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    language = await get_user_language_async(str(message.chat.id))

    await state.update_data(photo_id=photo_id, media_type='photo')
    
    # Удаляем сообщение с просьбой отправить фото
    try:
        await message.delete()
        msg = await message.answer(t("common.loading", language=language))
        await state.update_data(media_message_id=msg.message_id)
    except:
        pass
    
    await confirm_score(message, state)

# Обработка видео
@router.message(AddScoreState.adding_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    video_id = message.video.file_id
    language = await get_user_language_async(str(message.chat.id))

    await state.update_data(video_id=video_id, media_type='video')
    
    # Удаляем сообщение с просьбой отправить видео
    try:
        await message.delete()
        msg = await message.answer(t("common.loading", language=language))
        await state.update_data(media_message_id=msg.message_id)
    except:
        pass
    
    await confirm_score(message, state)

async def confirm_score(message_or_callback: Union[types.Message, types.CallbackQuery], state: FSMContext):
    # Разворачиваем message/callback
    if isinstance(message_or_callback, types.CallbackQuery):
        message = message_or_callback.message
        callback = message_or_callback
        bot = callback.bot
    else:
        message = message_or_callback
        callback = None
        bot = message.bot

    language = await get_user_language_async(str(message.chat.id))

    # Данные состояния
    data = await state.get_data()
    media_message_id = data.get('media_message_id')
    
    game_type: str = data.get('game_type')            # 'single' | 'double'
    score = data.get('score')
    sets = data.get('sets')
    game_diff = data.get('game_difference')
    winner_side = data.get('winner_side')             # 'team1' | 'team2'

    # Загрузка пользователей и текущего
    users = await storage.load_users()
    current_id = str(message.chat.id)
    current_user = copy.deepcopy(users.get(current_id, {}))

    if not current_user:
        if callback:
            await callback.message.edit_text(t("common.profile_not_found", language=language))
        else:
            await message.answer(t("common.profile_not_found", language=language))
        await state.clear()
        return

    # Уникальный ID игры
    game_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Сохраняем медиафайл (если есть)
    media_filename = None
    try:
        if 'photo_id' in data and bot:
            media_filename = await save_media_file(bot, data['photo_id'], 'photo', game_id)
        elif 'video_id' in data and bot:
            media_filename = await save_media_file(bot, data['video_id'], 'video', game_id)
    except Exception as e:
        print(f"Ошибка при сохранении медиа: {e}")

    # Утилиты для ID и получения рейтингов
    def pid(player_dict: dict | None) -> str | None:
        if not player_dict:
            return None
        return str(player_dict.get('telegram_id'))

    def rating_of(player_dict: dict | None) -> float:
        """Получить рейтинг игрока из users (если есть), иначе из самого объекта."""
        if not player_dict:
            return 0.0
        _id = pid(player_dict)
        if _id and _id in users:
            return float(users[_id].get('rating_points', 0))
        return float(player_dict.get('rating_points', 0))

    # Фиксируем старые рейтинги ДО изменений
    old_ratings: dict[str, float] = {}
    old_ratings[current_id] = float(current_user.get('rating_points', 0))

    partner = data.get('partner') if game_type == 'double' else None
    opponent1 = data.get('opponent1')
    opponent2 = data.get('opponent2') if game_type == 'double' else None

    if partner:
        pid_partner = pid(partner)
        if pid_partner:
            old_ratings[pid_partner] = rating_of(partner)
    if opponent1:
        pid_op1 = pid(opponent1)
        if pid_op1:
            old_ratings[pid_op1] = rating_of(opponent1)
    if opponent2:
        pid_op2 = pid(opponent2)
        if pid_op2:
            old_ratings[pid_op2] = rating_of(opponent2)

    # Готовим переменные для результата
    result_text = ""
    rating_changes_for_game: dict[str, float] = {}

    # ---- ТУРНИРНАЯ ИГРА ----
    if game_type == 'tournament':
        opponent = opponent1
        op_id = pid(opponent)
        tournament_id = data.get('tournament_id')
        
        if not opponent or not op_id or not tournament_id:
            err = "Ошибка: данные турнирной игры неполные"
            if callback:
                await callback.message.edit_text(err)
            else:
                await message.answer(err)
            await state.clear()
            return

        # Получаем информацию о турнире
        tournaments = await storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        tournament_name = tournament_data.get('name', 'Неизвестный турнир')

        # Старые рейтинги
        curr_old = old_ratings[current_id]
        opp_old = old_ratings[op_id]

        # Определяем победителя
        if winner_side == "team1":  # team1 = текущий пользователь
            winner_user = current_user
            loser_user = opponent
            winner_old = curr_old
            loser_old = opp_old
        else:  # победил соперник
            winner_user = opponent
            loser_user = current_user
            winner_old = opp_old
            loser_old = curr_old

        # Пересчёт рейтингов (как в одиночной игре)
        new_winner_points, new_loser_points = await calculate_new_ratings(
            winner_old, loser_old, game_diff
        )

        # Обновляем users по факту победителя/проигравшего
        if winner_side == "team1":
            # Текущий пользователь — победитель
            users[current_id]['rating_points'] = new_winner_points
            users[current_id]['player_level'] = calculate_level_from_points(
                int(new_winner_points), 
                users[current_id].get('sport', '🎾Большой теннис')
            )
            if op_id in users:
                users[op_id]['rating_points'] = new_loser_points
                users[op_id]['player_level'] = calculate_level_from_points(
                    int(new_loser_points), 
                    users[op_id].get('sport', '🎾Большой теннис')
                )

            # Дельты для game_data
            rating_changes_for_game[current_id] = float(new_winner_points - curr_old)
            rating_changes_for_game[op_id] = float(new_loser_points - opp_old)

            # Для state (если используется дальше)
            await state.update_data(
                rating_change=rating_changes_for_game[current_id],
                opponent_rating_change=rating_changes_for_game[op_id],
                rating_changes=rating_changes_for_game,
                old_ratings=old_ratings
            )
        else:
            # Соперник — победитель
            users[current_id]['rating_points'] = new_loser_points
            users[current_id]['player_level'] = calculate_level_from_points(
                int(new_loser_points), 
                users[current_id].get('sport', '🎾Большой теннис')
            )
            if op_id in users:
                users[op_id]['rating_points'] = new_winner_points
                users[op_id]['player_level'] = calculate_level_from_points(
                    int(new_winner_points), 
                    users[op_id].get('sport', '🎾Большой теннис')
                )

            rating_changes_for_game[current_id] = float(new_loser_points - curr_old)
            rating_changes_for_game[op_id] = float(new_winner_points - opp_old)

            await state.update_data(
                rating_change=rating_changes_for_game[current_id],
                opponent_rating_change=rating_changes_for_game[op_id],
                rating_changes=rating_changes_for_game,
                old_ratings=old_ratings
            )

        winner_rating_change = new_winner_points - winner_old
        loser_rating_change = new_loser_points - loser_old

        # Форматируем изменения рейтинга
        winner_rating_formatted = f"{'+' if winner_rating_change > 0 else ''}{format_rating(winner_rating_change)}"
        loser_rating_formatted = f"{'+' if loser_rating_change > 0 else ''}{format_rating(loser_rating_change)}"

        # Вычисляем новые рейтинги
        winner_new_rating = winner_old + winner_rating_change
        loser_new_rating = loser_old + loser_rating_change

        # Получаем имена пользователей
        winner_name = winner_user.get('first_name', '')
        loser_name = loser_user.get('first_name', '')

        # Форматируем строки изменений рейтинга
        winner_rating_line = f"• {winner_name}: {format_rating(winner_old)} → {format_rating(winner_new_rating)} ({winner_rating_formatted})"
        loser_rating_line = f"• {loser_name}: {format_rating(loser_old)} → {format_rating(loser_new_rating)} ({loser_rating_formatted})"

        result_text = t("enter_invoice.tournament_match_message", language,
            tournament_name=tournament_name,
            winner_name_link=await create_user_profile_link(winner_user, pid(winner_user) or "", additional=False),
            loser_name_link=await create_user_profile_link(loser_user, pid(loser_user) or "", additional=False),
            score=score,
            winner_rating_line=winner_rating_line,
            loser_rating_line=loser_rating_line
        )

    # ---- ОДИНОЧНАЯ ИГРА ----
    elif game_type == 'single':
        opponent = opponent1
        op_id = pid(opponent)
        if not opponent or not op_id:
            # Без соперника не можем подтвердить
            err = "Ошибка: соперник не выбран"
            if callback:
                await callback.message.edit_text(err)
            else:
                await message.answer(err)
            await state.clear()
            return

        # Старые рейтинги
        curr_old = old_ratings[current_id]
        opp_old = old_ratings[op_id]

        # Кто победил
        if winner_side == "team1":  # team1 = текущий пользователь
            winner_user = current_user
            loser_user = opponent
            winner_old = curr_old
            loser_old = opp_old
        else:  # победил соперник
            winner_user = opponent
            loser_user = current_user
            winner_old = opp_old
            loser_old = curr_old

        # Пересчёт рейтингов
        new_winner_points, new_loser_points = await calculate_new_ratings(
            winner_old, loser_old, game_diff
        )

        # Обновляем users по факту победителя/проигравшего
        if winner_side == "team1":
            # Текущий пользователь — победитель
            users[current_id]['rating_points'] = new_winner_points
            users[current_id]['player_level'] = calculate_level_from_points(
                int(new_winner_points), 
                users[current_id].get('sport', '🎾Большой теннис')
            )
            if op_id in users:
                users[op_id]['rating_points'] = new_loser_points
                users[op_id]['player_level'] = calculate_level_from_points(
                    int(new_loser_points), 
                    users[op_id].get('sport', '🎾Большой теннис')
                )

            # Дельты для game_data
            rating_changes_for_game[current_id] = float(new_winner_points - curr_old)
            rating_changes_for_game[op_id] = float(new_loser_points - opp_old)

            # Для state (если используется дальше)
            await state.update_data(
                rating_change=rating_changes_for_game[current_id],
                opponent_rating_change=rating_changes_for_game[op_id],
                rating_changes=rating_changes_for_game,
                old_ratings=old_ratings
            )
        else:
            # Соперник — победитель
            users[current_id]['rating_points'] = new_loser_points
            users[current_id]['player_level'] = calculate_level_from_points(
                int(new_loser_points), 
                users[current_id].get('sport', '🎾Большой теннис')
            )
            if op_id in users:
                users[op_id]['rating_points'] = new_winner_points
                users[op_id]['player_level'] = calculate_level_from_points(
                    int(new_winner_points), 
                    users[op_id].get('sport', '🎾Большой теннис')
                )

            rating_changes_for_game[current_id] = float(new_loser_points - curr_old)
            rating_changes_for_game[op_id] = float(new_winner_points - opp_old)

            await state.update_data(
                rating_change=rating_changes_for_game[current_id],
                opponent_rating_change=rating_changes_for_game[op_id],
                rating_changes=rating_changes_for_game,
                old_ratings=old_ratings
            )

        winner_rating_change = new_winner_points - winner_old
        loser_rating_change = new_loser_points - loser_old

        # Форматируем изменения рейтинга
        winner_rating_formatted = f"{'+' if winner_rating_change > 0 else ''}{format_rating(winner_rating_change)}"
        loser_rating_formatted = f"{'+' if loser_rating_change > 0 else ''}{format_rating(loser_rating_change)}"

        # Вычисляем новые рейтинги
        winner_new_rating = winner_old + winner_rating_change
        loser_new_rating = loser_old + loser_rating_change

        # Получаем имена пользователей
        winner_name = winner_user.get('first_name', '')
        loser_name = loser_user.get('first_name', '')

        # Форматируем строки изменений рейтинга
        winner_rating_line = f"• {winner_name}: {format_rating(winner_old)} → {format_rating(winner_new_rating)} ({winner_rating_formatted})"
        loser_rating_line = f"• {loser_name}: {format_rating(loser_old)} → {format_rating(loser_new_rating)} ({loser_rating_formatted})"

        result_text = t("enter_invoice.single_match_message", language,
            winner_link=await create_user_profile_link(winner_user, pid(winner_user) or "", additional=False),
            loser_link=await create_user_profile_link(loser_user, pid(loser_user) or "", additional=False),
            score=score,
            winner_rating_line=winner_rating_line,
            loser_rating_line=loser_rating_line
        )

    # ---- ПАРНАЯ ИГРА ----
    else:
        # Проверим наличие всех участников
        pid_partner = pid(partner)
        pid_op1 = pid(opponent1)
        pid_op2 = pid(opponent2)
        if not (pid_partner and pid_op1 and pid_op2):
            err = "Ошибка: для парной игры должны быть выбран(ы) партнёр и оба соперника"
            if callback:
                await callback.message.edit_text(err)
            else:
                await message.answer(err)
            await state.clear()
            return

        # Средние рейтинги команд (старые)
        team1_old_avg = (old_ratings[current_id] + old_ratings[pid_partner]) / 2
        team2_old_avg = (old_ratings[pid_op1] + old_ratings[pid_op2]) / 2

        if winner_side == "team1":
            winner_team = [current_user, partner]
            loser_team = [opponent1, opponent2]
            winner_old_avg = team1_old_avg
            loser_old_avg = team2_old_avg
        else:
            winner_team = [opponent1, opponent2]
            loser_team = [current_user, partner]
            winner_old_avg = team2_old_avg
            loser_old_avg = team1_old_avg

        # Пересчёт рейтингов для средних значений
        new_winner_avg, new_loser_avg = await calculate_new_ratings(
            winner_old_avg, loser_old_avg, game_diff
        )

        # Дельты (распределяем поровну каждому участнику своей команды — как и у вас ранее)
        delta_winner_each = new_winner_avg - winner_old_avg
        delta_loser_each = new_loser_avg - loser_old_avg

        # Обновляем users, добавляя дельту каждому игроку соответствующей команды
        for p in winner_team:
            _id = pid(p)
            if _id and _id in users:
                new_points = float(users[_id].get('rating_points', 0)) + float(delta_winner_each)
                users[_id]['rating_points'] = new_points
                users[_id]['player_level'] = calculate_level_from_points(
                    int(new_points), 
                    users[_id].get('sport', '🎾Большой теннис')
                )

        for p in loser_team:
            _id = pid(p)
            if _id and _id in users:
                new_points = float(users[_id].get('rating_points', 0)) + float(delta_loser_each)
                users[_id]['rating_points'] = new_points
                users[_id]['player_level'] = calculate_level_from_points(
                    int(new_points), 
                    users[_id].get('sport', '🎾Большой теннис')
                )

        # Считаем rating_changes_for_game на основе old_ratings
        for p in (winner_team + loser_team):
            _id = pid(p)
            if not _id:
                continue
            old_val = old_ratings.get(_id, float(p.get('rating_points', 0)))
            # Зная, к какой команде принадлежит p, применяем нужную дельту
            d = delta_winner_each if p in winner_team else delta_loser_each
            rating_changes_for_game[_id] = float(d)

        # Готовим текст результата
        async def line_player(player_dict: dict) -> str:
            _id = pid(player_dict) or ""
            name_link = await create_user_profile_link(player_dict, _id, additional=False)
            old_val = old_ratings.get(_id, rating_of(player_dict))
            delta = rating_changes_for_game.get(_id, 0.0)
            new_val = old_val + delta
            sign = '+' if delta > 0 else ''
            return f"• {name_link}: {format_rating(old_val)} → {format_rating(new_val)} ({sign}{format_rating(delta)})"

        result_text = t("enter_invoice.doubles_match_message", language,
            current_user_link=await create_user_profile_link(current_user, current_id, additional=False),
            partner_link=await create_user_profile_link(partner, pid_partner, additional=False),
            opponent1_link=await create_user_profile_link(opponent1, pid_op1, additional=False),
            opponent2_link=await create_user_profile_link(opponent2, pid_op2, additional=False),
            score=score
        )

        # Добавляем строки с изменениями для всех игроков (в порядке победители, потом проигравшие)
        for p in (winner_team + loser_team):
            result_text += await line_player(p) + "\n"

        # Для обратных действий (если у вас где-то есть откат) сохраню old_ratings в state
        await state.update_data(old_ratings=old_ratings, rating_changes=rating_changes_for_game)

    # ---- Сохранение игры в историю ----
    # Формируем списки игроков по командам
    players_block = {
        'team1': [current_id] + ([pid_partner] if game_type == 'double' and pid_partner else []),
        'team2': [pid_op1] + ([pid_op2] if game_type == 'double' and pid_op2 else [])
    }

    # game_data.rating_changes — используем уже посчитанные дельты (новый - старый)
    # Определим winner_id для записи (важно для турнирных таблиц)
    winner_id_for_record = None
    if game_type == 'tournament':
        # В турнире team1 = текущий пользователь, team2 = соперник1
        opponent = data.get('opponent1')
        op_id_local = pid(opponent) if opponent else None
        if winner_side == 'team1':
            winner_id_for_record = current_id
        elif winner_side == 'team2':
            winner_id_for_record = op_id_local
    elif game_type == 'single':
        opponent = data.get('opponent1')
        op_id_local = pid(opponent) if opponent else None
        if winner_side == 'team1':
            winner_id_for_record = current_id
        elif winner_side == 'team2':
            winner_id_for_record = op_id_local
    else:
        # double
        partner = data.get('partner')
        opponent1 = data.get('opponent1')
        opponent2 = data.get('opponent2')
        # Для пар — фиксируем победу за стороной (team1/team2); индивидуальные winner_id здесь не критичен для турниров
        if winner_side == 'team1':
            winner_id_for_record = current_id
        elif winner_side == 'team2':
            winner_id_for_record = pid(opponent1)
    game_data = {
        'id': game_id,
        'date': datetime.now().isoformat(),
        'type': game_type,
        'score': score,
        'sets': sets,
        'media_filename': media_filename,
        'players': players_block,
        'rating_changes': rating_changes_for_game,
        'tournament_id': data.get('tournament_id'),  # Добавляем ID турнира для турнирных игр
        'status': 'completed',
        'winner_id': winner_id_for_record
    }

    games = await storage.load_games()
    games.append(game_data)

    # Если это турнирная игра — добавим/обновим запись матча в самом турнире
    try:
        if game_type == 'tournament' and data.get('tournament_id'):
            tournaments = await storage.load_tournaments()
            tid = data.get('tournament_id')
            t_tournaments = tournaments.get(tid, {})
            t_matches = t_tournaments.get('matches') or []
            # Идентификация матча: по составу пар (без учета порядка)
            def key_of(p1: str | None, p2: str | None):
                if not p1 or not p2:
                    return None
                a, b = sorted([str(p1), str(p2)])
                return f"{a}__{b}"
            new_key = key_of(current_id, pid(opponent1))
            updated = False
            seen_keys = set()
            for m in t_matches:
                mk = key_of(str(m.get('player1_id')), str(m.get('player2_id')))
                if mk:
                    seen_keys.add(mk)
                if new_key and mk == new_key:
                    # обновим счет и победителя
                    m['score'] = score
                    m['winner_id'] = winner_id_for_record
                    updated = True
                    break
            if not updated and new_key:
                # Добавляем новый матч в список
                t_matches.append({
                    'round': data.get('tournament_round', 0),
                    'match_number': data.get('tournament_match_number', 0),
                    'player1_id': current_id,
                    'player2_id': pid(opponent1),
                    'score': score,
                    'winner_id': winner_id_for_record
                })
            t_tournaments['matches'] = t_matches
            tournaments[tid] = t_tournaments
            await storage.save_tournaments(tournaments)
    except Exception as e:
        print(f"[TOURNAMENT][MATCHES] Не удалось обновить матчи турнира: {e}")

    # Сохраняем игры и пользователей
    await storage.save_games(games)
    await storage.save_users(users)

    # Обновляем state — пригодится на экране подтверждения
    await state.update_data(result_text=result_text, game_id=game_id)
    await state.set_state(AddScoreState.confirming_score)

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=t("enter_invoice.confirm_button", language=language), callback_data="confirm:yes")
    keyboard.button(text=t("enter_invoice.edit_score_button", language=language), callback_data="confirm:edit_score")
    keyboard.button(text=t("common.cancel", language=language), callback_data="confirm:no")
    keyboard.adjust(1)

    # Подготовка медиа
    media_data = {}
    if 'photo_id' in data:
        media_data['photo_id'] = data['photo_id']
    elif 'video_id' in data:
        media_data['video_id'] = data['video_id']

    # Отправка/редактирование сообщения
    if callback:
        await edit_media_message(callback, result_text, keyboard.as_markup(), media_data)
    else:
        try:
            await message.delete()
        except:
            pass
        if 'photo_id' in data:
            await message.answer_photo(
                data['photo_id'],
                caption=result_text,
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
        elif 'video_id' in data:
            await message.answer_video(
                data['video_id'],
                caption=result_text,
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
        else:
            await message.answer(result_text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

    try:
        await bot.delete_message(message.chat.id, media_message_id)
    except:
        pass

@router.callback_query(F.data.startswith("confirm:"))
async def handle_score_confirmation(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    
    current_user_id = str(callback.message.chat.id)
    language = await get_user_language_async(str(callback.message.chat.id))
    await state.update_data(current_user_id=current_user_id)
    
    if action == "yes":
        data = await state.get_data()
        result_text = data.get('result_text', '')
        
        # Загружаем пользователей для обновления статистики
        users = await storage.load_users()
        game_type = data.get('game_type')
        winner_side = data.get('winner_side')
        
        # Для турнирной игры
        if game_type == 'tournament':
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            tournament_id = data.get('tournament_id')
            match_id = data.get('tournament_match_id')
            
            # Обновляем games_played для обоих игроков
            users[current_user_id]['games_played'] = users[current_user_id].get('games_played', 0) + 1
            if opponent_id in users:
                users[opponent_id]['games_played'] = users[opponent_id].get('games_played', 0) + 1
            
            # Обновляем games_wins для победителя
            winner_id = current_user_id if winner_side == "team1" else opponent_id
            if winner_side == "team1":  # Победил текущий пользователь
                users[current_user_id]['games_wins'] = users[current_user_id].get('games_wins', 0) + 1
            else:  # Победил соперник
                if opponent_id in users:
                    users[opponent_id]['games_wins'] = users[opponent_id].get('games_wins', 0) + 1
            
            # Обновляем результат матча в турнире и подготавливаем следующий раунд
            if match_id:
                await tournament_manager.update_match_result(match_id, winner_id, data.get('score'), bot=callback.bot)
                # После обновления результата можно уведомить участников о новых матчах
                try:
                    from utils.tournament_notifications import TournamentNotifications
                    notifications = TournamentNotifications(callback.bot)
                except Exception:
                    pass
        
        # Для одиночной игры
        elif game_type == 'single':
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            
            # Обновляем games_played для обоих игроков
            users[current_user_id]['games_played'] = users[current_user_id].get('games_played', 0) + 1
            if opponent_id in users:
                users[opponent_id]['games_played'] = users[opponent_id].get('games_played', 0) + 1
            
            # Обновляем games_wins для победителя
            if winner_side == "team1":  # Победил текущий пользователь
                users[current_user_id]['games_wins'] = users[current_user_id].get('games_wins', 0) + 1
            else:  # Победил соперник
                if opponent_id in users:
                    users[opponent_id]['games_wins'] = users[opponent_id].get('games_wins', 0) + 1
        
        # Для парной игры
        else:
            players = [
                current_user_id,
                data.get('partner', {}).get('telegram_id'),
                data.get('opponent1', {}).get('telegram_id'),
                data.get('opponent2', {}).get('telegram_id')
            ]
            
            # Обновляем games_played для всех игроков
            for player_id in players:
                if player_id in users:
                    users[player_id]['games_played'] = users[player_id].get('games_played', 0) + 1
            
            # Обновляем games_wins для победившей команды
            if winner_side == "team1":  # Победила команда текущего пользователя
                team1_players = [current_user_id, data.get('partner', {}).get('telegram_id')]
                for player_id in team1_players:
                    if player_id in users:
                        users[player_id]['games_wins'] = users[player_id].get('games_wins', 0) + 1
            else:  # Победила команда соперников
                team2_players = [
                    data.get('opponent1', {}).get('telegram_id'),
                    data.get('opponent2', {}).get('telegram_id')
                ]
                for player_id in team2_players:
                    if player_id in users:
                        users[player_id]['games_wins'] = users[player_id].get('games_wins', 0) + 1
        
        # Сохраняем обновленную статистику
        await storage.save_users(users)
        
        # Отправляем уведомления другим игрокам с ссылками на профили
        if game_type == 'tournament':
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            tournament_id = data.get('tournament_id')
            
            if opponent_id in users:
                try:
                    opponent_user = users[opponent_id]
                    current_user = users[current_user_id]
                    tournaments = await storage.load_tournaments()
                    tournament_data = tournaments.get(tournament_id, {})
                    tournament_name = tournament_data.get('name', 'Неизвестный турнир')
                    
                    opponent_link = await create_user_profile_link(current_user, current_user_id, additional=False)
                    
                    # Определяем результат для соперника
                    if winner_side == "team1":
                        # Текущий пользователь победил, соперник проиграл
                        result_msg = (
                            f"🏆 Турнирная игра завершена!\n"
                            f"🏆 Турнир: {tournament_name}\n\n"
                            f"📢 Вам засчитано поражение в игре против {opponent_link}\n"
                            f"Счет: {data.get('score')}\n"
                            f"Ваш новый рейтинг: {format_rating(users[opponent_id]['rating_points'])}"
                        )
                    else:
                        # Соперник победил
                        result_msg = (
                            f"🏆 Турнирная игра завершена!\n"
                            f"🏆 Турнир: {tournament_name}\n\n"
                            f"🎉 Поздравляем с победой в игре против {opponent_link}!\n"
                            f"Счет: {data.get('score')}\n"
                            f"Ваш новый рейтинг: {format_rating(users[opponent_id]['rating_points'])}"
                        )
                    
                    await callback.bot.send_message(
                        opponent_id,
                        result_msg,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    print(f"Ошибка при отправке уведомления сопернику: {e}")
        
        elif game_type == 'single':
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            if opponent_id in users:
                try:
                    opponent_user = users[opponent_id]
                    current_user = users[current_user_id]
                    
                    opponent_link = await create_user_profile_link(current_user, current_user_id, additional=False)
                    
                    # Определяем результат для соперника
                    if winner_side == "team1":
                        # Текущий пользователь победил, соперник проиграл
                        result_msg = (
                            f"📢 Вам засчитано поражение в игре против {opponent_link}\n"
                            f"Счет: {data.get('score')}\n"
                            f"Ваш новый рейтинг: {format_rating(users[opponent_id]['rating_points'])}"
                        )
                    else:
                        # Соперник победил
                        result_msg = (
                            f"🎉 Поздравляем с победой в игре против {opponent_link}!\n"
                            f"Счет: {data.get('score')}\n"
                            f"Ваш новый рейтинг: {format_rating(users[opponent_id]['rating_points'])}"
                        )
                    
                    await callback.bot.send_message(
                        opponent_id,
                        result_msg,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    print(f"Ошибка при отправке уведомления сопернику: {e}")
        
        else:  # Парная игра
            players_to_notify = [
                (data.get('partner', {}).get('telegram_id'), "партнер"),
                (data.get('opponent1', {}).get('telegram_id'), "соперник"),
                (data.get('opponent2', {}).get('telegram_id'), "соперник")
            ]
            
            current_user = users[current_user_id]
            
            for player_id, role in players_to_notify:
                if player_id in users:
                    try:
                        player_user = users[player_id]
                        
                        # Формируем список всех игроков со ссылками
                        all_players = []
                        for p_id in [current_user_id, 
                                    data.get('partner', {}).get('telegram_id'),
                                    data.get('opponent1', {}).get('telegram_id'),
                                    data.get('opponent2', {}).get('telegram_id')]:
                            if p_id in users:
                                p_user = users[p_id]
                                all_players.append(await create_user_profile_link(p_user, p_id, additional=False))
                        
                        players_list = "\n".join(all_players)
                        
                        # Определяем результат для игрока
                        if winner_side == "team1":
                            # Команда 1 (текущий пользователь + партнер) победила
                            if role == "партнер":
                                result_msg = (
                                    f"🎉 Поздравляем с победой в парной игре!\n\n"
                                    f"Участники:\n{players_list}\n\n"
                                    f"Счет: {data.get('score')}\n"
                                    f"Ваш новый рейтинг: {format_rating(users[player_id]['rating_points'])}"
                                )
                            else:
                                result_msg = (
                                    f"📢 Вам засчитано поражение в парной игре\n\n"
                                    f"Участники:\n{players_list}\n\n"
                                    f"Счет: {data.get('score')}\n"
                                    f"Ваш новый рейтинг: {format_rating(users[player_id]['rating_points'])}"
                                )
                        else:
                            # Команда 2 (соперники) победила
                            if role == "соперник":
                                result_msg = (
                                    f"🎉 Поздравляем с победой в парной игре!\n\n"
                                    f"Участники:\n{players_list}\n\n"
                                    f"Счет: {data.get('score')}\n"
                                    f"Ваш новый рейтинг: {format_rating(users[player_id]['rating_points'])}"
                                )
                            else:
                                result_msg = (
                                    f"📢 Вам засчитано поражение в парной игре\n\n"
                                    f"Участники:\n{players_list}\n\n"
                                    f"Счет: {data.get('score')}\n"
                                    f"Ваш новый рейтинг: {format_rating(users[player_id]['rating_points'])}"
                                )
                        
                        await callback.bot.send_message(
                            player_id,
                            result_msg,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        print(f"Ошибка при отправке уведомления игроку {player_id}: {e}")
        
        # Отправляем уведомление в канал о завершенной игре
        try:
            # Добавляем данные об изменениях рейтинга для отображения в канале
            data['rating_changes'] = data.get('rating_changes', {})
            data['old_ratings'] = data.get('old_ratings', {})
            await send_game_notification_to_channel(callback.bot, data, users, current_user_id)
        except Exception as e:
            print(f"Ошибка при отправке уведомления в канал: {e}")
        
        try:
            await callback.message.delete()
        except:
            pass
        
        # Вместо сообщения об успешном сохранении отправляем информацию об игре
        await callback.message.answer(
            result_text,
            reply_markup=None,
            parse_mode="Markdown"
        )
        await state.clear()
        
    elif action == "edit_score":
        await state.set_state(AddScoreState.selecting_set_score)
        keyboard = create_set_score_keyboard(1, language=language)
        
        # Удаляем текущее сообщение и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        new_msg = await callback.message.answer(
            t("enter_invoice.select_score", language, next_set_number=1),
            reply_markup=keyboard
        )
        save_message_id(callback.message.chat.id, new_msg.message_id)
        
    elif action == "no":
        # Откатываем изменения рейтинга и статистики
        users = await storage.load_users()
        data = await state.get_data()
        game_type = data.get('game_type')
        winner_side = data.get('winner_side')
        
        if game_type == 'tournament':
            current_user_id = str(callback.message.chat.id)
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            
            # Откатываем рейтинги
            old_ratings = data.get('old_ratings', {})
            if current_user_id in old_ratings:
                old_rating = old_ratings[current_user_id]
                users[current_user_id]['rating_points'] = old_rating
                users[current_user_id]['player_level'] = calculate_level_from_points(
                    int(old_rating), 
                    users[current_user_id].get('sport', '🎾Большой теннис')
                )
            if opponent_id in users and opponent_id in old_ratings:
                opponent_old_rating = old_ratings[opponent_id]
                users[opponent_id]['rating_points'] = opponent_old_rating
                users[opponent_id]['player_level'] = calculate_level_from_points(
                    int(opponent_old_rating), 
                    users[opponent_id].get('sport', '🎾Большой теннис')
                )
            
            # Откатываем статистику игр
            users[current_user_id]['games_played'] = max(0, users[current_user_id].get('games_played', 0) - 1)
            if opponent_id in users:
                users[opponent_id]['games_played'] = max(0, users[opponent_id].get('games_played', 0) - 1)
            
            # Откатываем победы
            if winner_side == "team1":  # Отменяем победу текущего пользователя
                users[current_user_id]['games_wins'] = max(0, users[current_user_id].get('games_wins', 0) - 1)
            else:  # Отменяем победу соперника
                if opponent_id in users:
                    users[opponent_id]['games_wins'] = max(0, users[opponent_id].get('games_wins', 0) - 1)
        
        elif game_type == 'single':
            current_user_id = str(callback.message.chat.id)
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            
            # Откатываем рейтинг
            old_rating = data.get('old_rating', 0)
            users[current_user_id]['rating_points'] = old_rating
            users[current_user_id]['player_level'] = calculate_level_from_points(
                int(old_rating), 
                users[current_user_id].get('sport', '🎾Большой теннис')
            )
            if opponent_id in users:
                opponent_old_rating = data.get('opponent_old_rating', 0)
                users[opponent_id]['rating_points'] = opponent_old_rating
                users[opponent_id]['player_level'] = calculate_level_from_points(
                    int(opponent_old_rating), 
                    users[opponent_id].get('sport', '🎾Большой теннис')
                )
            
            # Откатываем статистику игр
            users[current_user_id]['games_played'] = max(0, users[current_user_id].get('games_played', 0) - 1)
            if opponent_id in users:
                users[opponent_id]['games_played'] = max(0, users[opponent_id].get('games_played', 0) - 1)
            
            # Откатываем победы
            if winner_side == "team1":  # Отменяем победу текущего пользователя
                users[current_user_id]['games_wins'] = max(0, users[current_user_id].get('games_wins', 0) - 1)
            else:  # Отменяем победу соперника
                if opponent_id in users:
                    users[opponent_id]['games_wins'] = max(0, users[opponent_id].get('games_wins', 0) - 1)
        
        else:  # double
            # Откатываем рейтинги
            old_ratings = data.get('old_ratings', {})
            for user_id, old_rating in old_ratings.items():
                if user_id in users:
                    users[user_id]['rating_points'] = old_rating
                    users[user_id]['player_level'] = calculate_level_from_points(
                        int(old_rating), 
                        users[user_id].get('sport', '🎾Большой теннис')
                    )
            
            # Откатываем статистику игр для всех участников
            players = [
                str(callback.message.chat.id),
                data.get('partner', {}).get('telegram_id'),
                data.get('opponent1', {}).get('telegram_id'),
                data.get('opponent2', {}).get('telegram_id')
            ]
            
            for player_id in players:
                if player_id in users:
                    users[player_id]['games_played'] = max(0, users[player_id].get('games_played', 0) - 1)
            
            # Откатываем победы для победившей команды
            if winner_side == "team1":  # Отменяем победу команды 1
                team1_players = [
                    str(callback.message.chat.id),
                    data.get('partner', {}).get('telegram_id')
                ]
                for player_id in team1_players:
                    if player_id in users:
                        users[player_id]['games_wins'] = max(0, users[player_id].get('games_wins', 0) - 1)
            else:  # Отменяем победу команды 2
                team2_players = [
                    data.get('opponent1', {}).get('telegram_id'),
                    data.get('opponent2', {}).get('telegram_id')
                ]
                for player_id in team2_players:
                    if player_id in users:
                        users[player_id]['games_wins'] = max(0, users[player_id].get('games_wins', 0) - 1)
        
        await storage.save_users(users)
        
        # Удаляем сохраненный медиафайл, если есть
        game_id = data.get('game_id')
        if game_id:
            try:
                photo_path = f"data/games_photo/{game_id}_photo.*"
                video_path = f"data/games_photo/{game_id}_video.*"
                
                for file_path in [photo_path, video_path]:
                    for f in glob.glob(file_path):
                        os.remove(f)
            except:
                pass
        
        try:
            await callback.message.delete()
        except:
            pass

        await callback.message.answer(
            t("enter_invoice.invoice_cancelled", language=language),
            reply_markup=None
        )
        await state.clear()
    
    await callback.answer()

@router.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    language = await get_user_language_async(str(callback.message.chat.id))

    if current_state == AddScoreState.selecting_game_type.state:
        await callback.message.edit_text(t("common.action_cancelled", language=language))
        await state.clear()
        
    elif current_state == AddScoreState.selecting_tournament.state:
        await state.set_state(AddScoreState.selecting_game_type)
        
        keyboard = await create_game_type_keyboard(language=language)
        await callback.message.edit_text(t("enter_invoice.select_game_type", language=language), reply_markup=keyboard)
        
    elif current_state == AddScoreState.selecting_tournament_opponent.state:
        # Tournament logic moved to handlers.tournament_score
        from handlers.tournament_score import create_tournament_keyboard
        await state.set_state(AddScoreState.selecting_tournament)
        current_user_id = str(callback.message.chat.id)
        keyboard = await create_tournament_keyboard(current_user_id)
        await callback.message.edit_text(t("enter_invoice.select_tournament", language=language), reply_markup=keyboard)
        
    elif current_state == AddScoreState.searching_opponent.state:
        await state.set_state(AddScoreState.selecting_game_type)
        keyboard = await create_game_type_keyboard(language=language)
        await callback.message.edit_text(t("enter_invoice.select_game_type", language=language), reply_markup=keyboard)
        
    elif current_state == AddScoreState.selecting_opponent.state:
        await state.set_state(AddScoreState.searching_opponent)
        await callback.message.edit_text(
            t("enter_invoice.search_opponent_prompt", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        
    elif current_state == AddScoreState.selecting_partner.state:
        await state.set_state(AddScoreState.selecting_game_type)
        keyboard = await create_game_type_keyboard(language=language)
        await callback.message.edit_text(t("enter_invoice.select_game_type", language=language), reply_markup=keyboard)
        
    elif current_state == AddScoreState.searching_partner.state:
        await state.set_state(AddScoreState.selecting_partner)
        await callback.message.edit_text(
            t("enter_invoice.search_partner_prompt", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        
    elif current_state == AddScoreState.searching_opponent1.state:
        await state.set_state(AddScoreState.searching_partner)
        data = await state.get_data()
        search_query = data.get('partner_search', '')
        current_user_id = str(callback.message.chat.id)
        
        matching_users = await search_users(search_query, exclude_ids=[current_user_id])
        
        if matching_users:
            keyboard = await create_users_inline_keyboard(matching_users, "select_partner", language=language)
            await callback.message.edit_text(t("enter_invoice.select_partner", language=language), reply_markup=keyboard)
        else:
            await callback.message.edit_text(
                t("enter_invoice.search_partner_prompt", language=language),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
                )
            )
        
    elif current_state == AddScoreState.selecting_opponent1.state:
        await state.set_state(AddScoreState.searching_opponent1)
        await callback.message.edit_text(
            t("enter_invoice.search_opponent1_prompt", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        
    elif current_state == AddScoreState.searching_opponent2.state:
        await state.set_state(AddScoreState.selecting_opponent1)
        data = await state.get_data()
        search_query = data.get('opponent1_search', '')
        current_user_id = str(callback.message.chat.id)
        partner_id = data.get('partner', {}).get('telegram_id')
        
        matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id])
        
        if matching_users:
            keyboard = await create_users_inline_keyboard(matching_users, "select_opponent1", language=language)
            await callback.message.edit_text(t("enter_invoice.select_opponent", language=language), reply_markup=keyboard)
        else:
            await callback.message.edit_text(
                t("enter_invoice.search_opponent1_prompt", language=language),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
                )
            )
        
    elif current_state == AddScoreState.selecting_opponent2.state:
        await state.set_state(AddScoreState.searching_opponent2)
        await callback.message.edit_text(
            t("enter_invoice.search_opponent2_prompt", language=language),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
            )
        )
        
    elif current_state == AddScoreState.selecting_set_score.state:
        data = await state.get_data()
        game_type = data.get('game_type')
        
        if game_type == 'single':
            await state.set_state(AddScoreState.selecting_opponent)
            data = await state.get_data()
            search_query = data.get('opponent_search', '')
            current_user_id = str(callback.message.chat.id)
            
            matching_users = await search_users(search_query, exclude_ids=[current_user_id])
            
            if matching_users:
                keyboard = await create_users_inline_keyboard(matching_users, "select_opponent", language=language)
                await callback.message.edit_text(t("enter_invoice.select_opponent", language=language), reply_markup=keyboard)
            else:
                await callback.message.edit_text(
                    t("enter_invoice.search_opponent_prompt", language=language),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
                    )
                )
                
        else:
            data = await state.get_data()
            
            if 'opponent2' in data:
                await state.update_data(opponent2=None)
                await state.set_state(AddScoreState.selecting_opponent2)
                data = await state.get_data()
                search_query = data.get('opponent2_search', '')
                current_user_id = str(callback.message.chat.id)
                partner_id = data.get('partner', {}).get('telegram_id')
                opponent1_id = data.get('opponent1', {}).get('telegram_id')
                
                matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id, opponent1_id])
                
                if matching_users:
                    keyboard = await create_users_inline_keyboard(matching_users, "select_opponent2", language=language)
                    await callback.message.edit_text(t("enter_invoice.select_opponent2", language=language), reply_markup=keyboard)
                else:
                    await callback.message.edit_text(
                        t("enter_invoice.search_opponent2_prompt", language=language),
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
                        )
                    )
                
            else:
                await state.update_data(opponent1=None)
                await state.set_state(AddScoreState.selecting_opponent1)
                data = await state.get_data()
                search_query = data.get('opponent1_search', '')
                current_user_id = str(callback.message.chat.id)
                partner_id = data.get('partner', {}).get('telegram_id')
                
                matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id])
                
                if matching_users:
                    keyboard = await create_users_inline_keyboard(matching_users, "select_opponent1", language=language)
                    await callback.message.edit_text(t("enter_invoice.select_opponent", language=language), reply_markup=keyboard)
                else:
                    await callback.message.edit_text(
                        t("enter_invoice.search_opponent1_prompt", language=language),
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data="back")]]
                        )
                    )
        
    elif current_state == AddScoreState.adding_another_set.state:
        await state.set_state(AddScoreState.selecting_set_score)
        data = await state.get_data()
        sets = data.get('sets', [])
        current_set = len(sets)
        keyboard = create_set_score_keyboard(current_set, language=language)
        await callback.message.edit_text(t("enter_invoice.select_score", language, next_set_number=current_set), reply_markup=keyboard)
    
    elif current_state == AddScoreState.adding_media.state:
        await state.set_state(AddScoreState.selecting_set_score)
        data = await state.get_data()
        sets = data.get('sets', [])
        current_set = len(sets)
        keyboard = create_set_score_keyboard(current_set, language=language)
        await callback.message.edit_text(t("enter_invoice.select_score", language, next_set_number=current_set), reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("nav:"))
async def handle_navigation(callback: types.CallbackQuery, state: FSMContext):
    _, action, page_str = callback.data.split(":")
    page = int(page_str)
    
    language = await get_user_language_async(str(callback.message.chat.id))
    current_user_id = str(callback.message.chat.id)
    
    if action == "select_opponent":
        data = await state.get_data()
        search_query = data.get('opponent_search', '')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = await create_users_inline_keyboard(matching_users, action, page, has_more, language=language)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    elif action == "select_partner":
        data = await state.get_data()
        search_query = data.get('partner_search', '')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = await create_users_inline_keyboard(matching_users, action, page, has_more, language=language)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    elif action == "select_opponent1":
        data = await state.get_data()
        search_query = data.get('opponent1_search', '')
        partner_id = data.get('partner', {}).get('telegram_id')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = await create_users_inline_keyboard(matching_users, action, page, has_more, language=language)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    elif action == "select_opponent2":
        data = await state.get_data()
        search_query = data.get('opponent2_search', '')
        partner_id = data.get('partner', {}).get('telegram_id')
        opponent1_id = data.get('opponent1', {}).get('telegram_id')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id, opponent1_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = await create_users_inline_keyboard(matching_users, action, page, has_more, language=language)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("game_history:"))
async def handle_history_request(callback: types.CallbackQuery):
    """Обработчик запроса истории игр"""
    try:
        # Извлекаем ID пользователя, чью историю запрашиваем
        target_user_id = callback.data.split(":")[1]
        current_user_id = str(callback.message.chat.id)
        language = await get_user_language_async(current_user_id)
        
        # Проверяем права доступа для просмотра чужой истории
        if not await is_admin(callback.message.chat.id):
            if current_user_id != target_user_id:
                users = await storage.load_users()
                if not users.get(current_user_id, {}).get('subscription', {}).get('active', False):
                    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{callback.from_user.id}"
                    text = t("enter_invoice.game_history_locked", language, price=SUBSCRIPTION_PRICE, referral_link=referral_link)
                    
                    await callback.message.answer(
                        text,
                        parse_mode="HTML"
                    )
                    return

        # Показываем первую игру из истории
        await show_single_game_history(callback, target_user_id, 0)
        
    except Exception as e:
        print(f"Ошибка при выводе истории: {e}")
        await callback.answer("Произошла ошибка при загрузке истории")

@router.callback_query(F.data.startswith("history_nav:"))
async def handle_history_navigation(callback: types.CallbackQuery):
    """Обработчик навигации по истории игр"""
    try:
        _, target_user_id, game_index_str = callback.data.split(":")
        game_index = int(game_index_str)
        
        await show_single_game_history(callback, target_user_id, game_index)
        
    except Exception as e:
        print(f"Ошибка при навигации по истории: {e}")
        await callback.answer("Произошла ошибка при навигации")

async def show_single_game_history(callback: types.CallbackQuery, target_user_id: str, game_index: int):
    """Показывает одну игру из истории с навигацией"""
    # Загружаем игры и пользователей
    games = await storage.load_games()
    users = await storage.load_users()
    language = await get_user_language_async(str(callback.message.chat.id))
    
    # Получаем информацию о целевом пользователе
    target_user = users.get(target_user_id)
    if not target_user:
        await callback.answer(t("common.user_not_found", language=language))
        return
    
    # Фильтруем игры, в которых участвовал пользователь
    user_games = []
    for game in games:
        # Проверяем участие пользователя в командах
        players_team1 = game['players']['team1']
        players_team2 = game['players']['team2']
        
        if target_user_id in players_team1 or target_user_id in players_team2:
            user_games.append(game)
    
    # Сортируем игры по дате (новые сначала)
    user_games.sort(key=lambda x: x['date'], reverse=True)
    
    if not user_games:
        await callback.message.answer(
            t("enter_invoice.user_game_not_found", language, 
              first_name=target_user.get('first_name', ''), 
              last_name=target_user.get('last_name', '') 
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t("common.back", language=language), callback_data=f"back_to_profile:{callback.message.chat.id}")]]
            )
        )
        await callback.answer()
        return
    
    # Проверяем корректность индекса
    if game_index < 0:
        game_index = 0
    elif game_index >= len(user_games):
        game_index = len(user_games) - 1
    
    # Получаем текущую игру
    game = user_games[game_index]
    game_id = game['id']
    
    # Форматируем дату
    game_date = datetime.fromisoformat(game['date'])
    formatted_date = game_date.strftime("%d.%m.%Y %H:%M")
    
    # Определяем результат для пользователя
    user_in_team1 = target_user_id in game['players']['team1']
    
    team1_wins = sum(1 for set_score in game['sets'] 
                   if int(set_score.split(':')[0]) > int(set_score.split(':')[1]))
    team2_wins = sum(1 for set_score in game['sets'] 
                   if int(set_score.split(':')[0]) < int(set_score.split(':')[1]))
    
    if (user_in_team1 and team1_wins > team2_wins) or (not user_in_team1 and team2_wins > team1_wins):
        result = "✅ Победа" if language == "ru" else "✅ Victory"
    else:
        result = "❌ Поражение" if language == "ru" else "❌ Defeat"
    
    # Получаем изменение рейтинга
    rating_change = game['rating_changes'].get(target_user_id, 0)
    rating_change_str = f"+{format_rating(rating_change)}" if rating_change > 0 else f"{format_rating(rating_change)}"
    
    # Формируем информацию об игре
    game_ = "Игра" if language == "ru" else "Game"

    history_text = f"📊 {game_} #{game_index + 1} / {len(user_games)}\n\n"
    history_text += f"📅 {formatted_date}\n"
    history_text += f"🎯 {result}\n\n"
    
    # Формируем информацию о командах
    if game['type'] == 'single':
        # Для одиночной игры
        opponent_id = game['players']['team2'][0] if user_in_team1 else game['players']['team1'][0]
        opponent = users.get(opponent_id, {})

        history_text += f"👤 Игрок:\n" if language == "ru" else f"👤 Player:\n"
        history_text += f"• {target_user.get('first_name', '')} {target_user.get('last_name', '')}\n\n" 
        history_text += f"👤 Соперник:\n" if language == "ru" else f"👤 Rival:\n"
        history_text += f"• {await create_user_profile_link(opponent, opponent.get('telegram_id'), additional=False)}\n\n"
        
    else:
        # Для парной игры
        if user_in_team1:
            teammate_id = next(pid for pid in game['players']['team1'] if pid != target_user_id)
            opponents = game['players']['team2']
        else:
            teammate_id = next(pid for pid in game['players']['team2'] if pid != target_user_id)
            opponents = game['players']['team1']
        
        teammate = users.get(teammate_id, {})
        opponent1 = users.get(opponents[0], {})
        opponent2 = users.get(opponents[1], {})
        
        teammate_name = await create_user_profile_link(teammate, teammate_id, additional=False)
        opponent1_name = await create_user_profile_link(opponent1, opponents[0], additional=False)
        opponent2_name = await create_user_profile_link(opponent2, opponents[1], additional=False)
        
        pair = "Пара" if language == "ru" else "Pair"

        history_text += f"👥 {pair} 1:\n"
        history_text += f"• {await create_user_profile_link(target_user, target_user.get('telegram_id', ''), additional=False)}\n"
        history_text += f"• {teammate_name}\n\n"
        history_text += f"👥 {pair} 2:\n"
        history_text += f"• {opponent1_name}\n"
        history_text += f"• {opponent2_name}\n\n"
    
    check = "Счет" if language == "ru" else "Score"

    # Добавляем счет
    history_text += f"📊 {check}: {game['score']}\n\n"
    
    rating_change_ = "Изменение рейтинга" if language == "ru" else "Rating change"

    # Добавляем изменение рейтинга
    history_text += f"📈 {rating_change_}: {rating_change_str}\n"
    
    # Добавляем ID игры для админа
    if await is_admin(callback.message.chat.id):
        history_text += f"\n🆔 ID игры: `{game_id}`"
    
    # Создаем клавиатуру с навигацией
    keyboard_buttons = []
    
    # Кнопки навигации
    nav_buttons = []
    if game_index > 0:
        nav_buttons.append(InlineKeyboardButton(
            text=t("common.back", language=language), 
            callback_data=f"game_history:{target_user_id}:{game_index - 1}"
        ))
    if game_index < len(user_games) - 1:
        nav_buttons.append(InlineKeyboardButton(
            text=t("common.next", language=language), 
            callback_data=f"game_history:{target_user_id}:{game_index + 1}"
        ))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Кнопка возврата к профилю
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=t("common.to_profile", language=language), 
            callback_data=f"back_to_profile:{target_user_id}"
        )
    ])
    
    # Кнопка удаления игры для админа (если это не свой профиль или админ смотрит чужую игру)
    if (await is_admin(callback.message.chat.id)):
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🗑️ Удалить игру", 
                callback_data=f"admin_select_game:{game_id}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Проверяем, есть ли медиафайл
    if game.get('media_filename'):
        media_path = f"{GAMES_PHOTOS_DIR}/{game['media_filename']}"
        if os.path.exists(media_path):
            # Определяем тип медиа
            if game['media_filename'].endswith(('.jpg', '.jpeg', '.png')):
                with open(media_path, 'rb') as photo:
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo,
                        caption=history_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            elif game['media_filename'].endswith(('.mp4', '.mov')):
                with open(media_path, 'rb') as video:
                    await callback.message.delete()
                    await callback.message.answer_video(
                        video,
                        caption=history_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            else:
                try:
                    await callback.message.edit_text(history_text, reply_markup=keyboard, parse_mode='Markdown')
                except:
                    await callback.message.delete()
                    await callback.message.answer(history_text, reply_markup=keyboard, parse_mode='Markdown')
        else:
            try:
                await callback.message.edit_text(history_text, reply_markup=keyboard, parse_mode='Markdown')
            except:
                await callback.message.delete()
                await callback.message.answer(history_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        try:
            await callback.message.edit_text(history_text, reply_markup=keyboard, parse_mode='Markdown')
        except:
            await callback.message.delete()
            await callback.message.answer(history_text, reply_markup=keyboard, parse_mode='Markdown')
    
    await callback.answer()
