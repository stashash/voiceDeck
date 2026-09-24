"""Тесты edit.py, которые не требуют реального pptx: ошибки поиска колоды/слайда/истории.

Полный цикл правки (текст, образец, лента слайдов, агент, revert) проверен через HTTP
в tests/api/test_app.py — там же есть design_system из настоящего pptx, без которого
compose/build_scene не работают.
"""
from __future__ import annotations

import pytest

from designer import edit, store


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))


def test_set_slide_text_on_missing_deck_raises_deck_not_found():
    with pytest.raises(edit.DeckNotFound):
        edit.set_slide_text("no-such-deck", "a", 1, "el1", "текст")


def test_set_slide_pattern_on_missing_deck_raises_deck_not_found():
    with pytest.raises(edit.DeckNotFound):
        edit.set_slide_pattern("no-such-deck", "a", 1, "p001")


def test_list_slide_patterns_on_missing_deck_raises_deck_not_found():
    with pytest.raises(edit.DeckNotFound):
        edit.list_slide_patterns("no-such-deck", "a", 1)


def test_apply_slide_action_on_missing_deck_raises_deck_not_found():
    with pytest.raises(edit.DeckNotFound):
        edit.apply_slide_action("no-such-deck", "a", "delete", 1)


def test_apply_slide_action_unknown_action_raises_value_error():
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")  # deck.json варианта "a" нужен, чтобы дойти до проверки action

    with pytest.raises(ValueError):
        edit.apply_slide_action(deck_id, "a", "fly", 1)


def test_revert_without_history_raises_no_history():
    with pytest.raises(edit.NoHistory):
        edit.revert("some-deck-id", "a")


def test_rewrite_from_finding_on_missing_deck_raises_deck_not_found():
    with pytest.raises(edit.DeckNotFound):
        edit.rewrite_from_finding("no-such-deck", "a", "finding-1")



def test_text_edit_is_written_to_the_slide_intent():
    # Регрессия 2026-09-24: правка текста жила только в слоте, смена образца и просьба агенту
    # пересобирают слайд из намерения и затирали её.
    from types import SimpleNamespace
    from designer.contracts import Item, SlideIntent, SlideKind

    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Было", items=[Item(heading="А", body="б")])
    edit._set_intent_text(intent, SimpleNamespace(role="title"), None, None, "Своё название")
    edit._set_intent_text(intent, SimpleNamespace(role="heading"), object(), 0, "Новый пункт")
    edit._set_intent_text(intent, SimpleNamespace(role="body"), object(), 0, "Новый текст")
    assert intent.title == "Своё название"
    assert intent.items[0].heading == "Новый пункт"
    assert intent.items[0].body == "Новый текст"
