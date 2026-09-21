"""Хранилище на диске: пакеты дизайн-систем и колоды. Владелец: задача T-13.

Каталог берётся из переменной DESIGNER_DATA_DIR (по умолчанию ./data):
design-systems/<id>/ — пакет дизайн-системы (пишет parse.package.build_package);
decks/<id>/ — deck.json (статус, план, сцены, находки), run.json (карточка прогона),
events.jsonl (ход генерации по шагам) и files/ (deck.pptx, deck.html, deck.pdf, png/).

Идентификаторы проверяются шаблоном: пользовательский ввод не может стать частью пути.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from designer.contracts import Deck, Finding, RunManifest

DATA_DIR_ENV = "DESIGNER_DATA_DIR"
_DEFAULT_DATA_DIR = "./data"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class InvalidId(ValueError):
    """Идентификатор не проходит проверку формата: не годится для имени каталога."""


def _check_id(raw: str) -> str:
    if not _ID_RE.match(raw):
        raise InvalidId(f"недопустимый идентификатор: {raw!r}")
    return raw


def data_dir() -> Path:
    return Path(os.environ.get(DATA_DIR_ENV, _DEFAULT_DATA_DIR))


# ---------- дизайн-системы ----------

def design_systems_root() -> Path:
    root = data_dir() / "design-systems"
    root.mkdir(parents=True, exist_ok=True)
    return root


def design_system_dir(ds_id: str) -> Path:
    return design_systems_root() / _check_id(ds_id)


def list_design_system_ids() -> list[str]:
    root = design_systems_root()
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file())


def design_system_asset_path(ds_id: str, relative: str) -> Path | None:
    """Путь к файлу пакета (assets/..., tokens.css, ...); None — если имя выходит за пределы пакета."""
    return safe_join(design_system_dir(ds_id), relative)


# ---------- колоды ----------

def decks_root() -> Path:
    root = data_dir() / "decks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_deck_id() -> str:
    return uuid.uuid4().hex


def deck_dir(deck_id: str) -> Path:
    d = decks_root() / _check_id(deck_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_files_dir(deck_id: str) -> Path:
    d = deck_dir(deck_id) / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_state_path(deck_id: str) -> Path:
    return deck_dir(deck_id) / "deck.json"


def deck_run_path(deck_id: str) -> Path:
    return deck_dir(deck_id) / "run.json"


def deck_events_path(deck_id: str) -> Path:
    return deck_dir(deck_id) / "events.jsonl"


def deck_file_path(deck_id: str, name: str) -> Path | None:
    """Путь к готовому файлу колоды (deck.pptx, deck.html, deck.pdf); None — путь выходит за пределы каталога."""
    return safe_join(deck_files_dir(deck_id), name)


def init_deck(deck_id: str, design_system_id: str) -> None:
    _write_json(deck_state_path(deck_id), {
        "status": "running", "design_system_id": design_system_id,
        "plan": None, "specs": [], "scenes": [], "findings": [], "error": None,
    })


def save_deck_result(deck_id: str, deck: Deck, findings: list[Finding]) -> None:
    _write_json(deck_state_path(deck_id), {
        "status": "done",
        "design_system_id": deck.design_system_id,
        "plan": deck.plan.model_dump(mode="json"),
        "specs": [spec.model_dump(mode="json") for spec in deck.specs],
        "scenes": [scene.model_dump(mode="json") for scene in deck.scenes],
        "findings": [f.model_dump(mode="json") for f in findings],
        "error": None,
    })


def mark_deck_failed(deck_id: str, message: str) -> None:
    state = load_deck_state(deck_id) or {
        "status": "running", "design_system_id": "", "plan": None,
        "specs": [], "scenes": [], "findings": [], "error": None,
    }
    state["status"] = "error"
    state["error"] = message
    _write_json(deck_state_path(deck_id), state)


def load_deck_state(deck_id: str) -> dict | None:
    path = deck_state_path(deck_id)
    if not path.is_file():
        return None
    return _read_json(path)


def save_run(deck_id: str, manifest: RunManifest) -> None:
    _write_json(deck_run_path(deck_id), manifest.model_dump(mode="json"))


def load_run(deck_id: str) -> RunManifest | None:
    path = deck_run_path(deck_id)
    if not path.is_file():
        return None
    return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))


def append_event(deck_id: str, event: dict) -> None:
    path = deck_events_path(deck_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(deck_id: str) -> list[dict]:
    path = deck_events_path(deck_id)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------- общее ----------

def safe_join(base: Path, relative: str) -> Path | None:
    """Путь внутри base; None — если relative пытается выйти за его пределы (в т.ч. через "..")."""
    base = base.resolve()
    try:
        candidate = (base / relative).resolve()
        candidate.relative_to(base)
    except (ValueError, OSError):
        return None
    return candidate


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
