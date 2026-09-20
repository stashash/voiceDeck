"""Сборка пакета дизайн-системы на диске. Владелец: задача T-01."""
from pathlib import Path

from designer.contracts import DesignSystem


def build_package(pptx_path: Path, out_dir: Path) -> DesignSystem:
    """Пишет out_dir/manifest.json, tokens.css, assets/, fonts/ и возвращает манифест."""
    raise NotImplementedError("T-01")


def load_package(package_dir: Path) -> DesignSystem:
    raise NotImplementedError("T-01")
