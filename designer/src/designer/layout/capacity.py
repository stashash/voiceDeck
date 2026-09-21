"""Вместимость слотов: сколько знаков влезает при исходном и при уменьшенном кегле.

Владелец: задача T-07. Ширина знака и интерлиньяж те же, что у разбора и у аудита,
иначе слой вёрстки и слой проверок будут считать по-разному.
"""
from __future__ import annotations

import math
import re

from designer.contracts import Box, Margins, Pattern, RepeatGroup, SlideIntent, SlideKind, TypeStep
from designer.layout.units import map_shape_box, place_units
from designer.parse import geometry as geo

CHAR_WIDTH = 0.52
"""Средняя ширина знака в долях кегля."""

LINE_HEIGHT = 1.2
"""Интерлиньяж в долях кегля."""

EMU_PER_PT = 12700

OVERLAP_MIN = 0.05
"""Доля меньшей рамки, с которой перехлёст считается наездом; та же, что в аудите."""

SIZE_GRAIN = 0.5
"""Шаг промежуточного кегля вне шкалы, пункты."""

FREE_LINES = 8
"""Во сколько строк максимум раскладывается текст при подборе промежуточного кегля."""

FREE_TRIES = 8
"""Сколько полупунктов вниз пробуем, пока строки не встанут в рамку."""

HEAD_GAP = 0.02
"""Отступ от заголовка слайда до области содержимого, доли высоты."""

HEAD_ZONE = 0.4
"""Верхняя часть слайда: ниже неё заголовок уже не шапка."""

MIN_FREE = 0.004
"""Рамка мельче этой доли слайда местом не считается."""

_HEAD_SLOT_ROLES = ("title", "subtitle")
_HEAD_STEP_ROLES = ("display", "title", "heading")

_NUMBER_RE = re.compile(r"\d+(?:[ .,]\d+)*\s*%?")


def lead_number(intent: SlideIntent) -> str | None:
    """Число, на котором держится слайд: из пункта, иначе из заголовка или ключевой мысли.

    План часто называет число только словами заголовка, и слот под крупную цифру
    остаётся пустым. Берём число оттуда, иначе слайд с числом встанет без числа.
    """
    for item in intent.items:
        if item.number:
            return item.number
    if intent.kind is not SlideKind.big_number:
        return None
    for text in (intent.title, intent.key_message):
        found = _NUMBER_RE.search(text or "")
        if found:
            return found.group().strip()
    return None


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


def longest_word(text: str) -> str:
    """Самое длинное слово текста: оно решает, при каком кегле строка не порвётся посреди слова."""
    words = text.split()
    return max(words, key=len) if words else ""


def line_capacity(box: Box, size_pt: float, slide: tuple[float, float]) -> int:
    """Сколько знаков помещается в одну строку рамки."""
    if size_pt <= 0 or box[2] <= 0:
        return 0
    return max(1, int(box[2] * slide[0] / (size_pt * CHAR_WIDTH)))


def word_size(text: str, box: Box, slide: tuple[float, float]) -> float:
    """Кегль, при котором самое длинное слово влезает в ширину рамки целиком."""
    word = longest_word(text)
    if not word or box[2] <= 0:
        return math.inf
    return box[2] * slide[0] / (len(word) * CHAR_WIDTH)


def text_lines(text: str, box: Box, size_pt: float, slide: tuple[float, float]) -> int:
    """Сколько строк занимает набранный текст. Считается так же, как в аудите."""
    if not text or size_pt <= 0 or box[2] <= 0:
        return 1
    return max(1, math.ceil(len(text) * CHAR_WIDTH * size_pt / slide[0] / box[2]))


def ink_box(box: Box, text: str, size_pt: float, slide: tuple[float, float]) -> Box:
    """Место набранных строк внутри рамки: ширина по тексту, высота по числу строк.

    Рамки текста в шаблонах часто с запасом, поэтому наезд считается по строкам, а не по рамке.
    """
    if size_pt <= 0:
        return box
    lines = text_lines(text, box, size_pt, slide)
    width = min(box[2], len(text) * CHAR_WIDTH * size_pt / slide[0])
    return (box[0], box[1], max(width, 0.0), lines * size_pt * LINE_HEIGHT / slide[1])


def _fits(text: str, box: Box, size_pt: float, slide: tuple[float, float]) -> bool:
    """Помещается ли текст: по знакам, по самому длинному слову и по высоте набранных строк."""
    if len(text) > box_capacity(box, size_pt, slide)[0]:
        return False
    if size_pt > word_size(text, box, slide) + 1e-6:
        return False
    return ink_box(box, text, size_pt, slide)[3] <= box[3] + 1e-9


def _free_size(text: str, box: Box, slide: tuple[float, float]) -> float:
    """Крупнейший кегль вне шкалы, при котором набранный текст стоит в рамке.

    Перебираем, во сколько строк текст ляжет: чем больше строк, тем уже нужна строка
    и тем ниже потолок по высоте. Ноль значит, что рамке не помогает и промежуточный кегль.
    """
    width, height = box[2] * slide[0], box[3] * slide[1]
    if not text or width <= 0 or height <= 0:
        return 0.0
    room = max(
        min(height / (lines * LINE_HEIGHT), lines * width / (len(text) * CHAR_WIDTH))
        for lines in range(1, FREE_LINES + 1)
    )
    size = math.floor(min(room, word_size(text, box, slide)) / SIZE_GRAIN) * SIZE_GRAIN
    for _ in range(FREE_TRIES):
        if size <= 0 or _fits(text, box, size, slide):
            return max(size, 0.0)
        size -= SIZE_GRAIN
    return 0.0


def fit_size(
    text: str,
    box: Box,
    size_pt: float,
    scale: list[TypeStep],
    slide: tuple[float, float],
    floor: float | None = None,
    free_floor: float | None = None,
) -> float:
    """Кегль, при котором текст помещается: ступени шкалы вниз, но не ниже floor.

    Без floor нижняя граница это самая мелкая ступень шкалы. Текст, который не помещается
    и на ней, остаётся как есть: это найдёт аудит. free_floor разрешает крупному слоту кегль
    между ступенями, но не ниже этой границы: разделитель и крупное число иначе рвут слово
    посреди. Промежуточный кегль ниже границы не берётся, слот идёт по ступеням, как обычный.
    """
    size = size_pt
    if not text or size <= 0:
        return size
    if free_floor is not None and not _fits(text, box, size, slide):
        free = min(size, _free_size(text, box, slide))
        if free >= free_floor - 0.01:
            return free
    steps = sorted({step.size_pt for step in scale if step.size_pt > 0}, reverse=True)
    if floor is not None:
        allowed = [s for s in steps if s >= floor - 0.01]
        # Нижняя граница выше нынешнего кегля ничего не ограничивает: шкала идёт своим чередом.
        steps = allowed if any(s < size_pt - 0.01 for s in allowed) else steps
    while not _fits(text, box, size, slide):
        smaller = [s for s in steps if s < size - 0.01]
        if not smaller:
            break
        size = smaller[0]
    return size


def step_down(scale: list[TypeStep], size_pt: float, floor: float | None = None) -> float:
    """Ступень шкалы ниже нынешнего кегля, но не ниже floor. Ступени нет — кегль остаётся."""
    steps = sorted({s.size_pt for s in scale if 0 < s.size_pt < size_pt - 0.01}, reverse=True)
    if floor is not None:
        steps = [s for s in steps if s >= floor - 0.01]
    return steps[0] if steps else size_pt


def head_top(scale: list[TypeStep]) -> float | None:
    """Самая крупная ступень заголовков: выше неё кегль слота уже не со шкалы."""
    steps = [step.size_pt for step in scale if step.role in _HEAD_STEP_ROLES and step.size_pt > 0]
    return max(steps) if steps else None


def title_step(scale: list[TypeStep]) -> float | None:
    """Ступень title: ниже неё заголовок слайда не опускается даже вне шкалы."""
    steps = [step.size_pt for step in scale if step.role == "title" and step.size_pt > 0]
    if steps:
        return max(steps)
    head = [step.size_pt for step in scale if step.role in _HEAD_STEP_ROLES and step.size_pt > 0]
    return min(head) if head else None


def size_floor(scale: list[TypeStep], role: str) -> float | None:
    """Ниже какой ступени шкалы этот слот не опускается.

    Заголовок, набранный кеглем подписи, читается как ошибка вёрстки, поэтому у заголовков
    своя нижняя ступень. Крупное число слайда держится ступени title: мельче его не видно.
    У остального текста нижней границы нет.
    """
    if role == "number":
        return title_step(scale)
    if role not in ("title", "heading"):
        return None
    steps = [step.size_pt for step in scale if step.role in _HEAD_STEP_ROLES and step.size_pt > 0]
    return min(steps) if steps else None


def slot_size(
    text: str,
    box: Box,
    size_pt: float,
    role: str,
    scale: list[TypeStep],
    slide: tuple[float, float],
) -> float:
    """Кегль слота после подгонки. Слоту крупнее шкалы заголовков разрешён кегль между ступенями."""
    top = head_top(scale)
    free_floor = title_step(scale) if top is not None and size_pt > top + 0.01 else None
    return fit_size(text, box, size_pt, scale, slide, size_floor(scale, role), free_floor)


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
    """Группа, в которую идут пункты слайда: названная паттерном, иначе выбранная по слотам.

    Названную группу берём, только когда её блоки есть чем заполнить: ряд цветных полос
    без единого текстового слота останется на слайде пустым оформлением.
    """
    named = {group.id: group for group in pattern.groups}.get(pattern.primary_group_id or "")
    if named is not None and unit_text_slots(named, linked_groups(pattern, named)):
        return named
    return main_group(pattern)


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
