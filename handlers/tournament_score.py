"""
Модуль для внесения счета турнирных игр
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from models.states import AddScoreState
from services.storage import storage
from utils.tournament_manager import tournament_manager
from utils.utils import create_user_profile_link
from handlers.enter_invoice import (
    create_set_score_keyboard, 
    save_message_id,
    format_rating
)

router = Router()


# ==================== HELPER FUNCTIONS ====================

def _have_same_tournament_game(g: dict, tournament_id: str, user_a: str, user_b: str) -> bool:
    """Проверяет, является ли игра той же самой турнирной игрой"""
    try:
        if g.get('tournament_id') != tournament_id:
            return False
        t1 = [str(x) for x in g.get('players', {}).get('team1', [])]
        t2 = [str(x) for x in g.get('players', {}).get('team2', [])]
        ua = str(user_a)
        ub = str(user_b)
        # Single players are recorded as one per team for tournament mode
        return ((ua in t1 and ub in t2) or (ua in t2 and ub in t1))
    except Exception:
        return False


async def _already_played_in_tournament(tournament_id: str, user_a: str, user_b: str) -> bool:
    """Проверяет, сыграна ли уже игра между двумя игроками в данном турнире"""
    try:
        games = await storage.load_games()
        for g in games:
            if _have_same_tournament_game(g, tournament_id, user_a, user_b):
                return True
        return False
    except Exception:
        return False


async def create_tournament_keyboard(current_user_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора турнира, где пользователь может вносить счет.
    Доступны только турниры со статусом 'started'."""
    tournaments = await storage.load_tournaments()
    
    builder = InlineKeyboardBuilder()
    
    # Доступны турниры, в которых участвует пользователь и турнир запущен
    user_tournaments = {}
    for tournament_id, tournament_data in tournaments.items():
        if tournament_data.get('status') not in ['started']:
            continue
        participants = tournament_data.get('participants', {})
        if current_user_id in participants and len(participants) >= 2:
            user_tournaments[tournament_id] = tournament_data
    
    if not user_tournaments:
        builder.button(text="❌ Нет запущенных турниров для внесения счета", callback_data="tournament_score:no_tournaments")
    else:
        for tournament_id, tournament_data in user_tournaments.items():
            name = tournament_data.get('name', 'Без названия')
            city = tournament_data.get('city', 'Не указан')
            participants_count = len(tournament_data.get('participants', {}))
            builder.button(text=f"🏆 {name} ({city}) - {participants_count} участников", 
                          callback_data=f"tournament_score:select:{tournament_id}")
    
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()


async def create_tournament_opponents_keyboard(tournament_id: str, current_user_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора соперника из доступных в турнире"""
    builder = InlineKeyboardBuilder()
    
    # Запрещаем выбор соперника, если турнир не запущен
    tournaments = await storage.load_tournaments()
    t = tournaments.get(tournament_id, {})
    if t.get('status') != 'started':
        builder.button(text="⏳ Турнир еще не запущен админом", callback_data="tournament_score:no_participants")
        builder.button(text="🔙 Назад", callback_data="tournament_score:back_to_list")
        builder.adjust(1)
        return builder.as_markup()

    # Получаем доступных соперников через менеджер турниров
    available_opponents = await tournament_manager.get_available_opponents(tournament_id, current_user_id)

    # Фильтруем соперников, с которыми уже сыграна игра в этом турнире
    filtered: list[dict] = []
    for opp in available_opponents:
        opp_id = str(opp.get('user_id'))
        if not await _already_played_in_tournament(tournament_id, current_user_id, opp_id):
            filtered.append(opp)
    available_opponents = filtered
    
    if not available_opponents:
        builder.button(text="❌ Нет доступных соперников", callback_data="tournament_score:no_participants")
    else:
        for i, opponent in enumerate(available_opponents):
            name = opponent.get('name', 'Неизвестно')
            match_number = opponent.get('match_number', 0)
            builder.button(text=f"👤 {name} (Матч {match_number + 1})", 
                         callback_data=f"tournament_score:opponent:{tournament_id}:{i}")
    
    builder.button(text="🔙 Назад", callback_data="tournament_score:back_to_list")
    builder.adjust(1)
    return builder.as_markup()


# ==================== HANDLERS ====================

@router.callback_query(F.data.startswith("tournament_score:select:"))
async def handle_tournament_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора турнира"""
    tournament_id = callback.data.split(":", 2)[2]
    await state.update_data(tournament_id=tournament_id)
    
    # Проверяем, является ли пользователь участником турнира
    tournaments = await storage.load_tournaments()
    tournament_data = tournaments.get(tournament_id, {})
    participants = tournament_data.get('participants', {})
    current_user_id = str(callback.message.chat.id)
    
    if current_user_id not in participants:
        await callback.message.edit_text(
            "❌ Вы не являетесь участником этого турнира.\n\n"
            "Для участия в турнире необходимо сначала подать заявку.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        await callback.answer("Вы не участник турнира")
        return
    
    # Разрешаем вносить счет до старта, если есть участники (>=2) и есть с кем играть
    tournament_status = tournament_data.get('status', 'active')
    
    # Проверяем минимальное количество участников для внесения игр
    from config.tournament_config import MIN_PARTICIPANTS
    tournament_type = tournament_data.get('type', 'Олимпийская система')
    min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
    current_participants = len(participants)
    
    if current_participants < 2:
        await callback.message.edit_text(
            f"❌ Недостаточно участников для внесения игр!\n\n"
            f"🏆 Турнир: {tournament_data.get('name', 'Без названия')}\n"
            f"👥 Текущих участников: {current_participants}\n"
            f"📊 Требуется минимум: 2", 
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
        )
        await callback.answer()
        return
    
    await state.set_state(AddScoreState.selecting_tournament_opponent)
    keyboard = await create_tournament_opponents_keyboard(tournament_id, current_user_id)
    await callback.message.edit_text(
        "👥 Выберите соперника из участников турнира:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tournament_score:opponent:"))
async def handle_tournament_opponent_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора соперника из турнира"""
    parts = callback.data.split(":")
    tournament_id = parts[2]
    opponent_index = int(parts[3]) if len(parts) > 3 else 0
    current_user_id = str(callback.message.chat.id)
    
    print(f"[TOURNAMENT_SCORE] opponent_index: {opponent_index}")
    print(f"[TOURNAMENT_SCORE] tournament_id: {tournament_id}")
    print(f"[TOURNAMENT_SCORE] current_user_id: {current_user_id}")
    
    # Получаем доступных соперников
    available_opponents = await tournament_manager.get_available_opponents(tournament_id, current_user_id)
    print(f"[TOURNAMENT_SCORE] available_opponents count={len(available_opponents)}")
    print(f"[TOURNAMENT_SCORE] available_opponents={available_opponents}")
    
    # Проверяем корректность индекса
    if opponent_index >= len(available_opponents):
        await callback.answer("Соперник не найден")
        return
    
    selected_opponent_data = available_opponents[opponent_index]
    match_id = selected_opponent_data.get('match_id')
    opponent_id = selected_opponent_data.get('user_id')
    
    users = await storage.load_users()
    
    if opponent_id not in users:
        await callback.answer("Пользователь не найден")
        return
    
    selected_opponent = users[opponent_id]
    selected_opponent['telegram_id'] = opponent_id
    
    # Блокируем повторную игру в этом турнире
    if await _already_played_in_tournament(tournament_id, current_user_id, opponent_id):
        await callback.answer("Этот матч уже сыгран в этом турнире", show_alert=True)
        # Обновим список соперников
        keyboard = await create_tournament_opponents_keyboard(tournament_id, current_user_id)
        await callback.message.edit_text(
            "👥 Выберите соперника из участников турнира:",
            reply_markup=keyboard
        )
        return

    # Сохраняем информацию о матче
    await state.update_data(
        game_type='tournament',
        opponent1=selected_opponent, 
        tournament_match_id=match_id
    )
    await state.set_state(AddScoreState.selecting_set_score)
    
    keyboard = create_set_score_keyboard(1)
    
    username = selected_opponent.get('username', '')
    username_text = f"@{username}" if username else "не указан"
    
    await callback.message.edit_text( 
        f"🏆 Турнирная игра\n\n"
        f"Вы выбрали соперника:\n"
        f"👤 {await create_user_profile_link(selected_opponent, opponent_id, additional=False)}\n"
        f"📱 Username: {username_text}\n\n"
        f"Выберите счет 1-го сета:",
        reply_markup=keyboard, 
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "tournament_score:no_tournaments")
async def handle_no_tournaments(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отсутствия турниров"""
    await callback.message.edit_text(
        "❌ Вы не участвуете ни в одном активном турнире.\n\n"
        "Для участия в турнире необходимо подать заявку в разделе '🏆 Турниры'.\n\n"
        "Попробуйте выбрать другой тип игры.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
    )
    await callback.answer("Нет доступных турниров")


@router.callback_query(F.data == "tournament_score:no_participants")
async def handle_no_participants(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отсутствия участников в турнире"""
    await callback.message.edit_text(
        "❌ В турнире недостаточно участников или нет доступных соперников.\n\n"
        "Пожалуйста, подождите, пока другие игроки присоединятся к турниру.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
        )
    )
    await callback.answer("Нет участников")


@router.callback_query(F.data == "tournament_score:back_to_list")
async def handle_back_to_tournament_list(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку турниров"""
    current_user_id = str(callback.message.chat.id)
    await state.set_state(AddScoreState.selecting_tournament)
    keyboard = await create_tournament_keyboard(current_user_id)
    await callback.message.edit_text(
        "🏆 Выберите турнир для внесения счета:",
        reply_markup=keyboard
    )
    await callback.answer()

