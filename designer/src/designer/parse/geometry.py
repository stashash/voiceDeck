"""Геометрия разбора: рамки в долях слайда и поиск повторяющихся блоков. Владелец: задача T-02.

Модуль не знает про pptx: на вход идут рамки с сигнатурой, на выход ряды и сетки.
Рамка это (x, y, w, h) в долях слайда, начало в левом верхнем углу.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]

POS_TOL = 0.012
"""Допуск на совпадение краёв, доли слайда."""

STEP_TOL = 0.02
"""Допуск на постоянство шага."""

GAP_TOL = 0.06
"""Зазор, при котором соседняя фигура ещё считается частью того же блока."""

SIZE_ROUND = 2
"""Округление ширины и высоты в сигнатуре."""

FULL_BLEED = 0.92
"""Доля слайда, с которой фигура считается подложкой на весь кадр."""


def right(box: Box) -> float:
    return box[0] + box[2]


def bottom(box: Box) -> float:
    return box[1] + box[3]


def area(box: Box) -> float:
    return max(box[2], 0.0) * max(box[3], 0.0)


def union(boxes: list[Box]) -> Box:
    x = min(b[0] for b in boxes)
    y = min(b[1] for b in boxes)
    return (x, y, max(right(b) for b in boxes) - x, max(bottom(b) for b in boxes) - y)


def overlap(a: Box, b: Box) -> float:
    """Доля площади меньшей рамки, накрытая пересечением."""
    w = min(right(a), right(b)) - max(a[0], b[0])
    h = min(bottom(a), bottom(b)) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    small = min(area(a), area(b))
    return (w * h) / small if small > 0 else 0.0


def gap(a: Box, b: Box) -> float:
    """Зазор между рамками; ноль, если они касаются или пересекаются."""
    dx = max(a[0] - right(b), b[0] - right(a), 0.0)
    dy = max(a[1] - bottom(b), b[1] - bottom(a), 0.0)
    return max(dx, dy)


def content_box(boxes: list[Box]) -> Box:
    """Поля слайда: рамка вокруг всего, кроме подложек на весь кадр."""
    inner = [b for b in boxes if not (b[2] >= FULL_BLEED and b[3] >= FULL_BLEED)]
    if not inner:
        return (0.0, 0.0, 1.0, 1.0)
    return union(inner)


def signature(kind: str, box: Box, has_text: bool) -> tuple:
    """Сигнатура фигуры: тип, размер с округлением до 0,01, есть ли текст."""
    return (kind, round(box[2], SIZE_ROUND), round(box[3], SIZE_ROUND), has_text)


@dataclass(frozen=True)
class Frame:
    """Рамка фигуры со своей сигнатурой. key это shape_id в исходном слайде."""

    key: int
    box: Box
    sig: tuple


@dataclass
class Run:
    """Ряд фигур одной сигнатуры с постоянным шагом."""

    direction: str
    cols: int
    rows: int
    step: tuple[float, float]
    frames: list[Frame]


@dataclass
class RepeatCandidate:
    """Повторяющийся блок: ряды одной длины и одного шага, сложенные вместе."""

    direction: str
    cols: int
    rows: int
    step: tuple[float, float]
    units: list[list[Frame]] = field(default_factory=list)

    @property
    def unit_boxes(self) -> list[Box]:
        return [union([f.box for f in unit]) for unit in self.units]

    @property
    def unit_size(self) -> tuple[float, float]:
        boxes = self.unit_boxes
        return (max(b[2] for b in boxes), max(b[3] for b in boxes))

    @property
    def keys(self) -> list[int]:
        return [f.key for unit in self.units for f in unit]


def _cluster(values: list[float], tol: float = POS_TOL) -> tuple[list[float], list[int]]:
    """Свести близкие координаты в общие линии; вернуть линии и номер линии для каждого значения."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    lines: list[list[float]] = []
    index = [0] * len(values)
    for i in order:
        v = values[i]
        if lines and v - lines[-1][-1] <= tol:
            lines[-1].append(v)
        else:
            lines.append([v])
        index[i] = len(lines) - 1
    return [sum(line) / len(line) for line in lines], index


def _constant_step(centers: list[float]) -> tuple[float, bool]:
    if len(centers) < 2:
        return 0.0, True
    diffs = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    mean = sum(diffs) / len(diffs)
    return mean, all(abs(d - mean) <= STEP_TOL for d in diffs)


def arrange(frames: list[Frame]) -> Run | None:
    """Разложить фигуры одной сигнатуры в ряд, столбец или сетку с постоянным шагом."""
    if len(frames) < 2:
        return None
    cx, ix = _cluster([f.box[0] for f in frames])
    cy, iy = _cluster([f.box[1] for f in frames])
    cols, rows = len(cx), len(cy)
    if cols * rows != len(frames) or max(cols, rows) < 2:
        return None
    cells: dict[tuple[int, int], Frame] = {}
    for k, f in enumerate(frames):
        cell = (iy[k], ix[k])
        if cell in cells:
            return None
        cells[cell] = f
    step_x, ok_x = _constant_step(cx)
    step_y, ok_y = _constant_step(cy)
    if not ok_x or not ok_y:
        return None
    size_w = max(f.box[2] for f in frames)
    size_h = max(f.box[3] for f in frames)
    if cols > 1 and size_w > step_x + POS_TOL:
        return None
    if rows > 1 and size_h > step_y + POS_TOL:
        return None
    ordered = [cells[(r, c)] for r in range(rows) for c in range(cols)]
    direction = "row" if rows == 1 else "column" if cols == 1 else "grid"
    return Run(direction, cols, rows, (step_x, step_y), ordered)


def _try_merge(cand: RepeatCandidate, run: Run) -> bool:
    if (cand.cols, cand.rows) != (run.cols, run.rows):
        return False
    if abs(cand.step[0] - run.step[0]) > STEP_TOL or abs(cand.step[1] - run.step[1]) > STEP_TOL:
        return False
    boxes = cand.unit_boxes
    merged = []
    for i, f in enumerate(run.frames):
        if gap(boxes[i], f.box) > GAP_TOL:
            return False
        merged.append(union([boxes[i], f.box]))
    width = max(b[2] for b in merged)
    height = max(b[3] for b in merged)
    if cand.step[0] > 0 and width > cand.step[0] + POS_TOL:
        return False
    if cand.step[1] > 0 and height > cand.step[1] + POS_TOL:
        return False
    for i, f in enumerate(run.frames):
        cand.units[i].append(f)
    return True


def find_repeats(frames: list[Frame], min_units: int = 2) -> list[RepeatCandidate]:
    """Найти повторяющиеся блоки: собрать ряды по сигнатуре и сложить ряды одной длины и шага."""
    buckets: dict[tuple, list[Frame]] = defaultdict(list)
    for f in frames:
        buckets[f.sig].append(f)

    runs: list[Run] = []
    for group in buckets.values():
        if len(group) < min_units:
            continue
        run = arrange(group)
        if run is not None:
            runs.append(run)
    runs.sort(key=lambda r: (-len(r.frames), -sum(area(f.box) for f in r.frames)))

    cands: list[RepeatCandidate] = []
    for run in runs:
        for cand in cands:
            if _try_merge(cand, run):
                break
        else:
            cands.append(
                RepeatCandidate(run.direction, run.cols, run.rows, run.step, [[f] for f in run.frames])
            )

    cands.sort(key=lambda c: (-len(c.units), -sum(area(b) for b in c.unit_boxes)))
    picked: list[RepeatCandidate] = []
    for cand in cands:
        if len(cand.units) < min_units:
            continue
        boxes = cand.unit_boxes
        busy = [b for p in picked for b in p.unit_boxes]
        if any(overlap(b, other) > 0.2 for b in boxes for other in busy):
            continue
        picked.append(cand)
    return picked


def fit_units(
    origin: Box,
    unit_size: tuple[float, float],
    step: tuple[float, float],
    cols: int,
    rows: int,
    area_box: Box,
) -> int:
    """Сколько блоков с тем же шагом помещается в полях слайда."""

    def axis(start: float, size: float, gap_: float, count: int, field_start: float, field_size: float) -> int:
        if gap_ <= 1e-6:
            return count
        room = field_start + field_size - start - size
        if room < 0:
            return count
        return max(count, int(room / gap_ + 0.03) + 1)

    fit_cols = axis(origin[0], unit_size[0], step[0], cols, area_box[0], area_box[2])
    fit_rows = axis(origin[1], unit_size[1], step[1], rows, area_box[1], area_box[3])
    return fit_cols * fit_rows
