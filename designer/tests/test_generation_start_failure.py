import pytest

from designer import pipeline, store


def test_missing_package_fails_all_variants_without_leaving_running(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path))
    deck_id = store.new_deck_id()
    with pytest.raises(FileNotFoundError):
        pipeline.generate_deck(
            'missing-package', 'Brief', '', '', 3, lambda event: None,
            deck_id=deck_id, variants=['a', 'b', 'c'],
        )
    for variant in ['a', 'b', 'c']:
        state = store.load_deck_state(deck_id, variant)
        assert state['status'] == 'error'
        assert state['error']
