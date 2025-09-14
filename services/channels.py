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

async def send_game_notification_to_channel(bot: Bot, data: Dict[str, Any], users: Dict[str, Any], user_id: str):
    """Отправляет уведомление о завершенной игре в канал"""

    game_type = data.get('game_type')
    score = data.get('score')

    channel_id = channels_id[users.get(user_id).get('sport')]

    game_text = ""
    media_group = []

    if game_type == 'single':
        # Одиночная игра
        player1_id = data.get('current_user_id')
        player2_id = data.get('opponent1', {}).get('telegram_id')
        
        player1 = users.get(player1_id, {})
        player2 = users.get(player2_id, {})
        
        player1_link = await create_user_profile_link(player1, player1_id, False)
        player2_link = await create_user_profile_link(player2, player2_id, False)
        
        winner_side = data.get('winner_side')
        if winner_side == "team1":
            winner_link, loser_link = player1_link, player2_link
        else:
            winner_link, loser_link = player2_link, player1_link
        
        game_text = (
            "🎾 *Завершена одиночная игра!*\n\n"
            f"{winner_link} выиграл у {loser_link}\n\n"
            f"📊 Счет: {score}\n\n"
            f"#игра"
        )

        # соберем фото игроков
        for pl in (player1, player2):
            if pl.get("photo_path"):
                media_group.append(
                    types.InputMediaPhoto(media=open(pl["photo_path"], "rb"))
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
        
        team1_player1_link = await create_user_profile_link(team1_player1, team1_player1_id, False)
        team1_player2_link = await create_user_profile_link(team1_player2, team1_player2_id, False)
        team2_player1_link = await create_user_profile_link(team2_player1, team2_player1_id, False)
        team2_player2_link = await create_user_profile_link(team2_player2, team2_player2_id, False)
        
        winner_side = data.get('winner_side')
        if winner_side == "team1":
            winner_team = f"{team1_player1_link} и {team1_player2_link}"
            loser_team = f"{team2_player1_link} и {team2_player2_link}"
        else:
            winner_team = f"{team2_player1_link} и {team2_player2_link}"
            loser_team = f"{team1_player1_link} и {team1_player2_link}"
        
        game_text = (
            "🎾 *Завершена парная игра!*\n\n"
            f"{winner_team} выиграли у {loser_team}\n\n"
            f"📊 Счет: {score}\n\n"
            f"#игра"
        )

        # соберем фото игроков (до 4)
        for pl in (team1_player1, team1_player2, team2_player1, team2_player2):
            if pl.get("photo_path"):
                media_group.append(
                    types.InputMediaPhoto(media=open(pl["photo_path"], "rb"))
                )

    # --- Отправка в канал ---
    if 'photo_id' in data:
        await bot.send_photo(
            chat_id=channel_id,
            photo=data['photo_id'],
            caption=game_text,
            parse_mode="Markdown"
        )
    elif 'video_id' in data:
        await bot.send_video(
            chat_id=channel_id,
            video=data['video_id'],
            caption=game_text,
            parse_mode="Markdown"
        )
    elif media_group:
        # если фото/видео игры нет, шлём фото игроков как альбом
        media_group[0].caption = game_text
        media_group[0].parse_mode = "Markdown"
        await bot.send_media_group(chat_id=channel_id, media=media_group)
    else:
        # если вообще нет фото — только текст
        await bot.send_message(
            chat_id=channel_id,
            text=game_text,
            parse_mode="Markdown"
        )

async def send_game_offer_to_channel(bot: Bot, game_data: Dict[str, Any], user_id: str, user_data: Dict[str, Any]):
    """Отправляет предложение игры в телеграм-канал"""
    try:
        profile_link = await create_user_profile_link(user_data, user_id)
        sport = user_data.get('sport', 'Не указан')
        
        offer_text = (
            f"🎾 <b>Предложение игры</b>\n\n"
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

        photo_path = user_data.get("photo_path")

        if photo_path:
            # отправляем фото + текст в подписи
            await bot.send_photo(
                chat_id=channel_id,
                photo=FSInputFile(BASE_DIR / photo_path),
                caption=offer_text,
                parse_mode="HTML"
            )
        else:
            # если фото нет — обычное сообщение
            await bot.send_message(
                chat_id=channel_id,
                text=offer_text,
                parse_mode="HTML"
            )
        
    except Exception as e:
        print(f"Ошибка при отправке предложения игры: {e}")

async def send_tour_to_channel(bot: Bot, user_id: str, user_data: Dict[str, Any]):
    """Отправляет информацию о туре в телеграм-канал"""
    try:
        profile_link = await create_user_profile_link(user_data, user_id)
        sport = user_data.get('sport', 'Не указан')
        
        tour_text = (
            f"✈️ <b>Теннисный тур</b>\n\n"
            f"👤 {profile_link}\n"
            f"📍 {user_data.get('city', '—')}, {user_data.get('country', '—')}\n"
            f"📅 {user_data.get('vacation_start')} - {user_data.get('vacation_end')}\n\n"
            f"{sport}"
        )
        
        if user_data.get('vacation_comment'):
            tour_text += f"\n💬 {user_data['vacation_comment']} \n\n#тур"
        else:
            tour_text += " \n\n#тур"
            
        photo_path = user_data.get("photo_path")

        if photo_path:
            # отправляем фото + текст в подписи
            await bot.send_photo(
                chat_id=tour_channel_id,
                photo=FSInputFile(BASE_DIR / photo_path),
                caption=tour_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            # если фото нет — обычное сообщение
            await bot.send_message(
                chat_id=tour_channel_id,
                text=tour_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        
    except Exception as e:
        print(f"Ошибка при отправке тура в канал: {e}")

async def send_user_profile_to_channel(bot: Bot, user_id: str, user_data: Dict[str, Any]):
    """Отправляет анкету пользователя в канал (для регистрации)"""
    try:
        city = user_data.get('city', '—')
        district = user_data.get('district', '')
        if district:
            city = f"{city} - {district}"
            
        username_text = "\n"
        if user_data.get('username'):
            username_text = f"✉️ @{user_data.get('username')}\n\n"
        
        role = user_data.get('role', 'Игрок')
        channel_id = channels_id[user_data.get('sport')]

        # Разное оформление для тренеров и игроков
        if role == "Тренер":
            profile_text = (
                "👨‍🏫 <b>Новый тренер присоединился к платформе!</b>\n\n"
                f"🏆 {await create_user_profile_link(user_data, user_id)}\n"
                f"💰 {user_data.get('price', 0)} руб./тренировка\n"
                f"📍 {city} ({user_data.get('country', '')})\n"
                f"{username_text}"
                f"#тренер"
            )
        else:
            profile_text = (
                "🎾 <b>Новый игрок присоединился к сообществу!</b>\n\n"
                f"👤 {await create_user_profile_link(user_data, user_id)}\n" 
                f"💪 {user_data.get('player_level', 'Не указан')} уровень игры\n"
                f"📍 {city} ({user_data.get('country', '')})\n"
                f"{username_text}"
                f"#игрок"
            )
        
        photo_path = user_data.get("photo_path")

        if photo_path:
            await bot.send_photo(
                chat_id=channel_id,
                photo=FSInputFile(BASE_DIR / photo_path),
                caption=profile_text,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=channel_id,
                text=profile_text,
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"Ошибка отправки анкеты пользователя: {e}")
