"""Намерение слайда -> инструкция сборки на паттерне. Владелец: задача T-07.

Слот, для которого содержания нет, получает пустую строку: образцовый текст шаблона
на собранном слайде остаться не должен.
"""
from __future__ import annotations

from designer.contracts import (
    DesignSystem,
    Item,
    Pattern,
    RepeatGroup,
    SlideIntent,
    SlideSpec,
    Slot,
)
from designer.layout.capacity import main_group, unit_count
from designer.parse import geometry as geo

_HEAD_ROLES = ("heading", "title")
_BODY_ROLES = ("body", "caption", "label", "subtitle")
_ITEM_ROLES = ("body", "heading", "caption", "label")
_SIDE_ROLES = ("caption", "label", "footer", "subtitle", "body")
_VIZ_AREAS = ("chart", "table", "image")


def _take(free: list[Slot], roles: tuple[str, ...], biggest: bool = False) -> Slot | None:
    """Забрать свободный слот одной из ролей: первый по порядку чтения или самый крупный."""
    matches = [slot for slot in free if slot.role in roles]
    if not matches:
        return None
    slot = max(matches, key=lambda s: (s.box[2] * s.box[3], s.id)) if biggest else matches[0]
    free.remove(slot)
    return slot


def _item_text(item: Item) -> str:
    parts = [part for part in (item.heading, item.body) if part]
    return "\n".join(parts)


def _unit_texts(group: RepeatGroup, items: list[Item], n: int) -> list[dict[str, str]]:
    """Пункты по слотам блока: заголовок, текст, номер."""
    heads = [s for s in group.unit_slots if s.role in _HEAD_ROLES]
    bodies = [s for s in group.unit_slots if s.role in _BODY_ROLES]
    numbers = [s for s in group.unit_slots if s.role == "number"]
    out: list[dict[str, str]] = []
    for index in range(n):
        texts = {slot.id: "" for slot in group.unit_slots}
        item = items[index] if index < len(items) else None
        if item is not None:
            head = item.heading or (item.body if not bodies else "")
            if numbers:
                texts[numbers[0].id] = item.number or str(index + 1)
            elif item.number:
                # Номера в блоке нет: число не теряем, оно идёт впереди заголовка.
                head = f"{item.number} {head}".strip()
            if heads:
                texts[heads[0].id] = head
            if bodies:
                texts[bodies[0].id] = item.body or (item.heading if not heads else "")
        out.append(texts)
    return out


def _viz_target(
    intent: SlideIntent, pattern: Pattern, group: RepeatGroup | None, free: list[Slot]
) -> tuple[str | None, Slot | None]:
    """Куда положить диаграмму или таблицу.

    Своя область забирает визуализацию сразу. Своей нет: из чужой области, места блоков
    и крупного слота берётся самое просторное место.
    """
    want = "chart" if intent.chart is not None else "table"
    same = [a for a in pattern.areas if a.kind == want]
    if same:
        return max(same, key=lambda a: (a.box[2] * a.box[3], a.id)).id, None

    places = [(a.box, a.id) for a in pattern.areas if a.kind in _VIZ_AREAS]
    if group is not None and group.units:
        places.append((geo.union([unit.box for unit in group.units]), group.id))
    if places:
        return max(places, key=lambda place: (place[0][2] * place[0][3], place[1]))[1], None

    slot = _take(free, ("body",), biggest=True)
    if slot is not None:
        return slot.id, slot
    return None, None


def compose(intent: SlideIntent, pattern: Pattern, ds: DesignSystem) -> SlideSpec:
    """Инструкция сборки слайда: какой слот чем заполнить и сколько блоков поставить."""
    spec = SlideSpec(slide_id=intent.id, pattern_id=pattern.id, notes=intent.notes)
    texts = {slot.id: "" for slot in pattern.slots}
    free = list(pattern.slots)

    title = _take(free, ("title",)) or _take(free, ("heading",), biggest=True)
    if title is not None:
        texts[title.id] = intent.title

    group = main_group(pattern)
    if intent.chart is not None or intent.table is not None:
        target, slot = _viz_target(intent, pattern, group, free)
        spec.chart = intent.chart
        spec.table = intent.table
        spec.viz_area_id = target
        if slot is not None and slot in free:
            free.remove(slot)

    rest = list(intent.items)
    if rest and group is not None and spec.viz_area_id != group.id:
        n = unit_count(group, len(rest))
        spec.group_id = group.id
        spec.unit_text = _unit_texts(group, rest, n)
        rest = []

    if intent.key_message:
        slot = (
            _take(free, ("subtitle",))
            or _take(free, ("body",), biggest=True)
            or _take(free, ("heading",), biggest=True)
            or _take(free, ("caption",), biggest=True)
        )
        if slot is not None:
            texts[slot.id] = intent.key_message

    lead = next((item.number for item in intent.items if item.number), None)
    if lead:
        slot = _take(free, ("number",))
        if slot is not None:
            texts[slot.id] = lead

    if intent.attribution:
        slot = _take(free, _SIDE_ROLES)
        if slot is not None:
            texts[slot.id] = intent.attribution

    for item in rest:
        slot = _take(free, _ITEM_ROLES)
        if slot is None:
            break
        texts[slot.id] = _item_text(item)

    spec.slot_text = texts
    return spec
