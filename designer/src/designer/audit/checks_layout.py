"""Проверки вёрстки: границы, наложения, переполнение текста, поля, направляющие, пропорции.

Владелец: задача T-03.
"""
from designer.contracts import Box, DesignSystem, Finding, Scene

# deterministic.py собирает реестр проверок из этого модуля, поэтому его помощники
# (describe_element, on_template и другие) импортируются внутри функций, а не здесь:
# импорт на уровне модуля закольцовывает загрузку, если этот файл читается первым.

_EPS = 1e-6
_OVERLAP_TYPES = {"text", "image", "chart", "table", "icon"}
_GUIDE_TYPES = {"text", "image", "chart", "table"}
_GUIDE_TOLERANCE = 0.01
_CHAR_WIDTH_RATIO = 0.52
_LINE_HEIGHT_RATIO = 1.2
_ASPECT_TOLERANCE = 0.03
_EMU_PER_PT = 12700


def _slide_size_pt(ds: DesignSystem) -> tuple[float, float]:
    w_emu, h_emu = ds.slide_size_emu
    return w_emu / _EMU_PER_PT, h_emu / _EMU_PER_PT


def _intersect_area(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy


def check_out_of_bounds(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            x, y, w, h = el.box
            if x < -_EPS or y < -_EPS or x + w > 1 + _EPS or y + h > 1 + _EPS:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="layout.out_of_bounds", kind="deterministic",
                    severity="error", message=f"{describe_element(el).capitalize()}: выходит за границы слайда",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings


def _ink_box(el, slide_w_pt: float, slide_h_pt: float) -> Box | None:
    """Место, которое элемент занимает на деле. У текста это набранные строки, а не вся рамка:
    в шаблонах рамки текста часто с запасом и пересекаются, хотя строки друг друга не касаются."""
    if el.type != "text":
        return el.box
    if not el.text.strip():
        return None
    size_pt = el.style.size_pt if el.style and el.style.size_pt else None
    if not size_pt:
        return el.box
    x, y, w, h = el.box
    text_w = len(el.text) * _CHAR_WIDTH_RATIO * size_pt / slide_w_pt
    lines = max(1, -(-text_w // w)) if w > 0 else 1
    ink_w = min(w, text_w)
    ink_h = lines * size_pt * _LINE_HEIGHT_RATIO / slide_h_pt
    return (x, y, ink_w, ink_h)


def check_overlap(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    slide_w_pt, slide_h_pt = _slide_size_pt(ds)
    findings: list[Finding] = []
    for scene in scenes:
        inked = [(el, _ink_box(el, slide_w_pt, slide_h_pt)) for el in scene.elements if el.type in _OVERLAP_TYPES]
        els = [(el, box) for el, box in inked if box is not None]
        for i in range(len(els)):
            for j in range(i + 1, len(els)):
                (a, box_a), (b, box_b) = els[i], els[j]
                smaller = min(box_a[2] * box_a[3], box_b[2] * box_b[3])
                # Касание краями и перехлёст меньше двадцатой части меньшего блока огрехом не считаем.
                if smaller > 0 and _intersect_area(box_a, box_b) > 0.05 * smaller:
                    findings.append(Finding(
                        id="", slide_id=scene.slide_id, check_id="layout.overlap", kind="deterministic",
                        severity="error",
                        message=f"{describe_element(a).capitalize()} и {describe_element(b)}: накладываются друг на друга",
                        element_ids=[a.id, b.id], box=None, fixable=False,
                    ))
    return findings


def check_text_overflow(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    slide_w_pt, slide_h_pt = _slide_size_pt(ds)
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "text" or not el.text or el.style is None or el.style.size_pt is None:
                continue
            size_pt = el.style.size_pt
            x, y, w, h = el.box
            char_w_pt = _CHAR_WIDTH_RATIO * size_pt
            line_h_pt = size_pt * _LINE_HEIGHT_RATIO
            if char_w_pt <= 0 or line_h_pt <= 0:
                continue
            chars_per_line = int((w * slide_w_pt) // char_w_pt)
            lines_fit = int((h * slide_h_pt) // line_h_pt)
            capacity = chars_per_line * lines_fit
            if len(el.text) > capacity:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="layout.text_overflow", kind="deterministic",
                    severity="error",
                    message=f"{describe_element(el).capitalize()}: текст не помещается в рамку при кегле {size_pt:g} пт",
                    element_ids=[el.id], box=el.box, fixable=True,
                    fix_hint="уменьшить кегль до ступени шкалы",
                ))
    return findings


def check_in_margins(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    """Поля проверяются только у содержания: элемент на месте образца шаблона
    и оформление (фон, декор, колонтитул) огрехом полей не считаются (T-29)."""
    from designer.audit.deterministic import DECOR_ROLES, describe_element, on_template, pattern_by_id, template_frames
    m = ds.tokens.margins
    patterns = pattern_by_id(ds)
    findings: list[Finding] = []
    for scene in scenes:
        pattern = patterns.get(scene.pattern_id)
        frames = template_frames(pattern) if pattern else {}
        for el in scene.elements:
            if el.role in DECOR_ROLES or on_template(el, frames):
                continue
            x, y, w, h = el.box
            if (x < m.left - _EPS or y < m.top - _EPS
                    or x + w > 1 - m.right + _EPS or y + h > 1 - m.bottom + _EPS):
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="layout.in_margins", kind="deterministic",
                    severity="warning", message=f"{describe_element(el).capitalize()}: заходит в поля слайда",
                    element_ids=[el.id], box=el.box, fixable=True, fix_hint="сдвинуть к направляющей",
                ))
    return findings


def check_off_guides(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    """Элемент на месте образца шаблона направляющей не проверяется (T-29):
    шаблон сам и есть источник направляющих."""
    from designer.audit.deterministic import describe_element, on_template, pattern_by_id, template_frames
    guides = ds.tokens.guides_x
    if not guides:
        return []
    patterns = pattern_by_id(ds)
    findings: list[Finding] = []
    for scene in scenes:
        pattern = patterns.get(scene.pattern_id)
        frames = template_frames(pattern) if pattern else {}
        for el in scene.elements:
            if el.type not in _GUIDE_TYPES or on_template(el, frames):
                continue
            left = el.box[0]
            if min(abs(left - g) for g in guides) > _GUIDE_TOLERANCE:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="layout.off_guides", kind="deterministic",
                    severity="warning",
                    message=f"{describe_element(el).capitalize()}: левый край не стоит на направляющей шаблона",
                    element_ids=[el.id], box=el.box, fixable=True, fix_hint="сдвинуть к направляющей",
                ))
    return findings


def check_image_aspect(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    slide_w_pt, slide_h_pt = _slide_size_pt(ds)
    assets_by_id = {a.id: a for a in ds.assets}
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "image" or not el.asset:
                continue
            asset = assets_by_id.get(el.asset)
            if asset is None or not asset.height_px or not asset.width_px:
                continue
            x, y, w, h = el.box
            if h <= 0:
                continue
            box_aspect = (w * slide_w_pt) / (h * slide_h_pt)
            asset_aspect = asset.width_px / asset.height_px
            if abs(box_aspect - asset_aspect) / asset_aspect > _ASPECT_TOLERANCE:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="layout.image_aspect", kind="deterministic",
                    severity="warning",
                    message=f"{describe_element(el).capitalize()}: пропорции искажены",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings
