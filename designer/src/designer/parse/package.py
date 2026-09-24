"""Сборка пакета дизайн-системы на диске. Владелец: задача T-01."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn

from designer.contracts import DesignSystem, LayoutInfo, Pattern

SOURCE_NAME = "source.pptx"
from designer.parse.assets import _extract_embedded_fonts, extract_assets
from designer.parse.patterns import extract_layouts, extract_patterns
from designer.parse.tokens import extract_tokens

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _slugify(name: str) -> str:
    stem = Path(name).stem.lower()
    latin_chars = []
    for ch in stem:
        if ch in _TRANSLIT:
            latin_chars.append(_TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            latin_chars.append(ch)
        else:
            latin_chars.append("-")
    slug = "".join(latin_chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or "design-system"


def _display_name(filename: str) -> str:
    """Имя системы по умолчанию: имя файла без расширения, «_» и «-» — пробелами."""
    stem = Path(filename).stem
    name = stem.replace("_", " ").replace("-", " ")
    while "  " in name:
        name = name.replace("  ", " ")
    return name.strip() or stem


def _embedded_font_families(prs: Presentation) -> set[str]:
    """Имена шрифтов, перечисленных в embeddedFontLst, извлечены они или нет."""
    lst = prs.part._element.find(qn("p:embeddedFontLst"))
    if lst is None:
        return set()
    families = set()
    for embedded in lst.findall(qn("p:embeddedFont")):
        font_el = embedded.find(qn("p:font"))
        family = font_el.get("typeface") if font_el is not None else None
        if family:
            families.add(family)
    return families


def build_package(pptx_path: Path, out_dir: Path) -> DesignSystem:
    """Пишет out_dir/manifest.json, tokens.css, assets/, fonts/ и возвращает манифест."""
    pptx_path = Path(pptx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Исходник нужен сборщику pptx: слайды-образцы клонируются из него вместе с макетами и встроенными шрифтами.
    shutil.copyfile(pptx_path, out_dir / SOURCE_NAME)

    prs = Presentation(str(pptx_path))
    slide_size_emu = (prs.slide_width, prs.slide_height)

    tokens = extract_tokens(pptx_path)
    assets = extract_assets(pptx_path, out_dir)

    font_files = _extract_embedded_fonts(prs, out_dir / "fonts")
    embedded_families = _embedded_font_families(prs)
    for font_token in tokens.fonts:
        rel_path = font_files.get(font_token.family)
        if rel_path:
            font_token.embedded_file = rel_path
            font_token.embedded_state = "extracted"
        elif font_token.family in embedded_families:
            font_token.embedded_state = "embedded_not_extracted"
        else:
            font_token.embedded_state = "missing"

    try:
        patterns: list[Pattern] = extract_patterns(pptx_path)
    except NotImplementedError:
        patterns = []

    try:
        layouts: list[LayoutInfo] = extract_layouts(pptx_path)
    except NotImplementedError:
        layouts = []

    design_system = DesignSystem(
        id=_slugify(pptx_path.name),
        source_file=pptx_path.name,
        name=_display_name(pptx_path.name),
        created_at=datetime.now(timezone.utc).isoformat(),
        slide_size_emu=slide_size_emu,
        tokens=tokens,
        assets=assets,
        layouts=layouts,
        patterns=patterns,
    )

    (out_dir / "manifest.json").write_text(
        design_system.model_dump_json(indent=2), encoding="utf-8",
    )
    (out_dir / "tokens.css").write_text(_render_tokens_css(design_system), encoding="utf-8")

    return design_system


def load_package(package_dir: Path) -> DesignSystem:
    manifest_path = Path(package_dir) / "manifest.json"
    return DesignSystem.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def _css_var_name(prefix: str, key: str, index: int) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in key.lower())
    return f"--{prefix}-{safe}-{index}"


def _render_tokens_css(design_system: DesignSystem) -> str:
    lines = [":root {"]
    role_seen: dict[str, int] = {}
    for color in design_system.tokens.colors:
        if color.source != "usage":
            continue
        idx = role_seen.get(color.role, 0)
        role_seen[color.role] = idx + 1
        name = _css_var_name("color", color.role, idx) if idx else f"--color-{color.role}"
        lines.append(f"  {name}: #{color.hex};")
    for font in design_system.tokens.fonts:
        idx = role_seen.get(f"font-{font.role}", 0)
        role_seen[f"font-{font.role}"] = idx + 1
        name = f"--font-{font.role}" if not idx else _css_var_name("font", font.role, idx)
        lines.append(f'  {name}: "{font.family}";')
    for i, step in enumerate(design_system.tokens.type_scale):
        idx = role_seen.get(f"size-{step.role}", 0)
        role_seen[f"size-{step.role}"] = idx + 1
        name = f"--size-{step.role}" if not idx else _css_var_name("size", step.role, idx)
        lines.append(f"  {name}: {step.size_pt}pt;")
    margins = design_system.tokens.margins
    lines.append(f"  --margin-left: {margins.left};")
    lines.append(f"  --margin-top: {margins.top};")
    lines.append(f"  --margin-right: {margins.right};")
    lines.append(f"  --margin-bottom: {margins.bottom};")
    lines.append("}")
    return "\n".join(lines) + "\n"
