"""Таблица автора: csv, любой лист xlsx или картинка таблицы в строки и точные числа.

Пределы те же, что у разбора CSV в браузере (`frontend/src/stage/meaningCsv.ts` из ветки Стаса):
1 МиБ, 2000 строк данных, 50 столбцов, 2000 знаков в ячейке. Формулы не выполняются: из xlsx
берётся значение, которое Excel сохранил при последнем пересчёте, строка «=...» в csv остаётся текстом.

Таблицу ищем, а не требуем: заголовки и пояснения над шапкой пропускаются, объединённые ячейки
заполняются, шапка из двух строк склеивается, пустые столбцы убираются, листы перебираются по порядку.
Картинку таблицы (png, jpg или картинку внутри xlsx) читает модель: `insights/image_table.py`.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
MAX_COLS = 50
MAX_CELL = 2000
MAX_EMPTY_RUN = 1000
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


class TableError(ValueError):
    """Файл не годится: сообщение говорит автору, что поправить."""


@dataclass(frozen=True)
class Table:
    name: str
    headers: list[str]
    rows: list[list[str]]
    """Текст ячеек, как его видит автор."""
    numbers: list[list[Decimal | None]]
    """Число в ячейке или None, если ячейка не число."""
    lines: list[int]
    """Номер строки данных в файле, как его видит автор в Excel: пустые строки файла не сдвигают счёт."""
    sheet: str = ""
    """Лист xlsx, с которого прочитана таблица; у csv пусто."""
    from_image: bool = False
    """Таблицу прочитала модель с картинки: числа надо сверить с оригиналом."""


_NUMBER = re.compile(r"^[+-]?(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?$")
_MONTH_YEAR = re.compile(r"^\d{1,2}[./]\d{4}$")
"""«01.2026» это месяц и год, а не число 1,2026."""
_CURRENCY = re.compile(r"\s*(?:₽|руб\.?|р\.|\$|€|%)\s*$", re.I)


def parse_number(text: str) -> Decimal | None:
    """«1 234,5», «-12.3», «18 %», «−5», «120 ₽» в Decimal. Формулы, даты и текст не числа."""
    value = text.strip().replace("−", "-")
    if not value or value.startswith("=") or _MONTH_YEAR.match(value):
        return None
    value = _CURRENCY.sub("", value)
    if not _NUMBER.match(value):
        return None
    value = re.sub(r"[   ]", "", value).replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def file_name(filename: str) -> str:
    return (filename or "таблица").replace("\\", "/").rsplit("/", 1)[-1][:200]


def is_image(filename: str) -> bool:
    return file_name(filename).lower().endswith(IMAGE_SUFFIXES)


def check_size(data: bytes, filename: str) -> None:
    lower = file_name(filename).lower()
    if is_image(filename):
        if len(data) > MAX_IMAGE_BYTES:
            raise TableError("Картинка больше 5 МБ: обрежьте её по таблице или сохраните в jpg")
        return
    if len(data) > MAX_BYTES:
        extra = "листы, строки и столбцы" if lower.endswith(".xlsx") else "строки и столбцы"
        raise TableError(f"Файл больше 1 МБ: удалите лишние {extra}")


def read_tables(data: bytes, filename: str) -> list[Table]:
    """Таблицы файла по листам, по порядку. Ни одной: TableError с причиной.

    У картинки таблиц в ячейках нет: её читает модель (`image_table.read_image_table`).
    """
    check_size(data, filename)
    name = file_name(filename)
    lower = name.lower()
    if is_image(filename):
        raise TableError("Таблица на картинке: прочитать её может только модель.")
    if lower.endswith(".xlsx"):
        tables, reasons = [], []
        for sheet, grid in _read_xlsx(data):
            try:
                tables.append(table_from_grid(name, grid, sheet))
            except TableError as exc:
                reasons.append(f"лист «{sheet}»: {exc}")
        if tables:
            return tables
        raise TableError(_no_table(reasons))
    if lower.endswith(".csv") or lower.endswith(".txt"):
        return [table_from_grid(name, _read_csv(data))]
    raise TableError("Нужен файл xlsx, csv или картинка таблицы (png, jpg)")


def read_table(data: bytes, filename: str) -> Table:
    """Первая таблица файла: для csv единственная, для xlsx с первого листа, где она нашлась."""
    return read_tables(data, filename)[0]


def _no_table(reasons: list[str]) -> str:
    if len(reasons) == 1:
        sheet, reason = reasons[0].split(": ", 1)
        return f"{sheet[0].upper()}{sheet[1:]}: {reason}"
    return "Таблицы не нашлось ни на одном листе: " + "; ".join(reasons)


def images_in(data: bytes, filename: str) -> list[bytes]:
    """Картинки, в которых может быть таблица: сам файл-картинка или картинки внутри книги xlsx."""
    if is_image(filename):
        return [data]
    if not file_name(filename).lower().endswith(".xlsx"):
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [n for n in archive.namelist() if n.startswith("xl/media/") and n.lower().endswith(IMAGE_SUFFIXES)]
            return [archive.read(n) for n in sorted(names)]
    except zipfile.BadZipFile:
        return []


def _read_csv(data: bytes) -> list[list[str]]:
    if b"\0" in data:
        raise TableError("Файл сохранён не как csv: в Excel выберите «Сохранить как», тип «CSV UTF-8».")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel на русской Windows сохраняет CSV в cp1251 с разделителем «;».
        try:
            text = data.decode("cp1251")
        except UnicodeDecodeError as exc:
            raise TableError("Не удалось распознать кодировку: сохраните файл как «CSV UTF-8».") from exc
    first_line = text.split("\n", 1)[0]
    delimiter = max((";", ",", "\t"), key=first_line.count)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        return [row for row in reader]
    except csv.Error as exc:
        raise TableError(f"Строка {reader.line_num}: кавычка в значении не закрыта или стоит не на месте. "
                         "Сохраните таблицу из Excel заново как «CSV UTF-8».") from exc


def _read_xlsx(data: bytes) -> list[tuple[str, list[list[str]]]]:
    """Все листы книги. Значение объединённой ячейки стоит во всех её клетках: шапка «Выручка» над двумя
    столбцами и подпись группы на несколько строк иначе оставляли пустые клетки."""
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:  # повреждённый zip, не книга Excel, xls под видом xlsx
        raise TableError("Файл не открывается как xlsx: откройте его в Excel и сохраните как «Книга Excel (.xlsx)».") from exc
    sheets = []
    try:
        for sheet in workbook.worksheets:
            grid: list[list[str]] = []
            filled = empty_run = 0
            for row in sheet.iter_rows(values_only=True):
                cells = [_cell_text(value) for value in row[:MAX_COLS * 2]]
                grid.append(cells)
                # К пределу идут только строки с данными: пустые строки листа раньше съедали предел, и хвост
                # таблицы молча терялся, а сумма считалась по части (ред-тим 17.10, инженер ядра).
                if any(cell.strip() for cell in cells):
                    filled += 1
                    empty_run = 0
                else:
                    empty_run += 1
                # Тысяча пустых строк подряд это конец таблицы: лист с оформлением до строки 1 000 000
                # иначе читался секунду на каждый запрос (приёмка 17.10).
                if filled > MAX_ROWS + 10 or empty_run > MAX_EMPTY_RUN:
                    break
            for merged in sheet.merged_cells.ranges:
                value = _cell_text(sheet.cell(merged.min_row, merged.min_col).value)
                for r in range(merged.min_row - 1, min(merged.max_row, len(grid))):
                    row = grid[r]
                    while len(row) < merged.max_col:
                        row.append("")
                    for c in range(merged.min_col - 1, min(merged.max_col, MAX_COLS * 2)):
                        row[c] = value
            sheets.append((sheet.title, grid))
    finally:
        workbook.close()
    return sheets


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, dt.datetime):
        return value.strftime("%d.%m.%Y") if value.time() == dt.time() else value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M")
    if isinstance(value, float):
        return format(Decimal(repr(value)).normalize(), "f")
    return str(value)


def table_from_grid(name: str, grid: list[list[str]], sheet: str = "", from_image: bool = False) -> Table:
    """Таблица из клеток листа: шапка ищется, строки над ней (заголовок, источник, дата) пропускаются."""
    numbered = [(index, [cell.strip() for cell in row]) for index, row in enumerate(grid, start=1)]
    numbered = [(index, row) for index, row in numbered if any(row)]
    if not numbered:
        raise TableError("Таблица пустая.")
    width = max(len(row) for _, row in numbered)
    numbered = [(index, row + [""] * (width - len(row))) for index, row in numbered]
    used = [c for c in range(width) if any(row[c] for _, row in numbered)]
    if len(used) > MAX_COLS:
        raise TableError(f"Больше {MAX_COLS} столбцов: оставьте только нужные.")
    numbered = [(index, [row[c] for c in used]) for index, row in numbered]

    start = _header_row(numbered)
    if start is None:
        raise TableError("Не нашёл шапку таблицы: нужна строка с именами столбцов и хотя бы две строки данных под ней.")
    headers = list(numbered[start][1])
    body_from = start + 1
    second = numbered[body_from][1] if body_from < len(numbered) else []
    if second and _second_header(headers, second, numbered[body_from + 1:]):
        headers = [f"{top} {bottom}".strip() if bottom and bottom != top else top
                   for top, bottom in zip(headers, second)]
        body_from += 1
    headers = _unique(headers)
    body = numbered[body_from:]
    if len(body) > MAX_ROWS:
        raise TableError(f"Больше {MAX_ROWS} строк данных: оставьте только нужные.")
    if len(body) < 2:
        raise TableError("Нужны шапка и хотя бы две строки данных.")
    if any(len(cell) > MAX_CELL for _, row in body for cell in row):
        raise TableError(f"Ячейка длиннее {MAX_CELL} знаков.")
    rows = [row for _, row in body]
    return Table(name=name, headers=headers, rows=rows, numbers=[[parse_number(c) for c in row] for row in rows],
                 lines=[index for index, _ in body], sheet=sheet, from_image=from_image)


def _header_row(rows: list[tuple[int, list[str]]]) -> int | None:
    """Шапка: первая строка, где имён столбцов хотя бы два разных и заполнена хотя бы половина столбцов.

    Заголовок отчёта в объединённой ячейке на всю ширину даёт строку из одного повторённого значения:
    это не шапка. Под шапкой нужны хотя бы две строки.
    """
    width = len(rows[0][1])
    for position, (_, row) in enumerate(rows):
        values = [cell for cell in row if cell]
        if len(set(values)) >= 2 and len(values) >= max(2, width / 2) and len(rows) - position - 1 >= 2:
            numeric = sum(parse_number(cell) is not None and not _YEAR_CELL.fullmatch(cell) for cell in values)
            if numeric <= len(values) / 2:  # строка данных не шапка; годы в шапке («2025», «2026») не числа
                return position
    return None


_YEAR_CELL = re.compile(r"(19|20)\d{2}")


def _second_header(top: list[str], second: list[str], rest: list[tuple[int, list[str]]]) -> bool:
    """Вторая строка шапки: под объединённой ячейкой («Выручка» над «2025» и «2026») стоят подписи без чисел,
    а ниже идут строки с числами."""
    merged = any(a and a == b for a, b in zip(top, top[1:]))
    if not merged or not any(second):
        return False
    if any(parse_number(cell) is not None and not _YEAR_CELL.fullmatch(cell) for cell in second):
        return False
    return any(parse_number(cell) is not None for _, row in rest[:3] for cell in row)


def _unique(headers: list[str]) -> list[str]:
    out: list[str] = []
    for index, header in enumerate(headers, start=1):
        name = header or f"Столбец {index}"
        base, n = name, 2
        while name in out:
            name, n = f"{base} {n}", n + 1
        out.append(name)
    return out
