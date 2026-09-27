"""Читатель файла состояния не видит его пустым, пока писатель его перезаписывает."""
import json
import threading
import pytest

from designer import store


def test_reader_never_sees_empty_or_broken_json(tmp_path):
    path = tmp_path / "manifest.json"
    store.write_text_atomic(path, json.dumps({"n": 0}))
    payload = {"patterns": ["x" * 200] * 400}
    stop = threading.Event()
    broken: list[str] = []
    failures: list[Exception] = []

    def writer() -> None:
        n = 0
        try:
            while not stop.is_set():
                n += 1
                store.write_text_atomic(path, json.dumps({**payload, "n": n}))
        except Exception as error:
            failures.append(error)

    def reader() -> None:
        for _ in range(3000):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, PermissionError) as error:
                # PermissionError бывает только на Windows, пока os.replace меняет файл: это не пустой файл.
                if isinstance(error, ValueError):
                    broken.append(str(error))

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        reader()
    finally:
        stop.set()
        thread.join()
    assert broken == []
    assert failures == []
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))


def test_windows_sharing_violation_is_retried(tmp_path, monkeypatch):
    original = store.os.replace
    attempts = []
    def replace(source, destination):
        attempts.append(source)
        if len(attempts) == 1:
            error = PermissionError('sharing violation')
            error.winerror = 32
            raise error
        original(source, destination)
    monkeypatch.setattr(store.os, 'replace', replace)
    path = tmp_path / 'state.json'
    store.write_text_atomic(path, '{"ok": true}')
    assert len(attempts) == 2
    assert json.loads(path.read_text()) == {'ok': True}


def test_other_permission_errors_are_not_swallowed(tmp_path, monkeypatch):
    def denied(*args):
        raise PermissionError('denied')
    monkeypatch.setattr(store.os, 'replace', denied)
    with pytest.raises(PermissionError):
        store.write_text_atomic(tmp_path / 'state.json', '{}')
    assert not list(tmp_path.glob('*.tmp'))
