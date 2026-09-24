"""Детерминированные проверки готовой сцены. Владелец: задача T-03.

Общие помощники для калибровки под шаблон и для человекочитаемых сообщений
объявлены здесь и используются во всех проверках (задача T-29): элемент,
который шаблон поставил сам, не считается огрехом вёрстки, а сообщение
называет элемент ролью и началом текста, а не внутренним id фигуры.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import NamedTuple

from designer.contracts import Box, DesignSystem, Element, Finding, Pattern, RepeatGroup, Scene
from designer.layout.units import map_shape_box, place_units

CheckFunc = Callable[[list[Scene], DesignSystem], list[Finding]]

# Роли, которые несут оформление, а не содержание: фон, декоративные фигуры,
# логотип, колонтитул. Такие элементы не считаются при разборе полей и заполнения.
DECOR_ROLES = frozenset({"decor", "footer"})

_FRAME_TOLERANCE = 0.01
_UNIT_ID_RE = re.compile(r"^u(\d+)s\d+$")
_SNIPPET_LEN = 24

_ROLE_RU = {
    "title": "заголовок",
    "subtitle": "подзаголовок",
    "heading": "заголовок",
    "body": "текст",
    "caption": "подпись",
    "number": "число",
    "label": "подпись",
    "footer": "колонтитул",
    "decor": "оформление",
}

_TYPE_RU = {
    "chart": "диаграмма",
    "table": "таблица",
    "image": "картинка",
    "icon": "значок",
    "shape": "фигура",
    "text": "текст",
}


def pattern_by_id(ds: DesignSystem) -> dict[str, Pattern]:
    """Паттерны дизайн-системы по id — так проверки находят образец своей сцены."""
    return {p.id: p for p in ds.patterns}


def _box_close(a: Box, b: Box, tol: float) -> bool:
    return all(abs(a[i] - b[i]) <= tol for i in range(4))


_KEEP_SIZE_AREAS = ("image", "icon")


def _group_frames(group: RepeatGroup) -> dict[int, list[Box]]:
    """Рамки слотов и мест блока при любом числе блоков от min_units до max_units.

    Та же геометрия, что при сборке сцены (`layout.scene`, `layout.capacity.unit_boxes`):
    когда блоков меньше, чем в образце, сетка переукладывает их (шире или по-другому — тот
    же расчёт `place_units`), и это по-прежнему место, которое поставил шаблон, а не сдвиг."""
    frames: dict[int, list[Box]] = {}
    if not group.units:
        return frames
    old_unit = group.units[0].box
    for n in range(group.min_units, group.max_units + 1):
        try:
            new_units = place_units(group, n)
        except ValueError:
            continue
        for new_unit in new_units:
            for slot in group.unit_slots:
                sx, sy, sw, sh = slot.box
                absolute = (old_unit[0] + sx, old_unit[1] + sy, sw, sh)
                box = map_shape_box(old_unit, new_unit, absolute)
                frames.setdefault(slot.shape_id, []).append(box)
            for area in group.unit_areas:
                if area.shape_id is None:
                    continue
                ax, ay, aw, ah = area.box
                absolute = (old_unit[0] + ax, old_unit[1] + ay, aw, ah)
                box = map_shape_box(old_unit, new_unit, absolute, keep_size=area.kind in _KEEP_SIZE_AREAS)
                frames.setdefault(area.shape_id, []).append(box)
    return frames


def template_frames(pattern: Pattern) -> dict[int, list[Box]]:
    """Рамки, куда шаблон поставил свои слоты, картинки и фигуры оформления.

    Ключ — id исходной фигуры (shape_id). Для повторяющихся блоков (карточки,
    шаги) учтены рамки при любом числе блоков, какое допускает сетка группы:
    вёрстка вправе положить меньше блоков, чем в образце, это не самовольный сдвиг.
    """
    frames: dict[int, list[Box]] = {}

    def add(shape_id: int | None, box: Box) -> None:
        if shape_id is not None:
            frames.setdefault(shape_id, []).append(box)

    for slot in pattern.slots:
        add(slot.shape_id, slot.box)
    for area in pattern.areas:
        add(area.shape_id, area.box)
    for decor in pattern.decor:
        add(decor.shape_id, decor.box)
    for group in pattern.groups:
        for shape_id, boxes in _group_frames(group).items():
            frames.setdefault(shape_id, []).extend(boxes)
    return frames


def on_template(el: Element, frames: dict[int, list[Box]], tol: float = _FRAME_TOLERANCE) -> bool:
    """Элемент стоит там, куда его поставил шаблон: та же фигура образца, рамка не сдвинута."""
    if el.source_shape_id is None:
        return False
    for box in frames.get(el.source_shape_id, []):
        if _box_close(el.box, box, tol):
            return True
    return False


def _sample_slot(el: Element, pattern: Pattern | None):
    if pattern is None or el.source_shape_id is None:
        return None
    for slot in pattern.slots:
        if slot.shape_id == el.source_shape_id:
            return slot
    for group in pattern.groups:
        for slot in group.unit_slots:
            if slot.shape_id == el.source_shape_id:
                return slot
    return None


def sample_type_size(el: Element, pattern: Pattern | None) -> float | None:
    """Кегль, которым этот слот набран в образце паттерна."""
    slot = _sample_slot(el, pattern)
    return slot.style.size_pt if slot is not None else None


def sample_type_color(el: Element, pattern: Pattern | None) -> str | None:
    """Цвет текста, которым этот слот набран в образце паттерна."""
    slot = _sample_slot(el, pattern)
    return slot.style.color if slot is not None else None


def _snippet(text: str) -> str:
    line = next((s.strip() for s in text.splitlines() if s.strip()), "")
    if len(line) > _SNIPPET_LEN:
        return line[:_SNIPPET_LEN].rstrip() + "…"
    return line


def upper_first(text: str) -> str:
    """Заглавная только первая буква: str.capitalize() опускает остальные («Заголовок «перевод…»»)."""
    return text[:1].upper() + text[1:]


def describe_element(el: Element) -> str:
    """Человеческое имя элемента для сообщений находок: роль по-русски и начало текста,
    без внутреннего id фигуры вроде «s401» или «d1056»."""
    if el.type in ("chart", "table"):
        base = _TYPE_RU[el.type]
    elif el.role in _ROLE_RU:
        base = _ROLE_RU[el.role]
    else:
        base = _TYPE_RU.get(el.type, "элемент")
    match = _UNIT_ID_RE.match(el.id)
    if match:
        base = f"{base} блока {int(match.group(1)) + 1}"
    if el.type == "text" and el.text.strip():
        return f'{base} «{_snippet(el.text)}»'
    return base


class CheckDef(NamedTuple):
    id: str
    group: str
    title_ru: str
    func: CheckFunc


from designer.audit import checks_density, checks_integrity, checks_layout, checks_template  # noqa: E402

CHECKS: list[CheckDef] = [
    CheckDef("layout.out_of_bounds", "layout", "Элемент вышел за границы слайда", checks_layout.check_out_of_bounds),
    CheckDef("layout.overlap", "layout", "Наложение содержательных блоков", checks_layout.check_overlap),
    CheckDef("layout.text_overflow", "layout", "Текст не помещается в рамку", checks_layout.check_text_overflow),
    CheckDef("layout.in_margins", "layout", "Содержимое зашло в поля", checks_layout.check_in_margins),
    CheckDef("layout.off_guides", "layout", "Блок не совпадает с направляющей", checks_layout.check_off_guides),
    CheckDef("layout.image_aspect", "layout", "Картинка растянута", checks_layout.check_image_aspect),
    CheckDef("template.font", "template", "Шрифт не из шаблона", checks_template.check_font),
    CheckDef("template.type_scale", "template", "Кегль не из шкалы", checks_template.check_type_scale),
    CheckDef("template.color", "template", "Цвет не из палитры", checks_template.check_color),
    CheckDef("template.pattern", "template", "Паттерн отсутствует в дизайн-системе", checks_template.check_pattern),
    CheckDef("template.contrast", "template", "Низкий контраст текста", checks_template.check_contrast),
    CheckDef("density.bullets", "density", "Слишком много пунктов", checks_density.check_bullets),
    CheckDef("density.bullet_words", "density", "Слишком длинный пункт", checks_density.check_bullet_words),
    CheckDef("density.table", "density", "Слишком большая таблица", checks_density.check_table),
    CheckDef("density.series", "density", "Слишком много рядов на диаграмме", checks_density.check_series),
    CheckDef("density.fill", "density", "Заполнение слайда вне нормы", checks_density.check_fill),
    CheckDef("integrity.placeholder_text", "integrity", "Остался текст-заглушка", checks_integrity.check_placeholder_text),
    CheckDef("integrity.empty", "integrity", "Пустой слайд", checks_integrity.check_empty),
    CheckDef("integrity.chart_labels", "integrity", "Диаграмме не хватает подписей", checks_integrity.check_chart_labels),
    CheckDef("integrity.duplicate", "integrity", "Слайд дублирует другой", checks_integrity.check_duplicate),
]


def run_checks(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    """Прогоняет все зарегистрированные проверки и возвращает находки в стабильном порядке."""
    order = {scene.slide_id: idx for idx, scene in enumerate(scenes)}
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check.func(scenes, ds))
    findings.sort(key=lambda f: (order.get(f.slide_id, len(order)), f.check_id, f.element_ids))

    counters: dict[tuple[str, str], int] = {}
    for f in findings:
        key = (f.slide_id, f.check_id)
        n = counters.get(key, 0)
        f.id = f"{f.slide_id}.{f.check_id}.{n}"
        counters[key] = n + 1
    return findings
