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
from utils.admin import is_admin
from utils.media import save_media_file
from utils.utils import calculate_new_ratings, create_user_profile_link, search_users

def format_rating(rating: float) -> str:
    """Форматирует рейтинг, убирая лишние нули после запятой"""
    if rating == int(rating):
        return str(int(rating))
    return f"{rating:.1f}".rstrip('0').rstrip('.')

router = Router()

# ID последнего сообщения для редактирования
last_message_ids = {}

# Создание inline клавиатуры для выбора пользователей
def create_users_inline_keyboard(users_list: List[tuple], action: str, page: int = 0, has_more: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    users_per_page = 8
    
    start_idx = page * users_per_page
    end_idx = min(start_idx + users_per_page, len(users_list))
    
    for user_id, user_data in users_list[start_idx:end_idx]:
        name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}"
        rating = user_data.get('rating_points', 0)
        btn_text = f"{name} ({rating})"
        builder.button(text=btn_text, callback_data=f"{action}:{user_id}")
    
    builder.adjust(1)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"nav:{action}:{page-1}"))
    if has_more and end_idx < len(users_list):
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"nav:{action}:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    
    return builder.as_markup()

# Создание inline клавиатуры для выбора типа игры
def create_game_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Одиночная игра", callback_data="game_type:single")
    builder.button(text="👥 Парная игра", callback_data="game_type:double")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

# Создание inline клавиатуры для выбора счета сета
def create_set_score_keyboard(set_number: int = 1) -> InlineKeyboardMarkup:
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
    
    # Кнопки навигации
    if set_number > 1:
        builder.row(
            InlineKeyboardButton(text="⬅️ Предыдущий сет", callback_data=f"prev_set:{set_number-1}"),
            InlineKeyboardButton(text="➡️ Следующий сет", callback_data=f"next_set:{set_number+1}")
        )
    else:
        builder.row(InlineKeyboardButton(text="➡️ Следующий сет", callback_data=f"next_set:{set_number+1}"))
    
    builder.row(InlineKeyboardButton(text="✅ Завершить ввод счета", callback_data="finish_score"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    
    return builder.as_markup()

# Создание inline клавиатуры для добавления еще одного сета
def create_add_another_set_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, добавить еще сет", callback_data="add_another_set:yes")
    builder.button(text="❌ Нет, завершить ввод", callback_data="add_another_set:no")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

# Создание inline клавиатуры для медиа
def create_media_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📷 Прикрепить фото", callback_data="media:photo")
    builder.button(text="🎥 Прикрепить видео", callback_data="media:video")
    builder.button(text="➡️ Пропустить", callback_data="media:skip")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

# Создание inline клавиатуры для подтверждения
def create_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm:yes")
    builder.button(text="✏️ Редактировать счет", callback_data="confirm:edit_score")
    builder.button(text="❌ Отменить", callback_data="confirm:no")
    builder.adjust(1)
    return builder.as_markup()

# Создание inline клавиатуры для навигации по истории игр
def create_history_navigation_keyboard(game_index: int, total_games: int, target_user_id: str, current_user_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Кнопки навигации
    if game_index > 0:
        builder.button(text="⬅️ Предыдущая", callback_data=f"history_nav:{target_user_id}:{game_index-1}")
    
    if game_index < total_games - 1:
        builder.button(text="Следующая ➡️", callback_data=f"history_nav:{target_user_id}:{game_index+1}")
    
    builder.adjust(2)
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{current_user_id}")
    )
    
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

@router.message(F.text == "📝 Внести счет")
async def handle_add_score(message: types.Message, state: FSMContext):
    # Проверяем наличие активной подписки
    user_id = message.chat.id
    users = await storage.load_users()
    
    # @TODO 
    # if not await is_admin(user_id):
    #     if not users[str(user_id)].get('subscription', {}).get('active', False):
    #         # Показываем сообщение о необходимости подписки
    #         referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
    #         text = (
    #             "🔒 <b>Доступ закрыт</b>\n\n"
    #             "Функция внесения счета доступна только для пользователей с активной подписки Tennis-Play PRO.\n\n"
    #             f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n"
    #             "Перейдите в раздел '💳 Платежи' для оформления подписки.\n\n"
    #             "Также вы можете получить подписку бесплатно, пригласив 5 друзей.\n"
    #             "Ваша персональная ссылка для приглашений доступна в разделе «🔗 Пригласить друга».\n\n"
    #             f"🔗 <b>Ваша реферальная ссылка:</b>\n"
    #             f"<code>{referral_link}</code>\n\n"
    #         )
            
    #         await message.answer(
    #             text,
    #             parse_mode="HTML"
    #         )
    #         return
    
    # Если подписка активна, продолжаем процесс
    await state.set_state(AddScoreState.selecting_game_type)
    
    keyboard = create_game_type_keyboard()
    msg = await message.answer("Выберите тип игры:", reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("game_type:"))
async def handle_game_type_selection(callback: types.CallbackQuery, state: FSMContext):
    game_type = callback.data.split(":")[1]
    
    await state.update_data(game_type=game_type)
    
    if game_type == "single":
        await state.set_state(AddScoreState.searching_opponent)
        await callback.message.edit_text(
            "Поиск соперника\nНапишите имя или фамилию соперника:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        
    else:  # double
        await state.set_state(AddScoreState.selecting_partner)
        await callback.message.edit_text(
            "Ваш партнер по паре\nНапишите имя или фамилию партнера:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
    
    await callback.answer()

@router.message(AddScoreState.searching_opponent)
async def handle_opponent_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
        msg = await message.answer(
            "Пользователи не найдены. Попробуйте еще раз:",
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(opponent_search=search_query)
    await state.set_state(AddScoreState.selecting_opponent)
    
    keyboard = create_users_inline_keyboard(matching_users, "select_opponent")
    msg = await message.answer("Выберите соперника из списка:", reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.message(AddScoreState.selecting_partner)
async def handle_partner_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
        msg = await message.answer(
            "Пользователи не найдены. Попробуйте еще раз:",
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(partner_search=search_query)
    await state.set_state(AddScoreState.searching_partner)
    
    keyboard = create_users_inline_keyboard(matching_users, "select_partner")
    msg = await message.answer("Выберите партнера из списка:", reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("select_partner:"))
async def handle_partner_selection(callback: types.CallbackQuery, state: FSMContext):
    partner_id = callback.data.split(":")[1]
    users = await storage.load_users()
    
    if partner_id not in users:
        await callback.answer("Пользователь не найден")
        return
    
    selected_partner = users[partner_id]
    selected_partner['telegram_id'] = partner_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    partner_sport = selected_partner.get('sport', '')
    
    if current_user_sport != partner_sport:
        await callback.message.edit_text(
            f"❌ Нельзя играть с игроками другого вида спорта!\n\n"
            f"Ваш вид спорта: {current_user_sport}\n"
            f"Вид спорта партнера: {partner_sport}\n\n"
            f"Выберите партнера с тем же видом спорта.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        await callback.answer("Виды спорта не совпадают")
        return
    
    await state.update_data(partner=selected_partner)
    await state.set_state(AddScoreState.searching_opponent1)
    
    await callback.message.edit_text(
        "Поиск первого соперника\nНапишите имя или фамилию первого соперника:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
    )
    await callback.answer()

@router.message(AddScoreState.searching_opponent1)
async def handle_opponent1_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    data = await state.get_data()
    partner_id = data.get('partner', {}).get('telegram_id')
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
        msg = await message.answer(
            "Пользователи не найдены. Попробуйте еще раз:",
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(opponent1_search=search_query)
    await state.set_state(AddScoreState.selecting_opponent1)
    
    keyboard = create_users_inline_keyboard(matching_users, "select_opponent1")
    msg = await message.answer("Выберите первого соперника из списка:", reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("select_opponent1:"))
async def handle_opponent1_selection(callback: types.CallbackQuery, state: FSMContext):
    opponent_id = callback.data.split(":")[1]
    users = await storage.load_users()
    
    if opponent_id not in users:
        await callback.answer("Соперник не найден")
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    opponent_sport = selected_opponent.get('sport', '')
    
    if current_user_sport != opponent_sport:
        await callback.message.edit_text(
            f"❌ Нельзя играть с игроками другого вида спорта!\n\n"
            f"Ваш вид спорта: {current_user_sport}\n"
            f"Вид спорта соперника: {opponent_sport}\n\n"
            f"Выберите соперника с тем же видом спорта.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        await callback.answer("Виды спорта не совпадают")
        return
    
    await state.update_data(opponent1=selected_opponent)
    await state.set_state(AddScoreState.searching_opponent2)
    
    await callback.message.edit_text(
        "Поиск второго соперника\nНапишите имя или фамилию второго соперника:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
    )
    await callback.answer()

@router.message(AddScoreState.searching_opponent2)
async def handle_opponent2_search(message: types.Message, state: FSMContext):
    search_query = message.text
    current_user_id = str(message.chat.id)
    data = await state.get_data()
    partner_id = data.get('partner', {}).get('telegram_id')
    opponent1_id = data.get('opponent1', {}).get('telegram_id')
    
    matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id, opponent1_id])
    
    if not matching_users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
        msg = await message.answer(
            "Пользователи не найдены. Попробуйте еще раз:",
            reply_markup=keyboard
        )
        save_message_id(message.chat.id, msg.message_id)
        return
    
    await state.update_data(opponent2_search=search_query)
    await state.set_state(AddScoreState.selecting_opponent2)
    
    keyboard = create_users_inline_keyboard(matching_users, "select_opponent2")
    msg = await message.answer("Выберите второго соперника из списка:", reply_markup=keyboard)
    save_message_id(message.chat.id, msg.message_id)

@router.callback_query(F.data.startswith("select_opponent2:"))
async def handle_opponent2_selection(callback: types.CallbackQuery, state: FSMContext):
    opponent_id = callback.data.split(":")[1]
    users = await storage.load_users()
    
    if opponent_id not in users:
        await callback.answer("Соперник не найден")
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    opponent_sport = selected_opponent.get('sport', '')
    
    if current_user_sport != opponent_sport:
        await callback.message.edit_text(
            f"❌ Нельзя играть с игроками другого вида спорта!\n\n"
            f"Ваш вид спорта: {current_user_sport}\n"
            f"Вид спорта соперника: {opponent_sport}\n\n"
            f"Выберите соперника с тем же видом спорта.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        await callback.answer("Виды спорта не совпадают")
        return
    
    await state.update_data(opponent2=selected_opponent)
    await state.set_state(AddScoreState.selecting_set_score)
    
    data = await state.get_data()
    partner = data.get('partner')
    opponent1 = data.get('opponent1')
    opponent2 = selected_opponent
    
    team1_avg = (current_user.get('rating_points', 0) + partner.get('rating_points', 0)) / 2
    team2_avg = (opponent1.get('rating_points', 0) + opponent2.get('rating_points', 0)) / 2
    
    keyboard = create_set_score_keyboard(1)
    
    await callback.message.edit_text(
        f"Команды сформированы:\n\n"
        f"Команда 1 (ваша):\n"
        f"• {await create_user_profile_link(current_user, current_user.get('telegram_id'))}\n" 
        f"• {await create_user_profile_link(partner, partner.get('telegram_id'))}\n"
        f"Средний рейтинг: {team1_avg:.0f}\n\n"
        f"Команда 2:\n"
        f"• {await create_user_profile_link(opponent1, opponent1.get('telegram_id'))}\n"
        f"• {await create_user_profile_link(opponent2, opponent2.get('telegram_id'))}\n"
        f"Средний рейтинг: {team2_avg:.0f}\n\n"
        f"Выберите счет 1-го сета:",
        reply_markup=keyboard, 
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("select_opponent:"))
async def handle_single_opponent_selection(callback: types.CallbackQuery, state: FSMContext):
    opponent_id = callback.data.split(":")[1]
    users = await storage.load_users()
    
    if opponent_id not in users:
        await callback.answer("Соперник не найден")
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Проверяем совместимость видов спорта
    current_user = users.get(str(callback.message.chat.id))
    current_user_sport = current_user.get('sport', '')
    opponent_sport = selected_opponent.get('sport', '')
    
    if current_user_sport != opponent_sport:
        await callback.message.edit_text(
            f"❌ Нельзя играть с игроками другого вида спорта!\n\n"
            f"Ваш вид спорта: {current_user_sport}\n"
            f"Вид спорта соперника: {opponent_sport}\n\n"
            f"Выберите соперника с тем же видом спорта.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        await callback.answer("Виды спорта не совпадают")
        return
    
    await state.update_data(opponent1=selected_opponent)
    await state.set_state(AddScoreState.selecting_set_score)
    
    opponent = selected_opponent
    
    keyboard = create_set_score_keyboard(1)
    
    await callback.message.edit_text(
        f"Вы выбрали соперника:\n"
        f"👤 {await create_user_profile_link(opponent, opponent.get('telegram_id', ''))}\n\n"
        f"Ваш рейтинг: {current_user.get('rating_points', 0)}\n\n"
        f"Выберите счет 1-го сета:",
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
        keyboard = create_add_another_set_keyboard()
        
        sets_text = "\n".join([f"Сет {i+1}: {s}" for i, s in enumerate(sets)])
        
        await callback.message.edit_text(
            f"Текущий счет:\n{sets_text}\n\n"
            f"Добавить еще один сет?",
            reply_markup=keyboard
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("add_another_set:"))
async def handle_add_another_set(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    
    if action == "yes":
        data = await state.get_data()
        sets = data.get('sets', [])
        next_set_number = len(sets) + 1
        
        await state.set_state(AddScoreState.selecting_set_score)
        keyboard = create_set_score_keyboard(next_set_number)
        
        await callback.message.edit_text(
            f"Выберите счет {next_set_number}-го сета:",
            reply_markup=keyboard
        )
    else:
        await process_completed_game(callback, state)
    
    await callback.answer()

@router.callback_query(F.data.startswith(("prev_set:", "next_set:")))
async def handle_navigate_sets(callback: types.CallbackQuery, state: FSMContext):
    action, set_number_str = callback.data.split(":")
    set_number = int(set_number_str)
    
    await state.set_state(AddScoreState.selecting_set_score)
    keyboard = create_set_score_keyboard(set_number)
    
    await callback.message.edit_text(
        f"Выберите счет {set_number}-го сета:",
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
    
    if not sets:
        await callback.answer("Счет не введен")
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
    
    keyboard = create_media_keyboard()
    await callback.message.edit_text(
        "Хотите прикрепить фото или видео к результату?",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("media:"))
async def handle_media_selection(callback: types.CallbackQuery, state: FSMContext):
    media_type = callback.data.split(":")[1]
    
    if media_type == "skip":
        await confirm_score(callback, state)
    elif media_type == "photo":
        await callback.message.edit_text(
            "Пожалуйста, отправьте фото:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
    elif media_type == "video":
        await callback.message.edit_text(
            "Пожалуйста, отправьте видео:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
    
    await callback.answer()

# Обработка фото
@router.message(AddScoreState.adding_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id, media_type='photo')
    
    # Удаляем сообщение с просьбой отправить фото
    try:
        await message.delete()
        await message.answer("Загрузка фото...")
    except:
        pass
    
    await confirm_score(message, state)

# Обработка видео
@router.message(AddScoreState.adding_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    video_id = message.video.file_id
    await state.update_data(video_id=video_id, media_type='video')
    
    # Удаляем сообщение с просьбой отправить видео
    try:
        await message.delete()
        await message.answer("Загрузка видео...")
    except:
        pass
    
    await confirm_score(message, state)

async def confirm_score(message_or_callback: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """
    Подтверждение счета: пересчёт рейтингов, формирование итогового сообщения,
    сохранение игры в историю и обновление пользователей.
    Исправления:
      - Всегда фиксируем старые рейтинги ДО любых изменений.
      - rating_changes в game_data считаем на основе разницы (новый - старый), а не по данным уже перезаписанных объектов.
      - Аккуратно обновляем users[...] без перезаписи whole-объектов deep copy.
    """
    # Разворачиваем message/callback
    if isinstance(message_or_callback, types.CallbackQuery):
        message = message_or_callback.message
        callback = message_or_callback
        bot = callback.bot
    else:
        message = message_or_callback
        callback = None
        bot = message.bot

    # Данные состояния
    data = await state.get_data()
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
            await callback.message.edit_text("Ошибка: ваш профиль не найден")
        else:
            await message.answer("Ошибка: ваш профиль не найден")
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

    # ---- ОДИНОЧНАЯ ИГРА ----
    if game_type == 'single':
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
            if op_id in users:
                users[op_id]['rating_points'] = new_loser_points

            # Дельты для game_data
            rating_changes_for_game[current_id] = float(new_winner_points - curr_old)
            rating_changes_for_game[op_id] = float(new_loser_points - opp_old)

            # Для state (если используется дальше)
            await state.update_data(
                rating_change=rating_changes_for_game[current_id],
                opponent_rating_change=rating_changes_for_game[op_id]
            )
        else:
            # Соперник — победитель
            users[current_id]['rating_points'] = new_loser_points
            if op_id in users:
                users[op_id]['rating_points'] = new_winner_points

            rating_changes_for_game[current_id] = float(new_loser_points - curr_old)
            rating_changes_for_game[op_id] = float(new_winner_points - opp_old)

            await state.update_data(
                rating_change=rating_changes_for_game[current_id],
                opponent_rating_change=rating_changes_for_game[op_id]
            )

        # Текст результата
        # Показываем сверху победителя
        winner_name_link = await create_user_profile_link(winner_user, pid(winner_user) or "")
        loser_name_link = await create_user_profile_link(loser_user, pid(loser_user) or "")

        result_text = (
            f"🎯 Одиночная игра\n\n"
            f"👤 {winner_name_link}\n"
            f"🆚\n"
            f"👤 {loser_name_link}\n\n"
            f"📊 Счёт: {score}\n\n"
            f"📈 Изменение рейтинга:\n"
            f"• {winner_user.get('first_name', '')}: {format_rating(winner_old)} → "
            f"{format_rating(winner_old + (new_winner_points - winner_old))} "
            f"({'+' if (new_winner_points - winner_old) > 0 else ''}{format_rating(new_winner_points - winner_old)})\n"
            f"• {loser_user.get('first_name', '')}: {format_rating(loser_old)} → "
            f"{format_rating(loser_old + (new_loser_points - loser_old))} "
            f"({'+' if (new_loser_points - loser_old) > 0 else ''}{format_rating(new_loser_points - loser_old)})"
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
                users[_id]['rating_points'] = float(users[_id].get('rating_points', 0)) + float(delta_winner_each)

        for p in loser_team:
            _id = pid(p)
            if _id and _id in users:
                users[_id]['rating_points'] = float(users[_id].get('rating_points', 0)) + float(delta_loser_each)

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
            name_link = await create_user_profile_link(player_dict, _id)
            old_val = old_ratings.get(_id, rating_of(player_dict))
            delta = rating_changes_for_game.get(_id, 0.0)
            new_val = old_val + delta
            sign = '+' if delta > 0 else ''
            return f"• {name_link}: {format_rating(old_val)} → {format_rating(new_val)} ({sign}{format_rating(delta)})"

        result_text = (
            f"👥 Парная игра\n\n"
            f"Команда 1:\n"
            f"• {await create_user_profile_link(current_user, current_id)}\n"
            f"• {await create_user_profile_link(partner, pid_partner)}\n\n"
            f"Команда 2:\n"
            f"• {await create_user_profile_link(opponent1, pid_op1)}\n"
            f"• {await create_user_profile_link(opponent2, pid_op2)}\n\n"
            f"📊 Счёт: {score}\n\n"
            f"📈 Изменение рейтинга:\n"
        )

        # Добавляем строки с изменениями для всех игроков (в порядке победители, потом проигравшие)
        for p in (winner_team + loser_team):
            result_text += line_player(p) + "\n"

        # Для обратных действий (если у вас где-то есть откат) сохраню old_ratings в state
        await state.update_data(old_ratings=old_ratings)

    # ---- Сохранение игры в историю ----
    # Формируем списки игроков по командам
    players_block = {
        'team1': [current_id] + ([pid_partner] if game_type == 'double' and pid_partner else []),
        'team2': [pid_op1] + ([pid_op2] if game_type == 'double' and pid_op2 else [])
    }

    # game_data.rating_changes — используем уже посчитанные дельты (новый - старый)
    game_data = {
        'id': game_id,
        'date': datetime.now().isoformat(),
        'type': game_type,
        'score': score,
        'sets': sets,
        'media_filename': media_filename,
        'players': players_block,
        'rating_changes': rating_changes_for_game
    }

    games = await storage.load_games()
    games.append(game_data)

    # Сохраняем игры и пользователей
    await storage.save_games(games)
    await storage.save_users(users)

    # Обновляем state — пригодится на экране подтверждения
    await state.update_data(result_text=result_text, game_id=game_id)
    await state.set_state(AddScoreState.confirming_score)

    keyboard = create_confirmation_keyboard()

    # Подготовка медиа
    media_data = {}
    if 'photo_id' in data:
        media_data['photo_id'] = data['photo_id']
    elif 'video_id' in data:
        media_data['video_id'] = data['video_id']

    # Отправка/редактирование сообщения
    if callback:
        await edit_media_message(callback, result_text, keyboard, media_data)
    else:
        try:
            await message.delete()
        except:
            pass
        if 'photo_id' in data:
            await message.answer_photo(
                data['photo_id'],
                caption=result_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        elif 'video_id' in data:
            await message.answer_video(
                data['video_id'],
                caption=result_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await message.answer(result_text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("confirm:"))
async def handle_score_confirmation(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    
    current_user_id = str(callback.message.chat.id)
    await state.update_data(current_user_id=current_user_id)
    
    if action == "yes":
        data = await state.get_data()
        result_text = data.get('result_text', '')
        
        # Загружаем пользователей для обновления статистики
        users = await storage.load_users()
        game_type = data.get('game_type')
        winner_side = data.get('winner_side')
        
        # Для одиночной игры
        if game_type == 'single':
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
        if game_type == 'single':
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            if opponent_id in users:
                try:
                    opponent_user = users[opponent_id]
                    current_user = users[current_user_id]
                    
                    opponent_link = await create_user_profile_link(current_user, current_user_id)
                    
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
            current_user_link = await create_user_profile_link(current_user, current_user_id)
            
            for player_id, role in players_to_notify:
                if player_id in users:
                    try:
                        player_user = users[player_id]
                        player_link = await create_user_profile_link(player_user, player_id)
                        
                        # Формируем список всех игроков со ссылками
                        all_players = []
                        for p_id in [current_user_id, 
                                    data.get('partner', {}).get('telegram_id'),
                                    data.get('opponent1', {}).get('telegram_id'),
                                    data.get('opponent2', {}).get('telegram_id')]:
                            if p_id in users:
                                p_user = users[p_id]
                                all_players.append(await create_user_profile_link(p_user, p_id))
                        
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
        keyboard = create_set_score_keyboard(1)
        
        # Удаляем текущее сообщение и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        new_msg = await callback.message.answer(
            "Выберите счет 1-го сета:",
            reply_markup=keyboard
        )
        save_message_id(callback.message.chat.id, new_msg.message_id)
        
    elif action == "no":
        # Откатываем изменения рейтинга и статистики
        users = await storage.load_users()
        data = await state.get_data()
        game_type = data.get('game_type')
        winner_side = data.get('winner_side')
        
        if game_type == 'single':
            current_user_id = str(callback.message.chat.id)
            opponent_id = data.get('opponent1', {}).get('telegram_id')
            
            # Откатываем рейтинг
            users[current_user_id]['rating_points'] = data.get('old_rating', 0)
            if opponent_id in users:
                users[opponent_id]['rating_points'] = data.get('opponent_old_rating', 0)
            
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
            "❌ Внесение счета отменено. Все изменения отменены.",
            reply_markup=None
        )
        await state.clear()
    
    await callback.answer()

@router.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state == AddScoreState.selecting_game_type.state:
        await callback.message.edit_text("Действие отменено.")
        await state.clear()
        
    elif current_state == AddScoreState.searching_opponent.state:
        await state.set_state(AddScoreState.selecting_game_type)
        keyboard = create_game_type_keyboard()
        await callback.message.edit_text("Выберите тип игры:", reply_markup=keyboard)
        
    elif current_state == AddScoreState.selecting_opponent.state:
        await state.set_state(AddScoreState.searching_opponent)
        await callback.message.edit_text(
            "Поиск соперника\nНапишите имя или фамилию соперника:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        
    elif current_state == AddScoreState.selecting_partner.state:
        await state.set_state(AddScoreState.selecting_game_type)
        keyboard = create_game_type_keyboard()
        await callback.message.edit_text("Выберите тип игры:", reply_markup=keyboard)
        
    elif current_state == AddScoreState.searching_partner.state:
        await state.set_state(AddScoreState.selecting_partner)
        await callback.message.edit_text(
            "Ваш партнер по паре\nНапишите имя или фамилию партнера:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        
    elif current_state == AddScoreState.searching_opponent1.state:
        await state.set_state(AddScoreState.searching_partner)
        data = await state.get_data()
        search_query = data.get('partner_search', '')
        current_user_id = str(callback.message.chat.id)
        
        matching_users = await search_users(search_query, exclude_ids=[current_user_id])
        
        if matching_users:
            keyboard = create_users_inline_keyboard(matching_users, "select_partner")
            await callback.message.edit_text("Выберите партнера из списка:", reply_markup=keyboard)
        else:
            await callback.message.edit_text(
                "Ваш партнер по паре\nНапишите имя или фамилию партнера:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
                )
            )
        
    elif current_state == AddScoreState.selecting_opponent1.state:
        await state.set_state(AddScoreState.searching_opponent1)
        await callback.message.edit_text(
            "Поиск первого соперника\nНапишите имя или фамилию первого соперника:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
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
            keyboard = create_users_inline_keyboard(matching_users, "select_opponent1")
            await callback.message.edit_text("Выберите первого соперника из списка:", reply_markup=keyboard)
        else:
            await callback.message.edit_text(
                "Поиск первого соперника\nНапишите имя или фамилию первого соперника:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
                )
            )
        
    elif current_state == AddScoreState.selecting_opponent2.state:
        await state.set_state(AddScoreState.searching_opponent2)
        await callback.message.edit_text(
            "Поиск второго соперника\nНапишите имя или фамилию второго соперника:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
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
                keyboard = create_users_inline_keyboard(matching_users, "select_opponent")
                await callback.message.edit_text("Выберите соперника из списка:", reply_markup=keyboard)
            else:
                await callback.message.edit_text(
                    "Поиск соперника\nНапишите имя или фамилию соперника:",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
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
                    keyboard = create_users_inline_keyboard(matching_users, "select_opponent2")
                    await callback.message.edit_text("Выберите второго соперника из списка:", reply_markup=keyboard)
                else:
                    await callback.message.edit_text(
                        "Поиск второго соперника\nНапишите имя или фамилию второго соперника:",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
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
                    keyboard = create_users_inline_keyboard(matching_users, "select_opponent1")
                    await callback.message.edit_text("Выберите первого соперника из списка:", reply_markup=keyboard)
                else:
                    await callback.message.edit_text(
                        "Поиск первого соперника\nНапишите имя или фамилию первого соперника:",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
                        )
                    )
        
    elif current_state == AddScoreState.adding_another_set.state:
        await state.set_state(AddScoreState.selecting_set_score)
        data = await state.get_data()
        sets = data.get('sets', [])
        current_set = len(sets)
        keyboard = create_set_score_keyboard(current_set)
        await callback.message.edit_text(f"Выберите счет {current_set}-го сета:", reply_markup=keyboard)
    
    elif current_state == AddScoreState.adding_media.state:
        await state.set_state(AddScoreState.selecting_set_score)
        data = await state.get_data()
        sets = data.get('sets', [])
        current_set = len(sets)
        keyboard = create_set_score_keyboard(current_set)
        await callback.message.edit_text(f"Выберите счет {current_set}-го сета:", reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("nav:"))
async def handle_navigation(callback: types.CallbackQuery, state: FSMContext):
    _, action, page_str = callback.data.split(":")
    page = int(page_str)
    
    users = await storage.load_users()
    current_user_id = str(callback.message.chat.id)
    
    if action == "select_opponent":
        data = await state.get_data()
        search_query = data.get('opponent_search', '')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = create_users_inline_keyboard(matching_users, action, page, has_more)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    elif action == "select_partner":
        data = await state.get_data()
        search_query = data.get('partner_search', '')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = create_users_inline_keyboard(matching_users, action, page, has_more)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    elif action == "select_opponent1":
        data = await state.get_data()
        search_query = data.get('opponent1_search', '')
        partner_id = data.get('partner', {}).get('telegram_id')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = create_users_inline_keyboard(matching_users, action, page, has_more)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    elif action == "select_opponent2":
        data = await state.get_data()
        search_query = data.get('opponent2_search', '')
        partner_id = data.get('partner', {}).get('telegram_id')
        opponent1_id = data.get('opponent1', {}).get('telegram_id')
        matching_users = await search_users(search_query, exclude_ids=[current_user_id, partner_id, opponent1_id])
        
        has_more = len(matching_users) > (page + 1) * 8
        keyboard = create_users_inline_keyboard(matching_users, action, page, has_more)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("game_history:"))
async def handle_history_request(callback: types.CallbackQuery):
    """Обработчик запроса истории игр"""
    try:
        # Извлекаем ID пользователя, чью историю запрашиваем
        target_user_id = callback.data.split(":")[1]
        current_user_id = str(callback.message.chat.id)
        
        # Проверяем права доступа для просмотра чужой истории
        if not await is_admin(callback.message.chat.id):
            if current_user_id != target_user_id:
                users = await storage.load_users()
                if not users.get(current_user_id, {}).get('subscription', {}).get('active', False):
                    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{callback.from_user.id}"
                    text = (
                        "🔒 <b>Доступ закрыт</b>\n\n"
                        "Функция просмотра истории игр игроков доступна только для пользователей с активной подпиской Tennis-Play PRO.\n\n"
                        f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n"
                        "Перейдите в раздел '💳 Платежи' для оформления подписки.\n\n"
                        "Также вы можете получить подписку бесплатно, пригласив 5 друзей.\n\n"
                        f"Ваша персональная ссылка для приглашений <code>{referral_link}</code>\n\n"
                        "Статистика приглашений доступна в разделе «🔗 Пригласить друга».\n\n"
                    )
                    
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
    
    # Получаем информацию о целевом пользователе
    target_user = users.get(target_user_id)
    if not target_user:
        await callback.answer("Пользователь не найден")
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
            f"📊 История игр пользователя {target_user.get('first_name', '')} {target_user.get('last_name', '')}\n\n"
            "Пока нет сыгранных игр.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_profile:{callback.message.chat.id}")]]
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
        result = "✅ Победа"
    else:
        result = "❌ Поражение"
    
    # Получаем изменение рейтинга
    rating_change = game['rating_changes'].get(target_user_id, 0)
    rating_change_str = f"+{format_rating(rating_change)}" if rating_change > 0 else f"{format_rating(rating_change)}"
    
    # Формируем информацию об игре
    history_text = f"📊 Игра #{game_index + 1} из {len(user_games)}\n\n"
    history_text += f"📅 {formatted_date}\n"
    history_text += f"🎯 {result}\n\n"
    
    # Формируем информацию о командах
    if game['type'] == 'single':
        # Для одиночной игры
        opponent_id = game['players']['team2'][0] if user_in_team1 else game['players']['team1'][0]
        opponent = users.get(opponent_id, {})

        history_text += f"👤 Игрок:\n"
        history_text += f"• {target_user.get('first_name', '')} {target_user.get('last_name', '')}\n\n" 
        history_text += f"👤 Соперник:\n"
        history_text += f"• {await create_user_profile_link(opponent, opponent.get('telegram_id'))}\n\n"
        
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
        
        teammate_name = await create_user_profile_link(teammate, teammate_id)
        opponent1_name = await create_user_profile_link(opponent1, opponents[0])
        opponent2_name = await create_user_profile_link(opponent2, opponents[1])
        
        history_text += f"👥 Команда 1:\n"
        history_text += f"• {await create_user_profile_link(target_user, target_user.get('telegram_id', ''))}\n"
        history_text += f"• {teammate_name}\n\n"
        history_text += f"👥 Команда 2:\n"
        history_text += f"• {opponent1_name}\n"
        history_text += f"• {opponent2_name}\n\n"
    
    # Добавляем счет
    history_text += f"📊 Счет: {game['score']}\n\n"
    
    # Добавляем изменение рейтинга
    history_text += f"📈 Изменение рейтинга: {rating_change_str}\n"
    
    # Добавляем ID игры для админа
    if await is_admin(callback.message.chat.id):
        history_text += f"\n🆔 ID игры: `{game_id}`"
    
    # Создаем клавиатуру с навигацией
    keyboard_buttons = []
    
    # Кнопки навигации
    nav_buttons = []
    if game_index > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"game_history:{target_user_id}:{game_index - 1}"
        ))
    if game_index < len(user_games) - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ➡️", 
            callback_data=f"game_history:{target_user_id}:{game_index + 1}"
        ))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Кнопка возврата к профилю
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="🔙 К профилю", 
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
