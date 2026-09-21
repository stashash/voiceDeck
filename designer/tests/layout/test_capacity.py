"""Вместимость слотов при перекладке блоков. Задачи T-07, T-19 и T-22."""
from designer.contracts import (
    Margins, Pattern, RepeatGroup, RepeatUnit, SlideKind, Slot, TextStyle, TypeStep,
)
from designer.layout.capacity import (
    box_capacity, content_region, fit_size, free_box, head_top, line_capacity, linked_groups,
    main_group, primary_group, size_floor, slide_pt, slot_limits, slot_size, text_lines,
    title_step, unit_boxes, unit_text_slots, word_size,
)

SLIDE = (9144000, 5143500)
SLIDE_PT = slide_pt(SLIDE)
SCALE = [TypeStep(size_pt=36, role="title", share=0.2),
         TypeStep(size_pt=24, role="heading", share=0.2),
         TypeStep(size_pt=18, role="body", share=0.4),
         TypeStep(size_pt=12, role="caption", share=0.2)]
MARGINS = Margins(left=0.05, top=0.06, right=0.05, bottom=0.07)


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


# ---------- решения вёрстки: место содержимого, свободная рамка, кегль заголовка ----------

def test_content_region_starts_below_the_title():
    region = content_region(_pattern(), MARGINS)
    assert region[0] == MARGINS.left
    assert region[1] > 0.20  # заголовок образца кончается на 0,20
    assert round(region[1] + region[3], 6) == round(1 - MARGINS.bottom, 6)
    assert round(region[0] + region[2], 6) == round(1 - MARGINS.right, 6)


def test_content_region_of_a_slide_without_a_title_starts_at_the_margin():
    pattern = _pattern()
    pattern.slots = []
    assert content_region(pattern, MARGINS)[1] == MARGINS.top


def test_free_box_goes_around_a_filled_slot():
    box = free_box((0.05, 0.30, 0.90, 0.60), [(0.05, 0.30, 0.90, 0.10)])
    assert box is not None
    assert abs(box[1] - 0.40) < 1e-9 and abs(box[3] - 0.50) < 1e-9


def test_free_box_takes_the_roomiest_part():
    box = free_box((0.0, 0.0, 1.0, 1.0), [(0.0, 0.0, 0.3, 1.0)])
    assert box is not None and abs(box[2] - 0.7) < 1e-9


def test_free_box_is_none_when_the_place_is_busy():
    assert free_box((0.05, 0.30, 0.90, 0.60), [(0.0, 0.0, 1.0, 1.0)]) is None


def test_heading_stops_at_its_own_step_of_the_scale():
    box = (0.05, 0.1, 0.2, 0.06)
    assert size_floor(SCALE, "heading") == 24.0
    assert size_floor(SCALE, "body") is None
    assert fit_size("и" * 5000, box, 36.0, SCALE, SLIDE_PT, size_floor(SCALE, "heading")) == 24.0


def test_step_above_the_current_size_does_not_hold_the_font():
    scale = [TypeStep(size_pt=36, role="title", share=0.5), TypeStep(size_pt=18, role="body", share=0.5)]
    assert size_floor(scale, "heading") == 36.0
    assert fit_size("и" * 500, (0.05, 0.1, 0.2, 0.06), 20.0, scale, SLIDE_PT, 36.0) == 18.0


# ---------- подгонка по слову и промежуточный кегль ----------

WORD = "Согласование"
"""Слово из двенадцати знаков: при крупном кегле оно шире рамки разделителя."""


def test_font_fits_the_longest_word_in_the_width():
    box = (0.05, 0.30, 0.30, 0.20)
    size = fit_size(WORD, box, 80.0, SCALE, SLIDE_PT)
    assert size < 80.0
    assert size <= word_size(WORD, box, SLIDE_PT)
    assert line_capacity(box, size, SLIDE_PT) >= len(WORD)


def test_big_slot_gets_a_size_between_the_steps():
    scale = [TypeStep(size_pt=28, role="title", share=0.3),
             TypeStep(size_pt=18, role="body", share=0.4),
             TypeStep(size_pt=12, role="caption", share=0.3)]
    box = (0.05, 0.30, 0.30, 0.20)
    size = slot_size(WORD, box, 80.0, "title", scale, SLIDE_PT)
    assert size not in {28.0, 18.0, 12.0}
    assert size >= title_step(scale)
    assert size <= word_size(WORD, box, SLIDE_PT)


def test_intermediate_size_below_the_title_step_is_not_taken():
    """Промежуточный кегль ниже ступени title не берут: слот идёт по ступеням, как обычный."""
    box = (0.05, 0.30, 0.06, 0.20)
    size = slot_size(WORD, box, 80.0, "title", SCALE, SLIDE_PT)
    assert size < title_step(SCALE)
    assert size in {step.size_pt for step in SCALE}


def test_scale_names_the_top_of_headings_and_the_title_step():
    assert head_top(SCALE) == 36.0
    assert title_step(SCALE) == 36.0
    without_title = [TypeStep(size_pt=30, role="heading", share=0.5),
                     TypeStep(size_pt=14, role="body", share=0.5)]
    assert title_step(without_title) == 30.0


def test_text_lines_count_the_wrapped_lines():
    box = (0.05, 0.10, 0.20, 0.30)
    assert text_lines("коротко", box, 12.0, SLIDE_PT) == 1
    assert text_lines("и" * 60, box, 12.0, SLIDE_PT) == 3


# ---------- связанные группы ----------

def _linked_pair():
    """Ряд номеров и ряд подписей под ними: одна смысловая строка из двух групп."""
    numbers = RepeatGroup(
        id="g1", direction="row", cols=3, rows=1, step=(0.30, 0.0), unit_size=(0.10, 0.10),
        units=[RepeatUnit(index=i, box=(0.14 + i * 0.30, 0.35, 0.10, 0.10), shape_ids=[200 + i])
               for i in range(3)],
        max_units=3, unit_slots=[_slot(201, "number", (0.0, 0.0, 0.10, 0.10), 40)])
    heads = RepeatGroup(
        id="g2", direction="row", cols=3, rows=1, step=(0.30, 0.0), unit_size=(0.28, 0.14),
        units=[RepeatUnit(index=i, box=(0.05 + i * 0.30, 0.50, 0.28, 0.14), shape_ids=[210 + i])
               for i in range(3)],
        max_units=3, unit_slots=[_slot(211, "heading", (0.0, 0.0, 0.28, 0.14), 20)],
        linked_group_ids=["g1"])
    pattern = _pattern()
    pattern.groups = [numbers, heads]
    pattern.primary_group_id = "g2"
    return pattern


def test_primary_group_is_the_one_the_pattern_names():
    pattern = _linked_pair()
    assert primary_group(pattern).id == "g2"
    assert [g.id for g in linked_groups(pattern, primary_group(pattern))] == ["g1"]
    assert [s.id for s in unit_text_slots(primary_group(pattern), [])] == ["s211"]


def test_linked_blocks_keep_the_axis_of_the_main_ones():
    pattern = _linked_pair()
    group = primary_group(pattern)
    main, linked = unit_boxes(group, linked_groups(pattern, group), 2)
    assert len(main) == len(linked["g1"]) == 2
    for head, number in zip(main, linked["g1"]):
        assert abs((head[0] + head[2] / 2) - (number[0] + number[2] / 2)) < 0.001
