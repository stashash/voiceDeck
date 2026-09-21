"""Поиск повторов на синтетических рамках: pptx здесь не нужен."""
import pytest

from designer.parse import geometry as geo


def frame(key: int, kind: str, box, text: bool = False) -> geo.Frame:
    return geo.Frame(key=key, box=box, sig=geo.signature(kind, box, text))


def test_row_of_three():
    frames = [frame(i + 1, "text", (0.05 + i * 0.30, 0.30, 0.25, 0.40), True) for i in range(3)]
    found = geo.find_repeats(frames)
    assert len(found) == 1
    cand = found[0]
    assert cand.direction == "row"
    assert (cand.cols, cand.rows) == (3, 1)
    assert cand.step[0] == pytest.approx(0.30, abs=0.005)
    assert cand.step[1] == 0.0
    assert cand.unit_size == pytest.approx((0.25, 0.40))


def test_column_of_four():
    frames = [frame(i + 1, "text", (0.50, 0.10 + i * 0.20, 0.40, 0.15), True) for i in range(4)]
    cand = geo.find_repeats(frames)[0]
    assert cand.direction == "column"
    assert (cand.cols, cand.rows) == (1, 4)
    assert cand.step[1] == pytest.approx(0.20, abs=0.005)


def test_grid_three_by_two():
    frames = []
    for row in range(2):
        for col in range(3):
            frames.append(
                frame(len(frames) + 1, "shape", (0.03 + col * 0.32, 0.24 + row * 0.33, 0.30, 0.30))
            )
    cand = geo.find_repeats(frames)[0]
    assert cand.direction == "grid"
    assert (cand.cols, cand.rows) == (3, 2)
    assert len(cand.units) == 6
    assert cand.step == pytest.approx((0.32, 0.33), abs=0.005)


def test_parallel_runs_fold_into_one_block():
    frames = []
    for col in range(3):
        left = 0.05 + col * 0.32
        frames.append(frame(10 + col, "shape", (left, 0.25, 0.28, 0.35)))
        frames.append(frame(20 + col, "text", (left + 0.02, 0.28, 0.24, 0.06), True))
        frames.append(frame(30 + col, "text", (left + 0.02, 0.36, 0.24, 0.20), True))
    found = geo.find_repeats(frames)
    assert len(found) == 1
    cand = found[0]
    assert len(cand.units) == 3
    assert all(len(unit) == 3 for unit in cand.units)
    assert cand.unit_boxes[0] == pytest.approx((0.05, 0.25, 0.28, 0.35))


def test_irregular_step_is_not_a_repeat():
    lefts = (0.05, 0.35, 0.80)
    frames = [frame(i + 1, "text", (x, 0.30, 0.25, 0.40), True) for i, x in enumerate(lefts)]
    assert geo.find_repeats(frames) == []


def test_small_blocks_win_over_wide_container():
    frames = []
    for row in range(2):
        top = 0.235 + row * 0.326
        frames.append(frame(100 + row, "shape", (0.031, top, 0.937, 0.307)))
        for col in range(3):
            frames.append(frame(200 + row * 3 + col, "shape", (0.031 + col * 0.316, top, 0.306, 0.307)))
    found = geo.find_repeats(frames)
    assert len(found) == 1
    assert len(found[0].units) == 6
    assert 100 not in found[0].keys


def test_shapes_of_one_size_but_different_kind_do_not_mix():
    frames = [
        frame(1, "text", (0.05, 0.30, 0.25, 0.40), True),
        frame(2, "image", (0.35, 0.30, 0.25, 0.40)),
        frame(3, "text", (0.65, 0.30, 0.25, 0.40), True),
    ]
    found = geo.find_repeats(frames)
    assert len(found) == 1
    assert found[0].keys == [1, 3]
    assert found[0].step[0] == pytest.approx(0.60, abs=0.005)


def test_signature_rounds_size_to_hundredths():
    frames = [
        frame(1, "text", (0.05, 0.30, 0.252, 0.400), True),
        frame(2, "text", (0.35, 0.30, 0.249, 0.402), True),
    ]
    assert frames[0].sig == frames[1].sig
    assert len(geo.find_repeats(frames)[0].units) == 2


def test_row_survives_a_slightly_wider_block():
    widths = (0.19, 0.19, 0.19, 0.21)
    frames = [frame(i + 1, "text", (0.05 + i * 0.22, 0.40, w, 0.13), True) for i, w in enumerate(widths)]
    found = geo.find_repeats(frames)
    assert len(found) == 1
    assert len(found[0].units) == 4


def test_two_blocks_of_different_size_are_not_a_repeat():
    frames = [
        frame(1, "text", (0.05, 0.40, 0.19, 0.13), True),
        frame(2, "text", (0.27, 0.40, 0.21, 0.13), True),
    ]
    assert geo.find_repeats(frames) == []


def test_row_of_badges_above_captions_stays_its_own_block():
    frames = []
    for i in range(4):
        left = 0.05 + i * 0.22
        frames.append(frame(10 + i, "text", (left, 0.32, 0.07, 0.12), True))
        frames.append(frame(20 + i, "text", (left, 0.48, 0.20, 0.30), True))
    found = geo.find_repeats(frames)
    assert len(found) == 2
    assert all(len(cand.units) == 4 for cand in found)
    assert geo.in_lockstep(found[0].unit_boxes, found[1].unit_boxes)


def test_rows_with_different_rhythm_are_not_linked():
    first = [(0.05 + i * 0.22, 0.30, 0.20, 0.10) for i in range(3)]
    second = [(0.05 + i * 0.30, 0.50, 0.20, 0.10) for i in range(3)]
    assert not geo.in_lockstep(first, second)


def test_fit_units_counts_room_in_the_field():
    origin = (0.05, 0.20, 0.20, 0.30)
    fits = geo.fit_units(origin, (0.20, 0.30), (0.22, 0.0), 2, 1, (0.05, 0.05, 0.90, 0.90))
    assert fits == 4
    kept = geo.fit_units(origin, (0.20, 0.30), (0.0, 0.0), 2, 1, (0.05, 0.05, 0.90, 0.90))
    assert kept == 2


def test_content_box_drops_full_bleed_backing():
    boxes = [(0.0, 0.0, 1.0, 1.0), (0.10, 0.20, 0.30, 0.10), (0.60, 0.50, 0.30, 0.20)]
    assert geo.content_box(boxes) == pytest.approx((0.10, 0.20, 0.80, 0.50))


def test_overlap_gap_and_union():
    a = (0.0, 0.0, 0.40, 0.40)
    b = (0.20, 0.20, 0.40, 0.40)
    assert geo.overlap(a, b) == pytest.approx(0.25)
    assert geo.gap(a, b) == 0.0
    assert geo.gap(a, (0.50, 0.0, 0.10, 0.10)) == pytest.approx(0.10)
    assert geo.union([a, b]) == pytest.approx((0.0, 0.0, 0.60, 0.60))
