"""Общие фикстуры. Шаблоны не лежат в git: путь к ним берётся из переменной окружения.

DESIGNER_TEMPLATES_DIR  каталог с тремя выданными pptx
DESIGNER_FOREIGN_PPTX   сторонний pptx, которого нет среди выданных (защита от подгонки)
"""
import os
from pathlib import Path

import pytest


def _templates_dir() -> Path | None:
    raw = os.environ.get("DESIGNER_TEMPLATES_DIR")
    if raw and Path(raw).is_dir():
        return Path(raw)
    default = Path(__file__).resolve().parents[2] / "docs" / "requirements" / "template"
    return default if default.is_dir() else None


@pytest.fixture(scope="session")
def templates() -> list[Path]:
    root = _templates_dir()
    if root is None:
        pytest.skip("нет каталога с шаблонами: задайте DESIGNER_TEMPLATES_DIR")
    files = sorted(root.glob("*.pptx"))
    if not files:
        pytest.skip("в каталоге шаблонов нет pptx")
    return files


@pytest.fixture(scope="session")
def foreign_pptx() -> Path:
    raw = os.environ.get("DESIGNER_FOREIGN_PPTX")
    if not raw or not Path(raw).is_file():
        pytest.skip("нет стороннего pptx: задайте DESIGNER_FOREIGN_PPTX")
    return Path(raw)
