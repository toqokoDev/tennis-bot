import io
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from PIL import Image as PILImage
from PIL import Image, ImageDraw, ImageFont


def _load_fonts():
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 20)
        header_font = ImageFont.truetype("arialbd.ttf", 14)
        cell_font = ImageFont.truetype("arial.ttf", 12)
        return title_font, header_font, cell_font
    except Exception:
        f = ImageFont.load_default()
        return f, f, f


def _draw_game_photos_area(draw: ImageDraw.Draw, x: int, y: int, width: int, height: int, cell_font: ImageFont.FreeTypeFont):
    try:
        title = "Фото с игр турнира"
        try:
            bbox = draw.textbbox((0, 0), title, font=cell_font)
            draw.text((x + (width - (bbox[2]-bbox[0])) // 2, y + 6), title, fill=(31, 41, 55), font=cell_font)
        except Exception:
            draw.text((x + 10, y + 6), title, fill=(31, 41, 55), font=cell_font)
        draw.rectangle([x, y + 28, x + width, y + height - 6], fill=(250, 250, 250), outline=(209, 213, 219), width=2)
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

    width = padding * 2 + left_col_w + n * cell_w
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
    table_w = left_col_w + n * cell_w
    table_h = top_row_h + n * cell_h
    draw.rectangle([table_x, table_y, table_x + table_w, table_y + table_h], outline=(209, 213, 219), width=2)

    # Верхняя строка с именами
    for j, p in enumerate(players):
        x0 = table_x + left_col_w + j * cell_w
        y0 = table_y
        draw.rectangle([x0, y0, x0 + cell_w, y0 + top_row_h], fill=(248, 250, 252), outline=(209, 213, 219))
        name = p.get('name') or p.get('first_name') or 'Игрок'
        draw.text((x0 + 10, y0 + 12), name[:18] + ('…' if len(name) > 18 else ''), fill=(31, 41, 55), font=header_font)

    # Левая колонка с именами
    for i, p in enumerate(players):
        x0 = table_x
        y0 = table_y + top_row_h + i * cell_h
        draw.rectangle([x0, y0, x0 + left_col_w, y0 + cell_h], fill=(248, 250, 252), outline=(209, 213, 219))
        name = p.get('name') or p.get('first_name') or 'Игрок'
        draw.text((x0 + 10, y0 + 8), name[:26] + ('…' if len(name) > 26 else ''), fill=(31, 41, 55), font=cell_font)

    # Диагональ «—» и пустые клетки
    # Результаты: создадим словарь для быстрого поиска
    res_map: Dict[tuple, Dict[str, Any]] = {}
    for r in results or []:
        key = tuple(sorted([str(r.get('player1_id')), str(r.get('player2_id'))]))
        res_map[key] = r

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
                    winner_id = str(rec.get('winner_id')) if rec.get('winner_id') is not None else None
                    color = (34, 197, 94) if winner_id in {str(p1.get('id')), str(p2.get('id'))} else (31, 41, 55)
                    draw.text((x0 + 8, y0 + 8), score, fill=color, font=cell_font)
                else:
                    draw.text((x0 + 8, y0 + 8), "", fill=(31, 41, 55), font=cell_font)
            else:
                # нижняя половина таблицы – зеркальная, не заполняем повторно
                pass

    # Фото игр внизу
    photos_y = table_y + table_h + 40
    _draw_game_photos_area(draw, padding, photos_y, image.width - 2 * padding, photos_h, cell_font)

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


