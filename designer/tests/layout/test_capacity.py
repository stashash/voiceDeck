"""Вместимость слотов при перекладке блоков. Задача T-07."""
from designer.contracts import (
    Pattern, RepeatGroup, RepeatUnit, SlideKind, Slot, TextStyle, TypeStep,
)
from designer.layout.capacity import box_capacity, fit_size, main_group, slide_pt, slot_limits

SLIDE = (9144000, 5143500)
SLIDE_PT = slide_pt(SLIDE)
SCALE = [TypeStep(size_pt=36, role="title", share=0.2),
         TypeStep(size_pt=24, role="heading", share=0.2),
         TypeStep(size_pt=18, role="body", share=0.4),
         TypeStep(size_pt=12, role="caption", share=0.2)]


def _slot(shape_id, role, box, size=18.0):
    chars, lines = box_capacity(box, size, SLIDE_PT)
    return Slot(id=f"s{shape_id}", role=role, shape_id=shape_id, box=box,
                style=TextStyle(size_pt=size), max_chars=chars, max_lines=lines,
                sample_text="образец шаблона")


def _pattern(count=3, max_units=4, step=(0.30, 0.0), size=(0.28, 0.30)):
    units = [RepeatUnit(index=i, box=(0.05 + i * step[0], 0.35, size[0], size[1]), shape_ids=[100 + i])
             for i in range(count)]
    group = RepeatGroup(id="g1", direction="row", cols=count, rows=1, step=step, unit_size=size,
                        units=units, max_units=max_units,
                        unit_slots=[_slot(101, "heading", (0.0, 0.0, 0.26, 0.06), 20),
                                    _slot(102, "body", (0.0, 0.08, 0.26, 0.18), 12)])
    return Pattern(id="p001", source_slide=1, layout_name="макет", kind=SlideKind.cards,
                   kind_confidence=0.8, theme="light",
                   slots=[_slot(1, "title", (0.05, 0.08, 0.6, 0.12), 36)], groups=[group])


def test_box_capacity_counts_lines_and_chars():
    chars, lines = box_capacity((0.0, 0.0, 0.5, 0.2), 18.0, SLIDE_PT)
    assert lines == 3
    assert chars == 38 * 3


def test_fewer_units_means_roomier_slots():
    pattern = _pattern()
    wide = slot_limits(pattern, 2)
    narrow = slot_limits(pattern, 4)
    assert wide["s101"] > slot_limits(pattern, 3)["s101"] > narrow["s101"]
    assert wide["s102"] > narrow["s102"]


def test_slots_outside_groups_keep_their_capacity():
    pattern = _pattern()
    assert slot_limits(pattern, 2)["s1"] == pattern.slots[0].max_chars


def test_count_beyond_the_grid_is_clamped():
    pattern = _pattern()
    assert slot_limits(pattern, 99) == slot_limits(pattern, 4)
    assert slot_limits(pattern, 0) == slot_limits(pattern, 1)


def test_pattern_without_groups_returns_own_slots():
    pattern = _pattern()
    pattern.groups = []
    assert slot_limits(pattern, 3) == {"s1": pattern.slots[0].max_chars}
    assert main_group(pattern) is None


def test_font_steps_down_until_text_fits():
    box = (0.05, 0.1, 0.4, 0.12)
    text = "и" * 200
    assert fit_size(text, box, 36.0, SCALE, SLIDE_PT) < 36.0
    assert fit_size("коротко", box, 36.0, SCALE, SLIDE_PT) == 36.0


def test_font_never_goes_below_the_smallest_step():
    box = (0.05, 0.1, 0.2, 0.06)
    assert fit_size("и" * 5000, box, 36.0, SCALE, SLIDE_PT) == 12.0
