"""Читатель файла состояния не видит его пустым, пока писатель его перезаписывает."""
import json
import threading

from designer import store


def test_reader_never_sees_empty_or_broken_json(tmp_path):
    path = tmp_path / "manifest.json"
    store.write_text_atomic(path, json.dumps({"n": 0}))
    payload = {"patterns": ["x" * 200] * 400}
    stop = threading.Event()
    broken: list[str] = []

    def writer() -> None:
        n = 0
        while not stop.is_set():
            n += 1
            store.write_text_atomic(path, json.dumps({**payload, "n": n}))

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
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))
