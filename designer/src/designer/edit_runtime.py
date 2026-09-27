"""Single-process document locks and coalesced exports, independent of editing.

The persisted revision is authoritative. A stale export can never publish over
a newer document. Export failures stay visible and downloads retry after restart.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from threading import RLock
import os
import tempfile

from designer import store

_registry_lock = RLock()
_locks = {}
_jobs = {}
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deck-export")


def lock(deck_id, variant):
    key = str(store.deck_variant_state_path(deck_id, variant))
    with _registry_lock:
        return _locks.setdefault(key, RLock())


def serialized(fn):
    @wraps(fn)
    def run(deck_id, variant, *args, **kwargs):
        with lock(deck_id, variant):
            return fn(deck_id, variant, *args, **kwargs)
    return run


def _key(deck_id, variant):
    return str(store.deck_variant_state_path(deck_id, variant))


def schedule(deck_id, variant, revision):
    key = _key(deck_id, variant)
    with _registry_lock:
        existing = _jobs.get(key)
        if existing and existing[0] == revision and not existing[1].done():
            return existing[1]
        future = _pool.submit(_export, deck_id, variant, revision)
        _jobs[key] = (revision, future)
        return future


def _export(deck_id, variant, revision):
    from designer import edit
    with lock(deck_id, variant):
        state = edit._load(deck_id, variant)
        if state.raw.get("revision") != revision:
            return
    # Heavy work uses an immutable snapshot and never holds the editing lock.
    files = store.deck_variant_files_dir(deck_id, variant)
    with tempfile.TemporaryDirectory(prefix="export-", dir=files.parent) as directory:
        staging = Path(directory)
        edit._export_files(state, staging)
        with lock(deck_id, variant):
            if store.load_deck_state(deck_id, variant).get("revision") != revision:
                return
            for path in staging.iterdir():
                if path.is_file():
                    os.replace(path, files / path.name)
            images = staging / "slides"
            if images.exists():
                target = store.deck_variant_slides_dir(deck_id, variant)
                for path in images.iterdir():
                    os.replace(path, target / path.name)
            store._write_json(files / "export-revision.json", {"revision": revision})


def ensure_export(deck_id, variant):
    """Downloads wait for current files, never silently serve an old revision."""
    while True:
        with lock(deck_id, variant):
            raw = store.load_deck_state(deck_id, variant)
            revision = raw.get("revision")
            marker = store.deck_variant_files_dir(deck_id, variant) / "export-revision.json"
            if not revision or (marker.exists() and store.read_json_file(marker).get("revision") == revision):
                return
            future = schedule(deck_id, variant, revision)
        future.result()
