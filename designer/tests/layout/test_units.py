import pytest

from designer.contracts import RepeatGroup, RepeatUnit
from designer.layout.units import map_shape_box, place_units


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
