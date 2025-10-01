import io
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from PIL import Image as PILImage
from PIL import Image, ImageDraw, ImageFont

from config.paths import GAMES_PHOTOS_DIR


def _load_fonts():
    # Try system fonts with Unicode support, fallback to DejaVu, then default
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 20)
        header_font = ImageFont.truetype("arialbd.ttf", 14)
        cell_font = ImageFont.truetype("arial.ttf", 12)
        return title_font, header_font, cell_font
    except Exception:
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
            header_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
            cell_font = ImageFont.truetype("DejaVuSans.ttf", 12)
            return title_font, header_font, cell_font
        except Exception:
            f = ImageFont.load_default()
            return f, f, f


def _draw_game_photos_area(draw: ImageDraw.Draw, x: int, y: int, width: int, height: int, cell_font: ImageFont.FreeTypeFont, photo_paths: Optional[list[str]] = None):
    try:
        title = "Фото с игр турнира"
        try:
            bbox = draw.textbbox((0, 0), title, font=cell_font)
            draw.text((x + (width - (bbox[2]-bbox[0])) // 2, y + 6), title, fill=(31, 41, 55), font=cell_font)
        except Exception:
            draw.text((x + 10, y + 6), title, fill=(31, 41, 55), font=cell_font)
        draw.rectangle([x, y + 28, x + width, y + height - 6], fill=(250, 250, 250), outline=(209, 213, 219), width=2)
        if photo_paths:
            try:
                from PIL import Image as PILImage
                thumb_h = height - 50
                thumb_w = thumb_h * 4 // 3
                padding = 10
                visible = photo_paths[:6]
                total_w = len(visible) * thumb_w + (len(visible) - 1) * padding
                start_x = x + (width - total_w) // 2
                cur_x = start_x
                for p in visible:
                    print(f"p: {p}")
                    try:
                        img = PILImage.open(f"{GAMES_PHOTOS_DIR}/{p}")
                        img = img.convert('RGB')
                        img_thumb = img.copy()
                        img_thumb.thumbnail((thumb_w, thumb_h))
                        draw._image.paste(img_thumb, (cur_x, y + 36))
                        cur_x += thumb_w + padding
                    except Exception:
                        pass
                    
            except Exception:
                pass
        else:
            placeholder = "Здесь будут размещены фотографии с турнирных игр"
            try:
                bbox2 = draw.textbbox((0, 0), placeholder, font=cell_font)
                draw.text((x + (width - (bbox2[2]-bbox2[0])) // 2, y + (height // 2)), placeholder, fill=(107, 114, 128), font=cell_font)
            except Exception:
                draw.text((x + 10, y + (height // 2)), placeholder, fill=(107, 114, 128), font=cell_font)
    except Exception:
        pass


def build_round_robin_table(players: List[Dict[str, Any]], results: Optional[List[Dict[str, Any]]] = None, title: str = "Круговой турнир") -> bytes:
    """Строит простую таблицу кругового турнира и возвращает PNG bytes.

    players: список словарей с ключами id, name
    results: опционально список завершенных игр вида {player1_id, player2_id, score, winner_id}
    """
    title_font, header_font, cell_font = _load_fonts()

    n = len(players)
    # Размеры таблицы
    cell_w = 140
    cell_h = 32
    left_col_w = 220
    top_row_h = 40
    padding = 20
    extra_cols = ["Игры", "Победы", "Очки", "Места"]

    width = padding * 2 + left_col_w + n * cell_w + len(extra_cols) * cell_w
    photos_h = 120
    height = padding * 2 + top_row_h + n * cell_h + 80 + photos_h

    image = Image.new('RGB', (max(width, 800), height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Заголовок
    title_text = title
    try:
        bbox = draw.textbbox((0, 0), title_text, font=title_font)
        draw.text(((image.width - (bbox[2] - bbox[0])) // 2, 20), title_text, fill=(31, 41, 55), font=title_font)
    except Exception:
        draw.text((padding, 20), title_text, fill=(31, 41, 55), font=title_font)

    start_y = padding + 40
    start_x = padding

    # Рамка таблицы
    table_x = start_x
    table_y = start_y
    table_w = left_col_w + n * cell_w + len(extra_cols) * cell_w
    table_h = top_row_h + n * cell_h
    draw.rectangle([table_x, table_y, table_x + table_w, table_y + table_h], outline=(209, 213, 219), width=2)
    
    # Используем короткое имя: первая буква имени + фамилия
    def _short_name(p):
        name = p.get('name') or p.get('first_name') or 'Игрок'
        parts = name.strip().split()
        if len(parts) == 0:
            return "Игрок"
        if len(parts) == 1:
            return parts[0]
        first, last = parts[0], parts[-1]
        if first:
            return f"{first[0]}. {last}"
        return last

    # Верхняя строка с именами
    for j, p in enumerate(players):
        x0 = table_x + left_col_w + j * cell_w
        y0 = table_y
        draw.rectangle([x0, y0, x0 + cell_w, y0 + top_row_h], fill=(248, 250, 252), outline=(209, 213, 219))
        short_name = _short_name(p)
        draw.text((x0 + 10, y0 + 12), short_name[:18] + ('…' if len(short_name) > 18 else ''), fill=(31, 41, 55), font=header_font)

    # Заголовки дополнительных колонок
    xh = table_x + left_col_w + n * cell_w
    for col_name in extra_cols:
        draw.rectangle([xh, table_y, xh + cell_w, table_y + top_row_h], fill=(248, 250, 252), outline=(209, 213, 219))
        draw.text((xh + 10, table_y + 12), col_name, fill=(31, 41, 55), font=header_font)
        xh += cell_w

    # Левая колонка с именами
    for i, p in enumerate(players):
        x0 = table_x
        y0 = table_y + top_row_h + i * cell_h
        draw.rectangle([x0, y0, x0 + left_col_w, y0 + cell_h], fill=(248, 250, 252), outline=(209, 213, 219))
        short_name = _short_name(p)
        draw.text((x0 + 10, y0 + 8), short_name[:26] + ('…' if len(short_name) > 26 else ''), fill=(31, 41, 55), font=cell_font)

    # Диагональ «—» и пустые клетки
    # Результаты: создадим словарь для быстрого поиска, поддерживая разные форматы
    def _parse_ids(r: Dict[str, Any]) -> Optional[tuple]:
        p1 = r.get('player1_id')
        p2 = r.get('player2_id')
        if p1 is not None and p2 is not None:
            return str(p1), str(p2)
        gp = r.get('players')
        if isinstance(gp, dict):
            t1 = gp.get('team1') or []
            t2 = gp.get('team2') or []
            def norm(x):
                if isinstance(x, dict):
                    return str(x.get('id'))
                return str(x)
            if t1 and t2:
                return norm(t1[0]), norm(t2[0])
        elif isinstance(gp, list) and len(gp) >= 2:
            a, b = gp[0], gp[1]
            def norm2(x):
                if isinstance(x, dict):
                    return str(x.get('id'))
                return str(x)
            return norm2(a), norm2(b)
        return None

    def _parse_sets(r: Dict[str, Any]) -> List[tuple]:
        sets = []
        if r.get('sets'):
            for s in r['sets']:
                try:
                    a, b = s.split(':')
                    sets.append((int(a), int(b)))
                except Exception:
                    pass
        else:
            score = r.get('score')
            if score:
                parts = [x.strip() for x in str(score).split(',') if ':' in x]
                for s in parts:
                    try:
                        a, b = s.split(':')
                        sets.append((int(a), int(b)))
                    except Exception:
                        pass
        return sets

    photo_paths = []
    res_map: Dict[tuple, Dict[str, Any]] = {}
    for r in results or []:
        ids = _parse_ids(r)
        if not ids:
            continue
        a, b = ids
        sets = _parse_sets(r)
        a_sets = sum(1 for x, y in sets if x > y)
        b_sets = sum(1 for x, y in sets if y > x)
        res_map[tuple(sorted([a, b]))] = {
            'score': r.get('score') or ', '.join([f"{x}:{y}" for x, y in sets]),
            'a': a,
            'b': b,
            'a_sets': a_sets,
            'b_sets': b_sets,
        }
        photo_paths.append(r.get('media_filename'))

    # Подсчет статистики 3/1/0 и тай-брейк по разнице сетов между равными по очкам
    ids = [str(p.get('id')) for p in players]
    games_played = {pid: 0 for pid in ids}
    wins = {pid: 0 for pid in ids}
    points = {pid: 0 for pid in ids}
    tie_sd = {pid: 0 for pid in ids}

    for i in range(n):
        for j in range(i + 1, n):
            pa = str(players[i].get('id'))
            pb = str(players[j].get('id'))
            rec = res_map.get(tuple(sorted([pa, pb])))
            if not rec:
                continue
            games_played[pa] += 1
            games_played[pb] += 1
            if rec['a'] == pa:
                a_sets, b_sets = rec['a_sets'], rec['b_sets']
            else:
                a_sets, b_sets = rec['b_sets'], rec['a_sets']
            if a_sets > b_sets:
                wins[pa] += 1
                points[pa] += 3
            elif b_sets > a_sets:
                wins[pb] += 1
                points[pb] += 3
            else:
                points[pa] += 1
                points[pb] += 1

    from collections import defaultdict
    pts_groups = defaultdict(list)
    for pid in ids:
        pts_groups[points[pid]].append(pid)
    for pts, group in pts_groups.items():
        if len(group) <= 1:
            continue
        for pid in group:
            sd = 0
            for opp in group:
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

    for i in range(n):
        for j in range(n):
            x0 = table_x + left_col_w + j * cell_w
            y0 = table_y + top_row_h + i * cell_h
            draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=(209, 213, 219))
            if i == j:
                draw.text((x0 + cell_w // 2 - 4, y0 + 8), "—", fill=(107, 114, 128), font=cell_font)
            elif j > i:
                p1 = players[i]
                p2 = players[j]
                key = tuple(sorted([str(p1.get('id')), str(p2.get('id'))]))
                rec = res_map.get(key)
                if rec:
                    score = rec.get('score', '')
                    # черный цвет для счета
                    draw.text((x0 + 8, y0 + 8), score, fill=(31, 41, 55), font=cell_font)
                else:
                    draw.text((x0 + 8, y0 + 8), "", fill=(31, 41, 55), font=cell_font)
            else:
                # Нижняя половина: дублируем счет, чтобы был виден у обоих игроков
                p1 = players[j]
                p2 = players[i]
                key = tuple(sorted([str(p1.get('id')), str(p2.get('id'))]))
                rec = res_map.get(key)
                if rec:
                    score = rec.get('score', '')
                    draw.text((x0 + 8, y0 + 8), score, fill=(31, 41, 55), font=cell_font)
                else:
                    draw.text((x0 + 8, y0 + 8), "", fill=(31, 41, 55), font=cell_font)

    # Правые суммарные колонки: Игры, Победы, Очки, Места
    for i, p in enumerate(players):
        pid = str(p.get('id'))
        col_x = table_x + left_col_w + n * cell_w
        y0 = table_y + top_row_h + i * cell_h
        # Игры
        draw.rectangle([col_x, y0, col_x + cell_w, y0 + cell_h], outline=(209, 213, 219))
        draw.text((col_x + cell_w // 2 - 4, y0 + 8), str(games_played.get(pid, 0)), fill=(31, 41, 55), font=cell_font)
        col_x += cell_w
        # Победы
        draw.rectangle([col_x, y0, col_x + cell_w, y0 + cell_h], outline=(209, 213, 219))
        draw.text((col_x + cell_w // 2 - 4, y0 + 8), str(wins.get(pid, 0)), fill=(34, 197, 94), font=cell_font)
        col_x += cell_w
        # Очки
        draw.rectangle([col_x, y0, col_x + cell_w, y0 + cell_h], outline=(209, 213, 219))
        draw.text((col_x + cell_w // 2 - 4, y0 + 8), str(points.get(pid, 0)), fill=(31, 41, 55), font=cell_font)
        col_x += cell_w
        # Места — вычислим сортировку по points, затем tie_sd
        # Место рисуем после сортировки списка players по этим критериям
        # Здесь временно заполним, а ниже отрисуем корректные места поверх
        draw.rectangle([col_x, y0, col_x + cell_w, y0 + cell_h], outline=(209, 213, 219))
        col_x += cell_w

    # Пересортируем для определения мест
    order = sorted(range(n), key=lambda idx: (points.get(str(players[idx].get('id')), 0), tie_sd.get(str(players[idx].get('id')), 0)), reverse=True)
    place_of: Dict[str, int] = {}
    for rank, idx in enumerate(order, start=1):
        place_of[str(players[idx].get('id'))] = rank
    # Нарисуем места
    for i, p in enumerate(players):
        pid = str(p.get('id'))
        col_x = table_x + left_col_w + n * cell_w + 3 * cell_w
        y0 = table_y + top_row_h + i * cell_h
        draw.text((col_x + cell_w // 2 - 4, y0 + 8), str(place_of.get(pid, i + 1)), fill=(34, 197, 94), font=cell_font)

    # Примечание по тай-брейку
    note = "* При равенстве очков места определяются по разнице сетов в очных матчах."
    try:
        draw.text((padding, table_y + table_h + 10), note, fill=(107, 114, 128), font=cell_font)
    except Exception:
        pass

    # Фото игр внизу
    photos_y = table_y + table_h + 40
    _draw_game_photos_area(draw, padding, photos_y, image.width - 2 * padding, photos_h, cell_font, photo_paths)

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()
