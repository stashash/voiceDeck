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
    RepeatUnit,
    SlideIntent,
    SlideSpec,
    Slot,
)
from designer.layout.capacity import (
    OVERLAP_MIN,
    content_region,
    free_box,
    head_top,
    ink_box,
    lead_number,
    line_capacity,
    linked_groups,
    number_caption,
    primary_group,
    size_floor,
    slide_pt,
    slot_size,
    split_number,
    step_down,
    text_lines,
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

VIZ_INSIDE = 0.5
"""Доля площади фигуры оформления в рамке визуализации, с которой фигура оттуда уходит."""

EDGE_BAND = 0.1
"""Полоса у края кадра: там стоят логотип и колонтитул."""

EDGE_AREA = 0.02
"""Доля слайда, до которой фигура у края это логотип или колонтитул, а не оформление."""

MARKER_AREA = 0.002
"""Доля слайда, до которой фигура оформления это маркер строки: точка списка, значок."""

MARKER_GAP = 0.04
"""Насколько маркер отстоит от своей строки, доли кадра."""

HINT_CHARS = 20
"""До скольких знаков текст слота это подсказка шаблона, а не место под содержание."""

HINT_AREA = 0.02
"""Доля слайда, до которой плашка с подсказкой это значок под картинку, а не блок содержания."""


def _inside(box: Box, frame: Box) -> bool:
    return geo.covered(box, frame) >= INSIDE


def _edge_furniture(box: Box) -> bool:
    """Фон на весь кадр, логотип и колонтитул: рамка визуализации их не трогает."""
    if box[2] >= geo.FULL_BLEED and box[3] >= geo.FULL_BLEED:
        return True
    if geo.area(box) > EDGE_AREA:
        return False
    return (geo.right(box) <= EDGE_BAND or box[0] >= 1 - EDGE_BAND
            or geo.bottom(box) <= EDGE_BAND or box[1] >= 1 - EDGE_BAND)


def _on_line(box: Box, line: Box) -> bool:
    """Маркер стоит на той же строке: по высоте внутри строки и рядом по горизонтали."""
    high = min(geo.bottom(box), geo.bottom(line)) - max(box[1], line[1])
    if high <= 0 or high < box[3] / 2:
        return False
    return geo.gap(box, line) <= MARKER_GAP


def _hint_plate(pattern: Pattern, slot: Slot) -> int | None:
    """Фигура, на которой стоит подсказка «вставьте картинку»; None, если слот обычный.

    Шаблон держит место под фото пустым квадратом с подписью внутри. Картинок у нас нет:
    в такой слот текст не кладут, а квадрат уходит со слайда вместе с подписью.
    """
    if geo.area(slot.box) > HINT_AREA or slot.max_chars > HINT_CHARS:
        return None
    plates = [shape for shape in pattern.decor
              if not _edge_furniture(shape.box)
              and geo.area(shape.box) <= HINT_AREA * 2
              and geo.covered(slot.box, shape.box) >= INSIDE]
    if not plates:
        return None
    return min(plates, key=lambda shape: (geo.area(shape.box), shape.shape_id)).shape_id


def _hint_slots(pattern: Pattern) -> dict[str, int]:
    """Слоты-подсказки паттерна и фигуры, на которых они стоят."""
    found = {slot.id: _hint_plate(pattern, slot) for slot in pattern.slots}
    return {slot_id: plate for slot_id, plate in found.items() if plate is not None}


def _take(
    free: list[Slot], roles: tuple[str, ...], biggest: bool = False, avoid: Box | None = None,
    text: str = "",
) -> Slot | None:
    """Забрать свободный слот одной из ролей: первый по порядку чтения или самый крупный.

    avoid это рамка, отданная диаграмме или таблице: слот из неё берут, только если другого нет.
    text это то, что ляжет в слот: подпись месяца «Апр» из образца диаграммы фразу не держит.
    """
    room = min(len(text), HINT_CHARS)
    matches = [slot for slot in free if slot.role in roles and slot.max_chars >= room]
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


def _captioned_numbers(
    intent: SlideIntent, lead: str | None, lead_slot: Slot | None, free: list[Slot],
    avoid: Box | None, texts: dict[str, str],
) -> list[Item]:
    """Числа пунктов по свободным слотам числа, подпись пункта под числом в той же рамке.

    Шаблон рисует слайд с числом одной фигурой: «ххх%», перенос, «данные показателя».
    Пункт, чьи число и подпись встали в такую фигуру, дальше по слотам не идёт.
    Возвращает пункты, которые ещё надо разложить.
    """
    rest = list(intent.items)
    placed: list[tuple[Slot, Item]] = []
    if lead_slot is not None:
        owner = next((item for item in rest if item.number == lead), None)
        if owner is None and len(rest) == 1 and not rest[0].number:
            owner = rest[0]  # число взято из заголовка, единственный пункт его поясняет
        if owner is not None:
            placed.append((lead_slot, owner))
    for item in rest:
        if not item.number or any(item is done for _, done in placed):
            continue
        slot = _take(free, ("number",), avoid=avoid)
        if slot is None:
            break
        texts[slot.id] = item.number
        placed.append((slot, item))
    for slot, item in placed:
        caption = _item_text(item)
        if number_caption(slot) and caption:
            texts[slot.id] = f"{split_number(texts[slot.id])[0]}\n{caption}"
            rest = [other for other in rest if other is not item]
    return rest


def _number_text(value: str, slot: Slot, slide: tuple[float, float] | None) -> str:
    """Номер без ведущего нуля, когда «01» не встаёт в слот в одну строку."""
    size = slot.style.size_pt
    if slide is None or not size:
        return value
    if len(value) <= line_capacity(slot.box, size, slide):
        return value
    return value.lstrip("0") or value


def _unit_texts(
    groups: list[RepeatGroup],
    items: list[Item],
    n: int,
    lead_taken: bool = False,
    slide: tuple[float, float] | None = None,
    lead: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Пункты по слотам блока: номер, заголовок, пояснение.

    Слоты главной и связанных групп разбираются вместе: номер идёт в группу номеров,
    подпись в группу подписей. Слов пункта не теряем: когда текстовый слот один,
    заголовок и пояснение идут в него вместе. lead_taken значит, что число уже стоит
    крупным слотом слайда и в блоке его повторять не надо. lead это число, на котором
    держится слайд: когда оно названо только словами заголовка, в блок идёт оно,
    а не порядковый номер блока.
    """
    pairs = [(group.id, slot) for group in groups for slot in group.unit_slots]
    numbers = [pair for pair in pairs if pair[1].role == "number"]
    heads = [pair for pair in pairs if pair[1].role in _HEAD_ROLES]
    # Пояснение идёт в слот body; подпись и метка берут его, только когда body в блоке нет.
    bodies = sorted((pair for pair in pairs if pair[1].role in _BODY_ROLES),
                    key=lambda pair: pair[1].role != "body")
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
                own = item.number or (lead if lead and len(items) == 1 else str(index + 1))
                texts[gid][slot.id] = _number_text(own, slot, slide)
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


def _decor_in(pattern: Pattern, frame: Box) -> set[int]:
    """Оформление образца, лежащее в рамке больше чем наполовину своей площади.

    Под диаграммой оно просвечивает водяными знаками. Фон на весь кадр, логотип
    и колонтитул остаются: их рамка задевает краем, а не накрывает.
    """
    return {shape.shape_id for shape in pattern.decor
            if not _edge_furniture(shape.box) and geo.covered(shape.box, frame) >= VIZ_INSIDE}


def _slot_line(unit: RepeatUnit, slot: Slot) -> Box:
    """Рамка слота в блоке образца: слот задан от левого верхнего угла первого блока."""
    return (unit.box[0] + slot.box[0], unit.box[1] + slot.box[1], slot.box[2], slot.box[3])


def _blank_units(pattern: Pattern, spec: SlideSpec) -> tuple[set[int], list[Box], list[Box]]:
    """Блоки, которым слов не досталось, и строки образца: пустые и заполненные.

    Блок без единого слова уходит целиком. Пустые строки нужны, чтобы убрать их маркеры,
    заполненные — чтобы маркер живой строки на слайде остался.
    """
    shapes: set[int] = set()
    blank: list[Box] = []
    live: list[Box] = []
    for group in pattern.groups:
        if not group.unit_slots:
            continue  # блоки без текстовых слотов это оформление, пустыми они не бывают
        texts = (spec.unit_text if group.id == spec.group_id
                 else spec.linked_unit_text.get(group.id) or [])
        for unit in group.units:
            said = texts[unit.index] if unit.index < len(texts) else {}
            if not any(said.get(slot.id) for slot in group.unit_slots):
                shapes.update(unit.shape_ids)
            for slot in group.unit_slots:
                line = _slot_line(unit, slot)
                (live if said.get(slot.id) else blank).append(line)
    return shapes, blank, live


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
        if area.id == spec.viz_area_id:
            continue
        if area.shape_id is None:
            # Образец диаграммы собран из фигур оформления: своей фигуры у него нет.
            if area.kind in _SAMPLE_VIZ:
                out |= _decor_in(pattern, area.box)
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
        out |= _decor_in(pattern, spec.viz_box)

    empty, blank, live = _blank_units(pattern, spec)
    out |= empty
    for shape in pattern.decor:
        if geo.area(shape.box) > MARKER_AREA:
            continue
        if any(_on_line(shape.box, line) for line in live):
            continue
        if any(_on_line(shape.box, line) for line in blank):
            out.add(shape.shape_id)
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
        out[slot.id] = slot_size(text, slot.box, size, slot.role, scale, slide)

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
                slot_size(
                    unit_texts[index][slot.id],
                    unit_slot_box(old, new, slot.box),
                    size,
                    slot.role,
                    scale,
                    slide,
                )
                for index, new in enumerate(boxes)
                if index < len(unit_texts) and unit_texts[index].get(slot.id)
            ]
            if sizes:
                # Один кегль на все блоки: разнобой внутри ряда виден сразу.
                out[slot.id] = min(sizes)
    return out


def _room_below(box: Box, busy: list[Box]) -> float:
    """Высота от верха рамки до ближайшего, что стоит под ней."""
    tops = [b[1] for b in busy
            if b[1] > box[1] + 1e-9 and min(geo.right(box), geo.right(b)) - max(box[0], b[0]) > 0]
    return min([*tops, geo.bottom(box)]) - box[1]


def _slot_ink(slot: Slot, text: str, size: float, slide: tuple[float, float]) -> Box:
    """Набранные строки слота. Число с подписью занимает рамку целиком: подпись стоит под числом."""
    if number_caption(slot) and split_number(text)[1]:
        return slot.box
    return ink_box(slot.box, text, size, slide)


def _standing(
    pattern: Pattern, spec: SlideSpec, texts: dict[str, str], fitted: dict[str, float],
    slide: tuple[float, float], n: int, skip: str,
) -> list[Box]:
    """Что уже стоит на слайде: набранные строки слотов, блоки групп и картинки шаблона."""
    out = [_slot_ink(s, texts[s.id], fitted.get(s.id, s.style.size_pt or 0.0), slide)
           for s in pattern.slots if s.id != skip and texts.get(s.id)]
    out += [a.box for a in pattern.areas if not a.placeholder and a.kind not in _SAMPLE_VIZ]
    group = next((g for g in pattern.groups if g.id == spec.group_id), None)
    if group is not None and n:
        linked = [g for g in pattern.groups if g.id in spec.linked_unit_text]
        main, other = unit_boxes(group, linked, n)
        out += [*main, *(box for boxes in other.values() for box in boxes)]
    return out


def _room_fix(
    pattern: Pattern, spec: SlideSpec, texts: dict[str, str], fitted: dict[str, float],
    ds: DesignSystem, n: int,
) -> None:
    """Крупный слот ужимается до высоты, свободной над тем, что под ним.

    Рамка разделителя и крупного числа в шаблоне часто ниже самой строки: она выходит
    из рамки и наезжает на подпись. Обычный текст такой правки не требует, он и так по шкале.
    """
    slide = slide_pt(ds.slide_size_emu)
    scale = ds.tokens.type_scale
    top = head_top(scale)
    if top is None:
        return
    for slot in pattern.slots:
        text, size = texts.get(slot.id, ""), slot.style.size_pt or 0.0
        if not text or size <= top + 0.01:
            continue
        room = _room_below(slot.box, _standing(pattern, spec, texts, fitted, slide, n, slot.id))
        if room >= slot.box[3] - 1e-9:
            continue
        box = (slot.box[0], slot.box[1], slot.box[2], max(room, 0.0))
        fitted[slot.id] = slot_size(text, box, size, slot.role, scale, slide)


def _hit_slots(
    head: Slot,
    text: str,
    size: float,
    below: list[Slot],
    texts: dict[str, str],
    fitted: dict[str, float],
    slide: tuple[float, float],
) -> list[Slot]:
    """Слоты под заголовком, на которые заходят его набранные строки."""
    ink = ink_box(head.box, text, size, slide)
    out = []
    for slot in below:
        own = fitted.get(slot.id, slot.style.size_pt or 0.0)
        if geo.overlap(ink, _slot_ink(slot, texts[slot.id], own, slide)) > OVERLAP_MIN:
            out.append(slot)
    return out


def _head_fix(
    pattern: Pattern, head: Slot | None, texts: dict[str, str], fitted: dict[str, float], ds: DesignSystem
) -> set[int]:
    """Заголовок, ставший выше образца, разводится с тем, что стоит под ним.

    Сначала заголовок опускается на ступень шкалы. Если строки всё равно заходят на слот
    под ним, текст того слота убирается, а его фигура уходит со слайда.
    """
    if head is None or not texts.get(head.id):
        return set()
    slide = slide_pt(ds.slide_size_emu)
    scale = ds.tokens.type_scale
    text = texts[head.id]
    size = fitted.get(head.id, head.style.size_pt or 0.0)
    if not size or text_lines(text, head.box, size, slide) <= head.max_lines:
        return set()
    below = [s for s in pattern.slots
             if s.id != head.id and texts.get(s.id) and s.box[1] > head.box[1]]
    if not _hit_slots(head, text, size, below, texts, fitted, slide):
        return set()
    lower = step_down(scale, size, size_floor(scale, head.role))
    if lower < size:
        size = lower
        fitted[head.id] = size
    out: set[int] = set()
    for slot in _hit_slots(head, text, size, below, texts, fitted, slide):
        texts[slot.id] = ""
        fitted.pop(slot.id, None)
        out.add(slot.shape_id)
    return out


def compose(intent: SlideIntent, pattern: Pattern, ds: DesignSystem) -> SlideSpec:
    """Инструкция сборки слайда: какой слот чем заполнить, где диаграмма и что со слайда убрать."""
    spec = SlideSpec(slide_id=intent.id, pattern_id=pattern.id, notes=intent.notes)
    texts = {slot.id: "" for slot in pattern.slots}
    # Слот-подсказка под картинку содержанием не заполняется: без своей картинки он и его
    # плашка уходят со слайда, иначе на нём остаётся пустой квадрат с мелкой надписью.
    hints = _hint_slots(pattern)
    free = [slot for slot in pattern.slots if slot.id not in hints]
    want = "chart" if intent.chart is not None else "table" if intent.table is not None else None
    region = content_region(pattern, ds.tokens.margins) if want else None

    title = _take(free, ("title",)) or _take(free, ("heading",), biggest=True)
    if title is not None:
        texts[title.id] = intent.title

    lead = lead_number(intent)
    lead_slot = _take(free, ("number",), avoid=region) if lead else None
    if lead_slot is not None:
        texts[lead_slot.id] = lead

    group = primary_group(pattern) if want is None else None
    if group is not None and not group.unit_slots:
        # Блоки без единого текстового слота это оформление: заполнить их нечем.
        group = None
    linked = linked_groups(pattern, group) if group is not None else []
    rest = list(intent.items)
    if group is None:
        rest = _captioned_numbers(intent, lead, lead_slot, free, region, texts)
    n = 0
    if rest and group is not None:
        n = unit_count(group, len(rest))
        for other in linked:
            n = min(n, other.max_units)
        n = max(n, group.min_units)
        linked = [other for other in linked if other.min_units <= n <= other.max_units]
        spread = _unit_texts([group, *linked], rest, n,
                             lead_slot is not None and len(rest) == 1, slide_pt(ds.slide_size_emu),
                             lead)
        spec.group_id = group.id
        spec.unit_text = spread[group.id]
        spec.linked_unit_text = {other.id: spread[other.id] for other in linked}
        rest = []

    if intent.key_message:
        message = intent.key_message
        slot = (
            _take(free, ("subtitle",), avoid=region, text=message)
            or _take(free, ("body",), biggest=True, avoid=region, text=message)
            or _take(free, ("heading",), biggest=True, avoid=region, text=message)
            or _take(free, ("caption",), biggest=True, avoid=region, text=message)
        )
        if slot is not None:
            texts[slot.id] = message

    if intent.attribution:
        slot = _take(free, _SIDE_ROLES, avoid=region, text=intent.attribution)
        if slot is not None:
            texts[slot.id] = intent.attribution

    for item in rest:
        slot = _take(free, _ITEM_ROLES, avoid=region, text=_item_text(item))
        if slot is None:
            break
        texts[slot.id] = _item_text(item)

    if want is not None:
        spec.chart, spec.table = intent.chart, intent.table
        busy = [slot.box for slot in pattern.slots if texts.get(slot.id)]
        spec.viz_area_id, spec.viz_box = _viz_place(pattern, ds, want, busy)

    spec.slot_text = texts
    spec.fitted_size_pt = _fitted(pattern, spec, texts, ds, n)
    _room_fix(pattern, spec, texts, spec.fitted_size_pt, ds, n)
    cleared = _head_fix(pattern, title, texts, spec.fitted_size_pt, ds)
    plates = set(hints.values()) | {s.shape_id for s in pattern.slots if s.id in hints}
    spec.remove_shape_ids = sorted(set(_removed(pattern, spec, texts, n)) | cleared | plates)
    return spec
