"""
Модуль для управления турнирами и автоматического старта
"""

import logging
import math
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.tournament_brackets import create_tournament_bracket, Player, Match
from services.storage import storage
from config.tournament_config import MIN_PARTICIPANTS
from aiogram import Bot
from utils.tournament_notifications import TournamentNotifications
import random
import os
from PIL import Image, ImageDraw, ImageFont
import io
from config.paths import BASE_DIR

logger = logging.getLogger(__name__)


class TournamentManager:
    """Класс для управления турнирами"""
    
    def __init__(self):
        self.storage = storage
    
    def _create_winners_collage(self, top_players: List[Dict[str, Any]]) -> bytes:
        """Создает коллаж из фотографий топ-3 игроков (или меньше)
        
        top_players: список словарей с ключами 'user_id', 'name', 'photo_path', 'place'
        """
        try:
            # Размеры коллажа
            img_size = 200  # Размер каждой фотографии
            padding = 20
            label_height = 90  # Увеличено для места и имени
            
            # Количество игроков (максимум 3)
            n = min(len(top_players), 3)
            if n == 0:
                # Создаем пустое изображение
                img = Image.new('RGB', (400, 300), (255, 255, 255))
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                return buf.getvalue()
            
            # Размеры финального изображения
            width = n * img_size + (n + 1) * padding
            height = img_size + label_height + padding
            
            # Создаем изображение
            img = Image.new('RGB', (width, height), (255, 255, 255))
            draw = ImageDraw.Draw(img)
            
            # Загружаем шрифты
            try:
                font_path = os.path.join(BASE_DIR, "fonts", "Circe-Bold.ttf")
                title_font = ImageFont.truetype(font_path, 24)
                place_font = ImageFont.truetype(font_path, 32)
            except:
                try:
                    title_font = ImageFont.truetype("arialbd.ttf", 24)
                    place_font = ImageFont.truetype("arialbd.ttf", 32)
                except:
                    title_font = ImageFont.load_default()
                    place_font = ImageFont.load_default()
            
            # Отрисовываем каждого игрока
            for idx, player in enumerate(top_players[:3]):
                x = padding + idx * (img_size + padding)
                y = padding
                
                # Загружаем фото игрока
                photo_path = player.get('photo_path')
                player_img = None
                
                if photo_path:
                    try:
                        abs_path = photo_path if os.path.isabs(photo_path) else os.path.join(BASE_DIR, photo_path)
                        if os.path.exists(abs_path):
                            player_img = Image.open(abs_path)
                            player_img = player_img.convert('RGB')
                            # Обрезаем до квадрата
                            w, h = player_img.size
                            side = min(w, h)
                            left = (w - side) // 2
                            top = (h - side) // 2
                            player_img = player_img.crop((left, top, left + side, top + side))
                            player_img = player_img.resize((img_size, img_size), Image.LANCZOS)
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить фото игрока {player.get('user_id')}: {e}")
                
                # Если фото нет, создаем placeholder с серым фоном и инициалами
                if not player_img:
                    # Серый фон с градиентом для красоты
                    player_img = Image.new('RGB', (img_size, img_size), (180, 180, 180))
                    
                    # Добавляем инициалы крупным шрифтом
                    try:
                        name = player.get('name', '??')
                        parts = name.split()
                        if len(parts) >= 2:
                            initials = (parts[0][:1] + parts[1][:1]).upper()
                        else:
                            initials = name[:2].upper() if len(name) >= 2 else name.upper()
                        
                        # Создаем более крупный шрифт для инициалов
                        try:
                            font_path = os.path.join(BASE_DIR, "fonts", "Circe-Bold.ttf")
                            initials_font = ImageFont.truetype(font_path, 80)
                        except:
                            try:
                                initials_font = ImageFont.truetype("arialbd.ttf", 80)
                            except:
                                initials_font = place_font
                        
                        d = ImageDraw.Draw(player_img)
                        
                        # Вычисляем позицию для центрирования текста
                        bbox = d.textbbox((0, 0), initials, font=initials_font)
                        tw = bbox[2] - bbox[0]
                        th = bbox[3] - bbox[1]
                        tx = (img_size - tw) // 2
                        ty = (img_size - th) // 2
                        
                        # Рисуем белые инициалы с небольшой тенью для глубины
                        # Тень
                        d.text((tx + 2, ty + 2), initials, fill=(100, 100, 100), font=initials_font)
                        # Основной текст
                        d.text((tx, ty), initials, fill=(255, 255, 255), font=initials_font)
                    except Exception as e:
                        logger.warning(f"Не удалось добавить инициалы: {e}")
                
                # Вставляем фото
                img.paste(player_img, (x, y))
                
                # Рисуем рамку с цветом медали
                medal_colors = {
                    1: (255, 215, 0),   # Золото
                    2: (192, 192, 192),  # Серебро
                    3: (205, 127, 50)    # Бронза
                }
                color = medal_colors.get(idx + 1, (100, 100, 100))
                draw.rectangle([x-2, y-2, x+img_size+2, y+img_size+2], outline=color, width=4)
                
                # Добавляем место и имя
                place_text = f"{idx + 1} место"
                name = player.get('name', 'Игрок')
                
                # Рисуем место
                medal_y = y + img_size + 5
                try:
                    bbox = draw.textbbox((0, 0), place_text, font=title_font)
                    medal_w = bbox[2] - bbox[0]
                    medal_x = x + (img_size - medal_w) // 2
                    draw.text((medal_x, medal_y), place_text, fill=color, font=title_font)
                except:
                    draw.text((x + 5, medal_y), place_text, fill=color, font=title_font)
                
                # Рисуем имя (обрезаем если слишком длинное)
                name_y = medal_y + 30
                if len(name) > 15:
                    name = name[:13] + '...'
                try:
                    bbox = draw.textbbox((0, 0), name, font=title_font)
                    name_w = bbox[2] - bbox[0]
                    name_x = x + (img_size - name_w) // 2
                    draw.text((name_x, name_y), name, fill=(31, 41, 55), font=title_font)
                except:
                    draw.text((x + 5, name_y), name, fill=(31, 41, 55), font=title_font)
            
            # Сохраняем в буфер
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return buf.getvalue()
            
        except Exception as e:
            logger.error(f"Ошибка создания коллажа победителей: {e}")
            # Возвращаем пустое изображение в случае ошибки
            img = Image.new('RGB', (400, 300), (255, 255, 255))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return buf.getvalue()
    
    async def check_tournament_readiness(self, tournament_id: str) -> bool:
        """Проверяет, готов ли турнир к старту"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        
        if not tournament_data:
            return False
        
        participants = tournament_data.get('participants', {})
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        min_participants = MIN_PARTICIPANTS.get(tournament_type, 4)
        
        return len(participants) >= min_participants
    
    async def start_tournament(self, tournament_id: str) -> bool:
        """Запускает турнир и проводит жеребьевку"""
        try:
            tournaments = await self.storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            
            if not tournament_data:
                logger.error(f"Турнир {tournament_id} не найден")
                return False
            
            participants = tournament_data.get('participants', {})
            tournament_type = tournament_data.get('type', 'Олимпийская система')
            
            # Проводим жеребьевку
            matches = self._conduct_draw(participants, tournament_type, tournament_id, tournament_data)
            
            # Обновляем статус турнира
            tournament_data['status'] = 'started'
            tournament_data['started_at'] = datetime.now().isoformat()
            tournament_data['matches'] = matches
            tournament_data['current_round'] = 0
            
            tournaments[tournament_id] = tournament_data
            await self.storage.save_tournaments(tournaments)

            # Автоматически завершаем BYE-матчи и подготавливаем следующие раунды
            await self._rebuild_next_round(tournament_id)
            
            logger.info(f"Турнир {tournament_id} успешно запущен с {len(matches)} матчами")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска турнира {tournament_id}: {e}")
            return False
    
    def _conduct_draw(self, participants: Dict[str, Any], tournament_type: str, tournament_id: str, tournament_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Проводит жеребьевку для турнира.

        Логика:
        - Для олимпийской системы используем сохранённый посев `seeding` (если есть),
          иначе формируем порядок случайно. Пары первого круга — (1–2), (3–4), ...
          Недостающие слоты заполняем BYE (игрок отсутствует, is_bye=True).
        - Для круговой системы — каждый с каждым (порядок случайный).
        """
        matches: List[Dict[str, Any]] = []
        participant_ids = list(participants.keys())

        if not participant_ids:
            return matches

        if tournament_type == "Олимпийская система":
            # Используем сохранённый посев из данных турнира, если он есть
            seeding = list((tournament_data or {}).get('seeding') or [])

            # Отфильтруем посев от отсутствующих и дополним оставшимися участниками
            seen = set()
            ordered: List[str] = []
            for pid in seeding:
                if pid in participants and pid not in seen:
                    ordered.append(pid)
                    seen.add(pid)
            remaining = [pid for pid in participant_ids if pid not in seen]
            if remaining:
                random.shuffle(remaining)
                ordered.extend(remaining)

            # Доводим до степени двойки с BYE (None)
            size = len(ordered)
            bracket_size = 1 if size == 0 else 2 ** math.ceil(math.log2(size))
            while len(ordered) < bracket_size:
                ordered.append(None)  # BYE слот

            # Формируем пары (1–2), (3–4), ...
            for i in range(0, len(ordered), 2):
                p1 = ordered[i]
                p2 = ordered[i + 1] if i + 1 < len(ordered) else None

                is_bye = (p1 is None) or (p2 is None)
                match_data = {
                    'id': f"{tournament_id}_round_0_match_{i//2}",
                    'tournament_id': tournament_id,
                    'round': 0,
                    'match_number': i // 2,
                    'player1_id': p1,
                    'player2_id': p2,
                    'player1_name': (participants.get(p1, {}).get('name') if p1 else 'BYE'),
                    'player2_name': (participants.get(p2, {}).get('name') if p2 else 'BYE'),
                    'winner_id': None,
                    'score': None,
                    'status': 'pending',
                    'is_bye': is_bye,
                    'created_at': datetime.now().isoformat()
                }
                matches.append(match_data)

        elif tournament_type == "Круговая":
            # Каждый с каждым. Если есть посев — используем его порядок; иначе случайный
            ordered = list((tournament_data or {}).get('seeding') or [])
            seen = set()
            if ordered:
                ordered = [pid for pid in ordered if pid in participants and not (pid in seen or seen.add(pid))]
                remaining = [pid for pid in participant_ids if pid not in seen]
                if remaining:
                    random.shuffle(remaining)
                participant_ids = ordered + remaining
            else:
                random.shuffle(participant_ids)
            for i, p1 in enumerate(participant_ids):
                for p2 in participant_ids[i + 1:]:
                    match_data = {
                        'id': f"{tournament_id}_round_0_match_{len(matches)}",
                        'tournament_id': tournament_id,
                        'round': 0,
                        'match_number': len(matches),
                        'player1_id': p1,
                        'player2_id': p2,
                        'player1_name': participants[p1]['name'],
                        'player2_name': participants[p2]['name'],
                        'winner_id': None,
                        'score': None,
                        'status': 'pending',
                        'is_bye': False,
                        'created_at': datetime.now().isoformat()
                    }
                    matches.append(match_data)

        return matches

    async def _notify_pending_matches(self, tournament_id: str, bot: Bot) -> None:
        """Отправляет уведомления о назначенных матчах, если оба игрока известны и уведомление ещё не отправлено."""
        try:
            tournaments = await self.storage.load_tournaments()
            t = tournaments.get(tournament_id, {})
            matches = t.get('matches', []) or []
            if not matches:
                return
            if not bot:
                return
            notifier = TournamentNotifications(bot)
            changed = False
            for m in matches:
                if m.get('status') == 'pending' and not m.get('is_bye', False) and m.get('player1_id') and m.get('player2_id') and not m.get('notified'):
                    ok = await notifier.notify_match_assignment(tournament_id, m)
                    if ok:
                        m['notified'] = True
                        changed = True
            if changed:
                t['matches'] = matches
                tournaments[tournament_id] = t
                await self.storage.save_tournaments(tournaments)
        except Exception as e:
            logger.error(f"Ошибка уведомления о назначенных матчах {tournament_id}: {e}")

    async def _notify_completion_with_places(self, tournament_id: str, bot: Bot) -> None:
        """Если турнир завершён, отправляет участникам сообщения об итоговых местах."""
        try:
            tournaments = await self.storage.load_tournaments()
            t = tournaments.get(tournament_id, {})
            if not t:
                return
            
            # Если уведомления уже были отправлены, не отправляем повторно
            if t.get('completion_notified'):
                return
            
            participants = t.get('participants', {}) or {}
            matches = t.get('matches', []) or []
            if not participants:
                return
            
            # Проверяем завершение: все матчи завершены или BYE
            pending = [m for m in matches if m.get('status') != 'completed' and not m.get('is_bye', False)]
            if pending:
                logger.info(f"Турнир {tournament_id} еще не завершен. Осталось матчей: {len(pending)}")
                return
            
            logger.info(f"Все матчи турнира {tournament_id} завершены. Начинаем завершение турнира и отправку уведомлений.")
            
            # Обновим статус турнира
            t['status'] = 'finished'
            t['finished_at'] = datetime.now().isoformat()
            t['completion_notified'] = True  # Отмечаем, что уведомления отправлены

            # Готовим вычисление мест
            places: Dict[str, str] = {}
            summary_lines: List[str] = []
            t_type = t.get('type', 'Олимпийская система')

            if t_type == 'Круговая':
                # Подсчёт 3/1/0 и тай-брейк по разнице сетов между равными по очкам
                def parse_sets(score_text: str) -> List[tuple[int, int]]:
                    out: List[tuple[int, int]] = []
                    for s in [x.strip() for x in str(score_text or '').split(',') if ':' in x]:
                        try:
                            a, b = s.split(':')
                            out.append((int(a), int(b)))
                        except Exception:
                            continue
                    return out
                ids = [str(pid) for pid in participants.keys()]
                points = {pid: 0 for pid in ids}
                tie_sd = {pid: 0 for pid in ids}
                res_map: Dict[tuple, Dict[str, Any]] = {}
                for m in matches:
                    p1 = str(m.get('player1_id')) if m.get('player1_id') is not None else None
                    p2 = str(m.get('player2_id')) if m.get('player2_id') is not None else None
                    if not p1 or not p2:
                        continue
                    sets = parse_sets(m.get('score'))
                    a_sets = sum(1 for x, y in sets if x > y)
                    b_sets = sum(1 for x, y in sets if y > x)
                    key = tuple(sorted([p1, p2]))
                    res_map[key] = {'a': p1, 'b': p2, 'a_sets': a_sets, 'b_sets': b_sets}
                    # Очки 3/1/0
                    if a_sets > b_sets:
                        points[p1] += 3
                    elif b_sets > a_sets:
                        points[p2] += 3
                    else:
                        points[p1] += 1
                        points[p2] += 1
                # Тай-брейк внутри групп равных очков: сумма разницы сетов в очных
                from collections import defaultdict
                pts_groups = defaultdict(list)
                for pid in ids:
                    pts_groups[points[pid]].append(pid)
                for grp in pts_groups.values():
                    if len(grp) <= 1:
                        continue
                    for pid in grp:
                        sd = 0
                        for opp in grp:
                            if opp == pid:
                                continue
                            rec = res_map.get(tuple(sorted([pid, opp])))
                            if not rec:
                                continue
                            if rec['a'] == pid:
                                sd += rec['a_sets'] - rec['b_sets']
                            else:
                                sd += rec['b_sets'] - rec['a_sets']
                        tie_sd[pid] = sd
                order = sorted(ids, key=lambda pid: (points.get(pid, 0), tie_sd.get(pid, 0)), reverse=True)
                # Итоговые места
                for idx, pid in enumerate(order, start=1):
                    places[pid] = f"{idx} место"
                # Резюме топ-3
                def name_of(uid: str) -> str:
                    return participants.get(uid, {}).get('name', uid)
                summary_lines = [
                    f"🥇 1 место: {name_of(order[0])}" if order else "",
                    f"🥈 2 место: {name_of(order[1])}" if len(order) > 1 else "",
                    f"🥉 3 место: {name_of(order[2])}" if len(order) > 2 else "",
                ]
            else:
                # Олимпийская система: чемпион/финалист и точные места из утешительных матчей
                if not matches:
                    return
                
                # Функция для получения имени
                def pname(uid: str | None) -> str:
                    if not uid:
                        return "—"
                    return participants.get(uid, {}).get('name', uid)
                
                # Находим основной финал (не утешительный)
                main_matches = [m for m in matches if not m.get('is_consolation', False)]
                max_main_round = max(int(m.get('round', 0)) for m in main_matches) if main_matches else 0
                final_match = None
                for m in main_matches:
                    if int(m.get('round', 0)) == max_main_round and not m.get('is_consolation', False):
                        final_match = m
                        break
                
                champion = str(final_match.get('winner_id')) if final_match and final_match.get('winner_id') else None
                runner_up = None
                if final_match and champion:
                    a = str(final_match.get('player1_id'))
                    b = str(final_match.get('player2_id'))
                    runner_up = a if b == champion else b
                
                # Расставим основные места
                if champion:
                    places[champion] = "1 место"
                if runner_up:
                    places[runner_up] = "2 место"
                
                # Обрабатываем утешительные матчи для точного определения мест
                third_place_winner = None
                fourth_place = None
                
                # Матч за 3-4 место
                third_place_match = None
                for m in matches:
                    if m.get('is_consolation') and m.get('consolation_place') == '3-4':
                        third_place_match = m
                        break
                if third_place_match and third_place_match.get('status') == 'completed':
                    winner_3rd = str(third_place_match.get('winner_id'))
                    p1 = str(third_place_match.get('player1_id'))
                    p2 = str(third_place_match.get('player2_id'))
                    loser_3rd = p2 if winner_3rd == p1 else p1
                    places[winner_3rd] = "3 место"
                    places[loser_3rd] = "4 место"
                    third_place_winner = winner_3rd
                    fourth_place = loser_3rd
                    logger.info(f"Определены места 3-4: {winner_3rd} (3 место), {loser_3rd} (4 место)")
                
                # Матч за 5-6 место
                fifth_place_match = None
                for m in matches:
                    if m.get('is_consolation') and m.get('consolation_place') == '5-6':
                        fifth_place_match = m
                        break
                if fifth_place_match and fifth_place_match.get('status') == 'completed':
                    winner_5th = str(fifth_place_match.get('winner_id'))
                    p1 = str(fifth_place_match.get('player1_id'))
                    p2 = str(fifth_place_match.get('player2_id'))
                    loser_5th = p2 if winner_5th == p1 else p1
                    places[winner_5th] = "5 место"
                    places[loser_5th] = "6 место"
                    logger.info(f"Определены места 5-6: {winner_5th} (5 место), {loser_5th} (6 место)")
                
                # Матч за 7-8 место
                seventh_place_match = None
                for m in matches:
                    if m.get('is_consolation') and m.get('consolation_place') == '7-8':
                        seventh_place_match = m
                        break
                if seventh_place_match and seventh_place_match.get('status') == 'completed':
                    winner_7th = str(seventh_place_match.get('winner_id'))
                    p1 = str(seventh_place_match.get('player1_id'))
                    p2 = str(seventh_place_match.get('player2_id'))
                    loser_7th = p2 if winner_7th == p1 else p1
                    places[winner_7th] = "7 место"
                    places[loser_7th] = "8 место"
                    logger.info(f"Определены места 7-8: {winner_7th} (7 место), {loser_7th} (8 место)")
                
                # Для остальных участников (которым не определили точное место) — используем диапазон по раунду вылета
                first_round_matches = [m for m in main_matches if int(m.get('round', 0)) == 0]
                bracket_size = max(2, len(first_round_matches) * 2)
                
                for uid in participants.keys():
                    suid = str(uid)
                    if suid in places:
                        continue
                    
                    # Найти матч, где игрок проиграл (ищем последний проигрыш в основной сетке)
                    lost_round = None
                    for m in main_matches:
                        if m.get('status') != 'completed':
                            continue
                        p1 = str(m.get('player1_id')) if m.get('player1_id') is not None else None
                        p2 = str(m.get('player2_id')) if m.get('player2_id') is not None else None
                        if p1 != suid and p2 != suid:
                            continue
                        winner = str(m.get('winner_id')) if m.get('winner_id') is not None else None
                        if winner and winner != suid:
                            lost_round = int(m.get('round', 0))
                    
                    if lost_round is None:
                        lost_round = 0
                    
                    # Диапазон мест для проигравших в этом раунде
                    upper = bracket_size // (2 ** max(0, lost_round))
                    lower = upper // 2 + 1
                    if lower > upper:
                        lower = upper
                    places[suid] = f"{lower}-{upper} место"
                
                # Формируем резюме с учетом утешительных матчей
                summary_lines = [
                    f"🥇 Чемпион: {pname(champion)}",
                    f"🥈 Финалист: {pname(runner_up)}",
                ]
                if third_place_winner:
                    summary_lines.append(f"🥉 3 место: {pname(third_place_winner)}")
                if fourth_place:
                    summary_lines.append(f"4️⃣ 4 место: {pname(fourth_place)}")

            # Сохраним изменения в турнире
            tournaments[tournament_id] = t
            await self.storage.save_tournaments(tournaments)

            # Рассылка сообщений участникам
            if not bot:
                logger.warning(f"Bot не передан, уведомления не будут отправлены")
                return
            
            # Загружаем данные пользователей для получения фото
            users = await self.storage.load_users()
            
            # Готовим данные для топ-3 игроков
            top_players_data = []
            if t_type == 'Круговая':
                # Для круговой системы берем первых 3 из order
                for idx in range(min(3, len(order))):
                    uid = order[idx]
                    user_data = users.get(uid, {})
                    top_players_data.append({
                        'user_id': uid,
                        'name': participants.get(uid, {}).get('name', 'Игрок'),
                        'photo_path': user_data.get('photo_path'),
                        'place': idx + 1
                    })
            else:
                # Для олимпийской системы: чемпион, финалист, 3 место
                if champion:
                    user_data = users.get(champion, {})
                    top_players_data.append({
                        'user_id': champion,
                        'name': pname(champion),
                        'photo_path': user_data.get('photo_path'),
                        'place': 1
                    })
                if runner_up:
                    user_data = users.get(runner_up, {})
                    top_players_data.append({
                        'user_id': runner_up,
                        'name': pname(runner_up),
                        'photo_path': user_data.get('photo_path'),
                        'place': 2
                    })
                if third_place_winner:
                    user_data = users.get(third_place_winner, {})
                    top_players_data.append({
                        'user_id': third_place_winner,
                        'name': pname(third_place_winner),
                        'photo_path': user_data.get('photo_path'),
                        'place': 3
                    })
            
            # Создаем коллаж победителей
            collage_bytes = None
            if top_players_data:
                try:
                    collage_bytes = self._create_winners_collage(top_players_data)
                    logger.info(f"Создан коллаж победителей для турнира {tournament_id}")
                except Exception as e:
                    logger.error(f"Ошибка создания коллажа: {e}")
            
            summary = "\n".join([line for line in summary_lines if line])
            success_count = 0
            total_count = len(participants)
            
            for uid in participants.keys():
                user_place = places.get(str(uid), '—')
                user_name = participants.get(uid, {}).get('name', 'Участник')
                
                msg = (
                    f"🏁 <b>Турнир завершён!</b>\n\n"
                    f"🏆 <b>{t.get('name', 'Турнир')}</b>\n"
                    f"📍 {t.get('city', '')} {('(' + t.get('district','') + ')') if t.get('district') else ''}\n\n"
                    f"<b>Итоги турнира:</b>\n"
                    f"{summary}\n\n"
                    f"📣 <b>Ваш результат: {user_place}</b>\n\n"
                    f"🎉 Поздравляем всех участников!"
                )
                try:
                    # Отправляем с коллажем, если удалось его создать
                    if collage_bytes:
                        from aiogram.types import BufferedInputFile
                        photo = BufferedInputFile(collage_bytes, filename=f"winners_{tournament_id}.png")
                        await bot.send_photo(int(uid), photo=photo, caption=msg, parse_mode='HTML')
                    else:
                        await bot.send_message(int(uid), msg, parse_mode='HTML')
                    success_count += 1
                    logger.info(f"✅ Уведомление о завершении турнира отправлено участнику {uid} ({user_name})")
                except Exception as e:
                    logger.error(f"❌ Не удалось отправить сообщение пользователю {uid}: {e}")
            
            logger.info(f"Уведомления о завершении турнира {tournament_id} отправлены {success_count} из {total_count} участников")
        except Exception as e:
            logger.error(f"Ошибка уведомлений о завершении турнира {tournament_id}: {e}")
    
    async def get_tournament_matches(self, tournament_id: str) -> List[Dict[str, Any]]:
        """Получает матчи турнира"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        return tournament_data.get('matches', [])
    
    async def get_current_round_matches(self, tournament_id: str) -> List[Dict[str, Any]]:
        """Получает матчи текущего раунда"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        current_round = tournament_data.get('current_round', 0)
        matches = tournament_data.get('matches', [])
        
        return [match for match in matches if match['round'] == current_round]
    
    async def get_available_opponents(self, tournament_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Получает доступных соперников для пользователя в турнире"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        matches = tournament_data.get('matches', [])
        participants = tournament_data.get('participants', {})
        
        print(f"DEBUG: tournament_id={tournament_id}, user_id={user_id}")
        print(f"DEBUG: tournament_type={tournament_type}")
        print(f"DEBUG: matches count={len(matches)}")
        
        available_opponents = []
        
        if not matches:
            # Турнир ещё не стартовал или жеребьевка не проведена — разрешаем выбрать любого участника, кроме себя
            for pid, pdata in participants.items():
                if pid == user_id:
                    continue
                available_opponents.append({
                    'user_id': pid,
                    'name': pdata.get('name', 'Неизвестно'),
                    'match_id': None,
                    'match_number': 0
                })
            return available_opponents

        if tournament_type == "Олимпийская система":
            # В олимпийской системе ищем матч с этим пользователем
            for match in matches:
                print(f"DEBUG: match={match}")
                if match['status'] == 'pending' and not match.get('is_bye', False):
                    if match['player1_id'] == user_id:
                        # Пользователь играет против player2
                        opponent_data = {
                            'user_id': match['player2_id'],
                            'name': match['player2_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent1: {opponent_data}")
                    elif match['player2_id'] == user_id:
                        # Пользователь играет против player1
                        opponent_data = {
                            'user_id': match['player1_id'],
                            'name': match['player1_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent2: {opponent_data}")
                        
        elif tournament_type == "Круговая":
            # В круговой системе ищем все незавершенные матчи с этим пользователем
            for match in matches:
                print(f"DEBUG: match={match}")
                if match['status'] == 'pending' and not match.get('is_bye', False):
                    if match['player1_id'] == user_id:
                        opponent_data = {
                            'user_id': match['player2_id'],
                            'name': match['player2_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        if opponent_data['user_id'] and str(opponent_data['user_id']) != str(user_id):
                            available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent1: {opponent_data}")
                    elif match['player2_id'] == user_id:
                        opponent_data = {
                            'user_id': match['player1_id'],
                            'name': match['player1_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        if opponent_data['user_id'] and str(opponent_data['user_id']) != str(user_id):
                            available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent2: {opponent_data}")
        
        print(f"DEBUG: available_opponents={available_opponents}")
        return available_opponents
    
    async def update_match_result(self, match_id: str, winner_id: str, score: str, bot: Bot | None = None) -> bool:
        """Обновляет результат матча"""
        try:
            tournaments = await self.storage.load_tournaments()
            
            # Находим турнир и матч
            for tournament_id, tournament_data in tournaments.items():
                matches = tournament_data.get('matches', [])
                for match in matches:
                    if match['id'] == match_id:
                        match['winner_id'] = winner_id
                        match['score'] = score
                        match['status'] = 'completed'
                        match['completed_at'] = datetime.now().isoformat()
                        
                        # Сохраняем изменения
                        tournaments[tournament_id] = tournament_data
                        await self.storage.save_tournaments(tournaments)
                        
                        logger.info(f"Результат матча {match_id} обновлен: {winner_id} победил со счетом {score}")

                        # Пересобираем сетку следующих раундов и продвигаем стадию при необходимости
                        await self._rebuild_next_round(tournament_id)
                        await self.advance_tournament_round(tournament_id)
                        # Уведомим участников о назначенных матчах
                        if bot:
                            await self._notify_pending_matches(tournament_id, bot)
                            # Если турнир завершён — уведомим об итогах и местах
                            await self._notify_completion_with_places(tournament_id, bot)
                        return True
            
            logger.error(f"Матч {match_id} не найден")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка обновления результата матча {match_id}: {e}")
            return False

    async def _rebuild_next_round(self, tournament_id: str) -> None:
        """Автозакрывает BYE-матчи и создаёт матчи следующего раунда из победителей и проигравших (утешительные матчи)."""
        try:
            tournaments = await self.storage.load_tournaments()
            t = tournaments.get(tournament_id, {})
            if not t:
                return
            
            tournament_type = t.get('type', 'Олимпийская система')
            # Для круговой системы не нужны дополнительные матчи
            if tournament_type != 'Олимпийская система':
                return
            
            participants = t.get('participants', {}) or {}
            matches = t.get('matches', []) or []

            # Утилиты
            def player_name(uid: str) -> str:
                try:
                    return participants.get(uid, {}).get('name', 'Игрок')
                except Exception:
                    return 'Игрок'

            # 1) Автозавершаем BYE-матчи
            changed = False
            for m in matches:
                if m.get('is_bye') and m.get('status') == 'pending':
                    p1 = m.get('player1_id')
                    p2 = m.get('player2_id')
                    win = p1 or p2
                    m['winner_id'] = win
                    m['status'] = 'completed'
                    m['score'] = m.get('score') or 'BYE'
                    m['completed_at'] = datetime.now().isoformat()
                    changed = True

            if changed:
                t['matches'] = matches
                tournaments[tournament_id] = t
                await self.storage.save_tournaments(tournaments)

            # 2) Создаём матчи следующего раунда на основе победителей текущего
            # Группируем матчи по раундам и типам (основные vs утешительные)
            main_rounds: Dict[int, List[dict]] = {}  # Основная сетка (победители)
            consolation_rounds: Dict[int, List[dict]] = {}  # Утешительные матчи
            
            for m in matches:
                r = int(m.get('round', 0))
                is_consolation = m.get('is_consolation', False)
                if is_consolation:
                    consolation_rounds.setdefault(r, []).append(m)
                else:
                    main_rounds.setdefault(r, []).append(m)
            
            if not main_rounds:
                return

            max_main_round = max(main_rounds.keys())
            
            # 2a) Создаём матчи основной сетки (победители)
            for r in range(0, max_main_round + 1):
                cur = sorted(main_rounds.get(r, []), key=lambda x: int(x.get('match_number', 0)))
                # Собираем победителей текущего раунда
                winners: List[str] = []
                losers: List[str] = []  # Проигравшие для утешительных матчей
                
                for m in cur:
                    if m.get('status') == 'completed':
                        winner = m.get('winner_id')
                        p1 = m.get('player1_id')
                        p2 = m.get('player2_id')
                        if winner:
                            winners.append(winner)
                            # Определяем проигравшего
                            loser = p2 if str(winner) == str(p1) else p1
                            if loser and not m.get('is_bye', False):
                                losers.append(loser)
                    else:
                        winners.append(None)
                
                # Если недостаточно победителей — не создаём следующий раунд
                if len(winners) < 2:
                    continue
                    
                next_r = r + 1
                next_list = main_rounds.get(next_r, [])
                
                # Строим пары победителей 0-1, 2-3, ...
                for i in range(0, len(winners), 2):
                    w1 = winners[i]
                    w2 = winners[i + 1] if i + 1 < len(winners) else None
                    if not w1 or not w2:
                        continue
                    target_match_number = i // 2
                    # Ищем существующий матч следующего раунда
                    existing = None
                    for m in next_list or []:
                        if int(m.get('match_number', -1)) == target_match_number:
                            existing = m
                            break
                    if existing is None:
                        # Создаём новый матч
                        new_match = {
                            'id': f"{tournament_id}_round_{next_r}_match_{target_match_number}",
                            'tournament_id': tournament_id,
                            'round': next_r,
                            'match_number': target_match_number,
                            'player1_id': w1,
                            'player2_id': w2,
                            'player1_name': player_name(w1),
                            'player2_name': player_name(w2),
                            'winner_id': None,
                            'score': None,
                            'status': 'pending',
                            'is_bye': False,
                            'is_consolation': False,
                            'created_at': datetime.now().isoformat()
                        }
                        matches.append(new_match)
                        main_rounds.setdefault(next_r, []).append(new_match)
                        changed = True
                    else:
                        # Дозаполняем игроков, если нужно
                        if not existing.get('player1_id'):
                            existing['player1_id'] = w1
                            existing['player1_name'] = player_name(w1)
                            changed = True
                        if not existing.get('player2_id'):
                            existing['player2_id'] = w2
                            existing['player2_name'] = player_name(w2)
                            changed = True
                
                # 2b) Создаём утешительные матчи для проигравших
                # Матч за 3-4 место: если это полуфинал (2 матча) и оба завершены
                if len(cur) == 2 and len(losers) == 2 and all(m.get('status') == 'completed' for m in cur):
                    # Проверяем, не создан ли уже матч за 3-4 место
                    consolation_id = f"{tournament_id}_consolation_3rd_place"
                    if not any(m.get('id') == consolation_id for m in matches):
                        consolation_match = {
                            'id': consolation_id,
                            'tournament_id': tournament_id,
                            'round': next_r,  # Тот же раунд, что и финал
                            'match_number': 1000,  # Большой номер, чтобы не пересекаться
                            'player1_id': losers[0],
                            'player2_id': losers[1],
                            'player1_name': player_name(losers[0]),
                            'player2_name': player_name(losers[1]),
                            'winner_id': None,
                            'score': None,
                            'status': 'pending',
                            'is_bye': False,
                            'is_consolation': True,
                            'consolation_place': '3-4',
                            'created_at': datetime.now().isoformat()
                        }
                        matches.append(consolation_match)
                        changed = True
                        logger.info(f"Создан матч за 3-4 место: {losers[0]} vs {losers[1]}")
                
                # Матчи за 5-8 место: если это четвертьфинал (4 матча) и все завершены
                elif len(cur) == 4 and len(losers) == 4 and all(m.get('status') == 'completed' for m in cur):
                    # Создаём 2 полуфинала за 5-8 место
                    for i in range(0, 4, 2):
                        consolation_id = f"{tournament_id}_consolation_5-8_semi_{i//2}"
                        if not any(m.get('id') == consolation_id for m in matches):
                            consolation_match = {
                                'id': consolation_id,
                                'tournament_id': tournament_id,
                                'round': r,  # Тот же раунд
                                'match_number': 2000 + i // 2,
                                'player1_id': losers[i],
                                'player2_id': losers[i + 1],
                                'player1_name': player_name(losers[i]),
                                'player2_name': player_name(losers[i + 1]),
                                'winner_id': None,
                                'score': None,
                                'status': 'pending',
                                'is_bye': False,
                                'is_consolation': True,
                                'consolation_place': '5-8',
                                'created_at': datetime.now().isoformat()
                            }
                            matches.append(consolation_match)
                            consolation_rounds.setdefault(r, []).append(consolation_match)
                            changed = True
                            logger.info(f"Создан полуфинал за 5-8 место: {losers[i]} vs {losers[i+1]}")
            
            # 2c) Создаём финалы утешительных матчей (например, финал за 5-6 место из победителей полуфиналов 5-8)
            for r in sorted(consolation_rounds.keys()):
                cons_matches = [m for m in consolation_rounds[r] if m.get('consolation_place') == '5-8']
                if len(cons_matches) == 2 and all(m.get('status') == 'completed' for m in cons_matches):
                    # Собираем победителей и проигравших
                    cons_winners = []
                    cons_losers = []
                    for m in cons_matches:
                        winner = m.get('winner_id')
                        p1 = m.get('player1_id')
                        p2 = m.get('player2_id')
                        if winner:
                            cons_winners.append(winner)
                            loser = p2 if str(winner) == str(p1) else p1
                            if loser:
                                cons_losers.append(loser)
                    
                    # Финал за 5-6 место
                    if len(cons_winners) == 2:
                        final_5_6_id = f"{tournament_id}_consolation_5-6_final"
                        if not any(m.get('id') == final_5_6_id for m in matches):
                            final_match = {
                                'id': final_5_6_id,
                                'tournament_id': tournament_id,
                                'round': r + 1,
                                'match_number': 3000,
                                'player1_id': cons_winners[0],
                                'player2_id': cons_winners[1],
                                'player1_name': player_name(cons_winners[0]),
                                'player2_name': player_name(cons_winners[1]),
                                'winner_id': None,
                                'score': None,
                                'status': 'pending',
                                'is_bye': False,
                                'is_consolation': True,
                                'consolation_place': '5-6',
                                'created_at': datetime.now().isoformat()
                            }
                            matches.append(final_match)
                            changed = True
                            logger.info(f"Создан финал за 5-6 место: {cons_winners[0]} vs {cons_winners[1]}")
                    
                    # Матч за 7-8 место
                    if len(cons_losers) == 2:
                        match_7_8_id = f"{tournament_id}_consolation_7-8_final"
                        if not any(m.get('id') == match_7_8_id for m in matches):
                            match_7_8 = {
                                'id': match_7_8_id,
                                'tournament_id': tournament_id,
                                'round': r + 1,
                                'match_number': 3001,
                                'player1_id': cons_losers[0],
                                'player2_id': cons_losers[1],
                                'player1_name': player_name(cons_losers[0]),
                                'player2_name': player_name(cons_losers[1]),
                                'winner_id': None,
                                'score': None,
                                'status': 'pending',
                                'is_bye': False,
                                'is_consolation': True,
                                'consolation_place': '7-8',
                                'created_at': datetime.now().isoformat()
                            }
                            matches.append(match_7_8)
                            changed = True
                            logger.info(f"Создан матч за 7-8 место: {cons_losers[0]} vs {cons_losers[1]}")

            if changed:
                t['matches'] = matches
                tournaments[tournament_id] = t
                await self.storage.save_tournaments(tournaments)
                logger.info(f"Обновлена сетка турнира {tournament_id}. Всего матчей: {len(matches)}")
        except Exception as e:
            logger.error(f"Ошибка пересборки следующего раунда турнира {tournament_id}: {e}")
    
    async def advance_tournament_round(self, tournament_id: str) -> bool:
        """Переводит турнир на следующий раунд"""
        try:
            tournaments = await self.storage.load_tournaments()
            tournament_data = tournaments.get(tournament_id, {})
            
            if not tournament_data:
                return False
            
            current_round = tournament_data.get('current_round', 0)
            matches = tournament_data.get('matches', [])
            
            # Проверяем, завершены ли все матчи текущего раунда
            current_round_matches = [match for match in matches if match['round'] == current_round]
            completed_matches = [match for match in current_round_matches if match['status'] == 'completed']
            
            if len(completed_matches) == len(current_round_matches):
                # Переходим к следующему раунду
                tournament_data['current_round'] = current_round + 1
                tournaments[tournament_id] = tournament_data
                await self.storage.save_tournaments(tournaments)
                
                logger.info(f"Турнир {tournament_id} переведен на раунд {current_round + 1}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка перевода турнира {tournament_id} на следующий раунд: {e}")
            return False
    
    async def get_tournament_standings(self, tournament_id: str) -> Dict[str, Any]:
        """Получает таблицу результатов турнира"""
        tournaments = await self.storage.load_tournaments()
        tournament_data = tournaments.get(tournament_id, {})
        participants = tournament_data.get('participants', {})
        matches = tournament_data.get('matches', [])
        
        standings = {}
        
        # Инициализируем статистику для каждого участника
        for user_id in participants.keys():
            standings[user_id] = {
                'name': participants[user_id].get('name', 'Неизвестно'),
                'matches_played': 0,
                'matches_won': 0,
                'matches_lost': 0,
                'points': 0
            }
        
        # Подсчитываем результаты
        for match in matches:
            if match['status'] == 'completed' and not match['is_bye']:
                player1_id = match['player1_id']
                player2_id = match['player2_id']
                winner_id = match['winner_id']
                
                if player1_id in standings:
                    standings[player1_id]['matches_played'] += 1
                    if winner_id == player1_id:
                        standings[player1_id]['matches_won'] += 1
                        standings[player1_id]['points'] += 1
                    else:
                        standings[player1_id]['matches_lost'] += 1
                
                if player2_id in standings:
                    standings[player2_id]['matches_played'] += 1
                    if winner_id == player2_id:
                        standings[player2_id]['matches_won'] += 1
                        standings[player2_id]['points'] += 1
                    else:
                        standings[player2_id]['matches_lost'] += 1
        
        return standings


# Глобальный экземпляр менеджера турниров
tournament_manager = TournamentManager()
