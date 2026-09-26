import pytest

from designer.contracts import DecorShape, Pattern, RepeatGroup, RepeatUnit, SlideKind
from designer.layout.units import attach_unit_decor, keeps_aspect, map_shape_box, place_units


def _group(direction, cols, rows, count, max_units, step=(0.30, 0.32), size=(0.28, 0.30)):
    units = []
    for i in range(count):
        c, r = (i % cols, i // cols) if direction != "column" else (0, i)
        units.append(RepeatUnit(index=i, box=(0.03 + c * step[0], 0.24 + r * step[1], size[0], size[1]), shape_ids=[i]))
    return RepeatGroup(id="g", direction=direction, cols=cols, rows=rows, step=step, unit_size=size,
                       units=units, max_units=max_units)


def test_row_same_count_keeps_template_geometry():
    boxes = place_units(_group("row", 3, 1, 3, 4), 3)
    assert [round(b[0], 3) for b in boxes] == [0.03, 0.33, 0.63]
    assert round(boxes[0][2], 3) == 0.28


def test_row_fewer_units_fill_the_same_span():
    boxes = place_units(_group("row", 3, 1, 3, 4), 2)
    right = boxes[-1][0] + boxes[-1][2]
    assert round(right, 3) == round(0.63 + 0.28, 3)
    assert boxes[0][2] > 0.28


def test_column_keeps_size_and_step():
    boxes = place_units(_group("column", 1, 4, 4, 5, step=(0.0, 0.20), size=(0.36, 0.14)), 5)
    assert round(boxes[4][1] - boxes[3][1], 3) == 0.2
    assert boxes[4][2] == 0.36


def test_grid_adds_rows_and_cuts_tail():
    boxes = place_units(_group("grid", 3, 2, 6, 6), 5)
    assert len(boxes) == 5
    assert round(boxes[3][1] - boxes[0][1], 3) == 0.32


def test_grid_below_cols_behaves_as_row():
    boxes = place_units(_group("grid", 3, 2, 6, 6), 2)
    assert boxes[0][1] == boxes[1][1] and boxes[0][2] > 0.28


def test_out_of_range():
    with pytest.raises(ValueError):
        place_units(_group("row", 3, 1, 3, 4), 5)


def test_map_shape_box_scales_text_keeps_icon():
    old, new = (0.03, 0.24, 0.28, 0.30), (0.03, 0.24, 0.42, 0.30)
    text = map_shape_box(old, new, (0.05, 0.30, 0.24, 0.05))
    icon = map_shape_box(old, new, (0.05, 0.26, 0.02, 0.04), keep_size=True)
    assert round(text[2], 3) == 0.36 and round(text[0], 3) == 0.06
    assert icon[2] == 0.02


def test_circle_in_wider_unit_stays_a_circle():
    # Блоков стало меньше, блок шире: кружок с номером не тянется в овал, центр едет вместе с блоком.
    old, new = (0.03, 0.24, 0.28, 0.30), (0.03, 0.24, 0.42, 0.30)
    circle = (0.05, 0.26, 0.05, 0.05 * 16 / 9)
    assert keeps_aspect(old, circle, 16 / 9)
    box = map_shape_box(old, new, circle, keep_aspect=True)
    assert box[2] == pytest.approx(circle[2]) and box[3] == pytest.approx(circle[3])
    assert box[0] + box[2] / 2 == pytest.approx(0.03 + (0.075 - 0.03) * 1.5)


def test_card_background_still_stretches():
    old = (0.03, 0.24, 0.28, 0.30 * 16 / 9 * 0.28 / 0.30)
    assert not keeps_aspect(old, old, 16 / 9), "подложка на весь блок тянется вместе с блоком"


def _pattern_with_row_decor():
    group = _group("row", 3, 1, 3, 4, size=(0.28, 0.20))
    decor = [DecorShape(shape_id=100 + i, box=(0.08 + i * 0.30, 0.12, 0.05, 0.09)) for i in range(3)]
    decor.append(DecorShape(shape_id=200, box=(0.0, 0.0, 1.0, 0.08)))
    return Pattern(id="p", source_slide=1, layout_name="l", kind=SlideKind.cards, kind_confidence=1, theme="light",
                   groups=[group], decor_shape_ids=[d.shape_id for d in decor], decor=decor)


def test_decor_one_per_unit_moves_with_its_unit():
    pattern = attach_unit_decor(_pattern_with_row_decor())
    assert [u.shape_ids for u in pattern.groups[0].units] == [[0, 100], [1, 101], [2, 102]]
    assert pattern.decor_shape_ids == [200], "полоса на всю ширину остаётся оформлением слайда"
    assert attach_unit_decor(pattern) == pattern


def test_decor_not_one_per_unit_stays():
    pattern = _pattern_with_row_decor()
    pattern = pattern.model_copy(update={"decor": pattern.decor[:2] + pattern.decor[3:]})
    assert attach_unit_decor(pattern).groups[0].units[0].shape_ids == [0]


def test_figure_around_icon_moves_with_its_unit():
    # Цветная фигура, внутри которой стоит значок блока, едет вместе с блоком и не тянется в овал.
    group = _group("row", 3, 1, 3, 6, step=(0.305, 0.0), size=(0.037, 0.066))
    figures = [DecorShape(shape_id=100 + i, box=(0.02 + i * 0.305, 0.21, 0.071, 0.126)) for i in range(3)]
    pattern = Pattern(id="p", source_slide=1, layout_name="l", kind=SlideKind.cards, kind_confidence=1, theme="light",
                      groups=[group], decor_shape_ids=[f.shape_id for f in figures], decor=figures)
    attached = attach_unit_decor(pattern)
    assert [u.shape_ids for u in attached.groups[0].units] == [[0, 100], [1, 101], [2, 102]]
    assert keeps_aspect(group.units[0].box, figures[0].box, 16 / 9), "фигура крупнее блока это не подложка"
