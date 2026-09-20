"""Проверки соответствия шаблону: шрифты, кегли, цвета, ссылка на паттерн, контраст.

Владелец: задача T-03.
"""
from designer.contracts import DesignSystem, Finding, Scene

_FONT_LIMIT = 2
_TYPE_SCALE_TOLERANCE_PT = 0.5
_COLOR_CHANNEL_TOLERANCE = 8
_CONTRAST_MIN = 4.5


def _hex_to_rgb255(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_in_palette(hex_color: str, palette: list[str]) -> bool:
    r, g, b = _hex_to_rgb255(hex_color)
    for p in palette:
        pr, pg, pb = _hex_to_rgb255(p)
        if (abs(r - pr) <= _COLOR_CHANNEL_TOLERANCE
                and abs(g - pg) <= _COLOR_CHANNEL_TOLERANCE
                and abs(b - pb) <= _COLOR_CHANNEL_TOLERANCE):
            return True
    return False


def _linearize(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb255(hex_color)
    return (0.2126 * _linearize(r / 255) + 0.7152 * _linearize(g / 255)
            + 0.0722 * _linearize(b / 255))


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    la, lb = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def check_font(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    palette = {f.family for f in ds.tokens.fonts}
    findings: list[Finding] = []
    for scene in scenes:
        used: dict[str, list[str]] = {}
        for el in scene.elements:
            if el.type != "text" or el.style is None or not el.style.family:
                continue
            used.setdefault(el.style.family, []).append(el.id)
            if palette and el.style.family not in palette:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="template.font", kind="deterministic",
                    severity="warning",
                    message=f"Шрифт «{el.style.family}» в «{el.id}» не входит в токены дизайн-системы",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
        if len(used) > _FONT_LIMIT:
            el_ids = [eid for ids in used.values() for eid in ids]
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="template.font", kind="deterministic",
                severity="warning",
                message=f"На слайде {len(used)} гарнитур вместо не более {_FONT_LIMIT}",
                element_ids=el_ids, box=None, fixable=False,
            ))
    return findings


def check_type_scale(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    scale = ds.tokens.type_scale
    if not scale:
        return []
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "text" or el.style is None or el.style.size_pt is None:
                continue
            size = el.style.size_pt
            if min(abs(size - step.size_pt) for step in scale) > _TYPE_SCALE_TOLERANCE_PT:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="template.type_scale", kind="deterministic",
                    severity="warning", message=f"Кегль {size:g} pt в «{el.id}» не входит в шкалу шаблона",
                    element_ids=[el.id], box=el.box, fixable=True,
                    fix_hint="уменьшить кегль до ступени шкалы",
                ))
    return findings


def check_color(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    palette = [c.hex for c in ds.tokens.colors]
    if not palette:
        return []
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type == "text" and el.style is not None and el.style.color:
                if not _color_in_palette(el.style.color, palette):
                    findings.append(Finding(
                        id="", slide_id=scene.slide_id, check_id="template.color", kind="deterministic",
                        severity="warning",
                        message=f"Цвет текста «{el.style.color}» в «{el.id}» не из палитры",
                        element_ids=[el.id], box=el.box, fixable=True,
                        fix_hint="заменить цвет ближайшим из палитры",
                    ))
            if el.fill and not _color_in_palette(el.fill, palette):
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="template.color", kind="deterministic",
                    severity="warning", message=f"Заливка «{el.fill}» в «{el.id}» не из палитры",
                    element_ids=[el.id], box=el.box, fixable=True,
                    fix_hint="заменить цвет ближайшим из палитры",
                ))
    return findings


def check_pattern(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    ids = {p.id for p in ds.patterns}
    findings: list[Finding] = []
    for scene in scenes:
        if scene.pattern_id not in ids:
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="template.pattern", kind="deterministic",
                severity="error", message=f"Паттерн «{scene.pattern_id}» отсутствует в дизайн-системе",
                element_ids=[], box=None, fixable=False,
            ))
    return findings


def _background_for(el, scene: Scene) -> str | None:
    x, y, w, h = el.box
    best_fill = None
    best_area = None
    for other in scene.elements:
        if other is el or other.type != "shape" or not other.fill:
            continue
        ox, oy, ow, oh = other.box
        if ox <= x + 1e-6 and oy <= y + 1e-6 and ox + ow >= x + w - 1e-6 and oy + oh >= y + h - 1e-6:
            area = ow * oh
            if best_area is None or area < best_area:
                best_fill, best_area = other.fill, area
    return best_fill if best_fill is not None else scene.background_color


def check_contrast(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "text" or not el.text or el.style is None or not el.style.color:
                continue
            bg = _background_for(el, scene)
            if not bg:
                continue
            ratio = _contrast_ratio(el.style.color, bg)
            if ratio < _CONTRAST_MIN:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="template.contrast", kind="deterministic",
                    severity="error",
                    message=f"Контраст текста «{el.id}» к фону {ratio:.2f}:1 ниже 4,5:1",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings
