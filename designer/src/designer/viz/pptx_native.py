"""Родные диаграммы и таблицы PowerPoint в цветах шаблона. Владелец: задача T-05."""
from designer.contracts import Box, ChartSpec, TableSpec, Tokens


def add_chart(slide, spec: ChartSpec, box: Box, slide_size_emu: tuple[int, int], tokens: Tokens):
    """Добавляет на слайд python-pptx редактируемую диаграмму и возвращает её фигуру."""
    raise NotImplementedError("T-05")


def add_table(slide, spec: TableSpec, box: Box, slide_size_emu: tuple[int, int], tokens: Tokens):
    raise NotImplementedError("T-05")
