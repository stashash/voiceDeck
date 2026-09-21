"""Вместимость слотов: сколько знаков влезает при исходном и при уменьшенном кегле.

Владелец: задача T-07. Ширина знака и интерлиньяж те же, что у разбора и у аудита,
иначе слой вёрстки и слой проверок будут считать по-разному.
"""
from __future__ import annotations

from designer.contracts import Box, Margins, Pattern, RepeatGroup, TypeStep
from designer.layout.units import map_shape_box, place_units
from designer.parse import geometry as geo

CHAR_WIDTH = 0.52
"""Средняя ширина знака в долях кегля."""

LINE_HEIGHT = 1.2
"""Интерлиньяж в долях кегля."""

EMU_PER_PT = 12700

HEAD_GAP = 0.02
"""Отступ от заголовка слайда до области содержимого, доли высоты."""

HEAD_ZONE = 0.4
"""Верхняя часть слайда: ниже неё заголовок уже не шапка."""

MIN_FREE = 0.004
"""Рамка мельче этой доли слайда местом не считается."""

_HEAD_SLOT_ROLES = ("title", "subtitle")
_HEAD_STEP_ROLES = ("display", "title", "heading")


def slide_pt(slide_size_emu: tuple[int, int]) -> tuple[float, float]:
    """Размер слайда в пунктах."""
    return (slide_size_emu[0] / EMU_PER_PT, slide_size_emu[1] / EMU_PER_PT)


def box_capacity(box: Box, size_pt: float, slide: tuple[float, float]) -> tuple[int, int]:
    """Сколько знаков и строк помещается в рамке при этом кегле."""
    if size_pt <= 0:
        return 1, 1
    lines = max(1, int(box[3] * slide[1] / (size_pt * LINE_HEIGHT)))
    per_line = max(1, int(box[2] * slide[0] / (size_pt * CHAR_WIDTH)))
    return per_line * lines, lines


def fit_size(
    text: str,
    box: Box,
    size_pt: float,
    scale: list[TypeStep],
    slide: tuple[float, float],
    floor: float | None = None,
) -> float:
    """Кегль, при котором текст помещается: ступени шкалы вниз, но не ниже floor.

    Без floor нижняя граница это самая мелкая ступень шкалы. Текст, который не помещается
    и на ней, остаётся как есть: это найдёт аудит.
    """
    steps = sorted({step.size_pt for step in scale if step.size_pt > 0}, reverse=True)
    if floor is not None:
        allowed = [s for s in steps if s >= floor - 0.01]
        # Нижняя граница выше нынешнего кегля ничего не ограничивает: шкала идёт своим чередом.
        steps = allowed if any(s < size_pt - 0.01 for s in allowed) else steps
    size = size_pt
    if not text or size <= 0:
        return size
    while len(text) > box_capacity(box, size, slide)[0]:
        smaller = [s for s in steps if s < size - 0.01]
        if not smaller:
            return size
        size = smaller[0]
    return size


def size_floor(scale: list[TypeStep], role: str) -> float | None:
    """Ниже какой ступени шкалы этот слот не опускается.

    Заголовок, набранный кеглем подписи, читается как ошибка вёрстки, поэтому у заголовков
    своя нижняя ступень. У остального текста её нет.
    """
    if role not in ("title", "heading"):
        return None
    steps = [step.size_pt for step in scale if step.role in _HEAD_STEP_ROLES and step.size_pt > 0]
    return min(steps) if steps else None


def content_region(pattern: Pattern, margins: Margins) -> Box:
    """Область содержимого слайда: в полях шаблона и ниже заголовка."""
    left, right = margins.left, 1.0 - margins.right
    top, bottom = margins.top, 1.0 - margins.bottom
    heads = [s.box for s in pattern.slots if s.role in _HEAD_SLOT_ROLES and s.box[1] < HEAD_ZONE]
    if heads:
        top = max(top, max(geo.bottom(b) for b in heads) + HEAD_GAP)
    return (left, top, max(right - left, 0.0), max(bottom - top, 0.0))


def _split(rect: Box, hole: Box) -> list[Box]:
    """Части рамки, не накрытые занятым местом."""
    wide = min(geo.right(rect), geo.right(hole)) - max(rect[0], hole[0])
    high = min(geo.bottom(rect), geo.bottom(hole)) - max(rect[1], hole[1])
    if wide <= 0 or high <= 0:
        return [rect]
    parts: list[Box] = []
    if hole[0] > rect[0]:
        parts.append((rect[0], rect[1], hole[0] - rect[0], rect[3]))
    if geo.right(hole) < geo.right(rect):
        parts.append((geo.right(hole), rect[1], geo.right(rect) - geo.right(hole), rect[3]))
    if hole[1] > rect[1]:
        parts.append((rect[0], rect[1], rect[2], hole[1] - rect[1]))
    if geo.bottom(hole) < geo.bottom(rect):
        parts.append((rect[0], geo.bottom(hole), rect[2], geo.bottom(rect) - geo.bottom(hole)))
    return parts


def _maximal(rects: list[Box]) -> list[Box]:
    """Убрать мелочь и рамки, целиком лежащие внутри других."""
    big = [r for r in rects if geo.area(r) >= MIN_FREE]
    out: list[Box] = []
    for rect in sorted(big, key=lambda r: -geo.area(r)):
        inside = any(
            other[0] <= rect[0] + 1e-9 and other[1] <= rect[1] + 1e-9
            and geo.right(other) >= geo.right(rect) - 1e-9
            and geo.bottom(other) >= geo.bottom(rect) - 1e-9
            for other in out
        )
        if not inside:
            out.append(rect)
    return out


def free_box(region: Box, busy: list[Box]) -> Box | None:
    """Самая просторная пустая рамка внутри области после вычета занятых мест."""
    rects = [region] if geo.area(region) >= MIN_FREE else []
    for hole in busy:
        nxt: list[Box] = []
        for rect in rects:
            nxt.extend(_split(rect, hole))
        rects = _maximal(nxt)
        if not rects:
            return None
    if not rects:
        return None
    return max(rects, key=lambda b: (round(geo.area(b), 6), -b[1], -b[0]))


def main_group(pattern: Pattern) -> RepeatGroup | None:
    """Группа, которая несёт содержание слайда.

    Сначала та, у которой больше текстовых слотов: в неё ляжет и заголовок пункта, и пояснение.
    Дальше по размеру блока и по вместимости сетки.
    """
    if not pattern.groups:
        return None
    return min(
        pattern.groups,
        key=lambda g: (-len(g.unit_slots), -(g.unit_size[0] * g.unit_size[1]), -g.max_units, g.id),
    )


def primary_group(pattern: Pattern) -> RepeatGroup | None:
    """Группа, в которую идут пункты слайда: названная паттерном, иначе выбранная по слотам."""
    named = {group.id: group for group in pattern.groups}.get(pattern.primary_group_id or "")
    return named if named is not None else main_group(pattern)


def linked_groups(pattern: Pattern, group: RepeatGroup | None) -> list[RepeatGroup]:
    """Группы, которые повторяются синхронно с этой: ряд номеров и ряд подписей под ним."""
    if group is None:
        return []
    by_id = {other.id: other for other in pattern.groups}
    return [by_id[gid] for gid in group.linked_group_ids if gid in by_id and gid != group.id]


def unit_text_slots(group: RepeatGroup, linked: list[RepeatGroup] | None = None) -> list:
    """Слоты блока под слова пункта: номер несёт цифру, а не заголовок с пояснением."""
    groups = [group, *(linked or [])]
    return [slot for item in groups for slot in item.unit_slots if slot.role != "number"]


def unit_count(group: RepeatGroup, n: int) -> int:
    """Число блоков, которое группа вытянет: от min_units до max_units."""
    return max(group.min_units, min(n, group.max_units))


def unit_boxes(
    group: RepeatGroup, linked: list[RepeatGroup], n: int
) -> tuple[list[Box], dict[str, list[Box]]]:
    """Рамки n блоков главной группы и связанных с ней.

    Связанная группа переносится тем же преобразованием, что и главная: ряд номеров
    остаётся на оси ряда подписей, как в шаблоне.
    """
    main = place_units(group, n)
    old = group.units[0].box
    return main, {other.id: [map_shape_box(old, new, other.units[0].box) for new in main]
                  for other in linked}


def unit_slot_box(unit_old: Box, unit_new: Box, slot_box: Box) -> Box:
    """Рамка слота блока после перекладки: слот задан от левого верхнего угла блока."""
    absolute = (unit_old[0] + slot_box[0], unit_old[1] + slot_box[1], slot_box[2], slot_box[3])
    return map_shape_box(unit_old, unit_new, absolute)


def _scaled(max_chars: int, max_lines: int, kx: float, ky: float) -> int:
    lines = max(1, int(max_lines * ky))
    per_line = max(1, int(max_chars / max(max_lines, 1) * kx))
    return per_line * lines


def slot_limits(pattern: Pattern, n_units: int) -> dict[str, int]:
    """Сколько знаков помещается в каждый слот паттерна и в слоты блока при n_units блоках.

    Ширина блока берётся из place_units: когда блоков меньше, чем в образце, они шире,
    и в слот блока влезает больше. По этим числам скилл заполнения пишет текст.
    """
    limits = {slot.id: slot.max_chars for slot in pattern.slots}
    for group in pattern.groups:
        for slot in group.unit_slots:
            limits[slot.id] = slot.max_chars

    group = primary_group(pattern)
    if group is None or not group.units:
        return limits

    old = group.units[0].box
    new = place_units(group, unit_count(group, n_units))[0]
    kx = new[2] / old[2] if old[2] else 1.0
    ky = new[3] / old[3] if old[3] else 1.0
    for slot in group.unit_slots:
        limits[slot.id] = _scaled(slot.max_chars, slot.max_lines, kx, ky)
    for linked in linked_groups(pattern, group):
        for slot in linked.unit_slots:
            limits[slot.id] = _scaled(slot.max_chars, slot.max_lines, kx, ky)
    return limits
