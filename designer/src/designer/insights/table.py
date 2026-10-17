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
import json
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
    """Исходная строка Excel/текста (начало CSV-записи); для JSON — индекс записи массива, начиная с 1."""
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
    if lower.endswith(".json"):
        return [_read_json(data, name)]
    if lower.endswith((".csv", ".txt", ".md", ".markdown")):
        return [_read_text_table(data, name)]
    raise TableError("Нужен файл xlsx, csv или картинка таблицы (png, jpg); также поддерживаются json, txt и md")


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


def _explicit_table(name: str, headers: list[str], rows: list[list[str]], lines: list[int]) -> Table:
    """Structured formats already identify their header; never guess or drop empty columns/rows."""
    if not headers or len(headers) > MAX_COLS:
        raise TableError(f"Нужны от 1 до {MAX_COLS} столбцов.")
    if any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
        raise TableError("Имена столбцов должны быть непустыми и уникальными.")
    if len(rows) < 2:
        raise TableError("Нужны шапка и хотя бы две строки данных.")
    if len(rows) > MAX_ROWS:
        raise TableError(f"Больше {MAX_ROWS} строк данных: оставьте только нужные.")
    if any(len(row) != len(headers) for row in rows):
        raise TableError("Число ячеек в строках не совпадает с числом столбцов.")
    if any(len(cell) > MAX_CELL for row in [headers, *rows] for cell in row):
        raise TableError(f"Ячейка длиннее {MAX_CELL} знаков.")
    return Table(name, headers, rows, [[parse_number(cell) for cell in row] for row in rows], lines)


def _read_json(data: bytes, name: str) -> Table:
    """JSON row provenance is the 1-based index in the source array, not a physical text line."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TableError(f"JSON: повторяется ключ «{key[:80]}».")
            result[key] = value
        return result

    def invalid_constant(value):
        raise TableError(f"JSON: недопустимое число {value}.")

    try:
        payload = json.loads(data.decode("utf-8-sig"), object_pairs_hook=object_pairs,
                             parse_float=Decimal, parse_int=Decimal, parse_constant=invalid_constant)
    except (UnicodeDecodeError, ValueError, RecursionError, InvalidOperation, OverflowError) as exc:
        if isinstance(exc, TableError):
            raise
        raise TableError("Некорректный JSON: нужен UTF-8 и массив объектов или объект {columns, rows}.") from exc
    if isinstance(payload, list):
        if not payload or not all(isinstance(row, dict) for row in payload):
            raise TableError("JSON: нужен непустой массив объектов.")
        if len(payload) > MAX_ROWS:
            raise TableError(f"Больше {MAX_ROWS} строк данных: оставьте только нужные.")
        headers = list(dict.fromkeys(key for row in payload for key in row))
        if len(headers) > MAX_COLS:
            raise TableError(f"Больше {MAX_COLS} столбцов: оставьте только нужные.")
        raw_rows = [[row.get(key) for key in headers] for row in payload]
    elif isinstance(payload, dict) and set(payload) == {"columns", "rows"}:
        headers, raw_rows = payload["columns"], payload["rows"]
        if not isinstance(headers, list) or not all(isinstance(h, str) for h in headers):
            raise TableError("JSON: columns должен быть массивом имён столбцов.")
        if not isinstance(raw_rows, list) or not all(isinstance(row, list) for row in raw_rows):
            raise TableError("JSON: rows должен быть массивом массивов ячеек.")
        if len(raw_rows) > MAX_ROWS or len(headers) > MAX_COLS:
            raise TableError(f"JSON: предел — {MAX_ROWS} строк и {MAX_COLS} столбцов.")
    else:
        raise TableError("JSON: нужен массив объектов или объект с полями columns и rows.")

    def cell(value):
        if isinstance(value, (dict, list)):
            raise TableError("JSON: вложенные объекты и массивы в ячейках не поддерживаются.")
        if isinstance(value, Decimal):
            # Bound expansion before formatting scientific notation (e.g. 1e99999999).
            if abs(value.adjusted()) > MAX_CELL or len(value.as_tuple().digits) > MAX_CELL:
                raise TableError(f"JSON: число длиннее {MAX_CELL} знаков.")
            return format(value, "f")
        return _cell_text(value)

    return _explicit_table(name, headers, [[cell(v) for v in row] for row in raw_rows],
                           list(range(1, len(raw_rows) + 1)))


def _read_text_table(data: bytes, name: str) -> Table:
    """One unambiguous delimited or Markdown table, optionally surrounded by prose.

    Prose after a delimited table must be separated by an empty line. Newlines inside
    quoted CSV fields are supported; provenance points at each record's starting line.
    Whitespace-aligned prose is deliberately not treated as a table.
    """
    if b"\0" in data:
        raise TableError("Файл сохранён не как csv: сохраните текст в UTF-8.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1251")
        except UnicodeDecodeError as exc:
            raise TableError("Не удалось распознать кодировку: сохраните файл как «CSV UTF-8».") from exc
    physical = text.splitlines()
    markdown = []
    covered = set()
    for i in range(1, len(physical)):
        separator = _pipe_cells(physical[i])
        if len(separator) < 2 or not all(re.fullmatch(r":?-{3,}:?", c) for c in separator):
            continue
        headers = _pipe_cells(physical[i - 1])
        rows, lines = [], []
        for j in range(i + 1, len(physical)):
            if not physical[j].strip() or "|" not in physical[j]:
                break
            rows.append(_pipe_cells(physical[j]))
            lines.append(j + 1)
        if len(headers) != len(separator):
            raise TableError("Markdown: число столбцов шапки и разделителя не совпадает.")
        markdown.append(_explicit_table(name, headers, rows, lines))
        covered.update([i - 1, i, *(line - 1 for line in lines)])
    if markdown:
        if len(markdown) != 1:
            raise TableError("Найдено несколько таблиц: оставьте одну таблицу в текстовом файле.")
        # Search the remaining prose too: a Markdown table plus a CSV table is ambiguous.
        text = "\n".join("" if index in covered else line for index, line in enumerate(physical))

    candidates, errors = list(markdown), []
    for delimiter in (";", ",", "\t", "|"):
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        blocks, block, start_line, blank = [], [], 1, False
        parsed = []
        try:
            for row in reader:
                line, start_line = start_line, reader.line_num + 1
                if not any(cell.strip() for cell in row):
                    blank = True
                    continue
                if len(row) < 2:
                    if block:
                        if not blank:
                            raise TableError(f"Строка {line}: число ячеек не совпадает с шапкой; отделите пояснение пустой строкой.")
                        blocks.append(block)
                        block = []
                else:
                    block.append((line, row))
                blank = False
            if block:
                blocks.append(block)
            for block in blocks:
                width = len(block[0][1])
                if any(len(row) != width for _, row in block):
                    raise TableError("Число ячеек в строках не совпадает с шапкой таблицы.")
                if any(row == block[0][1] for _, row in block[1:]):
                    raise TableError("Повторяется шапка: разделите несколько таблиц на отдельные файлы.")
                grid = [[] for _ in range(block[-1][0])]
                for line, row in block:
                    grid[line - 1] = row
                parsed.append(table_from_grid(name, grid))
            candidates.extend(parsed)
        except csv.Error as exc:
            errors.append(TableError(f"Строка {reader.line_num}: кавычка в значении не закрыта или стоит не на месте. "
                                     "Сохраните таблицу как CSV UTF-8."))
        except TableError as exc:
            errors.append(exc)
    if len(candidates) > 1:
        raise TableError("Неоднозначный текст: найдено несколько таблиц или разделителей. Оставьте одну таблицу.")
    if candidates:
        return candidates[0]
    if errors:
        raise errors[0]
    raise TableError("Не нашёл таблицу: нужны шапка и хотя бы две строки данных с разделителем ; , TAB или Markdown.")


def _pipe_cells(line: str) -> list[str]:
    """Basic Markdown pipes, including escaped literal pipes; no Markdown execution."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", line)]


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
    if any(len(cell) > MAX_CELL for cell in headers):
        raise TableError(f"Ячейка длиннее {MAX_CELL} знаков.")
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
