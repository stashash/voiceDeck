"""Подбор слайда-образца под намерение. Владелец: задача T-07.

Выбор детерминированный: один и тот же вход даёт один и тот же паттерн независимо
от порядка паттернов в дизайн-системе.
"""
from __future__ import annotations

from designer.contracts import DesignSystem, Pattern, SlideIntent, SlideKind
from designer.layout.capacity import main_group

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

W_KIND = 3.0
W_UNITS = 2.0
W_VIZ = 1.5
W_TITLE = 0.6
W_CONFIDENCE = 0.5
P_REPEAT = 0.8
P_REPEAT_LAST = 2.5


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
    if n_items <= 0:
        # Паттерн с блоками под слайд без пунктов годится, но хуже простого.
        return 1.0 if not pattern.groups else 0.45
    best = 0.0
    for group in pattern.groups:
        if group.min_units <= n_items <= group.max_units:
            best = max(best, 1.0)
        elif n_items > group.max_units:
            best = max(best, group.max_units / n_items)
        else:
            best = max(best, n_items / group.min_units)
    free = _item_slots(pattern)
    if free:
        best = max(best, 0.45 if free >= n_items else 0.45 * free / n_items)
    return best


def _viz_score(pattern: Pattern, intent: SlideIntent) -> float:
    kinds = {area.kind for area in pattern.areas}
    want = "chart" if intent.chart is not None else "table" if intent.table is not None else None
    if want is None:
        # Место под диаграмму или таблицу пустым не оставляют.
        return 0.5 if kinds & {"chart", "table"} else 1.0
    if want in kinds:
        return 1.0
    if kinds & {"chart", "table"}:
        return 0.8
    if "image" in kinds:
        return 0.7
    if main_group(pattern) is not None:
        return 0.5
    return 0.3 if _item_slots(pattern) else 0.1


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


def score_pattern(intent: SlideIntent, pattern: Pattern, used: list[str]) -> float:
    """Оценка кандидата: тип, вместимость блоков, место под визуализацию, уверенность, повтор."""
    total = (
        W_KIND * _kind_score(intent.kind, pattern.kind)
        + W_UNITS * _units_score(pattern, len(intent.items))
        + W_VIZ * _viz_score(pattern, intent)
        + W_TITLE * _title_score(pattern, intent)
        + W_CONFIDENCE * pattern.kind_confidence
        - _penalty(pattern, used)
    )
    return round(total, 6)


def choose_pattern(intent: SlideIntent, ds: DesignSystem, used: list[str] | None = None) -> Pattern:
    """Паттерн шаблона под намерение. При равных оценках побеждает меньший id."""
    if not ds.patterns:
        raise ValueError("в дизайн-системе нет ни одного паттерна")
    seen = list(used or [])
    return min(ds.patterns, key=lambda p: (-score_pattern(intent, p, seen), p.id))
