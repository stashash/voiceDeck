"""Три варианта вёрстки одного плана и правило подбора паттерна под вариант. Владелец: задача T-12.

Вариант это детерминированное преобразование намерений плюс список уже занятых id паттернов
(``used``), который передаётся в choose_pattern: чем он длиннее, тем сильнее штраф за повтор
и тем заметнее вариант отличается от соседних на глаз. Живых вызовов модели здесь нет: все
три варианта строятся из одного уже готового плана.
"""
from __future__ import annotations

import re

from designer.contracts import ChartSpec, DeckPlan, DesignSystem, Item, Series, SlideIntent, SlideKind

VARIANT_AXES: dict[str, str] = {
    "a": "как в шаблоне: план как есть, паттерн подбирается по точному числу блоков",
    "b": "плотнее: соседние слайды с одной мыслью сведены в один, карточек на слайде больше",
    "c": "данные вперёд: числа становятся крупной цифрой, диаграммой или таблицей раньше текста",
}
"""Обоснование оси различий одной фразой на вариант: попадает в run.json."""

_MERGEABLE_KINDS = (SlideKind.bullets, SlideKind.cards, SlideKind.steps, SlideKind.agenda)
_MERGE_MAX_ITEMS = 2
"""Слайд с таким и меньшим числом пунктов можно слить с соседним той же природы."""

_DEFAULT_CAPACITY = 6
"""Предел блоков на слайде, когда паттернов этого типа в дизайн-системе ещё нет."""

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def make_variants(plan: DeckPlan, ds: DesignSystem) -> dict[str, DeckPlan]:
    """План брифа -> три варианта: `a` как есть, `b` плотнее, `c` данные вперёд."""
    return {
        "a": plan.model_copy(deep=True),
        "b": _denser(plan, ds),
        "c": _data_first(plan),
    }


def variant_used_seed(variant: str, chosen_by_a: list[str]) -> list[str]:
    """Стартовый список занятых паттернов для choose_pattern при сборке слайдов варианта.

    `c` начинает с паттернов, уже выбранных вариантом `a`: choose_pattern штрафует их
    повтор, и вид `c` заметно отличается от `a`. `a` и `b` начинают с пустого списка.
    """
    if variant == "c":
        return list(chosen_by_a)
    return []


# ---------- b: плотнее ----------

def _pattern_capacity_for(ds: DesignSystem, kind: SlideKind) -> int:
    caps = [group.max_units for pattern in ds.patterns if pattern.kind == kind for group in pattern.groups]
    return max(caps) if caps else _DEFAULT_CAPACITY


def _mergeable(intent: SlideIntent) -> bool:
    return (intent.kind in _MERGEABLE_KINDS and intent.chart is None and intent.table is None
            and 0 < len(intent.items) <= _MERGE_MAX_ITEMS)


def _merge(first: SlideIntent, second: SlideIntent) -> SlideIntent:
    notes = " ".join(part for part in (first.notes, second.notes) if part)
    return first.model_copy(update={
        "items": [*first.items, *second.items],
        "key_message": first.key_message or second.key_message,
        "notes": notes,
    })


def _denser(plan: DeckPlan, ds: DesignSystem) -> DeckPlan:
    slides: list[SlideIntent] = []
    for intent in plan.slides:
        prev = slides[-1] if slides else None
        if (prev is not None and _mergeable(prev) and _mergeable(intent) and prev.kind == intent.kind
                and len(prev.items) + len(intent.items) <= _pattern_capacity_for(ds, intent.kind)):
            slides[-1] = _merge(prev, intent)
        else:
            slides.append(intent.model_copy(deep=True))
    return plan.model_copy(update={"slides": slides})


# ---------- c: данные вперёд ----------

def _numeric_value(raw: str) -> float | None:
    match = _NUMBER_RE.search(raw)
    return float(match.group().replace(",", ".")) if match else None


def _chart_from_items(title: str, items: list[Item]) -> ChartSpec | None:
    categories: list[str] = []
    values: list[float] = []
    for item in items:
        value = _numeric_value(item.number or "")
        if value is None:
            return None
        categories.append(item.heading or item.number or "")
        values.append(value)
    return ChartSpec(type="column", title=title, categories=categories,
                      series=[Series(name=title or "значение", values=values)])


def _slide_data_first(intent: SlideIntent) -> SlideIntent:
    if intent.chart is not None or intent.table is not None:
        return intent.model_copy(deep=True)
    numbered = [item for item in intent.items if item.number]
    if len(numbered) == 1 and len(intent.items) == 1:
        return intent.model_copy(update={"kind": SlideKind.big_number})
    if len(numbered) >= 2:
        chart = _chart_from_items(intent.title, numbered)
        if chart is not None:
            return intent.model_copy(update={"kind": SlideKind.chart, "chart": chart})
    return intent.model_copy(deep=True)


def _data_first(plan: DeckPlan) -> DeckPlan:
    return plan.model_copy(update={"slides": [_slide_data_first(intent) for intent in plan.slides]})
