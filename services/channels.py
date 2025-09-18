from typing import Any, Dict
from aiogram import Bot, types
from aiogram.types import FSInputFile

from config.paths import BASE_DIR
from config.profile import channels_id, tour_channel_id
from utils.utils import create_user_profile_link, escape_markdown

async def send_registration_notification(message: types.Message, profile: dict):
    """Отправляет уведомление о новой регистрации в канал"""
    try:
        city = profile.get('city', '—')
        district = profile.get('district', '')
        if district:
            city = f"{city} - {district}"
        
        role = profile.get('role', 'Игрок')
        sport = profile.get('sport', '🎾Большой теннис')
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))

        # Разное оформление для тренеров и игроков
        if role == "Тренер":
            price = escape_markdown(str(profile.get('price', 0)))
            country = escape_markdown(profile.get('country', ''))
            registration_text = (
                "👨‍🏫 *Новый тренер присоединился к платформе!*\n\n"
                f"🏆 *Тренер:* {await create_user_profile_link(profile, profile.get('telegram_id'), additional=False)}\n"
                f"💰 *Стоимость:* {price} руб./тренировка\n"
                f"📍 *Местоположение:* {escape_markdown(city)} ({country})\n"
                f"#тренер"
            )
        else:
            player_level = escape_markdown(profile.get('player_level', 'Не указан'))
            country = escape_markdown(profile.get('country', ''))
            registration_text = (
                "🎾 *Новый игрок присоединился к сообществу!*\n\n"
                f"👤 *Игрок:* {await create_user_profile_link(profile, profile.get('telegram_id'), additional=False)}\n" 
                f"💪 *Уровень игры:* {player_level}\n"
                f"📍 *Местоположение:* {escape_markdown(city)} ({country})\n"
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

    sport = users.get(user_id, {}).get('sport', '🎾Большой теннис')
    channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))

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
        
        score_escaped = escape_markdown(score)
        game_text = (
            "🎾 *Завершена одиночная игра!*\n\n"
            f"🥇 *Победитель:* {winner_link}\n"
            f"🥈 *Проигравший:* {loser_link}\n\n"
            f"📊 *Счет:* {score_escaped}\n\n"
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
        
        score_escaped = escape_markdown(score)
        game_text = (
            "🎾 *Завершена парная игра!*\n\n"
            f"🥇 *Победившая команда:* {winner_team}\n"
            f"🥈 *Проигравшая команда:* {loser_team}\n\n"
            f"📊 *Счет:* {score_escaped}\n\n"
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
        from config.profile import get_sport_config
        
        profile_link = await create_user_profile_link(user_data, user_id)
        sport = game_data.get('sport', user_data.get('sport', 'Не указан'))
        
        # Получаем конфигурацию для вида спорта
        config = get_sport_config(sport)
        category = config.get("category", "court_sport")
        
        # Формируем текст в зависимости от категории
        if category == "dating":
            # Для знакомств
            city = game_data.get('city', '—')
            district = game_data.get('district', '')
            country = game_data.get('country', '')
            
            # Добавляем округ к городу если есть
            if district:
                city = f"{city} - {district}"
            
            location = f"{city}, {country}" if country else city
            
            location_escaped = escape_markdown(location)
            date_escaped = escape_markdown(game_data.get('date', '—'))
            time_escaped = escape_markdown(game_data.get('time', '—'))
            offer_text = (
                f"💕 *Анкета для знакомств*\n\n"
                f"👤 {profile_link}\n"
                f"📍 *Место:* {location_escaped}\n"
                f"📅 *Дата и время:* {date_escaped} в {time_escaped}\n"
            )
            
            # Добавляем поля знакомств
            if game_data.get('dating_goal'):
                dating_goal = escape_markdown(game_data.get('dating_goal'))
                offer_text += f"💕 *Цель знакомства:* {dating_goal}\n"
            
            if game_data.get('dating_interests'):
                interests = ', '.join(game_data.get('dating_interests', []))
                interests_escaped = escape_markdown(interests)
                offer_text += f"🎯 *Интересы:* {interests_escaped}\n"
            
            if game_data.get('dating_additional'):
                dating_additional = escape_markdown(game_data.get('dating_additional'))
                offer_text += f"📝 *О себе:* {dating_additional}\n"
        elif category == "meeting":
            # Для встреч
            if sport == "☕️Бизнес-завтрак":
                city = game_data.get('city', '—')
                district = game_data.get('district', '')
                country = game_data.get('country', '')
                
                # Добавляем округ к городу если есть
                if district:
                    city = f"{city} - {district}"
                
                location = f"{city}, {country}" if country else city
                location_escaped = escape_markdown(location)
                date_escaped = escape_markdown(game_data.get('date', '—'))
                time_escaped = escape_markdown(game_data.get('time', '—'))
                
                offer_text = (
                    f"☕️ *Предложение бизнес-завтрака*\n\n"
                    f"👤 {profile_link}\n"
                    f"📍 *Место:* {location_escaped}\n"
                    f"📅 *Дата и время:* {date_escaped} в {time_escaped}\n"
                )
            else:  # По пиву
                city = game_data.get('city', '—')
                district = game_data.get('district', '')
                country = game_data.get('country', '')
                
                # Добавляем округ к городу если есть
                if district:
                    city = f"{city} - {district}"
                
                location = f"{city}, {country}" if country else city
                location_escaped = escape_markdown(location)
                date_escaped = escape_markdown(game_data.get('date', '—'))
                time_escaped = escape_markdown(game_data.get('time', '—'))
                
                offer_text = (
                    f"🍻 *Предложение встречи за пивом*\n\n"
                    f"👤 {profile_link}\n"
                    f"📍 *Место:* {location_escaped}\n"
                    f"📅 *Дата и время:* {date_escaped} в {time_escaped}\n"
                )
        elif category == "outdoor_sport":
            # Для активных видов спорта
            city = game_data.get('city', '—')
            district = game_data.get('district', '')
            country = game_data.get('country', '')
            
            # Добавляем округ к городу если есть
            if district:
                city = f"{city} - {district}"
            
            location = f"{city}, {country}" if country else city
            location_escaped = escape_markdown(location)
            date_escaped = escape_markdown(game_data.get('date', '—'))
            time_escaped = escape_markdown(game_data.get('time', '—'))
            sport_escaped = escape_markdown(sport)
            
            offer_text = (
                f"🏃 *Предложение активности*\n\n"
                f"👤 {profile_link}\n"
                f"📍 *Место:* {location_escaped}\n"
                f"📅 *Дата и время:* {date_escaped} в {time_escaped}\n"
                f"🎯 *Вид спорта:* {sport_escaped}\n"
            )
        else:  # court_sport
            # Для спортивных видов с кортами
            city = game_data.get('city', '—')
            district = game_data.get('district', '')
            country = game_data.get('country', '')
            
            # Добавляем округ к городу если есть
            if district:
                city = f"{city} - {district}"
            
            location = f"{city}, {country}" if country else city
            location_escaped = escape_markdown(location)
            date_escaped = escape_markdown(game_data.get('date', '—'))
            time_escaped = escape_markdown(game_data.get('time', '—'))
            sport_escaped = escape_markdown(sport)
            game_type_escaped = escape_markdown(game_data.get('type', '—'))
            payment_type_escaped = escape_markdown(game_data.get('payment_type', '—'))
            
            offer_text = (
                f"🎾 *Предложение игры*\n\n"
                f"👤 {profile_link}\n"
                f"📍 *Место:* {location_escaped}\n"
                f"📅 *Дата и время:* {date_escaped} в {time_escaped}\n"
                f"🎯 *Вид спорта:* {sport_escaped} • {game_type_escaped}\n"
                f"💳 *Оплата:* {payment_type_escaped}"
            )
            
            if game_data.get('competitive'):
                offer_text += f"\n🏆 *Тип игры:* На счет"
        
        # Добавляем комментарий
        if game_data.get('comment'):
            comment_escaped = escape_markdown(game_data['comment'])
            offer_text += f"\n💬 *Комментарий:* {comment_escaped}"
        
        # Добавляем хештег
        if category == "dating":
            offer_text += " \n\n#знакомства"
        elif category == "meeting":
            offer_text += " \n\n#встречи"
        elif category == "outdoor_sport":
            offer_text += " \n\n#активность"
        else:
            offer_text += " \n\n#предложение"
            
        # Получаем ID канала для данного вида спорта
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))

        photo_path = user_data.get("photo_path")

        if photo_path:
            # отправляем фото + текст в подписи
            await bot.send_photo(
                chat_id=channel_id,
                photo=FSInputFile(BASE_DIR / photo_path),
                caption=offer_text,
                parse_mode="Markdown"
            )
        else:
            # если фото нет — обычное сообщение
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
        print(f"Начинаем отправку тура в канал для пользователя {user_id}")
        print(f"ID канала для туров: {tour_channel_id}")
        
        profile_link = await create_user_profile_link(user_data, user_id)
        sport = user_data.get('sport', '🎾Большой теннис')
        
        # Формируем текст тура
        sport_escaped = escape_markdown(sport)
        vacation_city = user_data.get('vacation_city', '—')
        vacation_district = user_data.get('vacation_district', '')
        vacation_country = user_data.get('vacation_country', '—')
        
        # Добавляем округ к городу если есть
        if vacation_district:
            vacation_city = f"{vacation_city} - {vacation_district}"
        
        vacation_city_escaped = escape_markdown(vacation_city)
        vacation_country_escaped = escape_markdown(vacation_country)
        vacation_start = escape_markdown(user_data.get('vacation_start', ''))
        vacation_end = escape_markdown(user_data.get('vacation_end', ''))
        
        tour_text = (
            f"✈️ *Тур по {sport_escaped}*\n\n"
            f"👤 {profile_link}\n"
            f"🌍 *Направление:* {vacation_city_escaped}, {vacation_country_escaped}\n"
            f"📅 *Даты:* {vacation_start} - {vacation_end}"
        )
        
        if user_data.get('vacation_comment'):
            vacation_comment = escape_markdown(user_data['vacation_comment'])
            tour_text += f"\n💬 *Комментарий:* {vacation_comment}"
        
        tour_text += "\n\n#тур"
        
        print(f"Сформирован текст тура: {tour_text[:100]}...")
            
        photo_path = user_data.get("photo_path")

        if photo_path:
            print(f"Отправляем фото с подписью в канал {tour_channel_id}")
            # отправляем фото + текст в подписи
            await bot.send_photo(
                chat_id=tour_channel_id,
                photo=FSInputFile(BASE_DIR / photo_path),
                caption=tour_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            print(f"Отправляем текстовое сообщение в канал {tour_channel_id}")
            # если фото нет — обычное сообщение
            await bot.send_message(
                chat_id=tour_channel_id,
                text=tour_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        
        print(f"Тур успешно отправлен в канал для пользователя {user_id}")
        
    except Exception as e:
        print(f"Ошибка при отправке тура в канал: {e}")
        print(f"Тип ошибки: {type(e).__name__}")

async def send_user_profile_to_channel(bot: Bot, user_id: str, user_data: Dict[str, Any]):
    """Отправляет анкету пользователя в канал (для регистрации)"""
    try:
        city = user_data.get('city', '—')
        district = user_data.get('district', '')
        if district:
            city = f"{city} - {district}"
            
        username_text = "\n"
        if user_data.get('username'):
            username = user_data.get('username')
            username_text = f"✉️ @{username}\n\n"
        
        role = user_data.get('role', 'Игрок')
        channel_id = channels_id[user_data.get('sport')]

        # Разное оформление для тренеров и игроков
        if role == "Тренер":
            price = escape_markdown(str(user_data.get('price', 0)))
            country = escape_markdown(user_data.get('country', ''))
            profile_text = (
                "👨‍🏫 <b>Новый тренер присоединился к платформе!</b>\n\n"
                f"🏆 <b>Тренер:</b> {await create_user_profile_link(user_data, user_id)}\n"
                f"💰 <b>Стоимость:</b> {price} руб./тренировка\n"
                f"📍 <b>Местоположение:</b> {escape_markdown(city)} ({country})\n"
                f"{username_text}"
                f"#тренер"
            )
        else:
            player_level = escape_markdown(user_data.get('player_level', 'Не указан'))
            country = escape_markdown(user_data.get('country', ''))
            profile_text = (
                "🎾 <b>Новый игрок присоединился к сообществу!</b>\n\n"
                f"👤 <b>Игрок:</b> {await create_user_profile_link(user_data, user_id)}\n" 
                f"💪 <b>Уровень игры:</b> {player_level}\n"
                f"📍 <b>Местоположение:</b> {escape_markdown(city)} ({country})\n"
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
