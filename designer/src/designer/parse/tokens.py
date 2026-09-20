"""Палитра, шрифты, шкала кеглей, поля и направляющие. Владелец: задача T-01."""
from __future__ import annotations

import colorsys
from collections import defaultdict
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from designer.contracts import ColorToken, FontToken, Margins, Tokens, TypeStep

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A_NS, "p": P_NS}

# 12 канонических цветов темы, ровно в этом порядке живут в <a:clrScheme>.
THEME_SLOTS = (
    "dk1", "lt1", "dk2", "lt2",
    "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
    "hlink", "folHlink",
)
# Роль по умолчанию для каждого слота темы (используется только для source="theme").
THEME_SLOT_ROLE = {
    "dk1": "text", "lt1": "background", "dk2": "text_muted", "lt2": "surface",
    "accent1": "accent", "accent2": "accent_alt",
    "accent3": "other", "accent4": "other", "accent5": "other", "accent6": "other",
    "hlink": "other", "folHlink": "other",
}
CLR_MAP_KEYS = THEME_SLOTS

MONO_HINTS = (
    "mono", "consolas", "courier", "menlo", "monaco", "cascadia",
    "code", "sfmono", "jetbrains", "hack", "inconsolata",
)

TITLE_TYPES = {"title", "ctrTitle"}
BODY_TYPES = {"body", "subTitle", "obj"}


# ---------- Тема и цвета ----------

def _color_from_slot_el(el) -> str | None:
    srgb = el.find("a:srgbClr", NS)
    if srgb is not None:
        return srgb.get("val", "").upper()
    sys_clr = el.find("a:sysClr", NS)
    if sys_clr is not None:
        return (sys_clr.get("lastClr") or "000000").upper()
    return None


def _load_theme_colors(theme_root) -> dict[str, str]:
    scheme = theme_root.find(".//a:clrScheme", NS)
    colors: dict[str, str] = {}
    if scheme is None:
        return colors
    for slot in THEME_SLOTS:
        el = scheme.find(f"a:{slot}", NS)
        if el is None:
            continue
        hexval = _color_from_slot_el(el)
        if hexval:
            colors[slot] = hexval
    return colors


def _load_theme_fonts(theme_root) -> dict[str, str]:
    major = theme_root.find(".//a:fontScheme/a:majorFont/a:latin", NS)
    minor = theme_root.find(".//a:fontScheme/a:minorFont/a:latin", NS)
    return {
        "+mj-lt": (major.get("typeface") if major is not None else "") or "",
        "+mn-lt": (minor.get("typeface") if minor is not None else "") or "",
    }


def _apply_lum_mods(hexval: str, el) -> str:
    """lumMod/lumOff меняют яркость цвета в пространстве HLS."""
    lum_mod = el.find("a:lumMod", NS)
    lum_off = el.find("a:lumOff", NS)
    if lum_mod is None and lum_off is None:
        return hexval
    try:
        r = int(hexval[0:2], 16) / 255
        g = int(hexval[2:4], 16) / 255
        b = int(hexval[4:6], 16) / 255
    except ValueError:
        return hexval
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    mod = int(lum_mod.get("val")) / 100000 if lum_mod is not None else 1.0
    off = int(lum_off.get("val")) / 100000 if lum_off is not None else 0.0
    l = max(0.0, min(1.0, l * mod + off))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _master_clr_map(master_root) -> dict[str, str]:
    el = master_root.find("p:clrMap", NS)
    if el is None:
        return {k: k for k in CLR_MAP_KEYS}
    return {k: el.get(k, k) for k in CLR_MAP_KEYS}


def _part_clr_map(part_root, base_map: dict[str, str]) -> dict[str, str]:
    """clrMapOvr слайда или макета переопределяет карту мастера, если задана явно."""
    ovr = part_root.find("p:clrMapOvr", NS)
    if ovr is None:
        return base_map
    override = ovr.find("a:overrideClrMapping", NS)
    if override is None:
        return base_map
    merged = dict(base_map)
    for key in CLR_MAP_KEYS:
        val = override.get(key)
        if val:
            merged[key] = val
    return merged


def _resolve_scheme_color(el, theme_colors: dict[str, str], clr_map: dict[str, str]) -> str | None:
    val = el.get("val")
    if not val:
        return None
    slot = clr_map.get(val, val)
    hexval = theme_colors.get(slot)
    if hexval is None:
        return None
    return _apply_lum_mods(hexval, el)


def _resolve_color_container(container, theme_colors: dict[str, str], clr_map: dict[str, str]) -> str | None:
    """container — элемент с прямым цветовым потомком (a:solidFill, a:buClr и т.п.)."""
    if container is None:
        return None
    srgb = container.find("a:srgbClr", NS)
    if srgb is not None:
        return _apply_lum_mods(srgb.get("val", "").upper(), srgb)
    scheme = container.find("a:schemeClr", NS)
    if scheme is not None:
        return _resolve_scheme_color(scheme, theme_colors, clr_map)
    sys_clr = container.find("a:sysClr", NS)
    if sys_clr is not None:
        return _apply_lum_mods((sys_clr.get("lastClr") or "000000").upper(), sys_clr)
    return None


def _resolve_typeface(raw: str | None, theme_fonts: dict[str, str]) -> str | None:
    if not raw:
        return None
    if raw in theme_fonts:
        return theme_fonts[raw] or None
    return raw


def _is_mono(family: str) -> bool:
    low = family.lower()
    return any(hint in low for hint in MONO_HINTS)


# ---------- Наследование кегля от заполнителя ----------

def _style_category(ph_type: str) -> str:
    if ph_type in TITLE_TYPES:
        return "titleStyle"
    if ph_type in BODY_TYPES:
        return "bodyStyle"
    return "otherStyle"


def _find_placeholder_shape(root, ph_type: str, ph_idx: str | None):
    exact = None
    same_type = None
    for sp in root.iter(f"{{{P_NS}}}sp"):
        ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            continue
        t = ph.get("type") or "body"
        idx = ph.get("idx")
        if t == ph_type and idx == ph_idx:
            exact = sp
            break
        if t == ph_type and same_type is None:
            same_type = sp
    return exact if exact is not None else same_type


def _level_size_from_lst_style(lst_style, level: int) -> float | None:
    if lst_style is None:
        return None
    lvl_el = lst_style.find(f"a:lvl{level + 1}pPr", NS)
    if lvl_el is None:
        return None
    def_rpr = lvl_el.find("a:defRPr", NS)
    if def_rpr is None:
        return None
    sz = def_rpr.get("sz")
    return int(sz) / 100 if sz else None


def _inherited_size_pt(ph_type: str, ph_idx: str | None, level: int, layout_root, master_root) -> float | None:
    layout_ph = _find_placeholder_shape(layout_root, ph_type, ph_idx)
    size = _level_size_from_lst_style(
        layout_ph.find("p:txBody/a:lstStyle", NS) if layout_ph is not None else None, level
    )
    if size is not None:
        return size
    master_ph = _find_placeholder_shape(master_root, ph_type, ph_idx)
    size = _level_size_from_lst_style(
        master_ph.find("p:txBody/a:lstStyle", NS) if master_ph is not None else None, level
    )
    if size is not None:
        return size
    category = _style_category(ph_type)
    styles = master_root.find(f"p:txStyles/p:{category}", NS)
    return _level_size_from_lst_style(styles, level)


# ---------- Основной проход ----------

def _shape_ph_key(sp) -> tuple[str, str | None] | None:
    ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
    if ph is None:
        return None
    return ph.get("type") or "body", ph.get("idx")


def _iter_shapes(root):
    for tag in ("sp", "pic", "cxnSp"):
        yield from root.iter(f"{{{P_NS}}}{tag}")


def _effective_background(slide_root, layout_root, master_root, theme_colors, slide_map, layout_map, master_map):
    for root, cmap in ((slide_root, slide_map), (layout_root, layout_map), (master_root, master_map)):
        bg = root.find("p:cSld/p:bg/p:bgPr/a:solidFill", NS)
        if bg is not None:
            color = _resolve_color_container(bg, theme_colors, cmap)
            if color:
                return color
    return None


class _Accumulator:
    def __init__(self) -> None:
        self.fill_usage: dict[str, float] = defaultdict(float)
        self.text_usage: dict[str, float] = defaultdict(float)
        self.line_usage: dict[str, float] = defaultdict(float)
        self.bg_counts: dict[str, int] = defaultdict(int)
        self.surface_usage: dict[str, float] = defaultdict(float)
        self.font_usage: dict[str, float] = defaultdict(float)
        self.heading_font_usage: dict[str, float] = defaultdict(float)
        self.sizes: list[float] = []
        self.left_edges: list[float] = []
        self.top_edges: list[float] = []
        self.right_edges: list[float] = []
        self.bottom_edges: list[float] = []


LARGE_BLOCK_AREA_RATIO = 0.1
CONTENT_MIN_AREA_RATIO = 0.001
CONTENT_MAX_AREA_RATIO = 0.9


def _walk_shapes(
    root, theme_colors, theme_fonts, clr_map, slide_area, acc: _Accumulator,
    layout_root=None, master_root=None, collect_geometry=False,
):
    for sp in _iter_shapes(root):
        spPr = sp.find("p:spPr", NS)
        if spPr is None:
            continue
        xfrm = spPr.find("a:xfrm", NS)
        area_ratio = 0.0
        box = None
        if xfrm is not None:
            off = xfrm.find("a:off", NS)
            ext = xfrm.find("a:ext", NS)
            if ext is not None:
                cx = int(ext.get("cx", 0))
                cy = int(ext.get("cy", 0))
                area_ratio = (cx * cy) / slide_area if slide_area else 0.0
                if off is not None and slide_area:
                    box = (
                        int(off.get("x", 0)),
                        int(off.get("y", 0)),
                        cx,
                        cy,
                    )

        fill = spPr.find("a:solidFill", NS)
        if fill is not None:
            color = _resolve_color_container(fill, theme_colors, clr_map)
            if color:
                weight = max(area_ratio, CONTENT_MIN_AREA_RATIO)
                acc.fill_usage[color] += weight
                if area_ratio >= LARGE_BLOCK_AREA_RATIO:
                    acc.surface_usage[color] += area_ratio

        line = spPr.find("a:ln/a:solidFill", NS)
        if line is not None:
            color = _resolve_color_container(line, theme_colors, clr_map)
            if color:
                acc.line_usage[color] += 1.0

        ph_key = _shape_ph_key(sp)
        tx_body = sp.find("p:txBody", NS)
        if tx_body is not None:
            for para in tx_body.findall("a:p", NS):
                level = int(para.find("a:pPr", NS).get("lvl", "0")) if para.find("a:pPr", NS) is not None else 0
                for run in para.findall("a:r", NS):
                    t_el = run.find("a:t", NS)
                    text = t_el.text if t_el is not None and t_el.text else ""
                    if not text:
                        continue
                    chars = len(text)
                    rpr = run.find("a:rPr", NS)
                    color = None
                    typeface = None
                    size_pt = None
                    if rpr is not None:
                        rfill = rpr.find("a:solidFill", NS)
                        if rfill is not None:
                            color = _resolve_color_container(rfill, theme_colors, clr_map)
                        latin = rpr.find("a:latin", NS)
                        if latin is not None:
                            typeface = _resolve_typeface(latin.get("typeface"), theme_fonts)
                        sz = rpr.get("sz")
                        if sz:
                            size_pt = int(sz) / 100
                    if color:
                        acc.text_usage[color] += chars
                    if typeface:
                        acc.font_usage[typeface] += chars
                        if ph_key is not None and ph_key[0] in TITLE_TYPES:
                            acc.heading_font_usage[typeface] += chars
                    if size_pt is None and ph_key is not None and layout_root is not None and master_root is not None:
                        size_pt = _inherited_size_pt(ph_key[0], ph_key[1], level, layout_root, master_root)
                    if size_pt:
                        acc.sizes.append(round(size_pt * 2) / 2)

        if collect_geometry and box is not None and CONTENT_MIN_AREA_RATIO < area_ratio < CONTENT_MAX_AREA_RATIO:
            x, y, cx, cy = box
            slide_w2 = slide_area  # заменяется ниже вызывающей стороной через box в долях
            acc.left_edges.append(x)
            acc.top_edges.append(y)
            acc.right_edges.append(x + cx)
            acc.bottom_edges.append(y + cy)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    frac = k - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _round_guide(value: float) -> float:
    return round(round(value / 0.005) * 0.005, 3)


def _saturation(hexval: str) -> float:
    try:
        r = int(hexval[0:2], 16) / 255
        g = int(hexval[2:4], 16) / 255
        b = int(hexval[4:6], 16) / 255
    except ValueError:
        return 0.0
    _, _, s = colorsys.rgb_to_hls(r, g, b)
    return s


def extract_tokens(pptx_path: Path) -> Tokens:
    prs = Presentation(str(pptx_path))
    slide_w, slide_h = prs.slide_width, prs.slide_height
    slide_area = slide_w * slide_h

    acc = _Accumulator()
    theme_cache: dict[str, tuple[dict, dict]] = {}

    def theme_for(master):
        key = master.part.partname
        if key not in theme_cache:
            theme_part = master.part.part_related_by(RT.THEME)
            theme_root = etree.fromstring(theme_part.blob)
            theme_cache[key] = (_load_theme_colors(theme_root), _load_theme_fonts(theme_root))
        return theme_cache[key]

    for master in prs.slide_masters:
        theme_colors, theme_fonts = theme_for(master)
        master_map = _master_clr_map(master._element)
        _walk_shapes(master._element, theme_colors, theme_fonts, master_map, slide_area, acc)
        for layout in master.slide_layouts:
            layout_map = _part_clr_map(layout._element, master_map)
            _walk_shapes(
                layout._element, theme_colors, theme_fonts, layout_map, slide_area, acc,
                layout_root=layout._element, master_root=master._element,
            )

    for slide in prs.slides:
        master = slide.slide_layout.slide_master
        theme_colors, theme_fonts = theme_for(master)
        master_map = _master_clr_map(master._element)
        layout_map = _part_clr_map(slide.slide_layout._element, master_map)
        slide_map = _part_clr_map(slide._element, layout_map)
        _walk_shapes(
            slide._element, theme_colors, theme_fonts, slide_map, slide_area, acc,
            layout_root=slide.slide_layout._element, master_root=master._element,
            collect_geometry=True,
        )
        bg = _effective_background(
            slide._element, slide.slide_layout._element, master._element,
            theme_colors, slide_map, layout_map, master_map,
        )
        if bg:
            acc.bg_counts[bg] += 1

    tokens_colors = _build_color_tokens(acc, theme_cache)
    tokens_fonts = _build_font_tokens(acc)
    type_scale = _build_type_scale(acc.sizes)
    margins = _build_margins(acc, slide_w, slide_h)
    guides_x, guides_y = _build_guides(acc, slide_w, slide_h)

    return Tokens(
        colors=tokens_colors,
        fonts=tokens_fonts,
        type_scale=type_scale,
        margins=margins,
        guides_x=guides_x,
        guides_y=guides_y,
    )


def _build_color_tokens(acc: _Accumulator, theme_cache) -> list[ColorToken]:
    result: list[ColorToken] = []

    # source="theme": уникальные цвета темы (по первому встреченному мастеру), равная доля.
    seen_theme: dict[str, str] = {}
    for theme_colors, _fonts in theme_cache.values():
        for slot in THEME_SLOTS:
            hexval = theme_colors.get(slot)
            if not hexval or hexval in seen_theme:
                continue
            seen_theme[hexval] = THEME_SLOT_ROLE.get(slot, "other")
        break  # берём тему первого мастера; несколько тем в одном файле — редкий случай
    if seen_theme:
        share = 1 / len(seen_theme)
        for hexval, role in seen_theme.items():
            result.append(ColorToken(hex=hexval, role=role, share=share, source="theme"))

    total_usage: dict[str, float] = defaultdict(float)
    for src in (acc.fill_usage, acc.text_usage, acc.line_usage):
        for hexval, weight in src.items():
            total_usage[hexval] += weight

    if not total_usage:
        return result

    background_hex = max(acc.bg_counts.items(), key=lambda kv: kv[1])[0] if acc.bg_counts else None
    text_hex = max(acc.text_usage.items(), key=lambda kv: kv[1])[0] if acc.text_usage else None

    ranked = sorted(total_usage.items(), key=lambda kv: -kv[1])
    top = [hexval for hexval, _ in ranked[:12]]
    for forced in (background_hex, text_hex):
        if forced and forced not in top:
            if len(top) >= 12:
                top.pop()
            top.append(forced)

    grand_total = sum(total_usage[h] for h in top) or 1.0
    remaining = [h for h in top if h not in (background_hex, text_hex)]
    remaining.sort(key=lambda h: -_saturation(h))
    accent_hex = remaining[0] if remaining else None
    accent_alt_hex = remaining[1] if len(remaining) > 1 else None
    rest = [h for h in remaining if h not in (accent_hex, accent_alt_hex)]
    surface_hex = max(rest, key=lambda h: acc.surface_usage.get(h, 0.0), default=None)
    if surface_hex is not None and acc.surface_usage.get(surface_hex, 0.0) <= 0:
        surface_hex = None

    for hexval in top:
        if hexval == background_hex:
            role = "background"
        elif hexval == text_hex:
            role = "text"
        elif hexval == accent_hex:
            role = "accent"
        elif hexval == accent_alt_hex:
            role = "accent_alt"
        elif hexval == surface_hex:
            role = "surface"
        elif acc.text_usage.get(hexval, 0.0) > 0:
            role = "text_muted"
        else:
            role = "other"
        result.append(ColorToken(
            hex=hexval, role=role, share=total_usage[hexval] / grand_total, source="usage",
        ))
    return result


def _build_font_tokens(acc: _Accumulator) -> list[FontToken]:
    if not acc.font_usage:
        return []
    total = sum(acc.font_usage.values()) or 1.0

    mono_hex = max(
        (f for f in acc.font_usage if _is_mono(f)),
        key=lambda f: acc.font_usage[f], default=None,
    )
    body_candidates = {f: w for f, w in acc.font_usage.items() if f != mono_hex}
    body = max(body_candidates.items(), key=lambda kv: kv[1], default=(None, 0))[0]
    heading_candidates = {
        f: w for f, w in acc.heading_font_usage.items() if f not in (mono_hex, body)
    }
    heading = max(heading_candidates.items(), key=lambda kv: kv[1], default=(None, 0))[0]

    tokens: list[FontToken] = []
    for family, weight in acc.font_usage.items():
        if family == mono_hex:
            role = "mono"
        elif family == heading:
            role = "heading"
        elif family == body:
            role = "body"
        else:
            role = "other"
        tokens.append(FontToken(family=family, role=role, share=weight / total))
    return tokens


def _build_type_scale(sizes: list[float]) -> list[TypeStep]:
    if not sizes:
        return []
    counts: dict[float, int] = defaultdict(int)
    for size in sizes:
        counts[size] += 1
    distinct = sorted(counts.keys(), reverse=True)[:6]
    total = sum(counts[size] for size in distinct) or 1
    roles = ["display", "title", "heading", "body", "caption"]
    steps = []
    for i, size in enumerate(distinct):
        role = roles[min(i, len(roles) - 1)]
        steps.append(TypeStep(size_pt=size, role=role, share=counts[size] / total))
    return steps


def _build_margins(acc: _Accumulator, slide_w: int, slide_h: int) -> Margins:
    if not acc.left_edges:
        return Margins(left=0.0, top=0.0, right=1.0, bottom=1.0)
    left_frac = [x / slide_w for x in acc.left_edges]
    top_frac = [y / slide_h for y in acc.top_edges]
    right_frac = [x / slide_w for x in acc.right_edges]
    bottom_frac = [y / slide_h for y in acc.bottom_edges]
    left = _percentile(left_frac, 5)
    top = _percentile(top_frac, 5)
    right = 1 - _percentile(right_frac, 95)
    bottom = 1 - _percentile(bottom_frac, 95)
    return Margins(
        left=round(max(0.0, left), 4),
        top=round(max(0.0, top), 4),
        right=round(max(0.0, right), 4),
        bottom=round(max(0.0, bottom), 4),
    )


def _build_guides(acc: _Accumulator, slide_w: int, slide_h: int) -> tuple[list[float], list[float]]:
    def top_edges(raw: list[float], span: int) -> list[float]:
        counts: dict[float, int] = defaultdict(int)
        for value in raw:
            counts[_round_guide(value / span)] += 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return [value for value, _ in ranked[:8]]

    return top_edges(acc.left_edges, slide_w), top_edges(acc.top_edges, slide_h)
