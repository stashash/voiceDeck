"""Готовые данные для репозитория: хранилище designer после examples/build.py -> каталог demo/.

Запуск: python examples/export_demo.py <каталог данных designer>
Берёт все дизайн-системы и по одной презентации на систему (последнюю готовую). Презентация
получает id своей дизайн-системы, чтобы путь читался: demo/decks/vk-tech-shablon/a/files/deck.pptx.
История правок не переносится. При первом старте designer копирует demo/ в пустое хранилище
(store.seed_demo).
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
_TEXT = {".json", ".jsonl", ".html"}


def _deck_system(deck: Path) -> tuple[str, str]:
    """(id дизайн-системы, время старта) по варианту a; пустая строка, если вариант не готов."""
    state_path = deck / "a" / "deck.json"
    if not state_path.is_file():
        return "", ""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("status") != "done":
        return "", ""
    run_path = deck / "a" / "run.json"
    started = json.loads(run_path.read_text(encoding="utf-8")).get("started_at", "") if run_path.is_file() else ""
    return state.get("design_system_id", ""), started


def main(data_dir: str) -> None:
    source = Path(data_dir)
    if DEMO.exists():
        shutil.rmtree(DEMO)
    for system in sorted((source / "design-systems").iterdir()):
        if (system / "manifest.json").is_file():
            # render-cache это кеш картинок слайдов с именами-хешами: сервис пересчитает его сам,
            # а длинные имена не помещаются в предел пути Windows при клонировании.
            shutil.copytree(system, DEMO / "design-systems" / system.name, ignore=shutil.ignore_patterns("render-cache"))
            print("система", system.name)
    latest: dict[str, tuple[str, Path]] = {}
    for deck in sorted((source / "decks").iterdir()):
        system, started = _deck_system(deck)
        if system and (system not in latest or started > latest[system][0]):
            latest[system] = (started, deck)
    for system, (_, deck) in sorted(latest.items()):
        target = DEMO / "decks" / system
        shutil.copytree(deck, target, ignore=shutil.ignore_patterns("history"))
        # id презентации встречается в журнале шагов и карточках прогона: меняем его на читаемый.
        for path in target.rglob("*"):
            if path.suffix in _TEXT and path.is_file():
                text = path.read_text(encoding="utf-8")
                if deck.name in text:
                    path.write_text(text.replace(deck.name, system), encoding="utf-8")
        print("презентация", deck.name, "->", system)


if __name__ == "__main__":
    main(sys.argv[1])
