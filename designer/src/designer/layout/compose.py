"""Намерение слайда -> инструкция сборки на паттерне. Владелец: задача T-07.

Слот, для которого содержания нет, получает пустую строку: образцовый текст шаблона
на собранном слайде остаться не должен. Всё, что меняет вид слайда, решает этот слой:
рамку диаграммы, кегли после подгонки и фигуры образца, которые со слайда уходят.
Экспорт исполняет решения буквально.
"""
from __future__ import annotations

from designer.contracts import (
    Area,
    Box,
    DesignSystem,
    Item,
    Pattern,
    RepeatGroup,
    SlideIntent,
    SlideSpec,
    Slot,
)
from designer.layout.capacity import (
    content_region,
    fit_size,
    free_box,
    linked_groups,
    primary_group,
    size_floor,
    slide_pt,
    unit_boxes,
    unit_count,
    unit_slot_box,
)
from designer.parse import geometry as geo

_HEAD_ROLES = ("heading", "title")
_BODY_ROLES = ("body", "caption", "label", "subtitle")
_ITEM_ROLES = ("body", "heading", "caption", "label")
_SIDE_ROLES = ("caption", "label", "footer", "subtitle", "body")
_SAMPLE_VIZ = ("chart", "table")

AREA_KEEP = 0.6
"""Доля свободной рамки, с которой родная область шаблона берётся как есть.

Меньше — диаграмма встанет маркой в углу, и рамку выбирает вёрстка.
"""

INSIDE = 0.6
"""Доля фигуры внутри рамки, с которой фигура считается лежащей в ней."""


def _inside(box: Box, frame: Box) -> bool:
    own = geo.area(box)
    wide = min(geo.right(box), geo.right(frame)) - max(box[0], frame[0])
    high = min(geo.bottom(box), geo.bottom(frame)) - max(box[1], frame[1])
    if own <= 0 or wide <= 0 or high <= 0:
        return False
    return (wide * high) / own >= INSIDE


def _take(
    free: list[Slot], roles: tuple[str, ...], biggest: bool = False, avoid: Box | None = None
) -> Slot | None:
    """Забрать свободный слот одной из ролей: первый по порядку чтения или самый крупный.

    avoid это рамка, отданная диаграмме или таблице: слот из неё берут, только если другого нет.
    """
    matches = [slot for slot in free if slot.role in roles]
    if avoid is not None:
        matches = [slot for slot in matches if not _inside(slot.box, avoid)] or matches
    if not matches:
        return None
    slot = max(matches, key=lambda s: (s.box[2] * s.box[3], s.id)) if biggest else matches[0]
    free.remove(slot)
    return slot


def _join(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def _item_text(item: Item) -> str:
    return _join(item.heading, item.body)


def _unit_texts(
    groups: list[RepeatGroup], items: list[Item], n: int, lead_taken: bool = False
) -> dict[str, list[dict[str, str]]]:
    """Пункты по слотам блока: номер, заголовок, пояснение.

    Слоты главной и связанных групп разбираются вместе: номер идёт в группу номеров,
    подпись в группу подписей. Слов пункта не теряем: когда текстовый слот один,
    заголовок и пояснение идут в него вместе. lead_taken значит, что число уже стоит
    крупным слотом слайда и в блоке его повторять не надо.
    """
    pairs = [(group.id, slot) for group in groups for slot in group.unit_slots]
    numbers = [pair for pair in pairs if pair[1].role == "number"]
    heads = [pair for pair in pairs if pair[1].role in _HEAD_ROLES]
    bodies = [pair for pair in pairs if pair[1].role in _BODY_ROLES]
    out: dict[str, list[dict[str, str]]] = {group.id: [] for group in groups}
    for index in range(n):
        texts = {group.id: {slot.id: "" for slot in group.unit_slots} for group in groups}
        item = items[index] if index < len(items) else None
        if item is not None:
            head, body = item.heading, item.body
            if not head:
                # Пункт без заголовка читается крупно, а не подписью под пустым местом.
                head, body = body, ""
            if lead_taken:
                pass  # число уже стоит крупным слотом слайда
            elif numbers:
                gid, slot = numbers[0]
                texts[gid][slot.id] = item.number or str(index + 1)
            elif item.number:
                # Номера в блоке нет: число не теряем, оно идёт впереди заголовка.
                head = f"{item.number} {head}".strip()
            if heads and bodies:
                texts[heads[0][0]][heads[0][1].id] = head
                texts[bodies[0][0]][bodies[0][1].id] = body
            elif heads:
                texts[heads[0][0]][heads[0][1].id] = _join(head, body)
            elif bodies:
                texts[bodies[0][0]][bodies[0][1].id] = _join(head, body)
        for group in groups:
            out[group.id].append(texts[group.id])
    return out


def _own_area(pattern: Pattern, want: str) -> Area | None:
    """Своя область шаблона под такую же визуализацию."""
    same = [area for area in pattern.areas if area.kind == want]
    return max(same, key=lambda a: (geo.area(a.box), a.id)) if same else None


def _viz_place(
    pattern: Pattern, ds: DesignSystem, want: str, busy: list[Box]
) -> tuple[str | None, Box | None]:
    """Где встанет диаграмма или таблица: своя область шаблона или свободная рамка слайда."""
    frame = free_box(content_region(pattern, ds.tokens.margins), busy)
    own = _own_area(pattern, want)
    if own is not None and not any(geo.overlap(own.box, box) > 0 for box in busy):
        if frame is None or geo.area(own.box) >= AREA_KEEP * geo.area(frame):
            return own.id, own.box
    return None, frame


def _removed(pattern: Pattern, spec: SlideSpec, texts: dict[str, str], n: int) -> list[int]:
    """Фигуры образца, которых на слайде не будет: пустые блоки, заглушки, чужие образцы."""
    out: set[int] = set()
    kept = {spec.group_id, *spec.linked_unit_text} - {None}
    for group in pattern.groups:
        if group.id in kept:
            for unit in group.units[n:]:
                out.update(unit.shape_ids)
            out.update(a.shape_id for a in group.unit_areas if a.placeholder and a.shape_id)
        else:
            for unit in group.units:
                out.update(unit.shape_ids)

    for area in pattern.areas:
        if area.shape_id is None or area.id == spec.viz_area_id:
            continue
        if area.placeholder or area.kind in _SAMPLE_VIZ:
            out.add(area.shape_id)
        elif spec.viz_box is not None and geo.overlap(area.box, spec.viz_box) > 0:
            # Рамка отдана диаграмме: картинка образца под ней не живёт.
            out.add(area.shape_id)

    if spec.viz_box is not None:
        for slot in pattern.slots:
            if not texts.get(slot.id) and _inside(slot.box, spec.viz_box):
                out.add(slot.shape_id)
    return sorted(out)


def _fitted(
    pattern: Pattern, spec: SlideSpec, texts: dict[str, str], ds: DesignSystem, n: int
) -> dict[str, float]:
    """Кегль каждого заполненного слота после подгонки по ступеням шкалы."""
    slide = slide_pt(ds.slide_size_emu)
    scale = ds.tokens.type_scale
    out: dict[str, float] = {}
    for slot in pattern.slots:
        text, size = texts.get(slot.id, ""), slot.style.size_pt
        if not text or not size:
            continue
        out[slot.id] = fit_size(text, slot.box, size, scale, slide, size_floor(scale, slot.role))

    group = next((g for g in pattern.groups if g.id == spec.group_id), None)
    if group is None or not n:
        return out
    linked = [g for g in pattern.groups if g.id in spec.linked_unit_text]
    main_boxes, linked_boxes = unit_boxes(group, linked, n)
    for item in (group, *linked):
        boxes = main_boxes if item is group else linked_boxes[item.id]
        unit_texts = spec.unit_text if item is group else spec.linked_unit_text[item.id]
        old = item.units[0].box
        for slot in item.unit_slots:
            size = slot.style.size_pt
            if not size:
                continue
            sizes = [
                fit_size(
                    unit_texts[index][slot.id],
                    unit_slot_box(old, new, slot.box),
                    size,
                    scale,
                    slide,
                    size_floor(scale, slot.role),
                )
                for index, new in enumerate(boxes)
                if index < len(unit_texts) and unit_texts[index].get(slot.id)
            ]
            if sizes:
                # Один кегль на все блоки: разнобой внутри ряда виден сразу.
                out[slot.id] = min(sizes)
    return out


def compose(intent: SlideIntent, pattern: Pattern, ds: DesignSystem) -> SlideSpec:
    """Инструкция сборки слайда: какой слот чем заполнить, где диаграмма и что со слайда убрать."""
    spec = SlideSpec(slide_id=intent.id, pattern_id=pattern.id, notes=intent.notes)
    texts = {slot.id: "" for slot in pattern.slots}
    free = list(pattern.slots)
    want = "chart" if intent.chart is not None else "table" if intent.table is not None else None
    region = content_region(pattern, ds.tokens.margins) if want else None

    title = _take(free, ("title",)) or _take(free, ("heading",), biggest=True)
    if title is not None:
        texts[title.id] = intent.title

    lead = next((item.number for item in intent.items if item.number), None)
    lead_slot = _take(free, ("number",), avoid=region) if lead else None
    if lead_slot is not None:
        texts[lead_slot.id] = lead

    group = primary_group(pattern) if want is None else None
    linked = linked_groups(pattern, group) if group is not None else []
    rest = list(intent.items)
    n = 0
    if rest and group is not None:
        n = unit_count(group, len(rest))
        for other in linked:
            n = min(n, other.max_units)
        n = max(n, group.min_units)
        linked = [other for other in linked if other.min_units <= n <= other.max_units]
        spread = _unit_texts([group, *linked], rest, n, lead_slot is not None and len(rest) == 1)
        spec.group_id = group.id
        spec.unit_text = spread[group.id]
        spec.linked_unit_text = {other.id: spread[other.id] for other in linked}
        rest = []

    if intent.key_message:
        slot = (
            _take(free, ("subtitle",), avoid=region)
            or _take(free, ("body",), biggest=True, avoid=region)
            or _take(free, ("heading",), biggest=True, avoid=region)
            or _take(free, ("caption",), biggest=True, avoid=region)
        )
        if slot is not None:
            texts[slot.id] = intent.key_message

    if intent.attribution:
        slot = _take(free, _SIDE_ROLES, avoid=region)
        if slot is not None:
            texts[slot.id] = intent.attribution

    for item in rest:
        slot = _take(free, _ITEM_ROLES, avoid=region)
        if slot is None:
            break
        texts[slot.id] = _item_text(item)

    if want is not None:
        spec.chart, spec.table = intent.chart, intent.table
        busy = [slot.box for slot in pattern.slots if texts.get(slot.id)]
        spec.viz_area_id, spec.viz_box = _viz_place(pattern, ds, want, busy)

    spec.slot_text = texts
    spec.remove_shape_ids = _removed(pattern, spec, texts, n)
    spec.fitted_size_pt = _fitted(pattern, spec, texts, ds, n)
    return spec
