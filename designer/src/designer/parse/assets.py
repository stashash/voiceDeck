"""Картинки и встроенные шрифты из pptx. Владелец: задача T-01."""
from pathlib import Path

from designer.contracts import Asset


def extract_assets(pptx_path: Path, package_dir: Path) -> list[Asset]:
    """Кладёт файлы в package_dir/assets и package_dir/fonts, возвращает опись картинок."""
    raise NotImplementedError("T-01")
