"""Слайд в браузере: картинка из pptx и текстовый слой поверх неё. Владелец: задача T-26.

Картинка несёт вид шаблона целиком: фон, карточки, значки, встроенный шрифт. Поверх неё
каждый текст сцены стоит в своей рамке настоящим текстом прозрачного цвета, поэтому текст
выделяется, ищется поиском по странице и читается программой чтения с экрана.

Файл самодостаточный: картинки встроены base64, внешних ссылок нет.
"""
from __future__ import annotations

import base64
import html

from designer.contracts import Box, Deck, DesignSystem, Element, Scene

_ROLE_SIZE_PT = {"display": 44.0, "title": 32.0, "heading": 24.0, "body": 16.0, "caption": 12.0}


def slide_html(png: bytes, scene: Scene, ds: DesignSystem) -> str:
    """Один слайд: картинка и текстовый слой. Живой режим отдаёт эту страницу в сцену."""
    return _document(
        title="Слайд", lang="ru", ds=ds,
        sections=_section(0, png, scene, ds),
    )


def render_deck_images(deck: Deck, ds: DesignSystem, pngs: list[bytes]) -> str:
    """Колода картинками слайдов с текстовым слоем: листание, полный экран и печать."""
    sections = "".join(
        _section(index, png, scene, ds)
        for index, (scene, png) in enumerate(zip(deck.scenes, pngs))
    )
    return _document(
        title=deck.plan.title or "Презентация", lang=deck.plan.language or "ru",
        ds=ds, sections=sections,
    )


# ---------- слайд ----------

def _png_data_uri(png: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"


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


def _text_layer_item(el: Element, ds: DesignSystem) -> str:
    style = [_box_style(el.box, el.z + 1)]
    size_pt = _size_pt(el, ds)
    if size_pt:
        style.append(f"font-size:{size_pt / _slide_width_pt(ds) * 100:.4f}cqw;")
    if el.style:
        if el.style.family:
            style.append(f"font-family:'{el.style.family}', sans-serif;")
        if el.style.bold:
            style.append("font-weight:700;")
        if el.style.italic:
            style.append("font-style:italic;")
        if el.style.align:
            style.append(f"text-align:{el.style.align};")
    return (
        f'<div class="el text el-{html.escape(el.role)}" style="{"".join(style)}">'
        f"{html.escape(el.text)}</div>"
    )


def _section(index: int, png: bytes, scene: Scene, ds: DesignSystem) -> str:
    layer = "".join(
        _text_layer_item(el, ds)
        for el in sorted(scene.elements, key=lambda e: e.z)
        if el.type == "text" and el.text
    )
    return (
        f'<section class="slide{" active" if index == 0 else ""}" id="slide-{index + 1}" data-index="{index}" '
        f'data-theme="{scene.theme}">'
        f'<img class="slide-image" src="{_png_data_uri(png)}" alt="">'
        f'<div class="layer">{layer}</div>'
        "</section>"
    )


# ---------- страница ----------

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


def _css(aspect: float) -> str:
    return f"""
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; height: 100%; background: #1a1a1a; }}
#deck {{ height: 100%; display: flex; align-items: center; justify-content: center; }}
.slide {{
  position: relative;
  width: min(100vw, {aspect:.6f} * 100vh);
  aspect-ratio: {aspect:.6f};
  container-type: inline-size;
  overflow: hidden;
  display: none;
}}
.slide.active {{ display: block; }}
.slide-image {{ position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: block; }}
.layer {{ position: absolute; left: 0; top: 0; width: 100%; height: 100%; }}
.el.text {{
  position: absolute;
  overflow: hidden;
  white-space: pre-wrap;
  color: transparent;
  line-height: 1.2;
  font-family: sans-serif;
}}
.el.text::selection {{ background: rgba(90, 150, 255, 0.35); }}
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


def _document(title: str, lang: str, ds: DesignSystem, sections: str) -> str:
    width_emu, height_emu = ds.slide_size_emu
    aspect = (width_emu / height_emu) if height_emu else 16 / 9
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{html.escape(lang)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>\n{_css(aspect)}\n</style>\n"
        "</head>\n"
        "<body>\n"
        f'<main id="deck">\n{sections}\n</main>\n'
        f"<script>\n{_SCRIPT}\n</script>\n"
        "</body>\n"
        "</html>\n"
    )
