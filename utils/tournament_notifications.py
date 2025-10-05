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
            
            logger.info(f"Начинаю отправку уведомлений для турнира {tournament_id} ({tournament_name})")
            logger.info(f"Участников: {len(participants)}, матчей: {len(matches)}")
            
            # Загружаем данные пользователей для получения username
            users = await storage.load_users()
            
            # Отправляем персональные уведомления каждому участнику
            success_count = 0
            for user_id, participant_data in participants.items():
                try:
                    logger.info(f"Обработка участника {user_id}...")
                    user_data = users.get(user_id, {})
                    username = user_data.get('username', '')
                    username_text = f"@{username}" if username else "нет username"
                    
                    # Находим матчи этого пользователя (нормализуем ID к строкам)
                    user_matches = []
                    for match in matches:
                        match_p1 = str(match.get('player1_id', ''))
                        match_p2 = str(match.get('player2_id', ''))
                        if match_p1 == str(user_id) or match_p2 == str(user_id):
                            user_matches.append(match)
                    
                    logger.info(f"Для участника {user_id} найдено матчей: {len(user_matches)}")
                    
                    if not user_matches:
                        logger.warning(f"У участника {user_id} нет матчей, пропускаем уведомление")
                        continue
                    
                    # Формируем персональное сообщение (используем HTML вместо Markdown для надежности)
                    message = f"🏆 <b>Турнир начался!</b>\n\n"
                    message += f"📋 Название: {tournament_name}\n"
                    message += f"⚔️ Тип: {tournament_type}\n"
                    message += f"👤 Ваше имя: {participant_data.get('name', 'Неизвестно')}\n\n"
                    
                    if tournament_type == "Олимпийская система":
                        message += f"🎯 <b>Ваш соперник в первом раунде:</b>\n"
                        for match in user_matches:
                            if match.get('status') == 'pending' and not match.get('is_bye'):
                                if str(match.get('player1_id')) == str(user_id):
                                    opponent_name = match.get('player2_name', 'Неизвестно')
                                    opponent_id = str(match.get('player2_id', ''))
                                else:
                                    opponent_name = match.get('player1_name', 'Неизвестно')
                                    opponent_id = str(match.get('player1_id', ''))
                                
                                opponent_data = users.get(opponent_id, {})
                                opponent_username = opponent_data.get('username', '')
                                opponent_username_text = f"@{opponent_username}" if opponent_username else "нет username"
                                
                                message += f"⚔️ {opponent_name}\n"
                                message += f"📱 Для связи: {opponent_username_text}\n"
                                
                    elif tournament_type == "Круговая":
                        message += f"🎯 <b>Ваши соперники:</b>\n"
                        for match in user_matches:
                            if match.get('status') == 'pending' and not match.get('is_bye'):
                                if str(match.get('player1_id')) == str(user_id):
                                    opponent_name = match.get('player2_name', 'Неизвестно')
                                    opponent_id = str(match.get('player2_id', ''))
                                else:
                                    opponent_name = match.get('player1_name', 'Неизвестно')
                                    opponent_id = str(match.get('player1_id', ''))
                                
                                opponent_data = users.get(opponent_id, {})
                                opponent_username = opponent_data.get('username', '')
                                opponent_username_text = f"@{opponent_username}" if opponent_username else "нет username"
                                
                                message += f"⚔️ {opponent_name}\n"
                                message += f"📱 Для связи: {opponent_username_text}\n"
                    
                    logger.info(f"Отправка сообщения участнику {user_id}, длина сообщения: {len(message)}")
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    success_count += 1
                    logger.info(f"✅ Уведомление успешно отправлено участнику {user_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки уведомления пользователю {user_id}: {e}", exc_info=True)
            
            logger.info(f"Уведомления о начале турнира {tournament_id} отправлены {success_count} из {len(participants)} участников")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о начале турнира {tournament_id}: {e}", exc_info=True)
            return False
    
    async def notify_match_assignment(self, tournament_id: str, match_data: Dict[str, Any]) -> bool:
        """Уведомляет игроков о назначенном матче"""
        try:
            tournament_data = await storage.load_tournaments()
            tournament_info = tournament_data.get(tournament_id, {})
            tournament_name = tournament_info.get('name', 'Турнир')
            
            player1_id = match_data.get('player1_id')
            player2_id = match_data.get('player2_id')
            
            message = f"⚔️ <b>Новый матч в турнире!</b>\n\n"
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
                        parse_mode='HTML'
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
                                parse_mode='HTML'
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
            
            message = f"🏆 <b>Турнир завершен!</b>\n\n"
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
                        parse_mode='HTML'
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления о завершении турнира пользователю {user_id}: {e}")
            
            logger.info(f"Уведомления о завершении турнира {tournament_id} отправлены {success_count} из {len(participants)} участников")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о завершении турнира {tournament_id}: {e}")
            return False
