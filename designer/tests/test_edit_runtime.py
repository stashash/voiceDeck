from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

from designer import edit, edit_runtime, store


def test_recovery_during_model_wait_prevents_late_mutation(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / 'data'))
    deck_id=store.new_deck_id()
    store.init_deck(deck_id,'ds')
    path=store.deck_variant_state_path(deck_id,'a')
    store._write_json(path,{'revision':'before'})
    started,release=Event(),Event()
    pattern=SimpleNamespace(id='p')
    def load(*_):
        return SimpleNamespace(raw=store.load_deck_state(deck_id,'a'),plan=SimpleNamespace(slides=[object()]),
            specs=[SimpleNamespace(pattern_id='p')],ds=SimpleNamespace(patterns=[pattern]))
    monkeypatch.setattr(edit,'_load',load)
    monkeypatch.setattr(edit,'_slide_index',lambda *_:0)
    def model(*_):
        started.set()
        assert release.wait(5)
        return object()
    monkeypatch.setattr(edit,'_rewrite_intent',model)
    monkeypatch.setattr(edit,'_persist',lambda *_:pytest.fail('Cancelled model must not save'))
    with ThreadPoolExecutor(2) as pool:
        job=pool.submit(edit.ask_agent_rewrite,deck_id,'a',1,'rewrite')
        assert started.wait(5)
        try:
            pool.submit(edit.recover_editor,deck_id,'a').result(timeout=2)
        finally:
            release.set()
        with pytest.raises(ValueError,match='остановлена'):
            job.result(timeout=2)


def test_stale_export_cannot_publish_and_edit_does_not_wait(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / 'data'))
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, 'ds')
    path = store.deck_variant_state_path(deck_id, 'a')
    started, release = Event(), Event()
    monkeypatch.setattr(edit, '_load', lambda *_: SimpleNamespace(raw=store.load_deck_state(deck_id, 'a')))

    def export(state, directory):
        if state.raw['revision'] == 'old':
            started.set()
            assert release.wait(5)
        (directory / 'deck.html').write_text(state.raw['revision'])

    monkeypatch.setattr(edit, '_export_files', export)
    store._write_json(path, {'revision': 'old'})
    with ThreadPoolExecutor(1) as pool:
        job = pool.submit(edit_runtime._export, deck_id, 'a', 'old')
        assert started.wait(5)
        # The export is blocked, but the edit lock must remain immediately free.
        with edit_runtime.lock(deck_id, 'a'):
            store._write_json(path, {'revision': 'new'})
        release.set()
        job.result(timeout=5)
    assert not (store.deck_variant_files_dir(deck_id, 'a') / 'deck.html').exists()
    edit_runtime.ensure_export(deck_id, 'a')
    assert (store.deck_variant_files_dir(deck_id, 'a') / 'deck.html').read_text() == 'new'


def test_failed_export_retries_without_losing_document(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / 'data'))
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, 'ds')
    path = store.deck_variant_state_path(deck_id, 'a')
    store._write_json(path, {'revision': 'new'})
    monkeypatch.setattr(edit, '_load', lambda *_: SimpleNamespace(raw={'revision': 'new'}))
    attempts = []

    def export(state, directory):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError('converter failed')
        (directory / 'deck.html').write_text('new')

    monkeypatch.setattr(edit, '_export_files', export)
    import pytest
    with pytest.raises(RuntimeError):
        edit_runtime.ensure_export(deck_id, 'a')
    edit_runtime.ensure_export(deck_id, 'a')
    assert len(attempts) == 2
    assert store.load_deck_state(deck_id, 'a')['revision'] == 'new'
