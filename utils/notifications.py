from aiogram import Bot
from datetime import datetime
from config.config import CHANNEL_ID
from config.paths import BASE_DIR
from utils.json_data import load_users
from utils.utils import create_user_profile_link

async def send_subscription_reminders(bot: Bot):
    """Отправка напоминаний о скором истечении подписки"""
    users = load_users()
    current_time = datetime.now()
    
    for user_id, user_data in users.items():
        if 'subscription' in user_data and user_data['subscription'].get('active', False):
            subscription_until = user_data['subscription'].get('until')
            if subscription_until:
                try:
                    until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                    days_remaining = (until_date - current_time).days
                    
                    # Напоминание за 3 дня до истечения
                    if days_remaining == 3:
                        try:
                            await bot.send_message(
                                int(user_id),
                                f"⚠️ Ваша подписка Tennis-Play PRO истекает через 3 дня ({until_date.strftime('%d.%m.%Y')}).\n\n"
                                "Не забудьте продлить подписку для непрерывного доступа к PRO-функциям!"
                            )
                        except Exception as e:
                            print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
                            
                    # Напоминание за 1 день до истечения
                    elif days_remaining == 1:
                        try:
                            await bot.send_message(
                                int(user_id),
                                f"🔔 Ваша подписка Tennis-Play PRO истекает завтра ({until_date.strftime('%d.%m.%Y')})!\n\n"
                                "Продлите подписку сейчас, чтобы сохранить доступ ко всем функциям."
                            )
                        except Exception as e:
                            print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
                            
                except ValueError:
                    continue

async def send_game_notification_to_channel(bot, data, users):
    """Отправляет уведомление о завершенной игре в канал"""
    try:
        game_type = data.get('game_type')
        score = data.get('score')

        if game_type == 'single':
            # Одиночная игра
            player1_id = data.get('current_user_id')
            player2_id = data.get('opponent1', {}).get('telegram_id')
            
            player1 = users.get(player1_id, {})
            player2 = users.get(player2_id, {})
            
            player1_link = create_user_profile_link(player1, player1_id)
            player2_link = create_user_profile_link(player2, player2_id)
            
            winner_side = data.get('winner_side')
            if winner_side == "team1":
                winner_link = player1_link
                loser_link = player2_link
            else:
                winner_link = player2_link
                loser_link = player1_link
            
            game_text = (
                "🎾 *Завершена одиночная игра!*\n\n"
                f"🏆 Победитель: {winner_link}\n"
                f"🥈 Проигравший: {loser_link}\n"
                f"📊 Счет: {score}\n\n"
                f"#игра #одиночная"
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
            
            team1_player1_link = create_user_profile_link(team1_player1, team1_player1_id)
            team1_player2_link = create_user_profile_link(team1_player2, team1_player2_id)
            team2_player1_link = create_user_profile_link(team2_player1, team2_player1_id)
            team2_player2_link = create_user_profile_link(team2_player2, team2_player2_id)
            
            winner_side = data.get('winner_side')
            if winner_side == "team1":
                winner_team = f"{team1_player1_link} & {team1_player2_link}"
                loser_team = f"{team2_player1_link} & {team2_player2_link}"
            else:
                winner_team = f"{team2_player1_link} & {team2_player2_link}"
                loser_team = f"{team1_player1_link} & {team1_player2_link}"
            
            game_text = (
                "🎾 *Завершена парная игра!*\n\n"
                f"🏆 Победители: {winner_team}\n"
                f"🥈 Проигравшие: {loser_team}\n"
                f"📊 Счет: {score}\n\n"
                f"#игра #парная"
            )
        
        if data.get('photo_id'):
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=data['photo_id'],
                caption=game_text,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=game_text,
                parse_mode="Markdown"
            )
        
    except:
        pass
