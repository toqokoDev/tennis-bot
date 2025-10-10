import io
import os
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from PIL import Image as PILImage

from config.paths import BASE_DIR


def _load_fonts():
    """Загрузка шрифтов с приоритетом Circe, затем Arial/DejaVu, затем дефолт."""
    def _try_font(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
        return None

    circe_regular = [
        "Circe-Regular.ttf",
        "Circe.ttf",
        os.path.join(BASE_DIR, "fonts", "Circe-Regular.ttf"),
        os.path.join(BASE_DIR, "fonts", "Circe.ttf"),
    ]
    circe_bold = [
        "Circe-Bold.ttf",
        os.path.join(BASE_DIR, "fonts", "Circe-Bold.ttf"),
    ]

    # Пытаемся Circe
    title_font = _try_font(circe_bold, 18)
    subtitle_font = _try_font(circe_regular, 18)
    header_font = _try_font(circe_bold, 18)
    cell_font = _try_font(circe_regular, 24)
    

    # Фолбэк Arial
    if not title_font:
        try:
            title_font = ImageFont.truetype("arialbd.ttf", 18)
        except Exception:
            title_font = None
    if not subtitle_font:
        try:
            subtitle_font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            subtitle_font = None
    if not header_font:
        try:
            header_font = ImageFont.truetype("arialbd.ttf", 18)
        except Exception:
            header_font = None
    if not cell_font:
        try:
            cell_font = ImageFont.truetype("arial.ttf", 24)
        except Exception:
            cell_font = None

    # Фолбэк DejaVu
    if not title_font:
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
        except Exception:
            title_font = None
    if not subtitle_font:
        try:
            subtitle_font = ImageFont.truetype("DejaVuSans.ttf", 18)
        except Exception:
            subtitle_font = None
    if not header_font:
        try:
            header_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
        except Exception:
            header_font = None
    if not cell_font:
        try:
            cell_font = ImageFont.truetype("DejaVuSans.ttf", 24)
        except Exception:
            cell_font = None

    # Последний фолбэк — дефолт
    if not title_font:
        title_font = ImageFont.load_default()
    if not subtitle_font:
        subtitle_font = ImageFont.load_default()
    if not header_font:
        header_font = ImageFont.load_default()
    if not cell_font:
        cell_font = ImageFont.load_default()
    return title_font, subtitle_font, header_font, cell_font


def _sanitize_title(text: str) -> str:
    """Удаляет эмодзи и связанные служебные символы из строки заголовка."""
    try:
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E6-\U0001F1FF"
            "\U00002700-\U000027BF"
            "\U0001F900-\U0001F9FF"
            "\U00002600-\U000026FF"
            "]+",
            flags=re.UNICODE,
        )
        cleaned = emoji_pattern.sub("", str(text or ""))
        cleaned = cleaned.replace("\u200d", "").replace("\ufe0f", "")
        return cleaned
    except Exception:
        return "".join(ch for ch in str(text or "") if ord(ch) <= 0xFFFF)


def build_round_robin_table(players: List[Dict[str, Any]], results: Optional[List[Dict[str, Any]]] = None, title: str = "Круговой турнир") -> bytes:
    """Строит простую таблицу кругового турнира и возвращает PNG bytes.

    players: список словарей с ключами id, name
    results: опционально список завершенных игр вида {player1_id, player2_id, score, winner_id}
    """
    title_font, subtitle_font, header_font, cell_font = _load_fonts()

    n = len(players)
    # Размеры таблицы
    cell_w = 100  # Уменьшено для ячеек счета
    cell_h = 70  # Увеличено для больших шрифтов
    left_col_w = 350  # Увеличено для полных имен
    top_row_h = 70  # Увеличено для больших аватаров
    extra_cell_w = 80  # Размер для колонок с цифрами
    padding = 20
    extra_cols = ["Победы", "Очки", "Места"]  # Убран столбец "Игры"

    width = padding * 2 + left_col_w + n * cell_w + len(extra_cols) * extra_cell_w
    # Уменьшаем дополнительную высоту под описание турнира
    height = padding * 2 + top_row_h + n * cell_h + 260

    image = Image.new('RGB', (max(width, 800), height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Заголовок турнира
    title_text = _sanitize_title(title)
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
    table_w = left_col_w + n * cell_w + len(extra_cols) * extra_cell_w
    table_h = top_row_h + n * cell_h
    draw.rectangle([table_x, table_y, table_x + table_w, table_y + table_h], outline=(209, 213, 219), width=2)
    
    # Инициалы (2 буквы) из имени/фамилии или name
    def _initials(p: Dict[str, Any]) -> str:
        first = (p.get('first_name') or '').strip()
        last = (p.get('last_name') or '').strip()
        if first or last:
            a = first[:1].upper() if first else ''
            b = last[:1].upper() if last else ''
            return (a + b) if (a or b) else '??'
        name = (p.get('name') or '').strip()
        if name:
            parts = name.split()
            if len(parts) >= 2:
                return (parts[0][:1] + parts[1][:1]).upper()
            return (name[:2]).upper() if len(name) >= 2 else (name[:1].upper() or '??')
        return '??'

    # Полное имя игрока
    def _short_name(p: Dict[str, Any]) -> str:
        name = (p.get('name') or '').strip()
        if not name:
            return _initials(p)
        return name

    # Хелпер: вставка аватара в указанные координаты
    def _paste_avatar(px: int, py: int, p: Dict[str, Any], size: int, font: ImageFont.FreeTypeFont) -> bool:
        def paste_placeholder() -> bool:
            try:
                # Светло-серый квадрат (#e5e5e5) с инициалами (если есть)
                img = PILImage.new('RGBA', (size, size), (229, 229, 229, 255))
                try:
                    initials = _initials(p)
                    if initials and initials != '??' and font:
                        d = ImageDraw.Draw(img)
                        bbox = d.textbbox((0, 0), initials, font=font)
                        tw = max(0, bbox[2] - bbox[0])
                        th = max(0, bbox[3] - bbox[1])
                        tx = (size - tw) // 2
                        ty = (size - th) // 2
                        # Текст белым без обводки (как в олимпийской сетке)
                        d.text((tx, ty), initials, fill=(255, 255, 255), font=font)
                except Exception:
                    pass
                draw._image.paste(img, (px, py), img)
                return True
            except Exception:
                return False

        path = p.get('photo_path') or p.get('photo_url')
        if path:
            try:
                abs_path = path if os.path.isabs(path) else f"{BASE_DIR}/{path}"
                if os.path.exists(abs_path):
                    img = PILImage.open(abs_path)
                    img = img.convert('RGBA')
                    w, h = img.size
                    side = min(w, h)
                    left = (w - side) // 2
                    top = (h - side) // 2
                    img = img.crop((left, top, left + side, top + side))
                    try:
                        resample = Image.Resampling.LANCZOS
                    except Exception:
                        resample = Image.LANCZOS
                    img = img.resize((size, size), resample)
                    # Слегка осветлим реальное фото (без инициалов на фото)
                    try:
                        overlay = PILImage.new('RGBA', (size, size), (255, 255, 255, 40))
                        img = PILImage.alpha_composite(img, overlay)
                    except Exception:
                        pass
                    draw._image.paste(img, (px, py), img)
                    return True
            except Exception:
                # Падать не будем — покажем серый квадрат
                return paste_placeholder()
        # Нет пути к фото — рисуем серый квадрат
        return paste_placeholder()

    # Верхний левый угол: подпись "Игроки"
    draw.rectangle([table_x, table_y, table_x + left_col_w, table_y + top_row_h], fill=(248, 250, 252), outline=(209, 213, 219))
    players_label = "Игроки"
    try:
        bbox = draw.textbbox((0, 0), players_label, font=header_font)
        label_width = bbox[2] - bbox[0]
        label_x = table_x + (left_col_w - label_width) // 2
        label_y = table_y + (top_row_h - 24) // 2
        draw.text((label_x, label_y), players_label, fill=(31, 41, 55), font=header_font)
    except Exception:
        draw.text((table_x + 10, table_y + (top_row_h - 24) // 2), players_label, fill=(31, 41, 55), font=header_font)
    
    # Верхняя строка: только аватар (без имени)
    for j, p in enumerate(players):
        x0 = table_x + left_col_w + j * cell_w
        y0 = table_y
        draw.rectangle([x0, y0, x0 + cell_w, y0 + top_row_h], fill=(248, 250, 252), outline=(209, 213, 219))
        # Центрируем увеличенный аватар в ячейке
        avatar_size = 60  # Увеличенный размер аватара
        avatar_x = x0 + (cell_w - avatar_size) // 2
        avatar_y = y0 + (top_row_h - avatar_size) // 2
        _paste_avatar(avatar_x, avatar_y, p, avatar_size, header_font)

    # Заголовки дополнительных колонок
    xh = table_x + left_col_w + n * cell_w
    for col_name in extra_cols:
        draw.rectangle([xh, table_y, xh + extra_cell_w, table_y + top_row_h], fill=(248, 250, 252), outline=(209, 213, 219))
        # Вертикальное центрирование заголовка
        header_y = table_y + (top_row_h - 24) // 2
        try:
            bbox = draw.textbbox((0, 0), col_name, font=header_font)
            text_width = bbox[2] - bbox[0]
            header_x = xh + (extra_cell_w - text_width) // 2
            draw.text((header_x, header_y), col_name, fill=(31, 41, 55), font=header_font)
        except Exception:
            draw.text((xh + 10, header_y), col_name, fill=(31, 41, 55), font=header_font)
        xh += extra_cell_w

    # Левая колонка с аватаром и именем
    for i, p in enumerate(players):
        x0 = table_x
        y0 = table_y + top_row_h + i * cell_h
        draw.rectangle([x0, y0, x0 + left_col_w, y0 + cell_h], fill=(255, 255, 255), outline=(209, 213, 219))
        # Увеличенный аватар
        avatar_size = 60
        pasted = _paste_avatar(x0 + 8, y0 + (cell_h - avatar_size) // 2, p, avatar_size, cell_font)
        full_name = _short_name(p)
        name_x = x0 + 8 + avatar_size + 12
        draw.text((name_x, y0 + (cell_h - 24) // 2), full_name, fill=(31, 41, 55), font=cell_font)

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
            # Вертикальное центрирование текста в увеличенной ячейке (с учетом увеличенного шрифта)
            text_y = y0 + (cell_h - 24) // 2
            if i == j:
                # Заливаем диагональную ячейку цветом #E5E5E5
                draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(229, 229, 229), outline=(209, 213, 219))
            else:
                draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=(209, 213, 219))
            if j > i:
                p1 = players[i]
                p2 = players[j]
                key = tuple(sorted([str(p1.get('id')), str(p2.get('id'))]))
                rec = res_map.get(key)
                if rec:
                    score = rec.get('score', '')
                    # черный цвет для счета
                    draw.text((x0 + 8, text_y), score, fill=(31, 41, 55), font=cell_font)
                else:
                    draw.text((x0 + 8, text_y), "", fill=(31, 41, 55), font=cell_font)
            else:
                # Нижняя половина: дублируем счет, чтобы был виден у обоих игроков
                p1 = players[j]
                p2 = players[i]
                key = tuple(sorted([str(p1.get('id')), str(p2.get('id'))]))
                rec = res_map.get(key)
                if rec:
                    score = rec.get('score', '')
                    draw.text((x0 + 8, text_y), score, fill=(31, 41, 55), font=cell_font)
                else:
                    draw.text((x0 + 8, text_y), "", fill=(31, 41, 55), font=cell_font)

    # Правые суммарные колонки: Победы, Очки, Места (столбец "Игры" убран)
    for i, p in enumerate(players):
        pid = str(p.get('id'))
        col_x = table_x + left_col_w + n * cell_w
        y0 = table_y + top_row_h + i * cell_h
        text_y = y0 + (cell_h - 24) // 2  # Вертикальное центрирование для увеличенного шрифта
        # Победы
        draw.rectangle([col_x, y0, col_x + extra_cell_w, y0 + cell_h], outline=(209, 213, 219))
        draw.text((col_x + extra_cell_w // 2 - 12, text_y), str(wins.get(pid, 0)), fill=(31, 41, 55), font=cell_font)
        col_x += extra_cell_w
        # Очки
        draw.rectangle([col_x, y0, col_x + extra_cell_w, y0 + cell_h], outline=(209, 213, 219))
        draw.text((col_x + extra_cell_w // 2 - 12, text_y), str(points.get(pid, 0)), fill=(31, 41, 55), font=cell_font)
        col_x += extra_cell_w
        # Места — вычислим сортировку по points, затем tie_sd
        # Место рисуем после сортировки списка players по этим критериям
        # Здесь временно заполним, а ниже отрисуем корректные места поверх
        draw.rectangle([col_x, y0, col_x + extra_cell_w, y0 + cell_h], outline=(209, 213, 219))
        col_x += extra_cell_w

    # Пересортируем для определения мест
    order = sorted(range(n), key=lambda idx: (points.get(str(players[idx].get('id')), 0), tie_sd.get(str(players[idx].get('id')), 0)), reverse=True)
    place_of: Dict[str, int] = {}
    for rank, idx in enumerate(order, start=1):
        place_of[str(players[idx].get('id'))] = rank
    # Нарисуем места
    for i, p in enumerate(players):
        pid = str(p.get('id'))
        col_x = table_x + left_col_w + n * cell_w + 2 * extra_cell_w  # 2 колонки до "Места": Победы, Очки
        y0 = table_y + top_row_h + i * cell_h
        text_y = y0 + (cell_h - 24) // 2  # Вертикальное центрирование для увеличенного шрифта
        draw.text((col_x + extra_cell_w // 2 - 12, text_y), str(place_of.get(pid, i + 1)), fill=(31, 41, 55), font=cell_font)

    # Примечание по тай-брейку (уменьшенный шрифт для описания)
    note = """* В столбце "Очки" показана общая разница в сетах между игроками с равным количеством побед.
Она используется для определения победителя между ними.

К примеру: У игроков А, Б и В равное кол-во побед (напр., по 1 у каждого), у игрока Г — 3.
Игрок Г получает 1-е место, для остальных требуется определить на основе очков в сетах.

Тогда для игрока А суммируются его очки в сетах в играх с Б и с В, и из них вычитаются
очки в сетах игроков Б и В в их играх с А. Эта разница и выводится в столбце.
Аналогично для игроков Б и В. У кого больше очков — выше место.
Очки в играх с другими игроками в этом подсчёте не учитываются.

В случае, когда число побед у игрока не совпадает с другими, дополнительный учёт очков в сетах не требуется."""
    try:
        # Подгрузим уменьшенный шрифт для описания
        def _load_small_font(sz: int = 12) -> ImageFont.FreeTypeFont:
            candidates = [
                ("Circe-Regular.ttf", sz),
                ("Circe.ttf", sz),
                (os.path.join(BASE_DIR, "fonts", "Circe-Regular.ttf"), sz),
                (os.path.join(BASE_DIR, "fonts", "Circe.ttf"), sz),
            ]
            for path, size in candidates:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
            try:
                return ImageFont.truetype("arial.ttf", sz)
            except Exception:
                try:
                    return ImageFont.truetype("DejaVuSans.ttf", sz)
                except Exception:
                    return ImageFont.load_default()

        small_note_font = _load_small_font(16)
        y_pos = table_y + table_h + 10
        line_spacing = 24  # Увеличенный межстрочный интервал для читаемости
        for line in note.split('\n'):
            draw.text((padding, y_pos), line, fill=(0, 0, 0), font=small_note_font)
            y_pos += line_spacing
    except Exception:
        pass

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()
