"""Сцены -> HTML-презентация разметкой. Владелец: задача T-06."""
from pathlib import Path

from designer.contracts import Deck, DesignSystem


def render_deck(deck: Deck, ds: DesignSystem, package_dir: Path) -> str:
    """Возвращает самодостаточный HTML: шрифты и картинки пакета встроены, слайды 16:9, печать в PDF по слайду на страницу."""
    raise NotImplementedError("T-06")
