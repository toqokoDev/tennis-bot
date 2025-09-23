"""
Модуль для уведомлений участников турниров
"""

import logging
from typing import List, Dict, Any
from aiogram import Bot
from services.storage import storage

logger = logging.getLogger(__name__)


class TournamentNotifications:
    """Класс для отправки уведомлений участникам турниров"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def notify_tournament_started(self, tournament_id: str, tournament_data: Dict[str, Any]) -> bool:
        """Уведомляет всех участников о начале турнира и их соперниках"""
        try:
            participants = tournament_data.get('participants', {})
            tournament_name = tournament_data.get('name', 'Турнир')
            tournament_type = tournament_data.get('type', 'Олимпийская система')
            matches = tournament_data.get('matches', [])
            
            # Загружаем данные пользователей для получения username
            users = await storage.load_users()
            
            # Отправляем персональные уведомления каждому участнику
            success_count = 0
            for user_id, participant_data in participants.items():
                try:
                    user_data = users.get(user_id, {})
                    username = user_data.get('username', '')
                    username_text = f"@{username}" if username else "нет username"
                    
                    # Находим матчи этого пользователя
                    user_matches = []
                    for match in matches:
                        if match['player1_id'] == user_id or match['player2_id'] == user_id:
                            user_matches.append(match)
                    
                    if not user_matches:
                        continue
                    
                    # Формируем персональное сообщение
                    message = f"🏆 *Турнир начался!*\n\n"
                    message += f"📋 Название: {tournament_name}\n"
                    message += f"⚔️ Тип: {tournament_type}\n"
                    message += f"👤 Ваше имя: {participant_data.get('name', 'Неизвестно')}\n\n"
                    
                    if tournament_type == "Олимпийская система":
                        message += f"🎯 *Ваш соперник в первом раунде:*\n"
                        for match in user_matches:
                            if match['status'] == 'pending' and not match['is_bye']:
                                if match['player1_id'] == user_id:
                                    opponent_name = match['player2_name']
                                    opponent_id = match['player2_id']
                                else:
                                    opponent_name = match['player1_name']
                                    opponent_id = match['player1_id']
                                
                                opponent_data = users.get(opponent_id, {})
                                opponent_username = opponent_data.get('username', '')
                                opponent_username_text = f"@{opponent_username}" if opponent_username else "нет username"
                                
                                message += f"⚔️ {opponent_name}\n"
                                message += f"📱 Для связи: {opponent_username_text}\n"
                                message += f"🆔 ID: {opponent_id}\n\n"
                                
                    elif tournament_type == "Круговая":
                        message += f"🎯 *Ваши соперники:*\n"
                        for match in user_matches:
                            if match['status'] == 'pending' and not match['is_bye']:
                                if match['player1_id'] == user_id:
                                    opponent_name = match['player2_name']
                                    opponent_id = match['player2_id']
                                else:
                                    opponent_name = match['player1_name']
                                    opponent_id = match['player1_id']
                                
                                opponent_data = users.get(opponent_id, {})
                                opponent_username = opponent_data.get('username', '')
                                opponent_username_text = f"@{opponent_username}" if opponent_username else "нет username"
                                
                                message += f"⚔️ {opponent_name}\n"
                                message += f"📱 Для связи: {opponent_username_text}\n"
                                message += f"🆔 ID: {opponent_id}\n\n"
                    
                    message += f"📊 Для внесения результатов используйте команду /add_score"
                    
                    await self.bot.send_message(
                        chat_id=int(user_id),
                        text=message,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
            
            logger.info(f"Уведомления о начале турнира {tournament_id} отправлены {success_count} из {len(participants)} участников")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о начале турнира {tournament_id}: {e}")
            return False
    
    async def notify_match_assignment(self, tournament_id: str, match_data: Dict[str, Any]) -> bool:
        """Уведомляет игроков о назначенном матче"""
        try:
            tournament_data = await storage.load_tournaments()
            tournament_info = tournament_data.get(tournament_id, {})
            tournament_name = tournament_info.get('name', 'Турнир')
            
            player1_id = match_data.get('player1_id')
            player2_id = match_data.get('player2_id')
            
            message = f"⚔️ *Новый матч в турнире!*\n\n"
            message += f"🏆 Турнир: {tournament_name}\n"
            message += f"📋 Раунд: {match_data['round'] + 1}\n\n"
            
            if match_data['is_bye']:
                # Уведомляем игрока о автоматическом прохождении
                player_id = player1_id or player2_id
                message += f"🆓 Вы автоматически проходите в следующий раунд!\n"
                message += f"Ожидайте следующего соперника."
                
                try:
                    await self.bot.send_message(
                        chat_id=int(player_id),
                        text=message,
                        parse_mode='Markdown'
                    )
                    return True
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления о BYE пользователю {player_id}: {e}")
                    return False
            else:
                # Уведомляем обоих игроков о матче
                player1_name = match_data.get('player1_name', 'Игрок 1')
                player2_name = match_data.get('player2_name', 'Игрок 2')
                
                message += f"👤 Ваш соперник: {player2_name if player1_id else player1_name}\n\n"
                message += f"📊 Для внесения результата используйте команду /add_score"
                
                success_count = 0
                for player_id in [player1_id, player2_id]:
                    if player_id:
                        try:
                            await self.bot.send_message(
                                chat_id=int(player_id),
                                text=message,
                                parse_mode='Markdown'
                            )
                            success_count += 1
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления о матче пользователю {player_id}: {e}")
                
                return success_count > 0
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о матче: {e}")
            return False
    
    async def notify_tournament_completed(self, tournament_id: str, tournament_data: Dict[str, Any], winner_data: Dict[str, Any]) -> bool:
        """Уведомляет всех участников о завершении турнира"""
        try:
            participants = tournament_data.get('participants', {})
            tournament_name = tournament_data.get('name', 'Турнир')
            winner_name = winner_data.get('name', 'Неизвестно')
            
            message = f"🏆 *Турнир завершен!*\n\n"
            message += f"📋 Название: {tournament_name}\n"
            message += f"🥇 Победитель: {winner_name}\n\n"
            message += f"🎉 Поздравляем победителя и благодарим всех участников!"
            
            # Отправляем уведомления всем участникам
            success_count = 0
            for user_id in participants.keys():
                try:
                    await self.bot.send_message(
                        chat_id=int(user_id),
                        text=message,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления о завершении турнира пользователю {user_id}: {e}")
            
            logger.info(f"Уведомления о завершении турнира {tournament_id} отправлены {success_count} из {len(participants)} участников")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о завершении турнира {tournament_id}: {e}")
            return False
