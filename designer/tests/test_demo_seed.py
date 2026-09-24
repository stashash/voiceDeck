"""Готовые данные из demo/ при первом старте: копируются один раз, удалённое не возвращается."""
from pathlib import Path

from designer import store


def _demo(root: Path) -> Path:
    demo = root / "demo"
    (demo / "design-systems" / "vk-tech").mkdir(parents=True)
    (demo / "design-systems" / "vk-tech" / "manifest.json").write_text("{}", encoding="utf-8")
    (demo / "decks" / "vk-tech" / "a").mkdir(parents=True)
    (demo / "decks" / "vk-tech" / "a" / "deck.json").write_text("{}", encoding="utf-8")
    return demo


def test_seed_copies_once_and_keeps_deleted_items_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    monkeypatch.setenv(store.DEMO_DIR_ENV, str(_demo(tmp_path)))

    assert store.seed_demo() == ["design-systems/vk-tech", "decks/vk-tech"]
    assert store.list_design_system_ids() == ["vk-tech"]
    assert store.list_deck_ids() == ["vk-tech"]

    store.delete_design_system("vk-tech")
    assert store.seed_demo() == []
    assert store.list_design_system_ids() == []


def test_seed_does_not_overwrite_existing_data(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    monkeypatch.setenv(store.DEMO_DIR_ENV, str(_demo(tmp_path)))
    own = store.design_system_dir("vk-tech")
    own.mkdir(parents=True)
    (own / "manifest.json").write_text('{"own": true}', encoding="utf-8")

    assert store.seed_demo() == ["decks/vk-tech"]
    assert (own / "manifest.json").read_text(encoding="utf-8") == '{"own": true}'


def test_seed_without_demo_dir_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    monkeypatch.delenv(store.DEMO_DIR_ENV, raising=False)
    assert store.seed_demo() == []
