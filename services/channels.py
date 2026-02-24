from typing import Any, Dict
import logging
import os
from aiogram import Bot, types
from aiogram.types import FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.paths import BASE_DIR
from config.profile import channels_id, tour_channel_id
from config.config import BOT_USERNAME
from utils.utils import calculate_age, create_user_profile_link, escape_markdown, remove_country_flag
from utils.translations import t
from config.profile import get_sport_translation

logger = logging.getLogger(__name__)

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
        
        # Получаем каналы для вида спорта
        channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Определяем список каналов для отправки
        target_channels = []
        if isinstance(channels, list):
            if len(channels) > 1 and profile.get('city') == 'Санкт-Петербург':
                target_channels.append(channels[1])
            else:
                target_channels.append(channels[0])
        else:
            # Для обратной совместимости (старый формат с одним каналом)
            target_channels.append(channels)
        
        # Получаем конфигурацию для вида спорта
        config = get_sport_config(sport)
        category = config.get("category", "court_sport")
        
        # Вычисляем возраст из даты рождения
        language = "ru"  # Каналы используют русский язык по умолчанию
        age_text = ""
        if profile.get('birth_date'):
            try:
                bd_str = profile.get('birth_date')
                birth_date = datetime.strptime(bd_str, "%d.%m.%Y")
                today = datetime.now()
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                age_text = t('channels.years_old', language, age=age)
            except ValueError:
                try:
                    birth_date = datetime.strptime(bd_str, "%d.%m")
                    today = datetime.now()
                    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    age_text = t('channels.years_old', language, age=age)
                except ValueError:
                    pass
        
        # Получаем пол
        gender = profile.get('gender', '')
        gender_emoji = "👨" if gender == "Мужской" else "👩" if gender == "Женский" else "👤"

        # Разное оформление для тренеров и игроков
        language = "ru"  # Каналы используют русский язык по умолчанию
        if role == "Тренер":
            price = escape_markdown(str(profile.get('price', 0)))
            country = escape_markdown(remove_country_flag(profile.get('country', '')))
            sport_translated = get_sport_translation(sport, language)
            sport_escaped = escape_markdown(sport_translated)
            registration_text = (
                f"{t('channels.new_trainer', language)}\n\n"
                f"🏆 {t('channels.trainer', language)} {await create_user_profile_link(profile, profile.get('telegram_id'), additional=False)}\n"
                f"📍 {t('channels.city', language)} {escape_markdown(city)} ({country})\n"
            )
            
            # Добавляем возраст и пол если есть
            if age_text and gender:
                registration_text += f"{gender_emoji} {t('channels.age', language)} {escape_markdown(age_text)}\n"
            elif age_text:
                registration_text += f"{gender_emoji} {t('channels.age', language)} {escape_markdown(age_text)}\n"
            elif gender:
                registration_text += f"{gender_emoji} {t('channels.gender', language)} {escape_markdown(gender)}\n"
            
            registration_text += (
                f"🎯 {t('channels.sport', language)} {sport_escaped}\n"
                f"💰 {t('channels.price', language)} {price} руб./тренировка\n"
            )
        
        else:
            country = escape_markdown(remove_country_flag(profile.get('country', '')))
            sport_escaped = escape_markdown(sport)
            registration_text = (
                f"{t('channels.new_player', language)}\n\n"
                f"👤 {t('channels.player', language)} {await create_user_profile_link(profile, profile.get('telegram_id'), additional=False)}\n"
                f"📍 {t('channels.city', language)} {escape_markdown(city)} ({country})\n"
            )
            
            # Добавляем возраст и пол если есть
            if age_text and gender:
                registration_text += f"{gender_emoji} {t('channels.age', language)} {escape_markdown(age_text)}\n"
            elif age_text:
                registration_text += f"{gender_emoji} {t('channels.age', language)} {escape_markdown(age_text)}\n"
            
            # Добавляем вид спорта
            registration_text += f"🎯 {t('channels.sport', language)} {sport_escaped}\n"
            
            # Добавляем уровень игры только если он указан
            if profile.get('player_level'):
                player_level = escape_markdown(profile.get('player_level'))
                registration_text += f"💪 {t('channels.level', language)} {player_level}\n"
            
            # Добавляем рейтинг если есть игры
            rating_points = profile.get('rating_points', 0)
            if rating_points and rating_points > 0:
                registration_text += f"⭐ {t('channels.rating', language)} {format_rating(rating_points)}\n"
        
        # Добавляем дополнительные поля в зависимости от вида спорта
        if category == "dating":
            # Для знакомств
            if profile.get('dating_goal'):
                dating_goal = escape_markdown(profile.get('dating_goal'))
                registration_text += f"💕 {t('channels.dating_goal', language)} {dating_goal}\n"
            
            if profile.get('dating_interests'):
                interests = ', '.join(profile.get('dating_interests', []))
                interests_escaped = escape_markdown(interests)
                registration_text += f"🎯 {t('channels.interests', language)} {interests_escaped}\n"
            
            if profile.get('dating_additional'):
                dating_additional = escape_markdown(profile.get('dating_additional'))
                registration_text += f"📝 {t('channels.about', language)} {dating_additional}"
            
        elif category == "meeting":
            # Для встреч
            if sport == "☕️Бизнес-завтрак":
                if profile.get('meeting_time'):
                    meeting_time = escape_markdown(profile.get('meeting_time'))
                    registration_text += f"☕️ {t('channels.meeting_time', language)} {meeting_time}"
            else:  # По пиву
                if profile.get('meeting_time'):
                    meeting_time = escape_markdown(profile.get('meeting_time'))
                    registration_text += f"🍻 {t('channels.meeting_time', language)} {meeting_time}"
                
        elif category == "outdoor_sport":
            # Для активных видов спорта
            if profile.get('profile_comment'):
                comment = escape_markdown(profile.get('profile_comment'))
                registration_text += f"💬 {t('channels.about', language)} {comment}"
            
        else:  # court_sport
            # Добавляем способ оплаты корта
            if profile.get('default_payment'):
                payment = escape_markdown(profile.get('default_payment'))
                registration_text += f"\n💳 {t('channels.court_payment', language)} {payment}\n"
            
            if profile.get('profile_comment'):
                comment = escape_markdown(profile.get('profile_comment'))
                registration_text += f"💬 {t('channels.about', language)} {comment}"
        
        # Отправляем во все целевые каналы
        for channel_id in target_channels:
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
        logger.error(f"[REG] ❌ Ошибка отправки уведомления о регистрации: {e}")
        logger.error(f"[REG] Тип ошибки: {type(e).__name__}")
        logger.error(f"[REG] Данные профиля: {profile}")
        import traceback
        logger.error(f"[REG] Traceback: {traceback.format_exc()}")

async def send_game_notification_to_channel(bot: Bot, data: Dict[str, Any], users: Dict[str, Any], user_id: str):
    """Отправляет уведомление о завершенной игре в канал"""

    game_type = data.get('game_type')
    score = data.get('score')

    # Берем вид спорта из данных игры, если нет - из профиля пользователя
    sport = data.get('sport', users.get(user_id, {}).get('sport', '🎾Большой теннис'))
    
    # Получаем каналы для вида спорта
    channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
    
    # Определяем список каналов для отправки
    target_channels = []
    # Берем город из данных игры, если нет - из профиля пользователя
    game_city = data.get('city', users.get(user_id, {}).get('city', ''))
    if isinstance(channels, list):
        if len(channels) > 1 and game_city == 'Санкт-Петербург':
            target_channels.append(channels[1])
        else:
            target_channels.append(channels[0])
    else:
        # Для обратной совместимости (старый формат с одним каналом)
        target_channels.append(channels)

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
        language = "ru"  # Каналы используют русский язык по умолчанию
        
        # Получаем информацию о турнире
        tournament_id = data.get('tournament_id')
        tournament_name = t('channels.unknown_tournament', language)
        if tournament_id:
            from services.storage import storage
            tournaments = await storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            tournament_name = tournament_data.get('name', t('channels.unknown_tournament', language))
        
        game_text = (
            f"{t('channels.tournament_game_completed', language)}\n\n"
            f"🏆 {t('channels.tournament', language)} {escape_markdown(tournament_name)}\n\n"
            f"🥇 {t('channels.winner_beats', language, winner=winner_link, loser=loser_link)}\n\n"
            f"📊 {t('channels.score', language)} {score_escaped}"
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
        language = "ru"  # Каналы используют русский язык по умолчанию
        
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
            f"{t('channels.single_game_completed', language)}\n\n"
            f"🥇 {t('channels.winner', language)} {winner_link}\n"
            f"🥈 {t('channels.loser', language)} {loser_link}\n\n"
            f"📊 {t('channels.score', language)} {score_escaped}\n\n"
            f"📈 {t('channels.rating_change', language)}\n"
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
        language = "ru"  # Каналы используют русский язык по умолчанию
        
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
        rating_changes_text = f"📈 {t('channels.rating_change', language)}\n"
        
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
            f"{t('channels.double_game_completed', language)}\n\n"
            f"🥇 {t('channels.winning_team', language)} {winner_links[0]} и {winner_links[1]}\n"
            f"🥈 {t('channels.losing_team', language)} {loser_links[0]} и {loser_links[1]}\n\n"
            f"📊 {t('channels.score', language)} {score_escaped}\n\n"
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
    language = "ru"  # Каналы используют русский язык по умолчанию
    reply_markup = None
    if game_type == 'tournament' and tournament_id:
        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=view_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text=t('channels.view_tournament', language), url=deep_link))
        reply_markup = builder.as_markup()
    
    # Отправляем во все целевые каналы
    for channel_id in target_channels:
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
                language = "ru"  # Каналы используют русский язык по умолчанию
                await bot.send_message(
                    chat_id=channel_id,
                    text=t('channels.tournament_info', language),
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
        
        profile_link = await create_user_profile_link(user_data, user_id, additional=False)
        language = "ru"  # Каналы используют русский язык по умолчанию

        age = 0
        if user_data.get('birth_date'):
            age = await calculate_age(user_data['birth_date'])

        if age > 0:
            profile_link += f"\n*{t('channels.age', language)} {age}*"
            
        sport = game_data.get('sport', user_data.get('sport', 'Не указан'))
        
        # Получаем конфигурацию для вида спорта
        config = get_sport_config(sport)
        category = config.get("category", "court_sport")
        
        # Формируем текст в зависимости от категории
        language = "ru"  # Каналы используют русский язык по умолчанию
        if category == "dating":
            # Для знакомств
            city = game_data.get('city', '—')
            district = game_data.get('district', '')
            country = game_data.get('country', '')
            
            # Добавляем округ к городу если есть
            if district:
                city = f"{city} - {district}"
            
            location = f"{city}, {remove_country_flag(country)}" if country else city
            
            location_escaped = escape_markdown(location)
            date_escaped = escape_markdown(game_data.get('date', '—'))
            time_escaped = escape_markdown(game_data.get('time', '—'))
            offer_text = (
                f"{t('channels.dating_profile', language)}\n\n"
                f"👤 {profile_link}\n"
                f"📍 {t('channels.city', language)} {location_escaped}\n"
                f"📅 {t('channels.date_time', language)} {date_escaped} в {time_escaped}\n"
            )
            
            # Добавляем поля знакомств
            if game_data.get('dating_goal'):
                dating_goal = escape_markdown(game_data.get('dating_goal'))
                offer_text += f"💕 {t('channels.dating_goal', language)} {dating_goal}\n"
            
            if game_data.get('dating_interests'):
                interests = ', '.join(game_data.get('dating_interests', []))
                interests_escaped = escape_markdown(interests)
                offer_text += f"🎯 {t('channels.interests', language)} {interests_escaped}\n"
            
            if game_data.get('dating_additional'):
                dating_additional = escape_markdown(game_data.get('dating_additional'))
                offer_text += f"📝 {t('channels.about', language)} {dating_additional}\n"
        elif category == "meeting":
            # Для встреч
            if sport == "☕️Бизнес-завтрак":
                city = game_data.get('city', '—')
                district = game_data.get('district', '')
                country = game_data.get('country', '')
                
                # Добавляем округ к городу если есть
                if district:
                    city = f"{city} - {district}"
                
                location = f"{city}, {remove_country_flag(country)}" if country else city
                location_escaped = escape_markdown(location)
                date_escaped = escape_markdown(game_data.get('date', '—'))
                time_escaped = escape_markdown(game_data.get('time', '—'))
                
                offer_text = (
                    f"{t('channels.business_breakfast_offer', language)}\n\n"
                    f"👤 {profile_link}\n"
                    f"📍 {t('channels.city', language)} {location_escaped}\n"
                    f"📅 {t('channels.date_time', language)} {date_escaped} в {time_escaped}\n"
                )
            else:  # По пиву
                city = game_data.get('city', '—')
                district = game_data.get('district', '')
                country = game_data.get('country', '')
                
                # Добавляем округ к городу если есть
                if district:
                    city = f"{city} - {district}"
                
                location = f"{city}, {remove_country_flag(country)}" if country else city
                location_escaped = escape_markdown(location)
                date_escaped = escape_markdown(game_data.get('date', '—'))
                time_escaped = escape_markdown(game_data.get('time', '—'))
                
                offer_text = (
                    f"{t('channels.beer_meeting_offer', language)}\n\n"
                    f"👤 {profile_link}\n"
                    f"📍 {t('channels.city', language)} {location_escaped}\n"
                    f"📅 {t('channels.date_time', language)} {date_escaped} в {time_escaped}\n"
                )
        elif category == "outdoor_sport":
            # Для активных видов спорта
            city = game_data.get('city', '—')
            district = game_data.get('district', '')
            country = game_data.get('country', '')
            
            # Добавляем округ к городу если есть
            if district:
                city = f"{city} - {district}"
            
            location = f"{city}, {remove_country_flag(country)}" if country else city
            location_escaped = escape_markdown(location)
            date_escaped = escape_markdown(game_data.get('date', '—'))
            time_escaped = escape_markdown(game_data.get('time', '—'))
            sport_translated = get_sport_translation(sport, language)
            sport_escaped = escape_markdown(sport_translated)
            
            offer_text = (
                f"{t('channels.activity_offer', language)}\n\n"
                f"👤 {profile_link}\n"
                f"📍 {t('channels.city', language)} {location_escaped}\n"
                f"📅 {t('channels.date_time', language)} {date_escaped} в {time_escaped}\n"
                f"🎯 {t('channels.sport', language)} {sport_escaped}\n"
            )
        else:  # court_sport
            # Для спортивных видов с кортами
            city = game_data.get('city', '—')
            district = game_data.get('district', '')
            country = game_data.get('country', '')
            
            # Добавляем округ к городу если есть
            if district:
                city = f"{city} - {district}"
            
            location = f"{city}, {remove_country_flag(country)}" if country else city
            location_escaped = escape_markdown(location)
            date_escaped = escape_markdown(game_data.get('date', '—'))
            time_escaped = escape_markdown(game_data.get('time', '—'))
            sport_translated = get_sport_translation(sport, language)
            sport_escaped = escape_markdown(sport_translated)
            game_type_escaped = escape_markdown(game_data.get('type', '—'))
            payment_type_escaped = escape_markdown(game_data.get('payment_type', '—'))
            
            if sport == "🏓Настольный теннис":
                level_text = t('channels.table_tennis_rating', language, rating=user_data.get('player_level'))
            else:
                level_text = f"🏆 {t('channels.level', language)} {user_data.get('player_level')} {t('channels.rating_points', language, points=user_data.get('rating_points', 0))}"
            
            offer_text = (
                f"{t('channels.game_offer', language)}\n\n"
                f"👤 {profile_link}\n"
                f"{level_text}\n"
                f"📍 {t('channels.city', language)} {location_escaped}\n"
                f"📅 {t('channels.date_time', language)} {date_escaped} в {time_escaped}\n"
                f"🎯 {t('channels.sport', language)} {sport_escaped}\n"
                f"🔍 {t('channels.game_type', language)} {game_type_escaped}\n"
                f"💳 {t('channels.payment', language)} {payment_type_escaped}"
            )
            
            if game_data.get('competitive'):
                offer_text += f"\n{t('channels.competitive_game', language)}"
        
        # Добавляем комментарий
        if game_data.get('comment'):
            comment_escaped = escape_markdown(game_data['comment'])
            offer_text += f"\n💬 {t('channels.comment', language)} {comment_escaped}"
            
        # Получаем каналы для вида спорта
        channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Определяем список каналов для отправки
        target_channels = []
        offer_city = game_data.get('city', '')
        if isinstance(channels, list):
            # Второй канал - только для Санкт-Петербурга
            if len(channels) > 1 and offer_city == 'Санкт-Петербург':
                print(f"DEBUG: Отправка в канал {channels[1]} для Санкт-Петербурга")
                target_channels.append(channels[1])
            else:
                print(f"DEBUG: Отправка в канал {channels[0]} для всех городов")
                target_channels.append(channels[0])
        else:
            # Для обратной совместимости (старый формат с одним каналом)
            target_channels.append(channels)

        photo_path = user_data.get("photo_path")

        # Отправляем во все целевые каналы
        for channel_id in target_channels:
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
        logger.error(f"[GAME] ❌ Ошибка при отправке предложения игры для пользователя {user_id}: {e}")
        logger.error(f"[GAME] Тип ошибки: {type(e).__name__}")
        logger.error(f"[GAME] Данные игры: {game_data}")
        import traceback
        logger.error(f"[GAME] Traceback: {traceback.format_exc()}")

async def send_tour_to_channel(bot: Bot, user_id: str, user_data: Dict[str, Any]):
    """Отправляет информацию о туре в телеграм-канал"""
    try:
        logger.info(f"[TOUR] Начало отправки тура в канал для пользователя {user_id}")
        logger.info(f"[TOUR] Данные: vacation_start={user_data.get('vacation_start')}, "
                   f"vacation_end={user_data.get('vacation_end')}, "
                   f"vacation_city={user_data.get('vacation_city')}, "
                   f"vacation_country={user_data.get('vacation_country')}, "
                   f"photo_path={user_data.get('photo_path')}")
        
        profile_link = await create_user_profile_link(user_data, user_id, additional=False)
        sport = user_data.get('sport', '🎾Большой теннис')
        language = "ru"  # Каналы используют русский язык по умолчанию
        
        # Формируем текст тура
        sport_translated = get_sport_translation(sport, language)
        sport_escaped = escape_markdown(sport_translated)
        vacation_city = user_data.get('vacation_city', '—')
        vacation_district = user_data.get('vacation_district', '')
        vacation_country = user_data.get('vacation_country', '—')
        
        # Добавляем округ к городу если есть
        if vacation_district:
            vacation_city = f"{vacation_city} - {vacation_district}"
        
        vacation_city_escaped = escape_markdown(vacation_city)
        vacation_country_escaped = escape_markdown(remove_country_flag(vacation_country))
        vacation_start = escape_markdown(user_data.get('vacation_start', ''))
        vacation_end = escape_markdown(user_data.get('vacation_end', ''))
        
        language = "ru"  # Каналы используют русский язык по умолчанию
        tour_text = (
            f"{t('channels.tour_title', language, sport=sport_escaped)}\n\n"
            f"👤 {profile_link}\n"
            f"🌍 {t('channels.destination', language)} {vacation_city_escaped}, {vacation_country_escaped}\n"
            f"📅 {t('channels.dates', language)} {vacation_start} - {vacation_end}"
        )
        
        if user_data.get('vacation_comment'):
            vacation_comment = escape_markdown(user_data['vacation_comment'])
            tour_text += f"\n💬 {t('channels.comment', language)} {vacation_comment}"
            
        photo_path = user_data.get("photo_path")

        if photo_path:
            logger.info(f"[TOUR] Отправка тура с фото: {photo_path}")
            await bot.send_photo(
                chat_id=tour_channel_id,
                photo=FSInputFile(BASE_DIR / photo_path),
                caption=tour_text,
                parse_mode="Markdown"
            )
        else:
            logger.info(f"[TOUR] Отправка тура без фото")
            await bot.send_message(
                chat_id=tour_channel_id,
                text=tour_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        
        logger.info(f"[TOUR] ✅ Тур успешно отправлен в канал для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"[TOUR] ❌ Ошибка при отправке тура в канал для пользователя {user_id}: {e}")
        logger.error(f"[TOUR] Тип ошибки: {type(e).__name__}")
        import traceback
        logger.error(f"[TOUR] Traceback: {traceback.format_exc()}")

async def send_tournament_created_to_channel(bot: Bot, tournament_id: str, tournament_data: Dict[str, Any]):
    """Отправляет уведомление о новом турнире в соответствующий канал с кнопкой "Участвовать"."""
    try:
        sport = tournament_data.get('sport', '🎾Большой теннис')
        
        # Получаем каналы для вида спорта
        channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Определяем список каналов для отправки
        target_channels = []
        tournament_city = tournament_data.get('city', '')
        if isinstance(channels, list):
            if len(channels) > 1 and tournament_city == 'Санкт-Петербург':
                target_channels.append(channels[1])
            else:
                target_channels.append(channels[0])
        else:
            # Для обратной совместимости (старый формат с одним каналом)
            target_channels.append(channels)

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

        language = "ru"  # Каналы используют русский язык по умолчанию
        text = (
            f"🏆 {t('channels.tournament_name', language, name=name)}\n\n"
            f"🌍 {t('channels.city', language)} {escape_markdown(city)}, {escape_markdown(remove_country_flag(country))}\n"
            f"🎯 {t('channels.tournament_type', language)} {type_text} • {gender}\n"
            f"🏅 {t('channels.category', language)} {category}\n"
            f"🧩 {t('channels.tournament_level', language)} {level}\n"
            f"👶 {t('channels.age_group', language)} {age_group}\n"
            f"⏱ {t('channels.duration', language)} {duration}\n"
            f"👥 {t('channels.participants', language)} {participants_count}\n"
        )
        if comment_escaped:
            text += f"\n💬 {t('channels.description', language)} {comment_escaped}"

        # Кнопка "Участвовать" как ссылка с deep-link
        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=join_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text=t('channels.join', language), url=deep_link))

        # Отправляем во все целевые каналы
        for channel_id in target_channels:
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
        
        # Получаем каналы для вида спорта
        channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Определяем список каналов для отправки
        target_channels = []
        tournament_city = tournament_data.get('city', '')
        if isinstance(channels, list):
            if len(channels) > 1 and tournament_city == 'Санкт-Петербург':
                target_channels.append(channels[1])
            else:
                target_channels.append(channels[0])
        else:
            # Для обратной совместимости (старый формат с одним каналом)
            target_channels.append(channels)

        # Ссылка на профиль пользователя
        user_link = await create_user_profile_link(user_data, user_id, additional=False)

        name = escape_markdown(tournament_data.get('name', 'Турнир'))
        current = len(tournament_data.get('participants', {}))
        total = tournament_data.get('participants_count', '—')
        total_text = escape_markdown(str(total))

        language = "ru"  # Каналы используют русский язык по умолчанию
        text = (
            f"{t('channels.new_participant', language)}\n\n"
            f"🏆 {t('channels.tournament', language)} {name}\n"
            f"👤 {t('channels.player', language)} {user_link}\n"
            f"👥 {t('channels.participants', language)} {current}/{total_text}\n\n"
            f"{t('channels.join_and_participate', language)}"
        )

        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=join_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text=t('channels.join', language), url=deep_link))

        # Проверяем, есть ли фото анкеты у участника
        photo_path = user_data.get('photo_path')
        
        # Отправляем во все целевые каналы
        for channel_id in target_channels:
            if photo_path:
                try:
                    # Формируем путь к фото
                    abs_path = photo_path if os.path.isabs(photo_path) else os.path.join(BASE_DIR, photo_path)
                    if os.path.exists(abs_path):
                        # Отправляем с фото
                        photo_file = FSInputFile(abs_path)
                        await bot.send_photo(
                            chat_id=channel_id,
                            photo=photo_file,
                            caption=text,
                            parse_mode="Markdown",
                            reply_markup=builder.as_markup(),
                        )
                        logger.info(f"Отправлено уведомление с фото участника {user_id} в канал {channel_id}")
                    else:
                        # Фото не найдено, отправляем без фото
                        await bot.send_message(
                            chat_id=channel_id,
                            text=text,
                            parse_mode="Markdown",
                            reply_markup=builder.as_markup(),
                            disable_web_page_preview=True,
                        )
                except Exception as e:
                    logger.warning(f"Не удалось отправить фото участника в канал {channel_id}: {e}")
                    # Если не удалось отправить с фото, отправляем без него
                    await bot.send_message(
                        chat_id=channel_id,
                        text=text,
                        parse_mode="Markdown",
                        reply_markup=builder.as_markup(),
                        disable_web_page_preview=True,
                    )
            else:
                # Нет фото, отправляем только текст
                await bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=builder.as_markup(),
                    disable_web_page_preview=True,
                )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления об участнике турнира: {e}")


async def send_tournament_started_to_channel(
    bot: Bot,
    tournament_id: str,
    tournament_data: Dict[str, Any],
    bracket_image_bytes: bytes = None
):
    """Отправляет уведомление в канал о начале турнира с фото сетки."""
    try:
        sport = tournament_data.get('sport', '🎾Большой теннис')
        
        # Получаем каналы для вида спорта
        channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Определяем список каналов для отправки
        target_channels = []
        tournament_city = tournament_data.get('city', '')
        if isinstance(channels, list):
            if len(channels) > 1 and tournament_city == 'Санкт-Петербург':
                target_channels.append(channels[1])
            else:
                target_channels.append(channels[0])
        else:
            # Для обратной совместимости (старый формат с одним каналом)
            target_channels.append(channels)

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
        
        language = "ru"  # Каналы используют русский язык по умолчанию
        text = (
            f"{t('channels.tournament_started', language)}\n\n"
            f"🏆 {t('channels.tournament_name', language, name=name)}\n\n"
            f"🌍 {t('channels.city', language)} {escape_markdown(city)}, {escape_markdown(remove_country_flag(country))}\n"
            f"🎯 {t('channels.tournament_type', language)} {type_text} • {gender}\n"
            f"🏅 {t('channels.category', language)} {category}\n"
            f"🧩 {t('channels.tournament_level', language)} {level}\n"
            f"👥 {t('channels.participants', language)} {participants_count}\n\n"
            f"{t('channels.tournament_follow', language)}"
        )

        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=view_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text=t('channels.view_tournament', language), url=deep_link))

        # Отправляем во все целевые каналы
        for channel_id in target_channels:
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


async def send_tournament_finished_to_channel(
    bot: Bot,
    tournament_id: str,
    tournament_data: Dict[str, Any],
    winners_collage_bytes: bytes = None,
    summary_text: str = ""
):
    """Отправляет уведомление в канал о завершении турнира с фото победителей."""
    try:
        sport = tournament_data.get('sport', '🎾Большой теннис')
        
        # Получаем каналы для вида спорта
        channels = channels_id.get(sport, channels_id.get("🎾Большой теннис"))
        
        # Определяем список каналов для отправки
        target_channels = []
        tournament_city = tournament_data.get('city', '')
        if isinstance(channels, list):
            if len(channels) > 1 and tournament_city == 'Санкт-Петербург':
                target_channels.append(channels[1])
            else:
                target_channels.append(channels[0])
        else:
            # Для обратной совместимости (старый формат с одним каналом)
            target_channels.append(channels)

        # Локация
        city = tournament_data.get('city', '—')
        district = tournament_data.get('district', '')
        country = tournament_data.get('country', '')
        if district:
            city = f"{city} - {district}"

        # Текст сообщения
        name = escape_markdown(tournament_data.get('name', 'Турнир'))
        type_text = escape_markdown(tournament_data.get('type', '—'))
        level = escape_markdown(tournament_data.get('level', 'Не указан'))
        participants_count = len(tournament_data.get('participants', {}))
        
        language = "ru"  # Каналы используют русский язык по умолчанию
        text = (
            f"{t('channels.tournament_finished', language)}\n\n"
            f"🏆 {t('channels.tournament_name', language, name=name)}\n\n"
            f"🌍 {t('channels.city', language)} {escape_markdown(city)}, {escape_markdown(remove_country_flag(country))}\n"
            f"🧩 {t('channels.tournament_level', language)} {level}\n"
            f"👥 {t('channels.participants', language)} {participants_count}\n\n"
        )
        
        if summary_text:
            # Summary уже содержит эмодзи, не экранируем его
            text += f"{t('channels.summary', language)}\n{summary_text}\n\n"
        
        text += t('channels.congratulations', language)

        builder = InlineKeyboardBuilder()
        deep_link = f"https://t.me/{BOT_USERNAME}?start=view_tournament_{tournament_id}"
        builder.row(InlineKeyboardButton(text=t('channels.view_tournament_button', language), url=deep_link))

        # Отправляем во все целевые каналы
        for channel_id in target_channels:
            # Отправляем с фото коллажа победителей, если оно есть
            if winners_collage_bytes:
                from aiogram.types import BufferedInputFile
                photo = BufferedInputFile(winners_collage_bytes, filename=f"winners_{tournament_id}.png")
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
        logger.info(f"✅ Уведомление о завершении турнира {tournament_id} отправлено во все каналы")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о завершении турнира в канал: {e}")