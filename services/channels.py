from typing import Any, Dict
from aiogram import Bot, types
from aiogram.types import FSInputFile

from config.paths import BASE_DIR
from config.profile import channels_id, tour_channel_id
from utils.utils import create_user_profile_link

async def send_registration_notification(message: types.Message, profile: dict):
    """Отправляет уведомление о новой регистрации в канал"""
    try:
        city = profile.get('city', '—')
        district = profile.get('district', '')
        if district:
            city = f"{city} - {district}"
            
        username_text = "\n"
        if profile.get('username'):
            username_text = f"✉️ @{profile.get('username')}\n\n"
        
        role = profile.get('role', 'Игрок')
        channel_id = channels_id[profile.get('sport')]

        # Разное оформление для тренеров и игроков
        if role == "Тренер":
            registration_text = (
                "👨‍🏫 *Новый тренер присоединился к платформе!*\n\n"
                f"🏆 {await create_user_profile_link(profile, profile.get('telegram_id'))}\n"
                f"💰 {profile.get('price', 0)} руб./тренировка\n"
                f"📍 {city} ({profile.get('country', '')})\n"
                f"{username_text}"
                f"#тренер"
            )
        else:
            registration_text = (
                "🎾 *Новый игрок присоединился к сообществу!*\n\n"
                f"👤 {await create_user_profile_link(profile, profile.get('telegram_id'))}\n" 
                f"💪 {profile.get('player_level', 'Не указан')} уровень игры\n"
                f"📍 {city} ({profile.get('country', '')})\n"
                f"{username_text}"
                f"#игрок"
            )
        
        if profile.get('photo_path'):
            await message.bot.send_photo(
                chat_id=channel_id,
                photo=FSInputFile(BASE_DIR / profile.get('photo_path')),
                caption=registration_text,
                parse_mode="Markdown"
            )
        else:
            await message.bot.send_message(
                chat_id=channel_id,
                text=registration_text,
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def send_game_notification_to_channel(bot: Bot, data: Dict[str, Any], users: Dict[str, Any]):
    """Отправляет уведомление о завершенной игре в канал"""
    try:
        game_type = data.get('game_type')
        score = data.get('score')

        channel_id = channels_id[users.get(data.get('current_user_id'), {}).get('sport')]

        if game_type == 'single':
            # Одиночная игра
            player1_id = data.get('current_user_id')
            player2_id = data.get('opponent1', {}).get('telegram_id')
            
            player1 = users.get(player1_id, {})
            player2 = users.get(player2_id, {})
            
            player1_link = await create_user_profile_link(player1, player1_id)
            player2_link = await create_user_profile_link(player2, player2_id)
            
            winner_side = data.get('winner_side')
            if winner_side == "team1":
                winner_link = player1_link
                loser_link = player2_link
            else:
                winner_link = player2_link
                loser_link = player1_link
            
            game_text = (
                "🎾 *Завершена одиночная игра!*\n\n"
                f"🏆 {winner_link}\n"
                f"🥈 {loser_link}\n\n"
                f"📊 Счет: {score}\n\n"
                f"#игра"
            )
            
        else:
            # Парная игра
            team1_player1_id = str(data.get('current_user_id'))
            team1_player2_id = data.get('partner', {}).get('telegram_id')
            team2_player1_id = data.get('opponent1', {}).get('telegram_id')
            team2_player2_id = data.get('opponent2', {}).get('telegram_id')
            
            team1_player1 = users.get(team1_player1_id, {})
            team1_player2 = users.get(team1_player2_id, {})
            team2_player1 = users.get(team2_player1_id, {})
            team2_player2 = users.get(team2_player2_id, {})
            
            team1_player1_link = await create_user_profile_link(team1_player1, team1_player1_id)
            team1_player2_link = await create_user_profile_link(team1_player2, team1_player2_id)
            team2_player1_link = await create_user_profile_link(team2_player1, team2_player1_id)
            team2_player2_link = await create_user_profile_link(team2_player2, team2_player2_id)
            
            winner_side = data.get('winner_side')
            if winner_side == "team1":
                winner_team = f"{team1_player1_link} & {team1_player2_link}"
                loser_team = f"{team2_player1_link} & {team2_player2_link}"
            else:
                winner_team = f"{team2_player1_link} & {team2_player2_link}"
                loser_team = f"{team1_player1_link} & {team1_player2_link}"
            
            game_text = (
                "🎾 *Завершена парная игра!*\n\n"
                f"🏆 {winner_team}\n"
                f"🥈 {loser_team}\n\n"
                f"📊 Счет: {score}\n\n"
                f"#игра"
            )
        
        if data.get('photo_id'):
            await bot.send_photo(
                chat_id=channel_id,
                photo=data['photo_id'],
                caption=game_text,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=channel_id,
                text=game_text,
                parse_mode="Markdown"
            )
        
    except:
        pass

async def send_game_offer_to_channel(bot: Bot, game_data: Dict[str, Any], user_id: str, user_data: Dict[str, Any]):
    """Отправляет предложение игры в телеграм-канал"""
    try:
        profile_link = await create_user_profile_link(user_data, user_id)
        sport = user_data.get('sport', 'Не указан')
        
        offer_text = (
            f"🎾 *Предложение игры*\n\n"
            f"👤 {profile_link}\n"
            f"📍 {game_data.get('city', '—')}\n"
            f"📅 {game_data.get('date', '—')} в {game_data.get('time', '—')}\n"
            f"{sport} • {game_data.get('type', '—')}\n"
            f"💳 {game_data.get('payment_type', '—')}"
        )
        
        if game_data.get('competitive'):
            offer_text += f"\n🏆 На счет"
            
        if game_data.get('comment'):
            offer_text += f"\n💬 {game_data['comment']} \n\n#предложение"
        else:
            offer_text += " \n\n#предложение"
            
        channel_id = channels_id[sport]

        await bot.send_message(
            chat_id=channel_id,
            text=offer_text,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        print(f"Ошибка при отправке предложения игры: {e}")

async def send_tour_to_channel(bot: Bot, user_id: str, user_data: Dict[str, Any]):
    """Отправляет информацию о туре в телеграм-канал"""
    try:
        profile_link = await create_user_profile_link(user_data, user_id)
        sport = user_data.get('sport', 'Не указан')
        
        tour_text = (
            f"✈️ *Теннисный тур*\n\n"
            f"👤 {profile_link}\n"
            f"📍 {user_data.get('city', '—')}, {user_data.get('country', '—')}\n"
            f"📅 {user_data.get('vacation_start')} - {user_data.get('vacation_end')}\n\n"
            f"{sport}"
        )
        
        if user_data.get('vacation_comment'):
            tour_text += f"\n💬 {user_data['vacation_comment']} \n\n#тур"
        else:
            tour_text += " \n\n#тур"
            
        await bot.send_message(
            chat_id=tour_channel_id,
            text=tour_text,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        print(f"Ошибка при отправке тура в канал: {e}")
