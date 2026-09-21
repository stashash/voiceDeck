"""Подбор паттерна под намерение. Задачи T-07 и T-19."""
import random

import pytest

from designer.contracts import (
    Area, ChartSpec, DesignSystem, Item, Margins, Pattern, RepeatGroup, RepeatUnit,
    Series, SlideIntent, SlideKind, Slot, TextStyle, Tokens, TypeStep,
)
from designer.layout.match import choose_pattern

SLIDE = (9144000, 5143500)
SLIDE_PT = (SLIDE[0] / 12700, SLIDE[1] / 12700)


def _slot(shape_id, role, box, size=18.0, text="образец шаблона"):
    lines = max(1, int(box[3] * SLIDE_PT[1] / (size * 1.2)))
    per_line = max(1, int(box[2] * SLIDE_PT[0] / (size * 0.52)))
    return Slot(id=f"s{shape_id}", role=role, shape_id=shape_id, box=box,
                style=TextStyle(size_pt=size), max_chars=per_line * lines, max_lines=lines,
                sample_text=text)


def _group(gid, count, max_units, unit_slots, step=(0.30, 0.0), size=(0.28, 0.30)):
    units = [RepeatUnit(index=i, box=(0.05 + i * step[0], 0.35, size[0], size[1]), shape_ids=[100 + i])
             for i in range(count)]
    return RepeatGroup(id=gid, direction="row", cols=count, rows=1, step=step, unit_size=size,
                       units=units, unit_slots=unit_slots, max_units=max_units)


def _pattern(pid, kind, confidence=0.8, slots=None, groups=None, areas=None, slide=1):
    return Pattern(id=pid, source_slide=slide, layout_name="макет", kind=kind,
                   kind_confidence=confidence, theme="light",
                   slots=slots if slots is not None else [_slot(1, "title", (0.05, 0.08, 0.6, 0.12), 36)],
                   groups=groups or [], areas=areas or [])


def _ds(patterns):
    tokens = Tokens(colors=[], fonts=[],
                    type_scale=[TypeStep(size_pt=36, role="title", share=0.2),
                                TypeStep(size_pt=18, role="body", share=0.8)],
                    margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05))
    return DesignSystem(id="ds", source_file="shablon.pptx", slide_size_emu=SLIDE,
                        tokens=tokens, patterns=patterns)


def _unit_slots():
    return [_slot(101, "heading", (0.0, 0.0, 0.24, 0.06), 20),
            _slot(102, "body", (0.0, 0.08, 0.24, 0.18), 12)]


def _cards(pid="p002", max_units=6):
    return _pattern(pid, SlideKind.cards, groups=[_group("g1", 3, max_units, _unit_slots())])


def _steps(pid="p003"):
    slots = [_slot(1, "title", (0.05, 0.08, 0.6, 0.12), 36)]
    unit_slots = [_slot(201, "number", (0.0, 0.0, 0.1, 0.06), 28),
                  _slot(202, "heading", (0.0, 0.08, 0.24, 0.06), 20),
                  _slot(203, "body", (0.0, 0.16, 0.24, 0.12), 12)]
    return _pattern(pid, SlideKind.steps, slots=slots,
                    groups=[_group("g1", 4, 6, unit_slots, step=(0.23, 0.0), size=(0.21, 0.30))])


def _title(pid="p001"):
    slots = [_slot(1, "title", (0.05, 0.3, 0.7, 0.16), 44),
             _slot(2, "subtitle", (0.05, 0.5, 0.7, 0.08), 20)]
    return _pattern(pid, SlideKind.title, confidence=0.5, slots=slots)


def _chart(pid="p004"):
    return _pattern(pid, SlideKind.chart, confidence=0.9,
                    areas=[Area(id="a9", kind="chart", box=(0.1, 0.25, 0.8, 0.6), shape_id=9)])


def _items(n):
    return [Item(heading=f"Пункт {i + 1}", body="Короткое пояснение") for i in range(n)]


def test_kind_decides_when_pattern_of_that_kind_exists():
    ds = _ds([_title(), _cards(), _steps(), _chart()])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p002"


def test_missing_kind_falls_back_to_nearest_structure():
    ds = _ds([_title(), _steps(), _chart()])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p003"


def test_item_count_picks_the_roomier_group():
    ds = _ds([_cards("p002", max_units=3), _cards("p005", max_units=6)])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Пять причин", items=_items(5))
    assert choose_pattern(intent, ds, []).id == "p005"


def test_repeat_in_a_row_is_penalised():
    ds = _ds([_title(), _cards(), _steps(), _chart()])
    intent = SlideIntent(id="s2", kind=SlideKind.cards, title="Ещё три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p002"
    assert choose_pattern(intent, ds, ["p002"]).id == "p003"


def test_chart_intent_goes_to_pattern_with_chart_area():
    ds = _ds([_title(), _cards(), _chart()])
    intent = SlideIntent(id="s3", kind=SlideKind.chart, title="Динамика",
                         chart=ChartSpec(type="column", categories=["I", "II"],
                                         series=[Series(name="план", values=[1, 2])]))
    assert choose_pattern(intent, ds, []).id == "p004"


def test_same_input_gives_same_pattern_in_any_order():
    patterns = [_title(), _cards(), _steps(), _chart()]
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    first = choose_pattern(intent, _ds(patterns), [])
    assert choose_pattern(intent, _ds(patterns), []).id == first.id
    shuffled = list(patterns)
    random.Random(7).shuffle(shuffled)
    assert choose_pattern(intent, _ds(shuffled), []).id == first.id


def test_design_system_without_patterns_raises():
    intent = SlideIntent(id="s1", kind=SlideKind.title, title="Заголовок колоды")
    with pytest.raises(ValueError):
        choose_pattern(intent, _ds([]), [])


# ---------- качество подбора: без чужих образцов, заглушек и тесных рамок ----------

def test_pattern_that_holds_on_photos_is_skipped():
    photo = _cards("p002")
    photo.needs_images = True
    ds = _ds([photo, _cards("p005")])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p005"


def test_sample_chart_is_not_taken_for_a_slide_without_one():
    ds = _ds([_cards(), _chart()])
    intent = SlideIntent(id="s1", kind=SlideKind.chart, title="Динамика", items=_items(2))
    assert choose_pattern(intent, ds, []).id == "p002"


def test_big_photo_of_the_sample_is_not_taken():
    photo = _pattern("p002", SlideKind.cards,
                     areas=[Area(id="a9", kind="image", box=(0.5, 0.3, 0.45, 0.5), shape_id=9)],
                     groups=[_group("g1", 3, 6, _unit_slots())])
    ds = _ds([photo, _cards("p005")])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p005"


def test_photo_placeholder_does_not_forbid_the_pattern():
    stub = _pattern("p002", SlideKind.cards,
                    areas=[Area(id="a9", kind="image", box=(0.5, 0.3, 0.45, 0.5), shape_id=9,
                                placeholder=True)],
                    groups=[_group("g1", 3, 6, _unit_slots())])
    ds = _ds([stub, _cards("p005", max_units=3)])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p002"


def test_exact_number_of_blocks_beats_reflow():
    six = _pattern("p005", SlideKind.cards,
                   groups=[_group("g1", 6, 6, _unit_slots(), step=(0.15, 0.0), size=(0.14, 0.30))])
    ds = _ds([_cards("p002", max_units=6), six])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p002"


def test_block_with_one_slot_loses_to_a_block_with_two():
    one = _pattern("p002", SlideKind.cards,
                   groups=[_group("g1", 3, 6, [_slot(101, "heading", (0.0, 0.0, 0.24, 0.06), 20)])])
    ds = _ds([one, _cards("p005")])
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Три причины", items=_items(3))
    assert choose_pattern(intent, ds, []).id == "p005"


def test_block_with_one_slot_fits_items_without_a_heading():
    one = _pattern("p002", SlideKind.cards,
                   groups=[_group("g1", 3, 6, [_slot(101, "heading", (0.0, 0.0, 0.24, 0.06), 20)])])
    ds = _ds([one, _cards("p005")])
    items = [Item(body=f"Пункт {i + 1} без заголовка") for i in range(3)]
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Что дальше", items=items)
    assert choose_pattern(intent, ds, []).id == "p002"


def test_big_number_needs_a_number_slot():
    numbered = _pattern("p005", SlideKind.cards,
                        slots=[_slot(1, "title", (0.05, 0.08, 0.6, 0.12), 36),
                               _slot(7, "number", (0.05, 0.35, 0.4, 0.3), 72)])
    ds = _ds([_cards("p002"), numbered])
    intent = SlideIntent(id="s1", kind=SlideKind.big_number, title="Сколько это занимает",
                         items=[Item(number="5", heading="минут на колоду")])
    assert choose_pattern(intent, ds, []).id == "p005"


def test_final_slide_avoids_blocks_and_visualisation():
    ds = _ds([_title(), _cards(), _chart()])
    intent = SlideIntent(id="s8", kind=SlideKind.thanks, title="Спасибо за внимание")
    assert choose_pattern(intent, ds, []).id == "p001"


def test_visualisation_needs_room_on_the_slide():
    tight = _pattern("p005", SlideKind.chart, confidence=0.9,
                     slots=[_slot(1, "title", (0.05, 0.05, 0.9, 0.8), 36)])
    ds = _ds([_cards("p002"), tight])
    intent = SlideIntent(id="s1", kind=SlideKind.chart, title="Динамика",
                         chart=ChartSpec(type="column", categories=["I", "II"],
                                         series=[Series(name="план", values=[1, 2])]))
    assert choose_pattern(intent, ds, []).id == "p002"
