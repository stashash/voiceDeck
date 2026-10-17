"""Откуда берётся таблица файла: ячейки любого листа или, если в ячейках выводов нет, картинка таблицы.

Порядок: таблицы листов по очереди, первая, по которой код нашёл кандидатов в выводы; потом самая
большая картинка файла, которую читает модель. Файл без таблицы и без картинки получает причину отказа
с листа, где таблицу искали.
"""
from __future__ import annotations

from designer.insights.facts import Fact, find_facts
from designer.insights.image_table import pick_image, read_image_table
from designer.insights.table import Table, TableError, check_size, file_name, images_in, is_image, read_tables
from designer.llm.client import LlmClient

NO_FACTS = ("В таблице нет ни столбца с числами, ни столбца с повторяющимися значениями: "
            "выводы считать не из чего.")
NO_FACTS_IMAGE = ("Таблицу с картинки прочитал, но в ней нет ни столбца с числами, ни столбца с повторяющимися "
                  "значениями: выводы считать не из чего.")
BAD_IMAGE = "Картинка не открывается или меньше 200 пикселей по стороне: таблицу на ней не прочитать."


def preview(data: bytes, filename: str) -> tuple[Table | None, bool]:
    """Разбор без модели: таблица из ячеек или пометка, что таблицу придётся читать с картинки."""
    check_size(data, filename)
    error = TableError(BAD_IMAGE)
    if not is_image(filename):
        try:
            for table in read_tables(data, filename):
                if find_facts(table):
                    return table, False
            error = TableError(NO_FACTS)
        except TableError as exc:
            error = exc
    if pick_image(images_in(data, filename)) is not None:
        return None, True
    raise error


def load(data: bytes, filename: str, client: LlmClient | None) -> tuple[Table, list[Fact]]:
    """Таблица и кандидаты в выводы. С картинки таблицу читает модель; без модели только из кэша."""
    table, _ = preview(data, filename)
    if table is not None:
        return table, find_facts(table)
    image = pick_image(images_in(data, filename))
    if image is None:
        raise TableError(BAD_IMAGE)
    table = read_image_table(image, file_name(filename), client)
    facts = find_facts(table)
    if not facts:
        raise TableError(NO_FACTS_IMAGE)
    return table, facts
