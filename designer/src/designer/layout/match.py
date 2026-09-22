"""Подбор слайда-образца под намерение. Владелец: задача T-07.

Выбор детерминированный: один и тот же вход даёт один и тот же паттерн независимо
от порядка паттернов в дизайн-системе.
"""
from __future__ import annotations

from designer.contracts import DesignSystem, Item, Pattern, RepeatGroup, SlideIntent, SlideKind
from designer.layout.capacity import (
    unit_count,
    content_region,
    lead_number,
    line_capacity,
    linked_groups,
    main_group,
    primary_group,
    slide_pt,
    title_step,
    unit_text_slots,
)
from designer.parse import geometry as geo

# Семьи типов: внутри семьи замена читается естественно.
_FAMILIES: tuple[tuple[SlideKind, ...], ...] = (
    (SlideKind.cards, SlideKind.steps, SlideKind.bullets, SlideKind.agenda,
     SlideKind.timeline, SlideKind.team, SlideKind.compare),
    (SlideKind.title, SlideKind.section, SlideKind.thanks, SlideKind.cta),
    (SlideKind.big_number, SlideKind.quote),
    (SlideKind.chart, SlideKind.table),
    (SlideKind.image_text, SlideKind.code),
)

# Ближайшая замена по структуре, когда образца нужного типа в шаблоне нет.
_NEAR: dict[SlideKind, tuple[SlideKind, ...]] = {
    SlideKind.cards: (SlideKind.steps, SlideKind.bullets, SlideKind.timeline,
                      SlideKind.compare, SlideKind.agenda, SlideKind.team),
    SlideKind.steps: (SlideKind.timeline, SlideKind.cards, SlideKind.bullets, SlideKind.agenda),
    SlideKind.bullets: (SlideKind.agenda, SlideKind.cards, SlideKind.steps),
    SlideKind.agenda: (SlideKind.bullets, SlideKind.cards, SlideKind.steps),
    SlideKind.timeline: (SlideKind.steps, SlideKind.cards, SlideKind.bullets),
    SlideKind.team: (SlideKind.cards, SlideKind.image_text),
    SlideKind.compare: (SlideKind.cards, SlideKind.bullets, SlideKind.table),
    SlideKind.title: (SlideKind.section, SlideKind.cta, SlideKind.thanks),
    SlideKind.section: (SlideKind.title, SlideKind.thanks, SlideKind.cta),
    SlideKind.thanks: (SlideKind.cta, SlideKind.section, SlideKind.title),
    SlideKind.cta: (SlideKind.thanks, SlideKind.section, SlideKind.title),
    SlideKind.big_number: (SlideKind.quote, SlideKind.section, SlideKind.cards),
    SlideKind.quote: (SlideKind.big_number, SlideKind.section, SlideKind.image_text),
    SlideKind.chart: (SlideKind.table, SlideKind.image_text, SlideKind.cards),
    SlideKind.table: (SlideKind.chart, SlideKind.cards, SlideKind.bullets),
    SlideKind.image_text: (SlideKind.cards, SlideKind.quote, SlideKind.section),
    SlideKind.code: (SlideKind.image_text, SlideKind.bullets, SlideKind.table),
    SlideKind.other: (),
}

_ITEM_ROLES = ("body", "heading", "caption", "label")
_TITLE_ROLES = ("title", "heading")
_SAMPLE_KINDS = ("chart", "table", "image")

# Слайды, которые несут одну мысль: блоки и визуализация на них лишние.
_PLAIN_KINDS = (SlideKind.title, SlideKind.section, SlideKind.thanks)

W_KIND = 3.0
W_UNITS = 2.0
W_VIZ = 1.5
W_TITLE = 0.6
W_CONFIDENCE = 0.5
P_REPEAT = 0.8
P_REPEAT_LAST = 2.5
P_UNIT_SLOTS = 1.0
P_NUMBER_FIT = 1.2
P_EMPTY_UNITS = 2.0
P_LOST_ITEMS = 2.0

VIZ_ROOM = 0.4
"""Доля слайда, с которой свободной рамки хватает под диаграмму или таблицу."""

SAMPLE_MIN = 0.05
"""Доля слайда, с которой картинка образца читается содержанием, а не значком."""

SAMPLE_TOTAL = 0.15
"""Доля слайда под мелкими картинками, с которой слайд держится на них целиком."""

REFLOW_FREE = 2
"""На сколько блоков перекладка ещё дёшева."""


def _family(kind: SlideKind) -> tuple[SlideKind, ...]:
    for family in _FAMILIES:
        if kind in family:
            return family
    return ()


def _kind_score(want: SlideKind, have: SlideKind) -> float:
    if want is have:
        return 1.0
    near = _NEAR.get(want, ())
    if have in near:
        return 0.7 - 0.08 * near.index(have)
    if have in _family(want):
        return 0.35
    return 0.1


def _item_slots(pattern: Pattern) -> int:
    return sum(1 for slot in pattern.slots if slot.role in _ITEM_ROLES)


def _units_score(pattern: Pattern, n_items: int) -> float:
    """Совпадение числа блоков. Точное ценится выше перекладки, дальняя перекладка штрафуется."""
    if n_items <= 0:
        # Паттерн с блоками под слайд без пунктов годится, но хуже простого.
        return 1.0 if not pattern.groups else 0.45
    best = 0.0
    for group in pattern.groups:
        if len(group.units) == n_items:
            best = max(best, 1.0)
        elif group.min_units <= n_items <= group.max_units:
            near = abs(len(group.units) - n_items) <= REFLOW_FREE
            best = max(best, 0.85 if near else 0.55)
        elif n_items > group.max_units:
            best = max(best, 0.4 * group.max_units / n_items)
        else:
            best = max(best, 0.4 * n_items / group.min_units)
    free = _item_slots(pattern)
    if free:
        best = max(best, 0.45 if free >= n_items else 0.45 * free / n_items)
    return best


def _viz_score(pattern: Pattern, intent: SlideIntent, ds: DesignSystem | None = None) -> float:
    kinds = {area.kind for area in pattern.areas}
    want = "chart" if intent.chart is not None else "table" if intent.table is not None else None
    if want is None:
        # Место под диаграмму или таблицу пустым не оставляют.
        return 0.5 if kinds & {"chart", "table"} else 1.0
    if want in kinds:
        return 1.0
    if kinds & {"chart", "table"}:
        return 0.8
    if ds is not None:
        # Своей области нет: чем просторнее место содержимого, тем крупнее встанет визуализация.
        return min(1.0, 0.4 + geo.area(content_region(pattern, ds.tokens.margins)))
    if "image" in kinds:
        return 0.7
    if main_group(pattern) is not None:
        return 0.5
    return 0.3 if _item_slots(pattern) else 0.1


def _samples(pattern: Pattern) -> set[str]:
    """Образцы шаблона, которые без своего содержания останутся на слайде чужими.

    Одна мелкая картинка это значок оформления. Но когда такой мелочи набирается
    на шестую часть слайда, слайд держится на ней, и своё содержание там не разместить.
    """
    areas = [a for a in (*pattern.areas, *(a for g in pattern.groups for a in g.unit_areas))
             if a.kind in _SAMPLE_KINDS and not a.placeholder]
    out = {a.kind for a in areas if a.kind != "image" or geo.area(a.box) >= SAMPLE_MIN}
    if sum(geo.area(a.box) for a in areas if a.kind == "image") >= SAMPLE_TOTAL:
        out.add("image")
    return out


def _viz_room(pattern: Pattern, ds: DesignSystem) -> bool:
    """Остаётся ли после удаления блоков и образцов рамка под диаграмму или таблицу."""
    return geo.area(content_region(pattern, ds.tokens.margins)) >= VIZ_ROOM


def _units_collide(group: RepeatGroup) -> bool:
    """Наезжают ли блоки группы друг на друга: перекладка такой сетки наезд только повторит."""
    boxes = [unit.box for unit in group.units]
    return any(
        geo.overlap(boxes[a], boxes[b]) > 0
        for a in range(len(boxes)) for b in range(a + 1, len(boxes))
    )


def _fit_penalty(pattern: Pattern, items: list[Item]) -> float:
    """Штраф за блок, который не вмещает пункт по слотам.

    Пункту с заголовком и пояснением нужны два текстовых слота: в блоке с одним слотом
    они сойдутся в одну строку. Блок с одним слотом годится пунктам без заголовка.
    """
    group = primary_group(pattern)
    if group is None or not items:
        return 0.0
    if not any(item.heading and item.body for item in items):
        return 0.0
    slots = unit_text_slots(group, linked_groups(pattern, group))
    return 0.0 if len(slots) >= 2 else P_UNIT_SLOTS


def _number_slot(pattern: Pattern) -> bool:
    """Есть ли на слайде место под крупное число."""
    return (any(slot.role == "number" for slot in pattern.slots)
            or any(slot.role == "number" for g in pattern.groups for slot in g.unit_slots))


def _number_penalty(pattern: Pattern, intent: SlideIntent, ds: DesignSystem | None) -> float:
    """Штраф за слот, в который число намерения не встаёт даже на ступени title."""
    value = lead_number(intent)
    slots = [slot for slot in pattern.slots if slot.role == "number"]
    if not value or ds is None or not slots:
        return 0.0
    floor = title_step(ds.tokens.type_scale)
    if not floor:
        return 0.0
    room = line_capacity(slots[0].box, floor, slide_pt(ds.slide_size_emu))
    return 0.0 if room >= len(value) else P_NUMBER_FIT


def _empty_units_penalty(pattern: Pattern, intent: SlideIntent) -> float:
    """Штраф за блоки, которые заполнить нечем: ни своих текстовых слотов, ни связанных."""
    group = primary_group(pattern)
    if not intent.items or group is None:
        return 0.0
    return 0.0 if unit_text_slots(group, linked_groups(pattern, group)) else P_EMPTY_UNITS


def _holds_items(pattern: Pattern, intent: SlideIntent) -> bool:
    """Есть ли куда положить пункты намерения: блок с текстовым слотом или свободные слоты.

    Слот под заголовок слайда и слот под ключевую мысль пункты не принимают, они заняты.
    Паттерн раздела с одной строкой съедает список молча, поэтому годным он не считается.
    """
    if not intent.items:
        return True
    group = primary_group(pattern)
    if group is not None and unit_text_slots(group, linked_groups(pattern, group)):
        return True
    taken = 1 if intent.key_message else 0
    places = _item_slots(pattern) + (1 if _number_slot(pattern) else 0)
    return places > taken


def fits(intent: SlideIntent, pattern: Pattern, ds: DesignSystem) -> bool:
    """Годится ли паттерн под намерение. Негодный берут, только когда годных нет совсем."""
    if pattern.needs_images:
        return False  # паттерн держится на фото, а своих картинок у намерения нет
    if intent.kind in _PLAIN_KINDS and (pattern.groups or _samples(pattern)):
        return False
    if intent.kind is SlideKind.big_number and not _number_slot(pattern):
        return False
    want = "chart" if intent.chart is not None else "table" if intent.table is not None else None
    if want is None:
        if _samples(pattern):
            return False  # чужой образец останется на слайде
    elif _samples(pattern) - {want} or not _viz_room(pattern, ds):
        return False
    if not _holds_items(pattern, intent):
        return False
    group = primary_group(pattern)
    if group is None or not intent.items:
        return True
    if _painted_units(pattern, ds) and unit_count(group, len(intent.items)) != len(group.units):
        return False  # подложки блоков нарисованы в картинке макета: лишний блок с неё не убрать
    return bool(unit_text_slots(group, linked_groups(pattern, group))) and not _units_collide(group)


def _painted_units(pattern: Pattern, ds: DesignSystem) -> bool:
    """Макет паттерна несёт картинку на весь кадр: подложки и номера блоков могут быть нарисованы в ней."""
    layout = next((l for l in ds.layouts if l.name == pattern.layout_name), None)
    return layout is not None and layout.full_bleed_picture


def _title_score(pattern: Pattern, intent: SlideIntent) -> float:
    if not intent.title:
        return 1.0
    return 1.0 if any(slot.role in _TITLE_ROLES for slot in pattern.slots) else 0.0


def _penalty(pattern: Pattern, used: list[str]) -> float:
    if not used:
        return 0.0
    if used[-1] == pattern.id:
        return P_REPEAT_LAST
    return P_REPEAT * used.count(pattern.id)


def score_pattern(
    intent: SlideIntent, pattern: Pattern, used: list[str], ds: DesignSystem | None = None
) -> float:
    """Оценка кандидата: тип, вместимость блоков, место под визуализацию, уверенность, повтор."""
    total = (
        W_KIND * _kind_score(intent.kind, pattern.kind)
        + W_UNITS * _units_score(pattern, len(intent.items))
        + W_VIZ * _viz_score(pattern, intent, ds)
        + W_TITLE * _title_score(pattern, intent)
        + W_CONFIDENCE * pattern.kind_confidence
        - _fit_penalty(pattern, intent.items)
        - _number_penalty(pattern, intent, ds)
        - _empty_units_penalty(pattern, intent)
        - (0.0 if _holds_items(pattern, intent) else P_LOST_ITEMS)
        - _penalty(pattern, used)
    )
    return round(total, 6)


def choose_pattern(intent: SlideIntent, ds: DesignSystem, used: list[str] | None = None) -> Pattern:
    """Паттерн шаблона под намерение. При равных оценках побеждает меньший id."""
    if not ds.patterns:
        raise ValueError("в дизайн-системе нет ни одного паттерна")
    seen = list(used or [])
    suitable = [p for p in ds.patterns if fits(intent, p, ds)]
    return min(suitable or ds.patterns, key=lambda p: (-score_pattern(intent, p, seen, ds), p.id))
