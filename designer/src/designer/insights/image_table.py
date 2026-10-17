"""Таблица с картинки: скриншот программы, отчёта или сетки, вставленный в xlsx или прикреплённый файлом.

Картинку читает модель с картинками (Qwen3.8-27B) по кускам сверху вниз: целиком высокая картинка
не прочиталась за 10 минут, а кусок увеличенной картинки читается за 20 с (проба 17.10 на программе
IT Community Day 525×2001). Куски режутся по пустым полосам между строками. Над каждым куском, кроме
первого, стоит полоса шапки: без неё модель не знает, какой столбец какой. Куски идут по очереди:
у LM Studio контекст делится между слотами, четыре куска разом не помещались.

Прочитанная таблица кэшируется по хешу картинки и версии скилла: пересчёт подсказок под новый бриф
картинку заново не читает.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Callable

from PIL import Image, ImageStat
from pydantic import BaseModel, Field

from designer import store
from designer.insights.table import Table, TableError, table_from_grid
from designer.llm.client import LlmClient
from designer.llm.skills import load_skill

SKILL = "read-table-image"
TARGET_WIDTH = 1500
"""Ширина куска для модели: мелкий текст скриншота читается после увеличения до неё."""
PIECE_HEIGHT = 1100
"""Высота куска в пикселях после увеличения: кусок с полосой шапки помещается в слот контекста."""
MIN_IMAGE_SIDE = 200


class _Answer(BaseModel):
    columns: list[str] = Field(min_length=2, max_length=10)
    rows: list[list[str]] = Field(max_length=60)


class _Labels(BaseModel):
    labels: list[str] = Field(max_length=15)
    """Подписи столбцов шапки слева направо: залы сетки или имена столбцов обычной таблицы."""


_LABELS_TASK = ("Это полоса шапки таблицы. Выпиши в labels подписи столбцов слева направо, по одной на столбец, "
                "дословно; подписи строк у левого края («Зал →», «Время») не пиши.")


def pick_image(images: list[bytes]) -> bytes | None:
    """Самая большая картинка: в книге рядом с таблицей бывают логотипы и иконки."""
    best, best_area = None, 0
    for data in images:
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
        except Exception:
            continue
        if min(width, height) >= MIN_IMAGE_SIDE and width * height > best_area:
            best, best_area = data, width * height
    return best


def read_image_table(image_data: bytes, name: str, client: LlmClient | None,
                     on_piece: Callable[[int, int], None] | None = None) -> Table:
    """Таблица с картинки. Без модели только из кэша: иначе TableError с причиной."""
    skill = load_skill(SKILL)
    key = hashlib.sha256(image_data + skill.sha256.encode()).hexdigest()
    cached = _cache_path(key)
    if cached.is_file():
        grid = json.loads(cached.read_text(encoding="utf-8"))
        return table_from_grid(name, grid, sheet="картинка", from_image=True)
    if client is None:
        raise TableError("Таблица на картинке: прочитать её может только модель, а модель остановлена.")
    image = Image.open(io.BytesIO(image_data)).convert("RGB")
    scale = TARGET_WIDTH / image.width
    image = image.resize((TARGET_WIDTH, max(1, round(image.height * scale))), Image.LANCZOS)
    header_bottom = _header_bottom(image)
    pieces = _pieces(image, header_bottom)
    # Подписи столбцов шапки читаются отдельно и крупно: в каждом куске модель читала зал заново и писала его
    # по-своему («МФ3», «ФПЭ», «МФЗ»), и пять залов считались десятью (прогон 17.10). В ответе с записями
    # модель подписи сетки не заполняла.
    header = image.crop((0, 0, image.width, header_bottom))
    header = header.resize((header.width * 3 // 2, header.height * 3 // 2), Image.LANCZOS)
    grid = [label.strip() for label in _Labels.model_validate(client.complete_json(
        system=skill.render(task=_LABELS_TASK), user="Картинка ниже.", schema=_Labels.model_json_schema(),
        images_png=[_png(header)], params=skill.params)).labels if label.strip()]
    names = (f" Подписи столбцов шапки слева направо: {json.dumps(grid, ensure_ascii=False)}; в столбце с ними "
             "пиши их в точности так." if grid else "")
    columns: list[str] = []
    rows: list[list[str]] = []
    for index, (top, bottom) in enumerate(pieces):
        if on_piece:
            on_piece(index + 1, len(pieces))
        if index == 0:
            picture = image.crop((0, 0, image.width, bottom))
            task = ("Это верх таблицы с шапкой. Выбери столбцы обычной таблицы (columns) и перепиши записи, "
                    f"которые видны на картинке (rows).{names}")
        else:
            picture = _stack(image.crop((0, 0, image.width, header_bottom)), image.crop((0, top, image.width, bottom)))
            task = (f"Сверху картинки полоса шапки таблицы, под чертой следующий кусок той же таблицы. Столбцы уже "
                    f"выбраны: {json.dumps(columns, ensure_ascii=False)}; верни их в columns без изменений.{names} "
                    "Перепиши в rows записи только из куска под чертой, строки полосы шапки не переписывай. Запись, "
                    "обрезанную сверху (видно только окончание длинного текста), пропусти: её начало уже переписано.")
        answer = _Answer.model_validate(client.complete_json(
            system=skill.render(task=task), user="Картинка ниже.", schema=_Answer.model_json_schema(),
            images_png=[_png(picture)], params=skill.params))
        if index == 0:
            columns = [column.strip() for column in answer.columns]
        rows += [_fit(row, len(columns)) for row in answer.rows]
    cells = [columns] + _same_spelling(_to_grid_labels(_tidy(rows), grid))
    table = table_from_grid(name, cells, sheet="картинка", from_image=True)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    return table


def _cache_path(key: str):
    return store.data_dir() / "image-tables" / f"{key}.json"


def _quiet_rows(image: Image.Image) -> list[bool]:
    """Строки пикселей без текста и линий: по ним режем, чтобы не разрезать строку таблицы пополам."""
    gray = image.convert("L")
    return [ImageStat.Stat(gray.crop((0, y, gray.width, y + 1))).stddev[0] < 6 for y in range(gray.height)]


def _header_bottom(image: Image.Image) -> int:
    """Низ полосы шапки: пустая полоса около 5 % высоты, в пределах от 3 до 15 %."""
    quiet = _quiet_rows(image)
    want = int(image.height * 0.05)
    low, high = int(image.height * 0.03), min(int(image.height * 0.15), want + 400)
    near = [y for y in range(low, high) if quiet[y]]
    return min(near, key=lambda y: abs(y - want)) if near else want


def _pieces(image: Image.Image, header_bottom: int) -> list[tuple[int, int]]:
    """Куски от низа шапки до низа картинки; первый кусок начинается с самого верха и включает шапку."""
    quiet = _quiet_rows(image)
    bounds, top = [], 0
    first_height = PIECE_HEIGHT
    while image.height - top > (first_height if not bounds else PIECE_HEIGHT - header_bottom) * 1.25:
        height = first_height if not bounds else PIECE_HEIGHT - header_bottom
        want = top + height
        near = [y for y in range(want - height // 3, min(image.height, want + height // 4)) if quiet[y]]
        cut = min(near, key=lambda y: abs(y - want)) if near else want
        bounds.append((top, cut))
        top = cut
    bounds.append((top, image.height))
    return bounds


def _stack(header: Image.Image, piece: Image.Image) -> Image.Image:
    """Полоса шапки, черта и кусок: черта отделяет то, что переписывать, от подписей столбцов."""
    out = Image.new("RGB", (piece.width, header.height + 12 + piece.height), (255, 255, 255))
    out.paste(header, (0, 0))
    out.paste(Image.new("RGB", (piece.width, 6), (220, 30, 30)), (0, header.height + 3))
    out.paste(piece, (0, header.height + 12))
    return out


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _fit(row: list[str], width: int) -> list[str]:
    cells = [str(cell).strip() for cell in row][:width]
    return cells + [""] * (width - len(cells))


def _tidy(rows: list[list[str]]) -> list[list[str]]:
    """Повторы убираются до заполнения: строка полосы шапки, которую модель переписала ещё раз, иначе
    подставляла своё время следующим строкам (прогон 17.10: «12:30-13:30 Регистрация» в каждом куске).
    Потом пустая первая ячейка берёт значение сверху: время в сетке подписано один раз на блок."""
    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []
    for row in rows:
        key = tuple(row)
        if any(row) and key not in seen:
            seen.add(key)
            unique.append(row)
    out: list[list[str]] = []
    for row in unique:
        if not row[0] and out:
            row = [out[-1][0]] + row[1:]
        if out and row == out[-1]:
            continue
        out.append(row)
    return out


def _to_grid_labels(rows: list[list[str]], grid: list[str]) -> list[list[str]]:
    """Столбец сетки (зал, день) получает подписи из шапки: в каждом куске модель читала зал заново и писала
    его по-своему («МФ3», «ФПЭ», «МФЗ»), и пять залов считались десятью (прогон 17.10). Столбец выбирается
    по сходству его значений с подписями, значение заменяется ближайшей подписью."""
    if not rows or len(grid) < 2:
        return rows

    def best(value: str) -> tuple[float, str]:
        return max((difflib.SequenceMatcher(None, _key(value), _key(label)).ratio(), label) for label in grid)

    scores = []
    for column in range(len(rows[0])):
        values = [row[column] for row in rows if row[column]]
        if values:
            scores.append((sum(best(v)[0] for v in values) / len(values), column))
    score, column = max(scores, default=(0.0, -1))
    if score < 0.5:
        return rows
    for row in rows:
        if row[column]:
            ratio, label = best(row[column])
            if ratio >= 0.4:
                row[column] = label
                continue
            # Не подпись шапки: обед или перерыв, вписанный в столбец зала («6 залов» вместо пяти, стек 17.10).
            # Значение уходит в первый свободный столбец правее, как у строки регистрации.
            free = next((c for c in range(column + 1, len(row)) if not row[c]), None)
            if free is not None:
                row[free] = row[column]
            row[column] = ""
    return rows


def _key(text: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]", "", text.lower().replace("ё", "е"))


def _same_spelling(rows: list[list[str]]) -> list[list[str]]:
    """Одно значение, прочитанное с картинки по-разному («МФ-3», «МФ3», «Кит (Литера ВЭ)», «КИТ (Литера ВЭ)»),
    сводится к самому частому написанию. Только в столбцах с повторами: имена и названия не трогаются."""
    if not rows:
        return rows
    for column in range(len(rows[0])):
        values = [row[column] for row in rows if row[column]]
        counts = Counter(values)
        if len(values) < 4 or len(counts) > 15 or counts.most_common(1)[0][1] < 2:
            continue
        canonical: dict[str, str] = {}
        for value, _ in counts.most_common():
            match = next((main for main in canonical.values()
                          if difflib.SequenceMatcher(None, _key(value), _key(main)).ratio() >= 0.8), None)
            canonical[value] = match or value
        for row in rows:
            if row[column]:
                row[column] = canonical[row[column]]
    return rows
