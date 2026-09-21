"""Картинка слайда из pptx. Владелец: задача T-26.

Слайд, собранный по инструкции вёрстки, выглядит родным для шаблона только в pptx: там
работают фон, градиенты, картинки оформления и встроенный шрифт. Поэтому в браузер идёт
картинка того же слайда, снятая движком конвертации через постоянную сессию.

render_spec собирает pptx из одной инструкции и снимает её слайд; результат кладётся в кеш
на диске по хешу инструкции, поэтому повторный показ того же слайда движок не трогает.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from designer.contracts import DesignSystem, SlideSpec
from designer.export import convert
from designer.export.pptx_deck import export_pptx

CACHE_DIR_NAME = "render-cache"
DEFAULT_WIDTH_PX = convert.DEFAULT_WIDTH_PX


def cache_key(spec: SlideSpec, ds: DesignSystem, width_px: int = DEFAULT_WIDTH_PX) -> str:
    """Хеш инструкции: тот же слайд той же ширины даёт тот же ключ."""
    payload = json.dumps(
        {"spec": spec.model_dump(mode="json"), "design_system": ds.id, "width": width_px},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_spec(spec: SlideSpec, ds: DesignSystem, package_dir: Path,
                 width_px: int = DEFAULT_WIDTH_PX) -> bytes:
    """PNG слайда по одной инструкции вёрстки. Берёт из кеша, если инструкция та же."""
    package_dir = Path(package_dir)
    cached = package_dir / CACHE_DIR_NAME / f"{cache_key(spec, ds, width_px)}.png"
    if cached.is_file():
        return cached.read_bytes()

    with tempfile.TemporaryDirectory(prefix="designer-render-") as tmp:
        pptx_path = Path(tmp) / "slide.pptx"
        export_pptx([spec], ds, package_dir, pptx_path)
        png = convert.get_session().png(pptx_path, 0, width_px)

    _write_cache(cached, png)
    return png


def render_slides(pptx_path: Path, count: int, width_px: int = DEFAULT_WIDTH_PX) -> list[bytes]:
    """Картинки слайдов готовой колоды: движок открывает файл один раз."""
    session = convert.get_session()
    pptx_path = Path(pptx_path)
    return [session.png(pptx_path, index, width_px) for index in range(count)]


def _write_cache(path: Path, png: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".png.part")
    tmp_path.write_bytes(png)
    tmp_path.replace(path)
