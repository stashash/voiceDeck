"""Сцены -> HTML-презентация разметкой. Владелец: задача T-06."""
from __future__ import annotations

import base64
import html
from pathlib import Path

from designer.contracts import Asset, Box, Deck, DesignSystem, Element, Scene, Tokens
from designer.export.svg_chart import chart_colors, render_chart

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_FONT_MIME = {
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}

_ROLE_SIZE_PT = {"display": 44.0, "title": 32.0, "heading": 24.0, "body": 16.0, "caption": 12.0}


def _data_uri(path: Path, mime: str) -> str:
    data = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _asset_by_id(ds: DesignSystem, asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    return next((a for a in ds.assets if a.id == asset_id), None)


def _image_data_uri(asset: Asset, package_dir: Path) -> str | None:
    path = package_dir / asset.path
    if not path.is_file():
        return None
    mime = _IMAGE_MIME.get(path.suffix.lower(), "image/png")
    return _data_uri(path, mime)


def _font_faces(ds: DesignSystem, package_dir: Path) -> str:
    faces = []
    for font in ds.tokens.fonts:
        if not font.embedded_file:
            continue
        path = package_dir / font.embedded_file
        if not path.is_file():
            continue
        mime = _FONT_MIME.get(path.suffix.lower(), "font/ttf")
        uri = _data_uri(path, mime)
        faces.append(f"@font-face {{ font-family: '{font.family}'; src: url({uri}); font-display: swap; }}")
    return "\n".join(faces)


def _root_vars(tokens: Tokens) -> str:
    lines: list[str] = []
    seen_colors: set[str] = set()
    for color in tokens.colors:
        if color.role in seen_colors:
            continue
        seen_colors.add(color.role)
        lines.append(f"--color-{color.role.replace('_', '-')}: #{color.hex};")
    seen_fonts: set[str] = set()
    for font in tokens.fonts:
        if font.role in seen_fonts:
            continue
        seen_fonts.add(font.role)
        lines.append(f"--font-{font.role}: '{font.family}', sans-serif;")
    return "\n".join(lines)


def _slide_width_pt(ds: DesignSystem) -> float:
    return ds.slide_size_emu[0] / 12700.0


def _size_pt(el: Element, ds: DesignSystem) -> float | None:
    if el.style and el.style.size_pt:
        return el.style.size_pt
    for step in ds.tokens.type_scale:
        if step.role == el.role:
            return step.size_pt
    return _ROLE_SIZE_PT.get(el.role)


def _box_style(box: Box, z: int) -> str:
    x, y, w, h = box
    return f"left:{x * 100:.4f}%;top:{y * 100:.4f}%;width:{w * 100:.4f}%;height:{h * 100:.4f}%;z-index:{z};"


def _render_text(el: Element, ds: DesignSystem) -> str:
    style = [_box_style(el.box, el.z)]
    size_pt = _size_pt(el, ds)
    if size_pt:
        cqw = size_pt / _slide_width_pt(ds) * 100
        style.append(f"font-size:{cqw:.4f}cqw;")
    if el.style:
        if el.style.family:
            style.append(f"font-family:'{el.style.family}', sans-serif;")
        if el.style.bold:
            style.append("font-weight:700;")
        if el.style.italic:
            style.append("font-style:italic;")
        if el.style.color:
            style.append(f"color:#{el.style.color};")
        if el.style.align:
            style.append(f"text-align:{el.style.align};")
    text = html.escape(el.text)
    role = html.escape(el.role)
    return f'<div class="el text el-{role}" style="{"".join(style)}">{text}</div>'


def _render_shape(el: Element) -> str:
    style = [_box_style(el.box, el.z)]
    if el.fill:
        style.append(f"background:#{el.fill};")
    return f'<div class="el shape" style="{"".join(style)}"></div>'


def _render_image(el: Element, ds: DesignSystem, package_dir: Path) -> str:
    style = _box_style(el.box, el.z)
    asset = _asset_by_id(ds, el.asset)
    src = _image_data_uri(asset, package_dir) if asset else None
    if src is None:
        return f'<div class="el {el.type} el-missing" style="{style}"></div>'
    return f'<img class="el {el.type}" style="{style}" src="{src}" alt="">'


def _render_table(el: Element) -> str:
    style = _box_style(el.box, el.z)
    spec = el.table
    if spec is None:
        return f'<div class="el table" style="{style}"></div>'
    head = "".join(f"<th>{html.escape(c)}</th>" for c in spec.columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in spec.rows
    )
    return f'<table class="el table" style="{style}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _render_chart_el(el: Element, colors: list[str]) -> str:
    style = _box_style(el.box, el.z)
    if el.chart is None:
        return f'<div class="el chart" style="{style}"></div>'
    svg = render_chart(el.chart, colors)
    return f'<div class="el chart" style="{style}">{svg}</div>'


def _render_element(el: Element, ds: DesignSystem, package_dir: Path, colors: list[str]) -> str:
    if el.type == "text":
        return _render_text(el, ds)
    if el.type == "shape":
        return _render_shape(el)
    if el.type in ("image", "icon"):
        return _render_image(el, ds, package_dir)
    if el.type == "table":
        return _render_table(el)
    if el.type == "chart":
        return _render_chart_el(el, colors)
    return ""


def _scene_background_style(scene: Scene, ds: DesignSystem, package_dir: Path) -> str:
    asset = _asset_by_id(ds, scene.background_asset)
    if asset:
        src = _image_data_uri(asset, package_dir)
        if src:
            return f"background-image:url({src});background-size:cover;background-position:center;"
    if scene.background_color:
        return f"background-color:#{scene.background_color};"
    return ""


def _render_scene(index: int, scene: Scene, ds: DesignSystem, package_dir: Path, colors: list[str]) -> str:
    bg = _scene_background_style(scene, ds, package_dir)
    elements = "".join(
        _render_element(el, ds, package_dir, colors) for el in sorted(scene.elements, key=lambda e: e.z)
    )
    return (
        f'<section class="slide{" active" if index == 0 else ""}" id="slide-{index + 1}" data-index="{index}" '
        f'data-theme="{scene.theme}" style="{bg}">{elements}</section>'
    )


_SCRIPT = """(function () {
  var slides = document.querySelectorAll('.slide');
  var total = slides.length;
  function indexFromHash() {
    var n = parseInt((location.hash || '').replace('#', ''), 10);
    if (isNaN(n) || n < 1 || n > total) { return 0; }
    return n - 1;
  }
  function show(i) {
    i = Math.max(0, Math.min(total - 1, i));
    for (var k = 0; k < total; k++) {
      slides[k].classList.toggle('active', k === i);
    }
    history.replaceState(null, '', '#' + (i + 1));
  }
  document.addEventListener('keydown', function (e) {
    var i = indexFromHash();
    if (e.key === 'ArrowRight' || e.key === ' ') {
      e.preventDefault();
      show(i + 1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      show(i - 1);
    } else if (e.key === 'f' || e.key === 'F') {
      var deck = document.getElementById('deck');
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else if (deck.requestFullscreen) {
        deck.requestFullscreen();
      }
    }
  });
  window.addEventListener('hashchange', function () { show(indexFromHash()); });
  show(indexFromHash());
})();"""


def _build_css(ds: DesignSystem, aspect: float) -> str:
    root_vars = _root_vars(ds.tokens)
    return f"""
:root {{
{root_vars}
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; height: 100%; background: #1a1a1a; }}
#deck {{ height: 100%; display: flex; align-items: center; justify-content: center; }}
.slide {{
  position: relative;
  width: min(100vw, {aspect:.6f} * 100vh);
  aspect-ratio: {aspect:.6f};
  container-type: inline-size;
  overflow: hidden;
  background: var(--color-background, #ffffff);
  display: none;
}}
.slide.active {{ display: block; }}
.el {{ position: absolute; overflow: hidden; }}
.el.text {{
  white-space: pre-wrap;
  font-family: var(--font-body, sans-serif);
  color: var(--color-text, #111111);
}}
.el.image, .el.icon {{ object-fit: contain; width: 100%; height: 100%; }}
.el.table {{ border-collapse: collapse; font-size: 1.6cqw; }}
.el.table th, .el.table td {{ border: 1px solid var(--color-text-muted, #999999); padding: 0.3em 0.5em; }}
.el.chart svg {{ width: 100%; height: 100%; }}
.chart-label, .chart-legend, .chart-title, .chart-unit {{
  font-size: 12px;
  fill: var(--color-text, #111111);
  font-family: sans-serif;
}}
@media print {{
  html, body {{ background: #ffffff; }}
  #deck {{ display: block; }}
  .slide {{
    display: block !important;
    width: 100vw;
    height: 100vh;
    page-break-after: always;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  @page {{ size: landscape; margin: 0; }}
}}
"""


def render_deck(deck: Deck, ds: DesignSystem, package_dir: Path) -> str:
    """Возвращает самодостаточный HTML: шрифты и картинки пакета встроены, слайды 16:9, печать в PDF по слайду на страницу."""
    package_dir = Path(package_dir)
    colors = chart_colors(ds.tokens)
    width_emu, height_emu = ds.slide_size_emu
    aspect = (width_emu / height_emu) if height_emu else 16 / 9
    sections = "".join(
        _render_scene(i, scene, ds, package_dir, colors) for i, scene in enumerate(deck.scenes)
    )
    css = _build_css(ds, aspect)
    fonts_css = _font_faces(ds, package_dir)
    lang = html.escape(deck.plan.language or "ru")
    title = html.escape(deck.plan.title or "Презентация")
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{fonts_css}\n{css}\n</style>\n"
        "</head>\n"
        "<body>\n"
        f'<main id="deck">\n{sections}\n</main>\n'
        f"<script>\n{_SCRIPT}\n</script>\n"
        "</body>\n"
        "</html>\n"
    )
