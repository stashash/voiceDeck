"""Починка находок аудита по выбору человека. Владелец: задача T-21.

Каждая проверка из списка ниже умеет чинить себя сама, без модели: кегль, цвет,
положение или текст меняются по детерминированному правилу. Проверка, для которой
починки нет (контекстная или не из списка), получает в отчёте skipped.
"""
import re
from collections.abc import Callable

from designer.audit.deterministic import describe_element
from designer.contracts import Box, DesignSystem, Element, Finding, Pattern, Scene, SlideSpec

_COLOR_CHANNEL_TOLERANCE = 8
_CHAR_WIDTH_RATIO = 0.52
_LINE_HEIGHT_RATIO = 1.2
_EMU_PER_PT = 12700
_OVERLAP_TYPES = {"text", "image", "chart", "table", "icon"}
_MAX_BULLETS = 6
_OFF_GUIDES_MAX_SHIFT = 0.02
_IN_MARGINS_MAX_SHIFT = 0.03
_UNIT_ID_RE = re.compile(r"^u(\d+)s(\d+)$")


# ---------- геометрия и цвет: те же формулы, что у проверок, но свои, чтобы не тянуть чужой модуль ----------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _in_palette(hex_color: str, palette: list[str]) -> bool:
    r, g, b = _hex_to_rgb(hex_color)
    for p in palette:
        pr, pg, pb = _hex_to_rgb(p)
        if (abs(r - pr) <= _COLOR_CHANNEL_TOLERANCE and abs(g - pg) <= _COLOR_CHANNEL_TOLERANCE
                and abs(b - pb) <= _COLOR_CHANNEL_TOLERANCE):
            return True
    return False


def _nearest_color(hex_color: str, palette: list[str]) -> str:
    r, g, b = _hex_to_rgb(hex_color)

    def dist(p: str) -> int:
        pr, pg, pb = _hex_to_rgb(p)
        return (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2

    return min(palette, key=dist)


def _linearize(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * _linearize(r / 255) + 0.7152 * _linearize(g / 255) + 0.0722 * _linearize(b / 255)


def _contrast(hex_a: str, hex_b: str) -> float:
    la, lb = _luminance(hex_a), _luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _background_for(el: Element, scene: Scene) -> str | None:
    x, y, w, h = el.box
    best_fill, best_area = None, None
    for other in scene.elements:
        if other is el or other.type != "shape" or not other.fill:
            continue
        ox, oy, ow, oh = other.box
        if ox <= x + 1e-6 and oy <= y + 1e-6 and ox + ow >= x + w - 1e-6 and oy + oh >= y + h - 1e-6:
            area = ow * oh
            if best_area is None or area < best_area:
                best_fill, best_area = other.fill, area
    return best_fill if best_fill is not None else scene.background_color


def _slide_pt(ds: DesignSystem) -> tuple[float, float]:
    w_emu, h_emu = ds.slide_size_emu
    return w_emu / _EMU_PER_PT, h_emu / _EMU_PER_PT


def _capacity(box: Box, size_pt: float, slide: tuple[float, float]) -> int:
    char_w_pt = _CHAR_WIDTH_RATIO * size_pt
    line_h_pt = size_pt * _LINE_HEIGHT_RATIO
    if char_w_pt <= 0 or line_h_pt <= 0:
        return 0
    chars_per_line = int((box[2] * slide[0]) // char_w_pt)
    lines_fit = int((box[3] * slide[1]) // line_h_pt)
    return chars_per_line * lines_fit


def _intersect_area(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy


def _creates_overlap(scene: Scene, el: Element, new_box: Box) -> bool:
    if el.type not in _OVERLAP_TYPES:
        return False
    area_new = new_box[2] * new_box[3]
    for other in scene.elements:
        if other is el or other.type not in _OVERLAP_TYPES:
            continue
        smaller = min(area_new, other.box[2] * other.box[3])
        if smaller > 0 and _intersect_area(new_box, other.box) > 0.05 * smaller:
            return True
    return False


# ---------- связь элемента сцены со слотом инструкции ----------

def _find_element(scene: Scene, el_id: str) -> Element | None:
    for el in scene.elements:
        if el.id == el_id:
            return el
    return None


def _pattern_for(scene: Scene, ds: DesignSystem) -> Pattern | None:
    return next((p for p in ds.patterns if p.id == scene.pattern_id), None)


def _slot_ref(el: Element, pattern: Pattern | None):
    """Слот паттерна для элемента: слот верхнего уровня либо слот повторяющегося блока.

    Для блока также нужен номер повтора: id элемента блока это "u{индекс}s{shape_id}",
    так его собирает сборка сцены.
    """
    if pattern is None:
        return None, None, None
    for slot in pattern.slots:
        if slot.id == el.id:
            return slot, None, None
    match = _UNIT_ID_RE.match(el.id)
    if not match or el.source_shape_id is None:
        return None, None, None
    index = int(match.group(1))
    for group in pattern.groups:
        for slot in group.unit_slots:
            if slot.shape_id == el.source_shape_id:
                return slot, group, index
    return None, None, None


def _set_fitted_size(spec: SlideSpec, slot, size_pt: float) -> None:
    spec.fitted_size_pt[slot.id] = size_pt


def _set_slot_text(spec: SlideSpec, slot, group, index: int | None, text: str) -> None:
    if group is None:
        spec.slot_text[slot.id] = text
        return
    target = spec.linked_unit_text[group.id] if group.id in spec.linked_unit_text else spec.unit_text
    if index is not None and 0 <= index < len(target):
        target[index][slot.id] = text


# ---------- починки по check_id ----------

def _fix_type_scale(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    scale = ds.tokens.type_scale
    if not scale or not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None or el.type != "text" or el.style is None or el.style.size_pt is None:
        return None
    old_size = el.style.size_pt
    if el.role == "number":
        return None  # крупное число подогнано по ширине рамки: ступень шкалы его сломает
    new_size = min(scale, key=lambda s: (abs(s.size_pt - old_size), s.size_pt)).size_pt
    if abs(new_size - old_size) < 0.5:
        return None
    el.style = el.style.model_copy(update={"size_pt": new_size})
    slot, group, index = _slot_ref(el, pattern)
    if slot is not None:
        _set_fitted_size(spec, slot, new_size)
    return f"{describe_element(el).capitalize()}: кегль {old_size:g} пт заменён ступенью шкалы {new_size:g} пт"


def _fix_color(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    palette = [c.hex for c in ds.tokens.colors]
    if not palette or not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None:
        return None
    changed = []
    if el.type == "text" and el.style is not None and el.style.color and not _in_palette(el.style.color, palette):
        old = el.style.color
        new = _nearest_color(old, palette)
        el.style = el.style.model_copy(update={"color": new})
        changed.append(f"цвет текста #{old} заменён на #{new}")
    if el.fill and not _in_palette(el.fill, palette):
        old = el.fill
        el.fill = _nearest_color(old, palette)
        changed.append(f"заливка #{old} заменена на #{el.fill}")
    if not changed:
        return None
    return f"{describe_element(el).capitalize()}: " + "; ".join(changed)


def _fix_text_overflow(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    scale = ds.tokens.type_scale
    if not scale or not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None or el.type != "text" or not el.text or el.style is None or el.style.size_pt is None:
        return None
    slide = _slide_pt(ds)
    steps = sorted({s.size_pt for s in scale if s.size_pt > 0}, reverse=True)
    if not steps:
        return None
    old_size = el.style.size_pt
    candidates = [s for s in steps if s <= old_size + 1e-6] or steps
    chosen = None
    for step in candidates:
        if _capacity(el.box, step, slide) >= len(el.text):
            chosen = step
            break
    if chosen is None:
        chosen = candidates[-1]
    if chosen >= old_size - 1e-6:
        return None  # опускать некуда: текст не помещается и на нижней ступени
    el.style = el.style.model_copy(update={"size_pt": chosen})
    slot, group, index = _slot_ref(el, pattern)
    if slot is not None:
        _set_fitted_size(spec, slot, chosen)
    return f"{describe_element(el).capitalize()}: кегль уменьшен с {old_size:g} до {chosen:g} пт, текст помещается в рамку"


def _fix_off_guides(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    guides = ds.tokens.guides_x
    if not guides or not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None:
        return None
    x, y, w, h = el.box
    nearest = min(guides, key=lambda g: abs(g - x))
    if abs(nearest - x) > _OFF_GUIDES_MAX_SHIFT:
        return None
    new_box = (nearest, y, w, h)
    if _creates_overlap(scene, el, new_box):
        return None
    el.box = new_box
    return f"{describe_element(el).capitalize()}: левый край сдвинут к направляющей шаблона"


def _fix_in_margins(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    if not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None:
        return None
    m = ds.tokens.margins
    x, y, w, h = el.box
    dx = 0.0
    if x < m.left:
        dx = m.left - x
    elif x + w > 1 - m.right:
        dx = (1 - m.right) - (x + w)
    dy = 0.0
    if y < m.top:
        dy = m.top - y
    elif y + h > 1 - m.bottom:
        dy = (1 - m.bottom) - (y + h)
    if abs(dx) > _IN_MARGINS_MAX_SHIFT or abs(dy) > _IN_MARGINS_MAX_SHIFT:
        return None
    if dx == 0.0 and dy == 0.0:
        return None
    el.box = (x + dx, y + dy, w, h)
    return f"{describe_element(el)} сдвинут внутрь полей слайда"


def _fix_contrast(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    palette = [c.hex for c in ds.tokens.colors]
    if not palette or not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None or el.type != "text" or el.style is None or not el.style.color:
        return None
    bg = _background_for(el, scene)
    if not bg:
        return None
    best = max(palette, key=lambda c: _contrast(c, bg))
    old = el.style.color
    el.style = el.style.model_copy(update={"color": best})
    return f"цвет текста {describe_element(el)} заменён с {old} на {best} для контраста к фону {bg}"


def _fix_placeholder_text(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    if not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None or el.type != "text":
        return None
    old = el.text
    el.text = ""
    slot, group, index = _slot_ref(el, pattern)
    if slot is not None:
        _set_slot_text(spec, slot, group, index, "")
    return f"текст-заглушка «{old}» очищен в {describe_element(el)}"


def _fix_bullets(finding: Finding, scene: Scene, spec: SlideSpec, pattern: Pattern | None, ds: DesignSystem):
    if not finding.element_ids:
        return None
    el = _find_element(scene, finding.element_ids[0])
    if el is None or el.type != "text" or not el.text:
        return None
    lines = [line for line in el.text.split("\n") if line.strip()]
    if len(lines) <= _MAX_BULLETS:
        return None
    kept, removed = lines[:_MAX_BULLETS], lines[_MAX_BULLETS:]
    new_text = "\n".join(kept)
    el.text = new_text
    slot, group, index = _slot_ref(el, pattern)
    if slot is not None:
        _set_slot_text(spec, slot, group, index, new_text)
    return f"{describe_element(el).capitalize()}: убраны лишние пункты: {'; '.join(removed)}"


_FIXERS: dict[str, Callable] = {
    "template.type_scale": _fix_type_scale,
    "template.color": _fix_color,
    "layout.text_overflow": _fix_text_overflow,
    "layout.off_guides": _fix_off_guides,
    "layout.in_margins": _fix_in_margins,
    "template.contrast": _fix_contrast,
    "integrity.placeholder_text": _fix_placeholder_text,
    "density.bullets": _fix_bullets,
}


def apply_fixes(specs: list[SlideSpec], scenes: list[Scene], findings: list[Finding], chosen_ids: list[str],
                ds: DesignSystem) -> tuple[list[SlideSpec], list[Scene], list[dict]]:
    """Чинит выбранные находки и возвращает новые инструкции, сцены и отчёт.

    Отчёт: по записи на находку: {"finding_id", "status": "fixed" | "skipped", "what": что изменено по-русски}.
    Входные объекты не меняются.
    """
    new_specs = [s.model_copy(deep=True) for s in specs]
    new_scenes = [s.model_copy(deep=True) for s in scenes]
    specs_by_slide = {s.slide_id: s for s in new_specs}
    scenes_by_slide = {s.slide_id: s for s in new_scenes}
    findings_by_id = {f.id: f for f in findings}

    report: list[dict] = []
    for finding_id in chosen_ids:
        finding = findings_by_id.get(finding_id)
        if finding is None:
            report.append({"finding_id": finding_id, "status": "skipped", "what": "находка не найдена"})
            continue
        fixer = _FIXERS.get(finding.check_id)
        if fixer is None:
            report.append({
                "finding_id": finding_id, "status": "skipped",
                "what": f"для проверки «{finding.check_id}» нет автоматической починки",
            })
            continue
        scene = scenes_by_slide.get(finding.slide_id)
        spec = specs_by_slide.get(finding.slide_id)
        if scene is None or spec is None:
            report.append({"finding_id": finding_id, "status": "skipped", "what": "слайд находки не найден"})
            continue
        pattern = _pattern_for(scene, ds)
        what = fixer(finding, scene, spec, pattern, ds)
        if what is None:
            report.append({
                "finding_id": finding_id, "status": "skipped",
                "what": "условия автоматической починки не выполнены",
            })
        else:
            report.append({"finding_id": finding_id, "status": "fixed", "what": what})

    return new_specs, new_scenes, report
