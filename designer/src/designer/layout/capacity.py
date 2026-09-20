"""Вместимость слотов: сколько знаков влезает при исходном и при уменьшенном кегле.

Владелец: задача T-07. Ширина знака и интерлиньяж те же, что у разбора и у аудита,
иначе слой вёрстки и слой проверок будут считать по-разному.
"""
from __future__ import annotations

from designer.contracts import Box, Pattern, RepeatGroup, TypeStep
from designer.layout.units import place_units

CHAR_WIDTH = 0.52
"""Средняя ширина знака в долях кегля."""

LINE_HEIGHT = 1.2
"""Интерлиньяж в долях кегля."""

EMU_PER_PT = 12700


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


def fit_size(text: str, box: Box, size_pt: float, scale: list[TypeStep], slide: tuple[float, float]) -> float:
    """Кегль, при котором текст помещается: ступени шкалы вниз, но не ниже самой мелкой.

    Текст, который не помещается и на самой мелкой ступени, остаётся как есть: это найдёт аудит.
    """
    steps = sorted({step.size_pt for step in scale if step.size_pt > 0}, reverse=True)
    size = size_pt
    if not text or size <= 0:
        return size
    while len(text) > box_capacity(box, size, slide)[0]:
        smaller = [s for s in steps if s < size - 0.01]
        if not smaller:
            return size
        size = smaller[0]
    return size


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


def unit_count(group: RepeatGroup, n: int) -> int:
    """Число блоков, которое группа вытянет: от min_units до max_units."""
    return max(group.min_units, min(n, group.max_units))


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

    group = main_group(pattern)
    if group is None or not group.units:
        return limits

    old = group.units[0].box
    new = place_units(group, unit_count(group, n_units))[0]
    kx = new[2] / old[2] if old[2] else 1.0
    ky = new[3] / old[3] if old[3] else 1.0
    for slot in group.unit_slots:
        limits[slot.id] = _scaled(slot.max_chars, slot.max_lines, kx, ky)
    return limits
