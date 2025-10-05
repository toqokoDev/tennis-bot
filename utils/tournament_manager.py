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

logger = logging.getLogger(__name__)


class TournamentManager:
    """Класс для управления турнирами"""
    
    def __init__(self):
        self.storage = storage
    
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
        import random

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

    async def _notify_pending_matches(self, tournament_id: str) -> None:
        """Отправляет уведомления о назначенных матчах, если оба игрока известны и уведомление ещё не отправлено."""
        try:
            tournaments = await self.storage.load_tournaments()
            t = tournaments.get(tournament_id, {})
            matches = t.get('matches', []) or []
            if not matches:
                return
            from utils.tournament_notifications import TournamentNotifications
            try:
                from main import bot
            except Exception:
                bot = None
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

    async def _notify_completion_with_places(self, tournament_id: str) -> None:
        """Если турнир завершён, отправляет участникам сообщения об итоговых местах."""
        try:
            tournaments = await self.storage.load_tournaments()
            t = tournaments.get(tournament_id, {})
            if not t:
                return
            participants = t.get('participants', {}) or {}
            matches = t.get('matches', []) or []
            if not participants:
                return
            # Проверяем завершение: все матчи завершены или BYE
            pending = [m for m in matches if m.get('status') != 'completed' and not m.get('is_bye', False)]
            if pending:
                return
            # Обновим статус турнира
            t['status'] = 'finished'
            t['finished_at'] = datetime.now().isoformat()

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
                # Олимпийская система: чемпион/финалист и диапазоны для остальных по раунду вылета
                if not matches:
                    return
                max_round = max(int(m.get('round', 0)) for m in matches)
                final_match = None
                for m in matches:
                    if int(m.get('round', 0)) == max_round:
                        final_match = m
                        break
                champion = str(final_match.get('winner_id')) if final_match else None
                runner_up = None
                if final_match and champion:
                    a = str(final_match.get('player1_id'))
                    b = str(final_match.get('player2_id'))
                    runner_up = a if b == champion else b
                # Функции имён
                def pname(uid: str | None) -> str:
                    if not uid:
                        return "—"
                    return participants.get(uid, {}).get('name', uid)
                # Расставим места
                if champion:
                    places[champion] = "1 место"
                if runner_up:
                    places[runner_up] = "2 место"
                # Для остальных по раунду вылета
                # Вычислим размер сетки как число участников первого раунда
                first_round_matches = [m for m in matches if int(m.get('round', 0)) == 0]
                bracket_size = max(2, len(first_round_matches) * 2)
                # Индекс раунда, где игрок проиграл
                for uid in participants.keys():
                    suid = str(uid)
                    if suid in places:
                        continue
                    # Найти матч, где игрок проиграл
                    lost_round = None
                    for m in matches:
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
                        # Никогда не проиграл (мог пройти по BYE и вылететь не зафиксировано) — ставим последний известный диапазон
                        lost_round = 0
                    # Диапазон мест для проигравших в этом раунде
                    upper = bracket_size // (2 ** max(0, lost_round))
                    lower = upper // 2 + 1
                    if lower > upper:
                        lower = upper
                    places[suid] = f"{lower}-{upper} место"
                summary_lines = [
                    f"🥇 Чемпион: {pname(champion)}",
                    f"🥈 Финалист: {pname(runner_up)}",
                ]

            # Сохраним изменения в турнире
            tournaments[tournament_id] = t
            await self.storage.save_tournaments(tournaments)

            # Рассылка сообщений участникам
            try:
                from main import bot
            except Exception:
                bot = None
            if not bot:
                return
            summary = "\n".join([line for line in summary_lines if line])
            for uid in participants.keys():
                msg = (
                    f"🏁 Турнир завершён!\n\n"
                    f"🏆 {t.get('name', 'Турнир')}\n"
                    f"📍 {t.get('city', '')} {('(' + t.get('district','') + ')') if t.get('district') else ''}\n\n"
                    f"{summary}\n\n"
                    f"📣 Ваш результат: {places.get(str(uid), '—')}"
                )
                try:
                    await bot.send_message(int(uid), msg)
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение пользователю {uid}: {e}")
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
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent1: {opponent_data}")
                    elif match['player2_id'] == user_id:
                        opponent_data = {
                            'user_id': match['player1_id'],
                            'name': match['player1_name'],
                            'match_id': match['id'],
                            'match_number': match['match_number']
                        }
                        available_opponents.append(opponent_data)
                        print(f"DEBUG: Added opponent2: {opponent_data}")
        
        print(f"DEBUG: available_opponents={available_opponents}")
        return available_opponents
    
    async def update_match_result(self, match_id: str, winner_id: str, score: str) -> bool:
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
                        await self._notify_pending_matches(tournament_id)
                        # Если турнир завершён — уведомим об итогах и местах
                        await self._notify_completion_with_places(tournament_id)
                        return True
            
            logger.error(f"Матч {match_id} не найден")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка обновления результата матча {match_id}: {e}")
            return False

    async def _rebuild_next_round(self, tournament_id: str) -> None:
        """Автозакрывает BYE-матчи и создаёт матчи следующего раунда из победителей."""
        try:
            tournaments = await self.storage.load_tournaments()
            t = tournaments.get(tournament_id, {})
            if not t:
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
            # Группируем матчи по раундам
            rounds: Dict[int, List[dict]] = {}
            for m in matches:
                r = int(m.get('round', 0))
                rounds.setdefault(r, []).append(m)
            if not rounds:
                return

            max_round = max(rounds.keys())
            for r in range(0, max_round + 1):
                cur = sorted(rounds.get(r, []), key=lambda x: int(x.get('match_number', 0)))
                # Собираем победителей текущего раунда
                winners: List[str] = []
                for m in cur:
                    if m.get('status') == 'completed' and m.get('winner_id'):
                        winners.append(m['winner_id'])
                    else:
                        winners.append(None)
                # Если недостаточно победителей — не создаём следующий раунд
                if len(winners) < 2:
                    continue
                next_r = r + 1
                next_list = rounds.get(next_r, [])
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
                            'created_at': datetime.now().isoformat()
                        }
                        matches.append(new_match)
                        rounds.setdefault(next_r, []).append(new_match)
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

            if changed:
                t['matches'] = matches
                tournaments[tournament_id] = t
                await self.storage.save_tournaments(tournaments)
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
