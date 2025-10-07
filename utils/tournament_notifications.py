"""
Модуль для уведомлений участников турниров
"""

import logging
from typing import List, Dict, Any
from aiogram import Bot
from aiogram.types import BufferedInputFile
from services.storage import storage
from utils.tournament_brackets import Player
from utils.bracket_image_generator import (
    build_tournament_bracket_image_bytes,
    create_simple_text_image_bytes,
)
from utils.round_robin_image_generator import build_round_robin_table
from config.tournament_config import MIN_PARTICIPANTS

logger = logging.getLogger(__name__)


class TournamentNotifications:
    """Класс для отправки уведомлений участникам турниров"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def _generate_bracket_image(self, tournament_data: dict, tournament_id: str) -> tuple[bytes, str]:
        """Генерирует изображение сетки турнира"""
        try:
            participants = tournament_data.get('participants', {}) or {}
            tournament_type = tournament_data.get('type', 'Олимпийская система')

            # Собираем игроков
            users = await storage.load_users()
            players: list[Player] = []
            for user_id, pdata in participants.items():
                u = users.get(user_id, {})
                players.append(
                    Player(
                        id=user_id,
                        name=pdata.get('name', u.get('first_name', 'Неизвестно')),
                        photo_url=u.get('photo_path'),
                        initial=None,
                    )
                )

            # Применяем посев (seeding)
            min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
            seeding = tournament_data.get('seeding') or []
            id_to_player = {p.id: p for p in players}
            ordered: list[Player] = []
            
            # Добираем из seeding
            for pid in seeding:
                if pid in id_to_player:
                    ordered.append(id_to_player.pop(pid))
            
            # Оставшиеся игроки
            import random
            remaining = list(id_to_player.values())
            random.shuffle(remaining)
            ordered.extend(remaining)

            players = ordered

            # Для олимпийской системы — добавляем номера посева
            if tournament_type == 'Олимпийская система':
                if seeding:
                    seed_index = {pid: i + 1 for i, pid in enumerate(seeding)}
                    players = [
                        Player(
                            id=p.id,
                            name=(f"№{seed_index.get(p.id)} {p.name}" if seed_index.get(p.id) else p.name),
                            photo_url=getattr(p, 'photo_url', None),
                            initial=getattr(p, 'initial', None),
                        )
                        for p in players
                    ]
                while len(players) < min_participants:
                    players.append(Player(id=f"empty_{len(players)}", name=" ", photo_url=None, initial=None))

            # Загружаем завершенные игры турнира
            completed_games: list[dict] = []
            try:
                games = await storage.load_games()
                normalized: list[dict] = []
                for g in games:
                    if g.get('tournament_id') != tournament_id:
                        continue
                    if g.get('type') not in (None, 'tournament'):
                        continue
                    
                    # Извлекаем игроков
                    p = g.get('players') or {}
                    team1_list: list[str] = []
                    team2_list: list[str] = []
                    if isinstance(p, dict):
                        t1 = p.get('team1') or []
                        t2 = p.get('team2') or []
                        if t1:
                            team1_list = [str(t1[0])] if not isinstance(t1[0], dict) else [str(t1[0].get('id'))]
                        if t2:
                            team2_list = [str(t2[0])] if not isinstance(t2[0], dict) else [str(t2[0].get('id'))]
                    elif isinstance(p, list) and len(p) >= 2:
                        a, b = p[0], p[1]
                        team1_list = [str(a)] if not isinstance(a, dict) else [str(a.get('id'))]
                        team2_list = [str(b)] if not isinstance(b, dict) else [str(b.get('id'))]

                    norm_game = {
                        'tournament_id': tournament_id,
                        'score': g.get('score') or (', '.join(g.get('sets', []) or [])),
                        'players': {
                            'team1': team1_list,
                            'team2': team2_list,
                        },
                        'winner_id': str(g.get('winner_id')) if g.get('winner_id') is not None else None,
                        'media_filename': g.get('media_filename'),
                        'date': g.get('date') or g.get('created_at'),
                        'status': g.get('status') or 'completed',
                    }
                    normalized.append(norm_game)
                
                completed_games = sorted(normalized, key=lambda x: x.get('date') or '', reverse=True)
            except Exception as e:
                logger.error(f"Ошибка при загрузке игр: {e}")

            # Генерируем изображение сетки
            if tournament_type == 'Круговая':
                table_players = [{"id": p.id, "name": p.name, "photo_path": getattr(p, 'photo_url', None)} for p in players]
                image_bytes = build_round_robin_table(table_players, completed_games, tournament_data.get('name', 'Турнир'))
                return image_bytes, "Круговая таблица"
            else:
                return build_tournament_bracket_image_bytes(tournament_data, players, completed_games)
                
        except Exception as e:
            logger.error(f"Ошибка при генерации изображения сетки: {e}", exc_info=True)
            fallback = "Турнирная сетка\n\nНе удалось загрузить данные"
            return create_simple_text_image_bytes(fallback, "Ошибка"), ""
    
    async def notify_tournament_started(self, tournament_id: str, tournament_data: Dict[str, Any]) -> bool:
        """Уведомляет всех участников о начале турнира и их соперниках"""
        try:
            participants = tournament_data.get('participants', {})
            tournament_name = tournament_data.get('name', 'Турнир')
            tournament_type = tournament_data.get('type', 'Олимпийская система')
            matches = tournament_data.get('matches', [])
            
            logger.info(f"Начинаю отправку уведомлений для турнира {tournament_id} ({tournament_name})")
            logger.info(f"Участников: {len(participants)}, матчей: {len(matches)}")
            
            # Генерируем изображение сетки турнира
            try:
                logger.info(f"Генерация изображения сетки турнира {tournament_id}")
                bracket_image_bytes, caption_suffix = await self._generate_bracket_image(tournament_data, tournament_id)
                bracket_photo = BufferedInputFile(bracket_image_bytes, filename=f"tournament_{tournament_id}_bracket.png")
                logger.info(f"Изображение сетки успешно сгенерировано: {len(bracket_image_bytes)} байт")
            except Exception as e:
                logger.error(f"Ошибка генерации изображения сетки: {e}", exc_info=True)
                bracket_photo = None
            
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
                    
                    # Отправляем с фото сетки, если оно есть
                    if bracket_photo:
                        try:
                            # Создаем новый BufferedInputFile для каждого пользователя
                            user_photo = BufferedInputFile(bracket_image_bytes, filename=f"tournament_{tournament_id}_bracket.png")
                            await self.bot.send_photo(
                                chat_id=user_id,
                                photo=user_photo,
                                caption=message,
                                parse_mode='HTML'
                            )
                        except Exception as photo_error:
                            logger.error(f"Ошибка отправки фото участнику {user_id}: {photo_error}")
                            # Если не удалось отправить с фото, отправляем просто текст
                            await self.bot.send_message(
                                chat_id=user_id,
                                text=message,
                                parse_mode='HTML'
                            )
                    else:
                        # Если фото не сгенерировано, отправляем только текст
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
