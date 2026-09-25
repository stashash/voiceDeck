"""Хранилище на диске: пакеты дизайн-систем и колоды. Владелец: задача T-13, варианты — T-12.

Каталог берётся из переменной DESIGNER_DATA_DIR (по умолчанию ./data):
design-systems/<id>/ — пакет дизайн-системы (пишет parse.package.build_package);
decks/<id>/<вариант>/ — deck.json (статус, бриф, план, сцены, находки), run.json (карточка
прогона), files/ (deck.pptx, deck.html, deck.markup.html, deck.pdf) и slides/ (картинки
слайдов). events.jsonl лежит на уровне колоды: шаги генерации всех вариантов идут в один
журнал по времени.
Пути без варианта (deck_files_dir, deck_state_path, ...) — это всегда вариант "a": так
старые вызовы и старые пути API продолжают работать после появления вариантов.

Идентификаторы проверяются шаблоном: пользовательский ввод не может стать частью пути.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from designer.contracts import Deck, Finding, RunManifest

DATA_DIR_ENV = "DESIGNER_DATA_DIR"
_DEFAULT_DATA_DIR = "./data"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SLIDE_NO_RE = re.compile(r"^[0-9]{1,4}$")


class InvalidId(ValueError):
    """Идентификатор не проходит проверку формата: не годится для имени каталога."""


def _check_id(raw: str) -> str:
    if not _ID_RE.match(raw):
        raise InvalidId(f"недопустимый идентификатор: {raw!r}")
    return raw


def data_dir() -> Path:
    return Path(os.environ.get(DATA_DIR_ENV, _DEFAULT_DATA_DIR))


# ---------- готовые данные ----------

DEMO_DIR_ENV = "DESIGNER_DEMO_DIR"
_DEMO_MARK = ".demo-seeded"


def seed_demo() -> list[str]:
    """Готовые дизайн-системы и презентации из репозитория (каталог demo/) при первом старте.

    Копирует только то, чего в хранилище нет. Метка в каталоге данных ставится после первого
    раза: систему или презентацию, которую человек удалил, следующий старт не возвращает.
    """
    raw = os.environ.get(DEMO_DIR_ENV, "")
    source = Path(raw) if raw else None
    mark = data_dir() / _DEMO_MARK
    if source is None or not source.is_dir() or mark.is_file():
        return []
    copied: list[str] = []
    for kind, target_root in (("design-systems", design_systems_root()), ("decks", decks_root())):
        source_root = source / kind
        if not source_root.is_dir():
            continue
        for item in sorted(source_root.iterdir()):
            if not item.is_dir() or not _ID_RE.match(item.name) or (target_root / item.name).exists():
                continue
            shutil.copytree(item, target_root / item.name)
            copied.append(f"{kind}/{item.name}")
    mark.write_text("\n".join(copied) + "\n", encoding="utf-8")
    return copied


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


def delete_design_system(ds_id: str) -> None:
    """Удаляет папку системы целиком. Тихо, если её уже нет."""
    path = design_system_dir(ds_id)
    if path.is_dir():
        shutil.rmtree(path)


def latest_design_system_id() -> str | None:
    """Последний загруженный шаблон: его берёт живой режим, когда сцена шаблон не выбрала."""
    root = design_systems_root()
    packages = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()]
    if not packages:
        return None
    return max(packages, key=lambda p: (p / "manifest.json").stat().st_mtime).name


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


_DEFAULT_VARIANT = "a"


def deck_variants(deck_id: str) -> list[str]:
    """Варианты, для которых уже есть каталог с deck.json; пусто, если колода ещё не начала строиться."""
    root = deck_dir(deck_id)
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "deck.json").is_file())


def list_deck_ids() -> list[str]:
    """Id колод, у которых есть хотя бы один вариант с deck.json."""
    root = decks_root()
    return sorted(p.name for p in root.iterdir() if p.is_dir() and deck_variants(p.name))


def deck_variant_dir(deck_id: str, variant: str) -> Path:
    d = deck_dir(deck_id) / _check_id(variant)
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_variant_files_dir(deck_id: str, variant: str) -> Path:
    d = deck_variant_dir(deck_id, variant) / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_variant_state_path(deck_id: str, variant: str) -> Path:
    return deck_variant_dir(deck_id, variant) / "deck.json"


def deck_variant_run_path(deck_id: str, variant: str) -> Path:
    return deck_variant_dir(deck_id, variant) / "run.json"


def deck_variant_file_path(deck_id: str, variant: str, name: str) -> Path | None:
    """Путь к готовому файлу варианта колоды; None — путь выходит за пределы каталога."""
    return safe_join(deck_variant_files_dir(deck_id, variant), name)


def deck_variant_history_dir(deck_id: str, variant: str) -> Path:
    """Снимки deck.json перед каждой правкой варианта (задача T-13, правка варианта)."""
    d = deck_variant_dir(deck_id, variant) / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshot_deck_history(deck_id: str, variant: str, state: dict) -> None:
    """Кладёт текущее deck.json варианта в history/<n>.json перед правкой, n по счёту с единицы."""
    history_dir = deck_variant_history_dir(deck_id, variant)
    numbers = [int(p.stem) for p in history_dir.glob("*.json") if p.stem.isdigit()]
    n = max(numbers, default=0) + 1
    _write_json(history_dir / f"{n}.json", state)


def read_json_file(path: Path) -> dict:
    return _read_json(path)


def deck_variant_slides_dir(deck_id: str, variant: str) -> Path:
    """Картинки слайдов варианта: slide-001.png и далее по порядку (задача T-26)."""
    d = deck_variant_dir(deck_id, variant) / "slides"
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_variant_slide_path(deck_id: str, variant: str, number: int | str) -> Path | None:
    """Путь к картинке слайда с этим номером; None — номер не число."""
    raw = str(number)
    if not _SLIDE_NO_RE.match(raw):
        return None
    return safe_join(deck_variant_slides_dir(deck_id, variant), f"slide-{int(raw):03d}.png")


def deck_variant_slide_numbers(deck_id: str, variant: str) -> list[int]:
    """Номера слайдов, картинки которых уже лежат в хранилище."""
    d = deck_variant_dir(deck_id, variant) / "slides"
    if not d.is_dir():
        return []
    numbers = []
    for path in d.glob("slide-*.png"):
        raw = path.stem.split("-")[-1]
        if raw.isdigit():
            numbers.append(int(raw))
    return sorted(numbers)


def deck_files_dir(deck_id: str) -> Path:
    return deck_variant_files_dir(deck_id, _DEFAULT_VARIANT)


def deck_state_path(deck_id: str) -> Path:
    return deck_variant_state_path(deck_id, _DEFAULT_VARIANT)


def deck_run_path(deck_id: str) -> Path:
    return deck_variant_run_path(deck_id, _DEFAULT_VARIANT)


def deck_events_path(deck_id: str) -> Path:
    return deck_dir(deck_id) / "events.jsonl"


def deck_file_path(deck_id: str, name: str) -> Path | None:
    """Путь к готовому файлу колоды (deck.pptx, deck.html, deck.pdf); None — путь выходит за пределы каталога."""
    return deck_variant_file_path(deck_id, _DEFAULT_VARIANT, name)


def init_deck(deck_id: str, design_system_id: str, variants: list[str] | None = None, brief: str = "") -> None:
    for variant in (variants or [_DEFAULT_VARIANT]):
        _write_json(deck_variant_state_path(deck_id, variant), {
            "status": "running", "design_system_id": design_system_id, "brief": brief,
            "plan": None, "specs": [], "scenes": [], "findings": [], "error": None,
        })


def save_deck_plan(deck_id: str, plan: dict, variant: str = _DEFAULT_VARIANT) -> None:
    """Пишет план в состояние варианта сразу после шага plan, до вёрстки слайдов."""
    state = load_deck_state(deck_id, variant) or {
        "status": "running", "design_system_id": "", "brief": "", "plan": None,
        "specs": [], "scenes": [], "findings": [], "error": None,
    }
    state["plan"] = plan
    _write_json(deck_variant_state_path(deck_id, variant), state)


def save_deck_result(deck_id: str, deck: Deck, findings: list[Finding], variant: str = _DEFAULT_VARIANT) -> None:
    previous = load_deck_state(deck_id, variant) or {}
    _write_json(deck_variant_state_path(deck_id, variant), {
        "status": "done",
        "design_system_id": deck.design_system_id,
        "brief": previous.get("brief", ""),
        "plan": deck.plan.model_dump(mode="json"),
        "specs": [spec.model_dump(mode="json") for spec in deck.specs],
        "scenes": [scene.model_dump(mode="json") for scene in deck.scenes],
        "findings": [f.model_dump(mode="json") for f in findings],
        "error": None,
    })


def mark_deck_failed(deck_id: str, message: str, variant: str = _DEFAULT_VARIANT) -> None:
    state = load_deck_state(deck_id, variant) or {
        "status": "running", "design_system_id": "", "brief": "", "plan": None,
        "specs": [], "scenes": [], "findings": [], "error": None,
    }
    state["status"] = "error"
    state["error"] = message
    _write_json(deck_variant_state_path(deck_id, variant), state)


def request_deck_cancel(deck_id: str) -> None:
    """Автор нажал «Остановить»: конвейер проверяет флаг между шагами."""
    path = decks_root() / _check_id(deck_id)
    if not path.is_dir():
        raise FileNotFoundError(deck_id)
    (path / "cancel").write_text("1", encoding="utf-8")


def deck_cancel_requested(deck_id: str) -> bool:
    return (decks_root() / _check_id(deck_id) / "cancel").is_file()


def rename_deck(deck_id: str, title: str) -> None:
    """Название презентации одно на все варианты: пишется в план каждого варианта."""
    if not (decks_root() / _check_id(deck_id)).is_dir():
        raise FileNotFoundError(deck_id)
    for variant in deck_variants(deck_id):
        path = deck_variant_state_path(deck_id, variant)
        state = _read_json(path)
        if state.get("plan"):
            state["plan"]["title"] = title
            _write_json(path, state)


def load_deck_state(deck_id: str, variant: str = _DEFAULT_VARIANT) -> dict | None:
    path = deck_variant_state_path(deck_id, variant)
    if not path.is_file():
        return None
    return _read_json(path)


def save_run(deck_id: str, manifest: RunManifest, variant: str = _DEFAULT_VARIANT, axis: str = "") -> None:
    data = manifest.model_dump(mode="json")
    data["axis"] = axis
    _write_json(deck_variant_run_path(deck_id, variant), data)


def load_run(deck_id: str, variant: str = _DEFAULT_VARIANT) -> RunManifest | None:
    path = deck_variant_run_path(deck_id, variant)
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


def write_text_atomic(path: Path, text: str) -> None:
    """Запись, которую читатель никогда не видит наполовину.

    write_text сначала обнуляет файл: страница, опрашивающая manifest.json или deck.json во время
    описания образцов и генерации, ловила пустой файл, и сервис отвечал 500. Текст пишется во
    временный файл рядом и подменяет старый одной операцией os.replace.
    """
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _write_json(path: Path, data: dict) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
