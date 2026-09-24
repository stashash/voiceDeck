"""Размещение повторяющихся блоков при смене их числа.

Общий модуль: им пользуются и вёрстка (сцена), и экспорт pptx, поэтому геометрия у них совпадает.
Менять только отдельной задачей.

Правила:
- ряд: n блоков делят исходную ширину ряда поровну, зазор между блоками сохраняется;
- столбец: размер и шаг блока сохраняются, блоки идут сверху вниз;
- сетка: число колонок как в образце, строки добавляются по мере надобности; если блоков меньше,
  чем колонок, сетка ведёт себя как ряд.
"""
from __future__ import annotations

import math

from designer.contracts import Box, RepeatGroup


def _origin(group: RepeatGroup) -> tuple[float, float]:
    return min(u.box[0] for u in group.units), min(u.box[1] for u in group.units)


def _row(x0: float, y: float, span: float, gap: float, height: float, n: int) -> list[Box]:
    width = (span - gap * (n - 1)) / n
    return [(x0 + i * (width + gap), y, width, height) for i in range(n)]


def place_units(group: RepeatGroup, n: int) -> list[Box]:
    """Рамки n блоков. ValueError, если n меньше min_units или больше max_units."""
    if n < group.min_units or n > group.max_units:
        raise ValueError(f"блоков {n}, допустимо от {group.min_units} до {group.max_units}")
    x0, y0 = _origin(group)
    unit_w, unit_h = group.unit_size
    step_x, step_y = group.step
    if group.direction == "column":
        return [(x0, y0 + i * step_y, unit_w, unit_h) for i in range(n)]
    cols = group.cols if group.direction == "grid" else max(group.cols, len(group.units))
    gap = max(step_x - unit_w, 0.0)
    span = cols * unit_w + (cols - 1) * gap
    if group.direction == "row" or n <= cols:
        if n > cols:
            # Редкий ряд (зазор шире блока) при добавлении блоков сжимал их до нечитаемой ширины:
            # лишний зазор отдаётся блокам, ширина ряда остаётся как в образце.
            gap = min(gap, unit_w * 0.25)
        return _row(x0, y0, span, gap, unit_h, n)
    rows = math.ceil(n / cols)
    boxes: list[Box] = []
    for r in range(rows):
        boxes.extend((x0 + c * step_x, y0 + r * step_y, unit_w, unit_h) for c in range(cols))
    return boxes[:n]


def map_shape_box(old_unit: Box, new_unit: Box, shape: Box, keep_size: bool = False) -> Box:
    """Рамка фигуры блока после переноса блока из old_unit в new_unit.

    Ширина текста и подложек тянется вместе с блоком. Значки и картинки (keep_size=True) размера не меняют,
    их смещение от края блока масштабируется.
    """
    kx = new_unit[2] / old_unit[2] if old_unit[2] else 1.0
    ky = new_unit[3] / old_unit[3] if old_unit[3] else 1.0
    x = new_unit[0] + (shape[0] - old_unit[0]) * kx
    y = new_unit[1] + (shape[1] - old_unit[1]) * ky
    if keep_size:
        return (x, y, shape[2], shape[3])
    return (x, y, shape[2] * kx, shape[3] * ky)
