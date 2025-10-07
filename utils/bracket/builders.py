import io
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont

from config.paths import GAMES_PHOTOS_DIR
from .models import Player, Match, TournamentBracket
from .renderer import BracketImageGenerator


def create_tournament_from_data() -> TournamentBracket:
    """Создает турнирную сетку на основе данных из примера"""
    # Создаем игроков
    players = [
        Player("1", "Шкирдов Виталий"),
        Player("2", "Максим Кочкин"),
        Player("3", "Александр Нефедов"),
        Player("4", "Шкирдов Сергей"),
        Player("5", "Дмитрий"),
        Player("6", "Сергей Шуваев"),
        Player("7", "Артем Логвинов"),
        Player("8", "Дмитрий Мельников")
    ]
    
    # Основная сетка - 1-ый круг
    round1_matches = [
        Match(players[0], players[1], players[1], "2-6, 1-6"),
        Match(players[2], players[3], players[3], "1-0"),
        Match(players[4], players[5], players[5], "1-7-4"),
        Match(players[6], players[7], players[6], "6-6")
    ]
    
    # Полуфинал
    round2_matches = [
        Match(players[1], players[3], players[1], "6-6"),
        Match(players[5], players[6], players[6], "6-5-6")
    ]
    
    # Финал
    round3_matches = [
        Match(players[1], players[6], players[1], "6-6")
    ]
    
    # Турнир за 3-4 места (проигравшие в полуфинале)
    tournament_3_4 = TournamentBracket(
        players=[players[3], players[5]],
        matches=[],
        rounds=[[Match(players[3], players[5], players[3], "6-6")]],
        name="Игра за 3-е место"
    )
    
    # Турнир за 5-8 места (проигравшие в первом круге)
    tournament_5_8 = TournamentBracket(
        players=[players[0], players[2], players[4], players[7]],
        matches=[],
        rounds=[
            [
                Match(players[0], players[2], players[0], "6-1"),
                Match(players[4], players[7], players[4], "6-0")
            ],
            [
                Match(players[0], players[4], players[0], "6-3")
            ]
        ],
        name="За 5-8 места"
    )
    
    main_bracket = TournamentBracket(
        players=players,
        matches=round1_matches + round2_matches + round3_matches,
        rounds=[round1_matches, round2_matches, round3_matches],
        additional_tournaments=[tournament_3_4, tournament_5_8],
        name="Турнир уровни 3.5-4.5 №16",
        tournament_type="Олимпийская система"
    )
    
    return main_bracket


def create_bracket_image(bracket: TournamentBracket) -> Image.Image:
    """Создает изображение турнирной сетки"""
    generator = BracketImageGenerator()
    return generator.generate_olympic_bracket_image(bracket)


def save_bracket_image(bracket: TournamentBracket, filepath: str) -> bool:
    """Сохраняет изображение турнирной сетки в файл"""
    try:
        image = create_bracket_image(bracket)
        image.save(filepath, 'PNG', quality=95)
        return True
    except Exception as e:
        print(f"Ошибка сохранения изображения: {e}")
        return False


def _normalize_players(players_input: List[Any]) -> List[Player]:
    """Преобразует входные объекты игроков к локальному датаклассу Player."""
    normalized: List[Player] = []
    for p in players_input:
        # поддерживаем объекты с атрибутами и словари
        try:
            pid = getattr(p, 'id', None) or p.get('id')
            name = getattr(p, 'name', None) or p.get('name')
            photo_url = getattr(p, 'photo_url', None) or p.get('photo_url')
            initial = getattr(p, 'initial', None) or p.get('initial')
        except AttributeError:
            pid = getattr(p, 'id', None)
            name = getattr(p, 'name', None)
            photo_url = getattr(p, 'photo_url', None)
            initial = getattr(p, 'initial', None)
        normalized.append(Player(id=str(pid), name=str(name or 'Игрок'), photo_url=photo_url, initial=initial))
    return normalized


def _build_olympic_rounds_from_players(players: List[Player]) -> TournamentBracket:
    """Строит структуру раундов для олимпийской сетки из упорядоченного списка игроков."""
    try:
        num_players = len(players)
        if num_players < 2:
            return TournamentBracket(players=players, matches=[], rounds=[[]], name="Турнир", tournament_type="Олимпийская система")

        # Доводим до степени двойки, заполняя пустыми слотами
        bracket_size = 1
        while bracket_size < num_players:
            bracket_size *= 2

        padded_players: List[Optional[Player]] = players[:]
        while len(padded_players) < bracket_size:
            padded_players.append(Player(id=f"empty_{len(padded_players)}", name="Свободное место"))

        # Раунды
        rounds: List[List[Match]] = []
        current_round: List[Match] = []

        # Первый раунд из упорядоченного списка
        for i in range(0, bracket_size, 2):
            p1 = padded_players[i]
            p2 = padded_players[i + 1] if i + 1 < len(padded_players) else None
            current_round.append(Match(player1=p1, player2=p2, match_number=(i // 2)))
        rounds.append(current_round)

        # Остальные раунды (пустые участники TBD)
        matches_in_round = len(current_round)
        while matches_in_round > 1:
            next_round: List[Match] = []
            for m in range(matches_in_round // 2):
                next_round.append(Match(player1=None, player2=None, match_number=m))
            rounds.append(next_round)
            matches_in_round = len(next_round)

        bracket = TournamentBracket(
            players=players,
            matches=[m for rnd in rounds for m in rnd],
            rounds=rounds,
            name="Турнир",
            tournament_type="Олимпийская система",
        )
        return bracket
    except Exception as e:
        print(f"Ошибка построения структуры олимпийской сетки: {e}")
        return TournamentBracket(players=players, matches=[], rounds=[[]], name="Турнир", tournament_type="Олимпийская система")


def _build_olympic_rounds_from_tournament(
    tournament_data: Dict[str, Any],
    players_fallback: List[Player],
    completed_games: Optional[List[Dict[str, Any]]] = None,
) -> TournamentBracket:
    """Строит структуру раундов из состояния турнира: participants + matches.

    - Если есть matches: используем их для заполнения раундов, победителей и счетов
    - Если матчей нет: возвращаем структуру из игроков
    - Если следующих раундов нет, но есть победители предыдущего, создаем плейсхолдеры с победителями
    """
    try:
        print("[BRACKET][OLY] Начинаю сборку сетки из данных турнира…")
        matches_raw: List[Dict[str, Any]] = tournament_data.get('matches', []) or []
        participants_map: Dict[str, Dict[str, Any]] = tournament_data.get('participants', {}) or {}
        print(f"[BRACKET][OLY] Турнир: '{tournament_data.get('name', 'Турнир')}', участников: {len(participants_map)}, матчей в данных турнира: {len(matches_raw)}")
        # Карта id -> Player
        id_to_player: Dict[str, Player] = {}
        for pid, pdata in participants_map.items():
            name = str(pdata.get('name') or pid)
            # Старайся сохранить фото, если оно есть в данных участника
            p_photo = pdata.get('photo_url') or pdata.get('photo_path')
            id_to_player[str(pid)] = Player(id=str(pid), name=name, photo_url=p_photo)
        # Дополняем из players_fallback отсутствующие поля (например, фото)
        for p in players_fallback:
            if p.id not in id_to_player:
                id_to_player[p.id] = p
            else:
                cur = id_to_player[p.id]
                try:
                    if not getattr(cur, 'photo_url', None) and getattr(p, 'photo_url', None):
                        cur.photo_url = p.photo_url
                except Exception:
                    pass

        # Базовая структура раундов: из matches_raw, иначе — каркас по игрокам
        if not matches_raw:
            print("[BRACKET][OLY] В tournament_data нет матчей — строю каркас по игрокам и наложу результаты из завершённых игр.")
            # КРИТИЧНО: сохраняем исходный порядок игроков (после перемешивания/посева)
            # Используем порядок players_fallback, но обогащаем объектами из id_to_player, если есть
            ordered_players: List[Player] = []
            try:
                for p in players_fallback:
                    cur = id_to_player.get(str(getattr(p, 'id', None) or p.id))
                    ordered_players.append(cur or p)
            except Exception:
                # Фолбэк — хотя бы список из карты
                ordered_players = list(id_to_player.values())
            players_bracket = _build_olympic_rounds_from_players(ordered_players)
            rounds: List[List[Match]] = [list(r) for r in players_bracket.rounds]
            max_round = len(rounds) - 1
        else:
            # Группируем матчи по раундам (ИСКЛЮЧАЯ placement-матчи)
            from collections import defaultdict
            round_to_matches: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
            max_round = 0
            for m in matches_raw:
                # Пропускаем placement-матчи — они обрабатываются отдельно
                if m.get('placement'):
                    continue
                rnd = int(m.get('round', 0))
                round_to_matches[rnd].append(m)
                max_round = max(max_round, rnd)

            # Сортируем внутри раундов по match_number
            for rnd in round_to_matches:
                round_to_matches[rnd] = sorted(round_to_matches[rnd], key=lambda x: int(x.get('match_number', 0)))
            print(f"[BRACKET][OLY] Обнаружено раундов: {max_round + 1}")

            # Создаем структуру раундов
            rounds = []
            for rnd in range(0, max_round + 1):
                current_round_matches = []
                raw_list = round_to_matches.get(rnd, [])
                print(f"[BRACKET][OLY] Раунд {rnd + 1}: матчей {len(raw_list)}")
                for raw in raw_list:
                    p1_id = raw.get('player1_id')
                    p2_id = raw.get('player2_id')
                    p1 = id_to_player.get(str(p1_id)) if p1_id else None
                    p2 = id_to_player.get(str(p2_id)) if p2_id else None
                    score = raw.get('score')
                    winner_id = raw.get('winner_id')
                    winner = id_to_player.get(str(winner_id)) if winner_id else None
                    is_bye = bool(raw.get('is_bye'))
                    mm = Match(player1=p1, player2=p2, winner=winner, score=score, is_bye=is_bye, match_number=int(raw.get('match_number', 0)))
                    current_round_matches.append(mm)
                    print(f"  - [{mm.match_number}] {p1.name if p1 else 'TBD'} vs {p2.name if p2 else 'TBD'} | score={score or '-'} | winner={(winner.name if winner else '-')} | bye={is_bye}")
                if current_round_matches:
                    rounds.append(current_round_matches)

        # Гарантируем наличие полного дерева до финала (даже если в данных не хватает последнего раунда)
        try:
            if rounds:
                matches_in_round = len(rounds[-1])
                while matches_in_round > 1:
                    next_round: List[Match] = []
                    for j in range(matches_in_round // 2):
                        next_round.append(Match(player1=None, player2=None, match_number=j))
                    rounds.append(next_round)
                    print(f"[BRACKET][OLY] Достроен каркас раунда: матчей {len(next_round)}")
                    matches_in_round = len(next_round)
        except Exception as e:
            print(f"[BRACKET][OLY] Ошибка достройки дерева раундов: {e}")

        # Наложим результаты из завершённых игр, если в матчах они отсутствуют
        try:
            if completed_games:
                print(f"[BRACKET][OLY] Завершённых игр передано: {len(completed_games)} — пробую наложить результаты")
                def norm(x):
                    return str(x) if x is not None else None
                results_map: Dict[tuple, Dict[str, Any]] = {}
                for g in completed_games:
                    gp = g.get('players') or {}
                    if not isinstance(gp, dict):
                        continue
                    t1 = gp.get('team1') or []
                    t2 = gp.get('team2') or []
                    if not t1 or not t2:
                        continue
                    a = norm(t1[0])
                    b = norm(t2[0])
                    if not a or not b:
                        continue
                    key = tuple(sorted([a, b]))
                    results_map[key] = {
                        'score': g.get('score'),
                        'winner_id': norm(g.get('winner_id'))
                    }
                # Проставляем score/winner там, где они отсутствуют
                for rnd_matches in rounds:
                    for m in rnd_matches:
                        a = norm(m.player1.id) if m.player1 else None
                        b = norm(m.player2.id) if m.player2 else None
                        if not a or not b:
                            continue
                        res = results_map.get(tuple(sorted([a, b])))
                        if res:
                            if not m.score and res.get('score'):
                                m.score = res.get('score')
                            if not m.winner and res.get('winner_id'):
                                wid = res.get('winner_id')
                                if m.player1 and m.player1.id == wid:
                                    m.winner = m.player1
                                elif m.player2 and m.player2.id == wid:
                                    m.winner = m.player2
                print("[BRACKET][OLY] Наложение результатов завершено")
        except Exception as e:
            print(f"[BRACKET][OLY] Ошибка наложения результатов: {e}")

        # Если следующих раундов нет, но есть победители предыдущего — создадим каркас следующего раунда
        def winners_of_round(rmatches: List[Match]) -> List[Optional[Player]]:
            ws: List[Optional[Player]] = []
            for m in rmatches:
                if m.is_bye and (m.player1 or m.player2):
                    ws.append(m.player1 or m.player2)
                elif m.winner:
                    ws.append(m.winner)
                else:
                    ws.append(None)
            return ws

        # Заполняем участников следующего раунда победителями предыдущего;
        # если следующего раунда нет — создаём каркас
        round_idx = 0
        while round_idx < len(rounds):
            current_round = rounds[round_idx]
            ws = winners_of_round(current_round)
            if len(ws) <= 1:
                break
            next_idx = round_idx + 1
            if next_idx < len(rounds):
                # Дополняем существующие матчи следующего раунда
                next_round = rounds[next_idx]
                for j in range((len(ws) + 1) // 2):
                    p1w = ws[2*j] if 2*j < len(ws) else None
                    p2w = ws[2*j + 1] if 2*j + 1 < len(ws) else None
                    if j < len(next_round):
                        # Всегда синхронизируем, чтобы победители отображались корректно на картинке
                        # Всегда синхронизируем участников, включая фото
                        if p1w and next_round[j].player1 is None:
                            next_round[j].player1 = p1w
                        elif p1w and next_round[j].player1 and not getattr(next_round[j].player1, 'photo_url', None):
                            next_round[j].player1.photo_url = getattr(p1w, 'photo_url', None)
                        if p2w and next_round[j].player2 is None:
                            next_round[j].player2 = p2w
                        elif p2w and next_round[j].player2 and not getattr(next_round[j].player2, 'photo_url', None):
                            next_round[j].player2.photo_url = getattr(p2w, 'photo_url', None)
                    else:
                        next_round.append(Match(player1=p1w, player2=p2w, match_number=j))
                print(f"[BRACKET][OLY] Обновлён следующий раунд {next_idx+1}: матчей {len(next_round)}")
            else:
                # Создаём новый раунд из победителей
                next_round: List[Match] = []
                for i in range(0, len(ws), 2):
                    p1w = ws[i] if i < len(ws) else None
                    p2w = ws[i + 1] if i + 1 < len(ws) else None
                    next_round.append(Match(player1=p1w, player2=p2w, match_number=len(next_round)))
                    rounds.append(next_round)
                    print(f"[BRACKET][OLY] Добавлен каркас следующего раунда: матчей {len(next_round)}")
            round_idx += 1

        # Соберем плоский список матчей
        flat_matches = [m for rnd in rounds for m in rnd]

        # Построим дополнительные мини-турниры за места из placement-матчей
        additional_tournaments: List[TournamentBracket] = []
        try:
            placement_raw = [mr for mr in (tournament_data.get('matches') or []) if mr.get('placement')]
            if placement_raw:
                # Группируем: "5-8" и "5th" объединяем в один ключ "5-6"; остальное отдельно
                def placement_key(val: str) -> str:
                    # Объединяем "5-8" (полуфиналы) и "5th" (финал) в один мини-турнир
                    if val in ('5-8', '5th'):
                        return '5-6'
                    return str(val)
                grouped: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
                for mr in placement_raw:
                    pk = placement_key(mr.get('placement'))
                    rnd = int(mr.get('round', 0))
                    grouped.setdefault(pk, {}).setdefault(rnd, []).append(mr)

                # Сортируем ключи для правильного порядка отображения: 5-6, 3rd, 7th
                sort_order = {'5-6': 0, '3rd': 1, '7th': 2}
                sorted_keys = sorted(grouped.keys(), key=lambda k: sort_order.get(k, 999))
                
                for pk in sorted_keys:
                    per_round = grouped[pk]
                    # Сортируем матчи в каждом раунде
                    for rnd in list(per_round.keys()):
                        try:
                            per_round[rnd] = sorted(per_round[rnd], key=lambda x: int(x.get('match_number', 0)))
                        except Exception:
                            pass
                    try:
                        max_r = max(per_round.keys()) if per_round else -1
                    except Exception:
                        max_r = -1
                    mini_rounds: List[List[Match]] = []
                    for r_index in range(0, max_r + 1):
                        lst = per_round.get(r_index, [])
                        mini_lst: List[Match] = []
                        for raw in lst:
                            try:
                                p1 = id_to_player.get(str(raw.get('player1_id'))) if raw.get('player1_id') else None
                                p2 = id_to_player.get(str(raw.get('player2_id'))) if raw.get('player2_id') else None
                                score = raw.get('score')
                                win = id_to_player.get(str(raw.get('winner_id'))) if raw.get('winner_id') else None
                                mnum = int(raw.get('match_number', 0)) if raw.get('match_number') is not None else 0
                                mini_lst.append(Match(player1=p1, player2=p2, winner=win, score=score, match_number=mnum, is_placement=True))
                            except Exception:
                                continue
                        mini_rounds.append(mini_lst)

                    # Наложим результаты завершённых игр и на мини-турниры
                    try:
                        if completed_games:
                            def norm(x):
                                return str(x) if x is not None else None
                            results_map: Dict[tuple, Dict[str, Any]] = {}
                            for g in completed_games:
                                gp = g.get('players') or {}
                                if not isinstance(gp, dict):
                                    continue
                                t1 = gp.get('team1') or []
                                t2 = gp.get('team2') or []
                                if not t1 or not t2:
                                    continue
                                a = norm(t1[0])
                                b = norm(t2[0])
                                if not a or not b:
                                    continue
                                key = tuple(sorted([a, b]))
                                results_map[key] = {'score': g.get('score'), 'winner_id': norm(g.get('winner_id'))}
                            for rnd_matches in mini_rounds:
                                for m in rnd_matches:
                                    a = norm(m.player1.id) if m.player1 else None
                                    b = norm(m.player2.id) if m.player2 else None
                                    if not a or not b:
                                        continue
                                    res = results_map.get(tuple(sorted([a, b])))
                                    if res:
                                        if not m.score and res.get('score'):
                                            m.score = res.get('score')
                                        if not m.winner and res.get('winner_id'):
                                            wid = res.get('winner_id')
                                            if m.player1 and m.player1.id == wid:
                                                m.winner = m.player1
                                            elif m.player2 and m.player2.id == wid:
                                                m.winner = m.player2
                    except Exception:
                        pass

                    # Название мини-турнира
                    if pk == '3rd':
                        mini_name = 'Игра за 3-4 место'
                    elif pk == '5-6':
                        mini_name = 'За 5-6 места'
                    elif pk == '7th':
                        mini_name = 'Игра за 7-8 место'
                    else:
                        mini_name = f'Доп. матчи: {pk}'

                    additional_tournaments.append(
                        TournamentBracket(
                            players=list(id_to_player.values()),
                            matches=[m for r in mini_rounds for m in r],
                            rounds=mini_rounds,
                            name=mini_name,
                            tournament_type='Олимпийская система'
                        )
                    )
            # Fallback: если placement-матчей нет в данных турнира — строим 3-е и 5–8 места из текущих раундов/результатов
            if not additional_tournaments:
                print("[BRACKET][OLY] placement-матчи не найдены — строю мини-сетки по результатам раундов")
                # Карта результатов из completed_games
                def norm2(x):
                    return str(x) if x is not None else None
                results_map2: Dict[tuple, Dict[str, Any]] = {}
                try:
                    if completed_games:
                        for g in completed_games:
                            gp = g.get('players') or {}
                            if not isinstance(gp, dict):
                                continue
                            t1 = gp.get('team1') or []
                            t2 = gp.get('team2') or []
                            if not t1 or not t2:
                                continue
                            a = norm2(t1[0])
                            b = norm2(t2[0])
                            if not a or not b:
                                continue
                            key = tuple(sorted([a, b]))
                            results_map2[key] = {'score': g.get('score'), 'winner_id': norm2(g.get('winner_id'))}
                except Exception:
                    pass

                # 3-е место из проигравших полуфиналов
                if len(rounds) >= 2 and len(rounds[-2]) >= 2:
                    sf = rounds[-2]
                    losers_sf: List[Player] = []
                    for m in sf:
                        if m.player1 and m.player2 and m.winner:
                            losers_sf.append(m.player2 if m.winner.id == m.player1.id else m.player1)
                    if len(losers_sf) == 2:
                        # Создаем матч за 3-е и накладываем счет из results_map2
                        m3 = Match(player1=losers_sf[0], player2=losers_sf[1], is_placement=True)
                        res = results_map2.get(tuple(sorted([losers_sf[0].id, losers_sf[1].id])))
                        if res:
                            m3.score = res.get('score')
                            wid = res.get('winner_id')
                            if wid == losers_sf[0].id:
                                m3.winner = losers_sf[0]
                            elif wid == losers_sf[1].id:
                                m3.winner = losers_sf[1]
                        additional_tournaments.append(
                            TournamentBracket(
                                players=list(id_to_player.values()),
                                matches=[m3],
                                rounds=[[m3]],
                                name='Игра за 3-е место',
                                tournament_type='Олимпийская система'
                            )
                        )

                # 5–8 места из проигравших четвертьфиналов
                if rounds and len(rounds[0]) >= 4:
                    qf = rounds[0]
                    losers_qf: List[Player] = []
                    for m in qf:
                        if m.player1 and m.player2 and m.winner:
                            losers_qf.append(m.player2 if m.winner.id == m.player1.id else m.player1)
                    if len(losers_qf) >= 2:
                        # Составим мини-сетку по проигравшим
                        mini = _build_olympic_rounds_from_players(losers_qf[:4])
                        # Наложим результаты
                        for rr in mini.rounds:
                            for mm in rr:
                                if mm.player1 and mm.player2:
                                    res = results_map2.get(tuple(sorted([mm.player1.id, mm.player2.id])))
                                    if res:
                                        mm.score = mm.score or res.get('score')
                                        wid = res.get('winner_id')
                                        if wid == (mm.player1.id if mm.player1 else None):
                                            mm.winner = mm.player1
                                        elif wid == (mm.player2.id if mm.player2 else None):
                                            mm.winner = mm.player2
                        mini.name = 'За 5–8 места'
                        additional_tournaments.append(mini)
        except Exception as e:
            print(f"[BRACKET][OLY] Ошибка построения доп. турниров: {e}")

        bracket = TournamentBracket(
            players=list(id_to_player.values()),
            matches=flat_matches,
            rounds=rounds,
            name=tournament_data.get('name', 'Турнир'),
            additional_tournaments=additional_tournaments if additional_tournaments else None,
            tournament_type='Олимпийская система'
        )
        print(f"[BRACKET][OLY] Итог: раундов {len(rounds)}, всего матчей {len(flat_matches)}")
        return bracket
    except Exception as e:
        print(f"Ошибка построения сетки из состояния турнира: {e}")
        return _build_olympic_rounds_from_players(players_fallback)


def create_simple_text_image_bytes(text: str, title: str = "Информация") -> bytes:
    """Создает простое изображение с заголовком и текстом и возвращает его как bytes (PNG)."""
    image = Image.new('RGB', (1000, 500), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    # Загружаем шрифты с учетом Unicode
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 20)
        text_font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
            text_font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except Exception:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()

    # Заголовок
    try:
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        draw.text(((1000 - (title_bbox[2] - title_bbox[0])) // 2, 20), title, fill=(31, 41, 55), font=title_font)
    except Exception:
        try:
            draw.text((20, 20), title, fill=(31, 41, 55), font=title_font)
        except Exception:
            # В крайнем случае удаляем не-ASCII символы
            safe_title = title.encode('ascii', 'ignore').decode('ascii')
            draw.text((20, 20), safe_title, fill=(31, 41, 55), font=title_font)

    # Текст с переносами строк
    y = 70
    for line in str(text or "").splitlines() or [""]:
        try:
            draw.text((30, y), line, fill=(31, 41, 55), font=text_font)
        except Exception:
            safe_line = str(line).encode('ascii', 'ignore').decode('ascii')
            draw.text((30, y), safe_line, fill=(31, 41, 55), font=text_font)
        y += 22

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


def build_tournament_bracket_image_bytes(tournament_data: Dict[str, Any], players_input: List[Any], completed_games: Optional[List[Dict[str, Any]]] = None):
    """Строит изображение турнирной сетки в байтах и текстовое представление.

    - Для типа "Олимпийская система" — рисует сетку BracketImageGenerator
    - Для остальных типов возвращает простое изображение-заглушку (круговая отрисовывается в другом модуле)
    """
    try:
        print(f"[BRACKET] Старт сборки изображения. Тип: {tournament_data.get('type')}, Название: {tournament_data.get('name')} ")
        tournament_type = tournament_data.get('type', 'Олимпийская система')
        name = tournament_data.get('name', 'Турнир')
        players = _normalize_players(players_input)
        print(f"[BRACKET] Игроков на входе: {len(players)} | завершенных игр: {len(completed_games or [])}")

        if tournament_type == 'Олимпийская система':
            # Строим сетку по фактическим матчам, если они есть, чтобы отображались пары, счет и победители
            bracket_struct = _build_olympic_rounds_from_tournament(tournament_data, players, completed_games)
            bracket_struct.name = name
            # Собираем пути до фото игр этого турнира
            photo_paths: list[str] = []
            try:
                if completed_games:
                    for g in completed_games:
                        fn = g.get('media_filename')
                        if fn:
                            photo_paths.append(f"{GAMES_PHOTOS_DIR}/{fn}")
            except Exception:
                pass
            generator = BracketImageGenerator()
            # Пробросим фото профилей в первую отрисовку (у игроков уже photo_url), а в нижний блок передадим фото игр
            image = generator.generate_olympic_bracket_image(bracket_struct, photo_paths)
            print(f"[BRACKET] Сгенерировано изображение олимпийской сетки. Фото прикреплено: {len(photo_paths)}")
            buf = io.BytesIO()
            image.save(buf, format='PNG')
            buf.seek(0)

            # Текстовое краткое описание пар первого круга
            lines = [f"{name}", "", "Первый круг:"]
            if bracket_struct.rounds:
                for m in bracket_struct.rounds[0]:
                    p1 = m.player1.name if m.player1 else 'TBD'
                    p2 = m.player2.name if m.player2 else 'TBD'
                    lines.append(f"- {p1} vs {p2}")
            text = "\n".join(lines)
            print("[BRACKET] Возвращаю байты изображения и краткий текст первого круга.")
            return buf.getvalue(), text
        else:
            # Для круговой таблицы используем отдельный генератор с фото
            from utils.round_robin_image_generator import build_round_robin_table
            table_players = [{"id": getattr(p, 'id', None) or p.get('id'), "name": getattr(p, 'name', None) or p.get('name')} for p in players_input]
            # Собираем фото путей
            photo_paths: list[str] = []
            try:
                if completed_games:
                    for g in completed_games:
                        fn = g.get('media_filename')
                        if fn:
                            photo_paths.append(f"{GAMES_PHOTOS_DIR}/{fn}")
            except Exception:
                pass
            # Генератор round robin сейчас не принимает фото, но мы расширили _draw_game_photos_area, так что передадим позже при интеграции
            # Возвращаем совместимо: старый вызов без фото (фото выводятся placeholders)
            image_bytes = build_round_robin_table(table_players, completed_games, name)
            print("[BRACKET][RR] Возвращаю изображение круговой таблицы.")
            return image_bytes, name
    except Exception as e:
        print(f"Ошибка сборки изображения турнирной сетки: {e}")
        fallback = "Не удалось сгенерировать изображение"
        return create_simple_text_image_bytes(fallback, tournament_data.get('name', 'Турнир')), fallback
