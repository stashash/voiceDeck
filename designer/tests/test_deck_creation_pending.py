from fastapi import BackgroundTasks

from designer import store
from designer.api.app import DeckCreateRequest, create_deck, get_deck


def test_created_deck_is_visible_before_background_work(monkeypatch, tmp_path):
    monkeypatch.setenv("DESIGNER_DATA_DIR", str(tmp_path))
    # Do not execute BackgroundTasks: this is the exact request/worker race.
    tasks = BackgroundTasks()
    response = create_deck(DeckCreateRequest(design_system_id="example", brief="Brief", variants=["a", "b", "c"]),
                           tasks, client=object())
    result = get_deck(response.deck_id)
    assert result.status == "running"
    assert set(result.variants) == {"a", "b", "c"}
    assert all(v.plan is None and v.status == "running" for v in result.variants.values())
    assert len(tasks.tasks) == 1
