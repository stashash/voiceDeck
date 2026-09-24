"""Три варианта одного плана и штраф за паттерн, уже занятый вариантом `a`. Задача T-12."""
from __future__ import annotations

from designer.contracts import (
    Area, DeckPlan, DesignSystem, Item, Margins, Pattern, RepeatGroup, RepeatUnit,
    SlideIntent, SlideKind, Slot, TextStyle, Tokens, TypeStep,
)
from designer.layout.match import choose_pattern
from designer.layout.variants import VARIANT_AXES, make_variants, variant_used_seed

SLIDE = (9144000, 5143500)
SLIDE_PT = (SLIDE[0] / 12700, SLIDE[1] / 12700)


def _slot(shape_id, role, box, size=18.0):
    lines = max(1, int(box[3] * SLIDE_PT[1] / (size * 1.2)))
    per_line = max(1, int(box[2] * SLIDE_PT[0] / (size * 0.52)))
    return Slot(id=f"s{shape_id}", role=role, shape_id=shape_id, box=box,
                style=TextStyle(size_pt=size), max_chars=per_line * lines, max_lines=lines)


def _unit_slots():
    return [_slot(101, "heading", (0.0, 0.0, 0.24, 0.06), 20),
            _slot(102, "body", (0.0, 0.08, 0.24, 0.18), 12)]


def _group(gid, count, max_units, step=(0.30, 0.0), size=(0.28, 0.30)):
    units = [RepeatUnit(index=i, box=(0.05 + i * step[0], 0.35, size[0], size[1]), shape_ids=[100 + i])
             for i in range(count)]
    return RepeatGroup(id=gid, direction="row", cols=count, rows=1, step=step, unit_size=size,
                        units=units, unit_slots=_unit_slots(), max_units=max_units)


def _pattern(pid, kind, slots=None, groups=None, areas=None):
    return Pattern(id=pid, source_slide=1, layout_name="макет", kind=kind, kind_confidence=0.8,
                   theme="light",
                   slots=slots if slots is not None else [_slot(1, "title", (0.05, 0.08, 0.6, 0.12), 36)],
                   groups=groups or [], areas=areas or [])


def _ds(patterns):
    tokens = Tokens(colors=[], fonts=[],
                     type_scale=[TypeStep(size_pt=36, role="title", share=0.2),
                                 TypeStep(size_pt=18, role="body", share=0.8)],
                     margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05))
    return DesignSystem(id="ds", source_file="shablon.pptx", slide_size_emu=SLIDE,
                         tokens=tokens, patterns=patterns)


def _title():
    return _pattern("p_title", SlideKind.title, slots=[_slot(1, "title", (0.05, 0.3, 0.7, 0.16), 44)])


def _thanks():
    return _pattern("p_thanks", SlideKind.thanks, slots=[_slot(1, "title", (0.05, 0.3, 0.7, 0.16), 44)])


def _bullets(pid="p_bullets", max_units=4):
    return _pattern(pid, SlideKind.bullets, groups=[_group("g1", 3, max_units)])


def _chart():
    return _pattern("p_chart", SlideKind.chart,
                     areas=[Area(id="a1", kind="chart", box=(0.1, 0.25, 0.8, 0.6), shape_id=9)])


def _plan() -> DeckPlan:
    slides = [
        SlideIntent(id="s1", kind=SlideKind.title, title="Итоги квартала"),
        SlideIntent(id="s2", kind=SlideKind.bullets, title="Проблема",
                    items=[Item(heading="Запись", body="Долго ждут ответа")]),
        SlideIntent(id="s3", kind=SlideKind.bullets, title="Решение",
                    items=[Item(heading="Бот", body="Отвечает мгновенно")]),
        SlideIntent(id="s4", kind=SlideKind.bullets, title="Рост конверсии",
                    items=[Item(number="12", heading="было"), Item(number="20", heading="стало"),
                           Item(number="35", heading="цель")]),
        SlideIntent(id="s5", kind=SlideKind.thanks, title="Спасибо"),
    ]
    return DeckPlan(title="План", purpose="показать эффект", audience="регистратура", slides=slides)


def _choose_all(slides: list[SlideIntent], ds: DesignSystem, seed: list[str]) -> list[str]:
    used = list(seed)
    ids: list[str] = []
    for intent in slides:
        pattern = choose_pattern(intent, ds, used)
        used.append(pattern.id)
        ids.append(pattern.id)
    return ids


def test_three_variants_differ_by_patterns_or_slide_count():
    ds = _ds([_title(), _bullets(), _chart(), _thanks()])
    variants = make_variants(_plan(), ds)

    assert set(variants) == {"a", "b", "c"}
    chosen_a = _choose_all(variants["a"].slides, ds, variant_used_seed("a", []))
    chosen_c = _choose_all(variants["c"].slides, ds, variant_used_seed("c", chosen_a))

    assert len(variants["b"].slides) != len(variants["a"].slides) or chosen_c != chosen_a


def test_variant_b_merges_short_neighbours_and_is_not_longer():
    ds = _ds([_title(), _bullets(), _chart(), _thanks()])
    variants = make_variants(_plan(), ds)

    assert len(variants["b"].slides) <= len(variants["a"].slides)
    assert len(variants["b"].slides) < len(variants["a"].slides)  # s2 и s3 одной природы слиты
    merged = variants["b"].slides[1]
    assert len(merged.items) == 2


def test_variant_c_has_at_least_as_many_data_slides_as_a():
    ds = _ds([_title(), _bullets(), _chart(), _thanks()])
    variants = make_variants(_plan(), ds)

    data_kinds = {SlideKind.big_number, SlideKind.chart, SlideKind.table}
    count_a = sum(1 for s in variants["a"].slides if s.kind in data_kinds)
    count_c = sum(1 for s in variants["c"].slides if s.kind in data_kinds)

    assert count_c >= count_a
    assert count_c > count_a  # s4 с сопоставимыми числами стала диаграммой


def test_variant_used_seed_only_penalises_c():
    assert variant_used_seed("a", ["p1", "p2"]) == []
    assert variant_used_seed("b", ["p1", "p2"]) == []
    assert variant_used_seed("c", ["p1", "p2"]) == ["p1", "p2"]


def test_seed_from_variant_a_changes_pattern_choice_for_c():
    twin = _bullets("p_bullets_twin", max_units=4)
    ds = _ds([_title(), _bullets(), twin, _chart(), _thanks()])
    variants = make_variants(_plan(), ds)

    used_by_a = _choose_all(variants["a"].slides, ds, variant_used_seed("a", []))

    intent_c = variants["c"].slides[1]  # та же природа, что и s2 варианта a
    without_seed = choose_pattern(intent_c, ds, variant_used_seed("a", used_by_a)).id
    with_seed = choose_pattern(intent_c, ds, variant_used_seed("c", used_by_a)).id

    assert without_seed == "p_bullets"
    assert with_seed != without_seed


def test_variant_axes_have_one_phrase_each():
    assert set(VARIANT_AXES) == {"a", "b", "c"}
    assert all(phrase for phrase in VARIANT_AXES.values())
