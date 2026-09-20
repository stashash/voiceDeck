"""Слайды-образцы как паттерны: слоты, повторяющиеся блоки, тип слайда. Владелец: задача T-02."""
from pathlib import Path

from designer.contracts import LayoutInfo, Pattern


def extract_patterns(pptx_path: Path) -> list[Pattern]:
    raise NotImplementedError("T-02")


def extract_layouts(pptx_path: Path) -> list[LayoutInfo]:
    raise NotImplementedError("T-02")
