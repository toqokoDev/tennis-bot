from typing import Any, Dict
from aiogram import Bot, types
from aiogram.types import FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.paths import BASE_DIR
from config.profile import channels_id, tour_channel_id
from config.config import BOT_USERNAME
from utils.utils import create_user_profile_link, escape_markdown

def format_rating(rating: float) -> str:
    """Форматирует рейтинг, убирая лишние нули после запятой"""
    if rating == int(rating):
        return str(int(rating))
    return f"{rating:.1f}".rstrip('0').rstrip('.')

async def send_registration_notification(message: types.Message, profile: dict):
    """Отправляет уведомление о новой регистрации в канал"""
    try:
        from config.profile import get_sport_config
        from datetime import datetime
        
        city = profile.get('city', '—')
        district = profile.get('district', '')
        if district:
            city = f"{city} - {district}"
        
        role = profile.get('role', 'Игрок')
        sport = profile.get('sport', '🎾Большой теннис')
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Получаем конфигурацию для вида спорта
        config = get_sport_config(sport)
        category = config.get("category", "court_sport")
        
        # Вычисляем возраст из даты рождения
        age_text = ""
        if profile.get('birth_date'):
            try:
                birth_date = datetime.strptime(profile.get('birth_date'), "%d.%m.%Y")
                today = datetime.now()
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                age_text = f"{age} лет"
            except:
                pass
        
        # Получаем пол
        gender = profile.get('gender', '')
        gender_emoji = "👨" if gender == "Мужской" else "👩" if gender == "Женский" else "👤"
        
        # Получаем username
        username_text = ""
        if profile.get('username'):
            username = escape_markdown(profile.get('username'))
            username_text = f"✉️ @{username}\n"

        # Разное оформление для тренеров и игроков
        if role == "Тренер":
            price = escape_markdown(str(profile.get('price', 0)))
            country = escape_markdown(profile.get('country', ''))
            registration_text = (
                "👨‍🏫 *Новый тренер присоединился к платформе!*\n\n"
                f"🏆 *Тренер:* {await create_user_profile_link(profile, profile.get('telegram_id'), additional=False)}\n"
            )
            
            # Добавляем возраст и пол если есть
            if age_text and gender:
                registration_text += f"{gender_emoji} *Возраст:* {escape_markdown(age_text)}\n"
            elif age_text:
                registration_text += f"{gender_emoji} *Возраст:* {escape_markdown(age_text)}\n"
            elif gender:
                registration_text += f"{gender_emoji} *Пол:* {escape_markdown(gender)}\n"
            
            registration_text += (
                f"💰 *Стоимость:* {price} руб./тренировка\n"
                f"📍 *Местоположение:* {escape_markdown(city)} ({country})\n"
            )
            
            # Добавляем информацию о корте/клубе для тренеров
            if profile.get('profile_comment'):
                trainer_comment = escape_markdown(profile.get('profile_comment'))
                registration_text += f"🎾 *О себе* {trainer_comment}\n"
            
            registration_text += f"{username_text}"
        else:
            country = escape_markdown(profile.get('country', ''))
            registration_text = (
                "🎾 *Новый игрок присоединился к сообществу!*\n\n"
                f"👤 *Игрок:* {await create_user_profile_link(profile, profile.get('telegram_id'), additional=False)}\n" 
            )
            
            # Добавляем возраст и пол если есть
            if age_text and gender:
                registration_text += f"{gender_emoji} *Возраст:* {escape_markdown(age_text)}\n"
            elif age_text:
                registration_text += f"{gender_emoji} *Возраст:* {escape_markdown(age_text)}\n"
            
            # Добавляем уровень игры только если он указан
            if profile.get('player_level'):
                player_level = escape_markdown(profile.get('player_level'))
                registration_text += f"💪 *Уровень игры:* {player_level}\n"
            
            # Добавляем рейтинг если есть игры
            rating_points = profile.get('rating_points', 0)
            if rating_points and rating_points > 0:
                registration_text += f"⭐ *Рейтинг:* {format_rating(rating_points)}\n"
            
            registration_text += f"📍 *Местоположение:* {escape_markdown(city)} ({country})\n{username_text}"
        
        # Добавляем дополнительные поля в зависимости от вида спорта
        if category == "dating":
            # Для знакомств
            if profile.get('dating_goal'):
                dating_goal = escape_markdown(profile.get('dating_goal'))
                registration_text += f"💕 *Цель знакомства:* {dating_goal}\n"
            
            if profile.get('dating_interests'):
                interests = ', '.join(profile.get('dating_interests', []))
                interests_escaped = escape_markdown(interests)
                registration_text += f"🎯 *Интересы:* {interests_escaped}\n"
            
            if profile.get('dating_additional'):
                dating_additional = escape_markdown(profile.get('dating_additional'))
                registration_text += f"📝 *О себе:* {dating_additional}"
            
        elif category == "meeting":
            # Для встреч
            if sport == "☕️Бизнес-завтрак":
                if profile.get('meeting_time'):
                    meeting_time = escape_markdown(profile.get('meeting_time'))
                    registration_text += f"☕️ *Время встречи:* {meeting_time}"
            else:  # По пиву
                if profile.get('meeting_time'):
                    meeting_time = escape_markdown(profile.get('meeting_time'))
                    registration_text += f"🍻 *Время встречи:* {meeting_time}"
                
        elif category == "outdoor_sport":
            # Для активных видов спорта
            if profile.get('profile_comment'):
                comment = escape_markdown(profile.get('profile_comment'))
                registration_text += f"💬 *О себе:* {comment}"
            
        else:  # court_sport
            # Добавляем способ оплаты корта
            if profile.get('default_payment'):
                payment = escape_markdown(profile.get('default_payment'))
                registration_text += f"💳 *Оплата корта:* {payment}\n"
            
            if profile.get('profile_comment'):
                comment = escape_markdown(profile.get('profile_comment'))
                registration_text += f"💬 *О себе:* {comment}"
        
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

    if game_type == 'tournament':
        # Турнирная игра
        player1_id = str(user_id)
        player2_id = data.get('opponent1', {}).get('telegram_id')
        
        player1 = users.get(player1_id, {})
        player2 = users.get(player2_id, {})
        
        player1_link = await create_user_profile_link(player1, player1_id, False)
        player2_link = await create_user_profile_link(player2, player2_id, False)
        
        winner_side = data.get('winner_side')
        if winner_side == "team1":
            winner_link, loser_link = player1_link, player2_link
            winner_name, loser_name = player1.get('first_name', ''), player2.get('first_name', '')
        else:
            winner_link, loser_link = player2_link, player1_link
            winner_name, loser_name = player2.get('first_name', ''), player1.get('first_name', '')
        
        score_escaped = escape_markdown(score)
        
        # Получаем информацию о турнире
        tournament_id = data.get('tournament_id')
        tournament_name = "Неизвестный турнир"
        if tournament_id:
            from services.storage import storage
            tournaments = await storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            tournament_name = tournament_data.get('name', 'Неизвестный турнир')
        
        game_text = (
            "🏆 *Завершена турнирная игра!*\n\n"
            f"🏆 *Турнир:* {escape_markdown(tournament_name)}\n\n"
            f"🥇 {winner_link} выиграл у {loser_link}\n\n"
            f"📊 *Счет:* {score_escaped}"
        )
        
        # Собираем фото игроков
        for pl in (player1, player2):
            if pl.get("photo_path"):
                media_group.append(
                    types.InputMediaPhoto(media=FSInputFile(BASE_DIR / pl["photo_path"]))
                )
    
    elif game_type == 'single':
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
        
        # Получаем изменения рейтинга
        rating_changes = data.get('rating_changes', {})
        old_ratings = data.get('old_ratings', {})
        
        # Отладочная информация
        print(f"DEBUG: rating_changes = {rating_changes}")
        print(f"DEBUG: old_ratings = {old_ratings}")
        print(f"DEBUG: player1_id = {player1_id}, player2_id = {player2_id}")
        
        # Определяем победителя и проигравшего
        if winner_side == "team1":
            winner_id, loser_id = player1_id, player2_id
            winner_name, loser_name = player1.get('first_name', ''), player2.get('first_name', '')
        else:
            winner_id, loser_id = player2_id, player1_id
            winner_name, loser_name = player2.get('first_name', ''), player1.get('first_name', '')
        
        # Получаем старые рейтинги и изменения
        winner_old = old_ratings.get(winner_id, 0.0)
        loser_old = old_ratings.get(loser_id, 0.0)
        winner_change = rating_changes.get(winner_id, 0.0)
        loser_change = rating_changes.get(loser_id, 0.0)
        
        # Вычисляем новые рейтинги
        winner_new = winner_old + winner_change
        loser_new = loser_old + loser_change
        
        # Форматируем строки изменений
        winner_change_str = f"+{format_rating(winner_change)}" if winner_change > 0 else f"{format_rating(winner_change)}"
        loser_change_str = f"+{format_rating(loser_change)}" if loser_change > 0 else f"{format_rating(loser_change)}"
        
        game_text = (
            "🎾 *Завершена одиночная игра!*\n\n"
            f"🥇 *Победитель:* {winner_link}\n"
            f"🥈 *Проигравший:* {loser_link}\n\n"
            f"📊 *Счет:* {score_escaped}\n\n"
            f"📈 *Изменение рейтинга:*\n"
            f"• {winner_name}: {format_rating(winner_old)} → {format_rating(winner_new)} ({winner_change_str})\n"
            f"• {loser_name}: {format_rating(loser_old)} → {format_rating(loser_new)} ({loser_change_str})"
        )

        # соберем фото игроков
        for pl in (player1, player2):
            if pl.get("photo_path"):
                media_group.append(
                    types.InputMediaPhoto(media=FSInputFile(BASE_DIR / pl["photo_path"]))
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
        
        score_escaped = escape_markdown(score)
        
        # Получаем изменения рейтинга для всех игроков
        rating_changes = data.get('rating_changes', {})
        old_ratings = data.get('old_ratings', {})
        
        # Отладочная информация
        print(f"DEBUG DOUBLE: rating_changes = {rating_changes}")
        print(f"DEBUG DOUBLE: old_ratings = {old_ratings}")
        print(f"DEBUG DOUBLE: team1_player1_id = {team1_player1_id}, team1_player2_id = {team1_player2_id}")
        print(f"DEBUG DOUBLE: team2_player1_id = {team2_player1_id}, team2_player2_id = {team2_player2_id}")
        
        # Определяем команды и их данные
        if winner_side == "team1":
            winner_players = [team1_player1, team1_player2]
            winner_links = [team1_player1_link, team1_player2_link]
            winner_ids = [team1_player1_id, team1_player2_id]
            loser_players = [team2_player1, team2_player2]
            loser_links = [team2_player1_link, team2_player2_link]
            loser_ids = [team2_player1_id, team2_player2_id]
        else:
            winner_players = [team2_player1, team2_player2]
            winner_links = [team2_player1_link, team2_player2_link]
            winner_ids = [team2_player1_id, team2_player2_id]
            loser_players = [team1_player1, team1_player2]
            loser_links = [team1_player1_link, team1_player2_link]
            loser_ids = [team1_player1_id, team1_player2_id]
        
        # Формируем строки изменений рейтинга
        rating_changes_text = "📈 *Изменение рейтинга:*\n"
        
        # Добавляем изменения для победившей команды
        for player, player_id in zip(winner_players, winner_ids):
            player_name = player.get('first_name', '')
            old_rating = old_ratings.get(player_id, 0.0)
            rating_change = rating_changes.get(player_id, 0.0)
            new_rating = old_rating + rating_change
            change_str = f"+{format_rating(rating_change)}" if rating_change > 0 else f"{format_rating(rating_change)}"
            rating_changes_text += f"• {player_name}: {format_rating(old_rating)} → {format_rating(new_rating)} ({change_str})\n"
        
        # Добавляем изменения для проигравшей команды
        for player, player_id in zip(loser_players, loser_ids):
            player_name = player.get('first_name', '')
            old_rating = old_ratings.get(player_id, 0.0)
            rating_change = rating_changes.get(player_id, 0.0)
            new_rating = old_rating + rating_change
            change_str = f"+{format_rating(rating_change)}" if rating_change > 0 else f"{format_rating(rating_change)}"
            rating_changes_text += f"• {player_name}: {format_rating(old_rating)} → {format_rating(new_rating)} ({change_str})\n"
        
        game_text = (
            "🎾 *Завершена парная игра!*\n\n"
            f"🥇 *Победившая команда:* {winner_links[0]} и {winner_links[1]}\n"
            f"🥈 *Проигравшая команда:* {loser_links[0]} и {loser_links[1]}\n\n"
            f"📊 *Счет:* {score_escaped}\n\n"
            f"{rating_changes_text}"
        )

        # соберем фото игроков (до 4)
        for pl in (team1_player1, team1_player2, team2_player1, team2_player2):
            if pl.get("photo_path"):
                media_group.append(
                    types.InputMediaPhoto(media=FSInputFile(BASE_DIR / pl["photo_path"]))
                )

    # --- Отправка в канал ---
    # Создаем кнопку для турнирной игры
    reply_markup = None
    if game_type == 'tournament' and tournament_id:
        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=view_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text="👀 Смотреть турнир", url=deep_link))
        reply_markup = builder.as_markup()
    
    if 'photo_id' in data:
        await bot.send_photo(
            chat_id=channel_id,
            photo=data['photo_id'],
            caption=game_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif 'video_id' in data:
        await bot.send_video(
            chat_id=channel_id,
            video=data['video_id'],
            caption=game_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif media_group:
        # если фото/видео игры нет, шлём фото игроков как альбом
        media_group[0].caption = game_text
        media_group[0].parse_mode = "Markdown"
        await bot.send_media_group(chat_id=channel_id, media=media_group)
        # Для media_group отправляем кнопку отдельным сообщением (если есть)
        if reply_markup:
            await bot.send_message(
                chat_id=channel_id,
                text="🏆 *Информация о турнире:*",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    else:
        # если вообще нет фото — только текст
        await bot.send_message(
            chat_id=channel_id,
            text=game_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
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
        from config.profile import get_sport_config
        
        city = user_data.get('city', '—')
        district = user_data.get('district', '')
        if district:
            city = f"{city} - {district}"
            
        username_text = "\n"
        if user_data.get('username'):
            username = user_data.get('username')
            username_text = f"✉️ @{username}\n\n"
        
        role = user_data.get('role', 'Игрок')
        sport = user_data.get('sport', '🎾Большой теннис')
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Получаем конфигурацию для вида спорта
        config = get_sport_config(sport)
        category = config.get("category", "court_sport")

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
            )
        else:
            country = escape_markdown(user_data.get('country', ''))
            profile_text = (
                "🎾 <b>Новый игрок присоединился к сообществу!</b>\n\n"
                f"👤 <b>Игрок:</b> {await create_user_profile_link(user_data, user_id)}\n" 
            )
            
            # Добавляем уровень игры только если он указан
            if user_data.get('player_level'):
                player_level = escape_markdown(user_data.get('player_level'))
                profile_text += f"💪 <b>Уровень игры:</b> {player_level}\n"
            
            profile_text += f"📍 <b>Местоположение:</b> {escape_markdown(city)} ({country})\n"
            profile_text += f"{username_text}"
        
        # Добавляем дополнительные поля в зависимости от вида спорта
        if category == "dating":
            # Для знакомств
            if user_data.get('dating_goal'):
                dating_goal = escape_markdown(user_data.get('dating_goal'))
                profile_text += f"💕 <b>Цель знакомства:</b> {dating_goal}\n"
            
            if user_data.get('dating_interests'):
                interests = ', '.join(user_data.get('dating_interests', []))
                interests_escaped = escape_markdown(interests)
                profile_text += f"🎯 <b>Интересы:</b> {interests_escaped}\n"
            
            if user_data.get('dating_additional'):
                dating_additional = escape_markdown(user_data.get('dating_additional'))
                profile_text += f"📝 <b>О себе:</b> {dating_additional}\n"
            
        elif category == "meeting":
            # Для встреч
            if sport == "☕️Бизнес-завтрак":
                if user_data.get('meeting_time'):
                    meeting_time = escape_markdown(user_data.get('meeting_time'))
                    profile_text += f"☕️ <b>Время встречи:</b> {meeting_time}\n"
            else:  # По пиву
                if user_data.get('meeting_time'):
                    meeting_time = escape_markdown(user_data.get('meeting_time'))
                    profile_text += f"🍻 <b>Время встречи:</b> {meeting_time}\n"
                
        elif category == "outdoor_sport":
            # Для активных видов спорта
            if user_data.get('profile_comment'):
                comment = escape_markdown(user_data.get('profile_comment'))
                profile_text += f"💬 <b>О себе:</b> {comment}\n"
            
        else:  # court_sport
            # Для спортивных видов с кортами
            if user_data.get('profile_comment'):
                comment = escape_markdown(user_data.get('profile_comment'))
                profile_text += f"💬 <b>О себе:</b> {comment}\n"
        
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

async def send_tournament_created_to_channel(bot: Bot, tournament_id: str, tournament_data: Dict[str, Any]):
    """Отправляет уведомление о новом турнире в соответствующий канал с кнопкой "Участвовать"."""
    try:
        sport = tournament_data.get('sport', '🎾Большой теннис')
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))

        # Локация
        city = tournament_data.get('city', '—')
        district = tournament_data.get('district', '')
        country = tournament_data.get('country', '')
        if district:
            city = f"{city} - {district}"

        # Текст сообщения
        name = escape_markdown(tournament_data.get('name', 'Новый турнир'))
        type_text = escape_markdown(tournament_data.get('type', '—'))
        gender = escape_markdown(tournament_data.get('gender', '—'))
        category = escape_markdown(tournament_data.get('category', '—'))
        level = escape_markdown(tournament_data.get('level', 'Не указан'))
        age_group = escape_markdown(tournament_data.get('age_group', '—'))
        duration = escape_markdown(tournament_data.get('duration', '—'))
        participants_count = escape_markdown(str(tournament_data.get('participants_count', '—')))
        comment = tournament_data.get('comment')
        comment_escaped = escape_markdown(comment) if comment else None

        text = (
            f"🏆 *{name}*\n\n"
            f"🌍 *Место:* {escape_markdown(city)}, {escape_markdown(country)}\n"
            f"🎯 *Тип:* {type_text} • {gender}\n"
            f"🏅 *Категория:* {category}\n"
            f"🧩 *Уровень:* {level}\n"
            f"👶 *Возраст:* {age_group}\n"
            f"⏱ *Продолжительность:* {duration}\n"
            f"👥 *Участников:* {participants_count}\n"
        )
        if comment_escaped:
            text += f"\n💬 *Описание:* {comment_escaped}"

        # Кнопка "Участвовать" как ссылка с deep-link
        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=join_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text="✅ Участвовать", url=deep_link))

        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup(),
            disable_web_page_preview=True,
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления о новом турнире: {e}")

async def send_tournament_application_to_channel(
    bot: Bot,
    tournament_id: str,
    tournament_data: Dict[str, Any],
    user_id: str,
    user_data: Dict[str, Any],
):
    """Отправляет уведомление в канал о том, что пользователь записался в турнир, с кнопкой "Участвовать"."""
    try:
        sport = tournament_data.get('sport', '🎾Большой теннис')
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))

        # Ссылка на профиль пользователя
        user_link = await create_user_profile_link(user_data, user_id, additional=False)

        name = escape_markdown(tournament_data.get('name', 'Турнир'))
        current = len(tournament_data.get('participants', {}))
        total = tournament_data.get('participants_count', '—')
        total_text = escape_markdown(str(total))

        text = (
            "🎉 *Новый участник в турнире!*\n\n"
            f"🏆 *Турнир:* {name}\n"
            f"👤 *Игрок:* {user_link}\n"
            f"👥 *Участников:* {current}/{total_text}\n\n"
            "Присоединяйтесь и участвуйте!"
        )

        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=join_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text="✅ Участвовать", url=deep_link))

        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup(),
            disable_web_page_preview=True,
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления об участнике турнира: {e}")


async def send_tournament_started_to_channel(
    bot: Bot,
    tournament_id: str,
    tournament_data: Dict[str, Any],
    bracket_image_bytes: bytes = None
):
    """Отправляет уведомление в канал о начале турнира с фото сетки."""
    try:
        sport = tournament_data.get('sport', '🎾Большой теннис')
        channel_id = channels_id.get(sport, channels_id.get("🎾Большой теннис"))

        # Локация
        city = tournament_data.get('city', '—')
        district = tournament_data.get('district', '')
        country = tournament_data.get('country', '')
        if district:
            city = f"{city} - {district}"

        # Текст сообщения
        name = escape_markdown(tournament_data.get('name', 'Турнир'))
        type_text = escape_markdown(tournament_data.get('type', '—'))
        gender = escape_markdown(tournament_data.get('gender', '—'))
        category = escape_markdown(tournament_data.get('category', '—'))
        level = escape_markdown(tournament_data.get('level', 'Не указан'))
        participants_count = len(tournament_data.get('participants', {}))
        
        text = (
            f"🏁 *Турнир начался!*\n\n"
            f"🏆 *{name}*\n\n"
            f"🌍 *Место:* {escape_markdown(city)}, {escape_markdown(country)}\n"
            f"🎯 *Тип:* {type_text} • {gender}\n"
            f"🏅 *Категория:* {category}\n"
            f"🧩 *Уровень:* {level}\n"
            f"👥 *Участников:* {participants_count}\n\n"
            f"Турнир запущен! Следите за результатами!"
        )

        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=view_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text="👀 Смотреть турнир", url=deep_link))

        # Отправляем с фото сетки, если оно есть
        if bracket_image_bytes:
            from aiogram.types import BufferedInputFile
            photo = BufferedInputFile(bracket_image_bytes, filename=f"tournament_{tournament_id}_bracket.png")
            await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=builder.as_markup(),
            )
        else:
            # Если фото нет, отправляем только текст
            await bot.send_message(
                chat_id=channel_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=builder.as_markup(),
                disable_web_page_preview=True,
            )
    except Exception as e:
        print(f"Ошибка отправки уведомления о начале турнира в канал: {e}")
