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

from designer.contracts import Box, Pattern, RepeatGroup

_UNIT_DECOR_KINDS = ("shape", "image", "other")


def attach_unit_decor(pattern: Pattern) -> Pattern:
    """Фигура оформления, которая стоит по одной у каждого блока ряда или столбца, принадлежит блоку.

    Разбор не видит в ней повтора, когда у каждого блока своя фигура (круг, квадрат, щит). Такие фигуры
    оставались на местах образца: у четырёх пунктов было три значка, у таймлайна на три шага лишние точки.
    Привязанная к блоку фигура переносится, копируется и убирается вместе с ним. Повторный вызов ничего не меняет.
    """
    decor = {d.shape_id: d for d in pattern.decor if d.kind in _UNIT_DECOR_KINDS}
    if not decor:
        return pattern
    taken: set[int] = set()
    groups = []
    for group in pattern.groups:
        if len(group.units) < 2 or group.direction not in ("row", "column"):
            groups.append(group)
            continue
        axis = 0 if group.direction == "row" else 1
        cross = 1 - axis
        low = min(u.box[cross] for u in group.units)
        high = max(u.box[cross] + u.box[cross + 2] for u in group.units)
        band = (high - low) * 0.75  # фигура над блоком или под ним
        per_unit: list[list[int]] = [[] for _ in group.units]
        for shape_id, shape in decor.items():
            if shape_id in taken:
                continue
            box = shape.box
            if box[cross] + box[cross + 2] < low - band or box[cross] > high + band:
                continue
            center = box[axis] + box[axis + 2] / 2
            for i, unit in enumerate(group.units):
                start, size = unit.box[axis], unit.box[axis + 2]
                if start <= center <= start + size and box[axis + 2] <= size * 1.1:
                    per_unit[i].append(shape_id)
                    break
        counts = {len(ids) for ids in per_unit}
        if len(counts) != 1 or counts == {0}:
            groups.append(group)
            continue
        taken.update(shape_id for ids in per_unit for shape_id in ids)
        units = [u.model_copy(update={"shape_ids": list(u.shape_ids) + ids}) for u, ids in zip(group.units, per_unit)]
        groups.append(group.model_copy(update={"units": units}))
    if not taken:
        return pattern
    return pattern.model_copy(update={
        "groups": groups,
        "decor_shape_ids": [s for s in pattern.decor_shape_ids if s not in taken],
        "decor": [d for d in pattern.decor if d.shape_id not in taken],
    })


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


SQUARE_TOLERANCE = 0.2
"""Насколько фигура может отличаться от квадрата (по сторонам на слайде), чтобы считаться кружком или квадратиком."""
CONTAINER_PART = 0.9
"""Фигура на 90 % блока и больше это подложка блока: она тянется вместе с блоком."""


def keeps_aspect(unit: Box, shape: Box, slide_ratio: float) -> bool:
    """Кружок, кружок с номером, квадратный значок в блоке: при смене числа блоков форма не растягивается в овал.

    slide_ratio это ширина слайда к высоте: рамки заданы в долях слайда, квадрат на слайде 16:9 в долях не квадрат.
    """
    if not (unit[2] and unit[3] and shape[2] and shape[3]):
        return False
    aspect = shape[2] * slide_ratio / shape[3]
    container = shape[2] >= unit[2] * CONTAINER_PART and shape[3] >= unit[3] * CONTAINER_PART
    return not container and 1 - SQUARE_TOLERANCE <= aspect <= 1 / (1 - SQUARE_TOLERANCE)


def map_shape_box(old_unit: Box, new_unit: Box, shape: Box, keep_size: bool = False,
                  keep_aspect: bool = False) -> Box:
    """Рамка фигуры блока после переноса блока из old_unit в new_unit.

    Ширина текста и подложек тянется вместе с блоком. Значки и картинки (keep_size=True) размера не меняют,
    их смещение от края блока масштабируется. Кружки и квадратики (keep_aspect=True) масштабируются
    одинаково по обеим осям, центр переносится вместе с блоком.
    """
    kx = new_unit[2] / old_unit[2] if old_unit[2] else 1.0
    ky = new_unit[3] / old_unit[3] if old_unit[3] else 1.0
    x = new_unit[0] + (shape[0] - old_unit[0]) * kx
    y = new_unit[1] + (shape[1] - old_unit[1]) * ky
    if keep_size:
        return (x, y, shape[2], shape[3])
    if keep_aspect:
        scale = min(kx, ky)
        cx = new_unit[0] + (shape[0] + shape[2] / 2 - old_unit[0]) * kx
        cy = new_unit[1] + (shape[1] + shape[3] / 2 - old_unit[1]) * ky
        w, h = shape[2] * scale, shape[3] * scale
        return (cx - w / 2, cy - h / 2, w, h)
    return (x, y, shape[2] * kx, shape[3] * ky)
