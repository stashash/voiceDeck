"""Родные диаграммы и таблицы PowerPoint в цветах шаблона. Владелец: задача T-05, тема — T-20."""
from __future__ import annotations

from typing import Literal

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Emu, Pt

from designer.contracts import Box, ChartSpec, TableSpec, Tokens
from designer.viz import palette

_CHART_TYPES = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "pie": XL_CHART_TYPE.PIE,
    "donut": XL_CHART_TYPE.DOUGHNUT,
}

EMU_PER_PT = 12700

LINE_HEIGHT = 1.2
"""Интерлиньяж в долях кегля, тот же, что у вёрстки."""

ROW_AIR = 1.8
"""Во сколько кеглей обходится строка таблицы вместе с воздухом сверху и снизу."""

CHART_LABEL_ROWS = 12
"""На сколько строк подписей рассчитана рамка диаграммы: шкала, деления и названия рядов."""


def _steps(tokens: Tokens) -> list[float]:
    return sorted({step.size_pt for step in tokens.type_scale if step.size_pt > 0})


def _cap_size_pt(tokens: Tokens) -> float | None:
    """Потолок подписей: ступень title. Крупнее них подписи диаграммы уже спорят с заголовком."""
    title = [step.size_pt for step in tokens.type_scale if step.role == "title" and step.size_pt > 0]
    if title:
        return max(title)
    steps = _steps(tokens)
    return steps[len(steps) // 2] if steps else None


def _label_size_pt(tokens: Tokens, box: Box, slide_size_emu: tuple[int, int], rows: int) -> float | None:
    """Кегль подписей по высоте, которая достаётся одной строке, но не ниже мелкой ступени шкалы.

    Ступень образца рассчитана на мелкую подпись; в просторной рамке такой кегль читается
    как брак вёрстки. Поэтому берём самую крупную ступень, которая в строку ещё встаёт.
    """
    steps = _steps(tokens)
    if not steps:
        return None
    small, cap = steps[0], _cap_size_pt(tokens) or steps[-1]
    height_pt = box[3] * slide_size_emu[1] / EMU_PER_PT
    room = height_pt / max(rows, 1) / ROW_AIR
    fitting = [step for step in steps if step <= room + 0.01 and step <= cap + 0.01]
    return max(fitting) if fitting else small


def _box_to_emu(box: Box, slide_size_emu: tuple[int, int]) -> tuple[Emu, Emu, Emu, Emu]:
    """Переводит долю слайда в абсолютные EMU."""
    slide_w, slide_h = slide_size_emu
    x, y, w, h = box
    return (
        Emu(round(x * slide_w)),
        Emu(round(y * slide_h)),
        Emu(round(w * slide_w)),
        Emu(round(h * slide_h)),
    )


def _body_font_family(tokens: Tokens) -> str | None:
    """Семейство шрифта body из токенов; без хардкода, если токенов нет — None."""
    body = [f for f in tokens.fonts if f.role == "body"]
    if body:
        return max(body, key=lambda f: f.share).family
    if tokens.fonts:
        return tokens.fonts[0].family
    return None


def _color_by_role(tokens: Tokens, role: str) -> str | None:
    for token in tokens.colors:
        if token.role == role:
            return token.hex
    return None


def add_chart(
    slide,
    spec: ChartSpec,
    box: Box,
    slide_size_emu: tuple[int, int],
    tokens: Tokens,
    theme: Literal["light", "dark"] = "light",
):
    """Добавляет на слайд python-pptx редактируемую диаграмму и возвращает её фигуру."""
    if len(spec.series) > 5:
        raise ValueError("не больше пяти рядов")

    chart_data = CategoryChartData()
    chart_data.categories = spec.categories
    for series in spec.series:
        chart_data.add_series(series.name, series.values)

    left, top, width, height = _box_to_emu(box, slide_size_emu)
    graphic_frame = slide.shapes.add_chart(_CHART_TYPES[spec.type], left, top, width, height, chart_data)
    chart = graphic_frame.chart

    family = _body_font_family(tokens)
    if family:
        chart.font.name = family
    label_size = _label_size_pt(tokens, box, slide_size_emu, CHART_LABEL_ROWS)
    if label_size:
        chart.font.size = Pt(label_size)

    text_hex = palette.theme_text_color(tokens, theme) if theme == "dark" else None
    if text_hex:
        chart.font.color.rgb = RGBColor.from_string(text_hex)

    colors = palette.series_colors(tokens)
    is_pie = spec.type in ("pie", "donut")

    if is_pie:
        series_obj = chart.series[0]
        chart.plots[0].has_data_labels = True
        if text_hex:
            chart.plots[0].data_labels.font.color.rgb = RGBColor.from_string(text_hex)
        if colors:
            for idx, point in enumerate(series_obj.points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = RGBColor.from_string(colors[idx % len(colors)])
    else:
        if colors:
            for idx, series_obj in enumerate(chart.series):
                series_obj.format.fill.solid()
                series_obj.format.fill.fore_color.rgb = RGBColor.from_string(colors[idx % len(colors)])
        if spec.unit:
            value_axis = chart.value_axis
            value_axis.has_title = True
            value_axis.axis_title.text_frame.text = spec.unit
            if text_hex:
                title_run = value_axis.axis_title.text_frame.paragraphs[0].runs[0]
                title_run.font.color.rgb = RGBColor.from_string(text_hex)
        gridline_color = palette.muted_gridline_color(tokens, theme) if theme == "dark" else _color_by_role(tokens, "text_muted")
        if gridline_color:
            chart.value_axis.has_major_gridlines = True
            chart.value_axis.major_gridlines.format.line.color.rgb = RGBColor.from_string(gridline_color)
        if label_size:
            # Подписи делений наследуют кегль не всегда: у них свой, и без этого они мельчают.
            chart.value_axis.tick_labels.font.size = Pt(label_size)
            chart.category_axis.tick_labels.font.size = Pt(label_size)
        if text_hex:
            chart.value_axis.tick_labels.font.color.rgb = RGBColor.from_string(text_hex)
            chart.category_axis.tick_labels.font.color.rgb = RGBColor.from_string(text_hex)

    if len(spec.series) >= 2:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.RIGHT
        chart.legend.include_in_layout = False
        if text_hex:
            chart.legend.font.color.rgb = RGBColor.from_string(text_hex)

    return graphic_frame


def _fill_cell(cell, hex_color: str | None) -> None:
    if hex_color:
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_string(hex_color)
    else:
        cell.fill.background()


def _write_cell(cell, text: str, family: str | None, size_pt: float | None, color_hex: str | None) -> None:
    cell.text = text
    paragraph = cell.text_frame.paragraphs[0]
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    if family:
        run.font.name = family
    if size_pt:
        run.font.size = Pt(size_pt)
    if color_hex:
        run.font.color.rgb = RGBColor.from_string(color_hex)


def _set_row_heights(table, size_pt: float | None, height_emu: int) -> None:
    """Высоты строк по содержимому: шапка той же высоты, что строка текста.

    Без этого python-pptx делит рамку поровну, и шапка выходит вдвое выше своей строки.
    Пустое место рамки при этом остаётся под таблицей, а не внутри строк.
    """
    if not size_pt:
        return
    row_emu = max(int(size_pt * LINE_HEIGHT * ROW_AIR * EMU_PER_PT), 1)
    rows = len(table.rows)
    if row_emu * rows > height_emu:
        row_emu = max(int(height_emu / rows), 1)
    for row in table.rows:
        row.height = Emu(row_emu)


def add_table(
    slide,
    spec: TableSpec,
    box: Box,
    slide_size_emu: tuple[int, int],
    tokens: Tokens,
    theme: Literal["light", "dark"] = "light",
):
    """Добавляет на слайд родную таблицу python-pptx и возвращает её фигуру."""
    if len(spec.columns) > 5:
        raise ValueError("не больше пяти колонок")
    if len(spec.rows) > 7:
        raise ValueError("не больше семи строк")

    left, top, width, height = _box_to_emu(box, slide_size_emu)
    graphic_frame = slide.shapes.add_table(len(spec.rows) + 1, len(spec.columns), left, top, width, height)
    table = graphic_frame.table

    accent_colors = palette.series_colors(tokens)
    accent_hex = accent_colors[0] if accent_colors else None
    header_text_color = palette.contrast_text_color(accent_hex) if accent_hex else None
    surface_hex = _color_by_role(tokens, "surface")
    family = _body_font_family(tokens)
    size_pt = _label_size_pt(tokens, box, slide_size_emu, len(spec.rows) + 1)

    body_text_color = None
    shade_hex = surface_hex
    if theme == "dark":
        # на тёмном фоне светлый текст читается только на тёмной подложке surface,
        # иначе строка остаётся без заливки, чтобы не перекрыть текст светлым пятном
        body_text_color = palette.theme_text_color(tokens, theme)
        if surface_hex is None or not palette.is_dark(surface_hex):
            shade_hex = None

    for col_idx, heading in enumerate(spec.columns):
        cell = table.cell(0, col_idx)
        _fill_cell(cell, accent_hex)
        _write_cell(cell, heading, family, size_pt, header_text_color)

    for row_idx, row_values in enumerate(spec.rows):
        shaded = row_idx % 2 == 0
        for col_idx, value in enumerate(row_values):
            cell = table.cell(row_idx + 1, col_idx)
            _fill_cell(cell, shade_hex if shaded else None)
            _write_cell(cell, value, family, size_pt, body_text_color)

    _set_row_heights(table, size_pt, height)
    return graphic_frame
