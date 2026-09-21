"""Тесты HTTP API: импорт шаблона через /design-systems, живой слайд, путь с ".." в имени файла.

Задача T-13. Клиент модели подменяется через app.dependency_overrides[get_llm_client] —
живых вызовов нет. Конвертер отключается монки-патчем — окна на экране не открываются.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from designer import store
from designer.api.app import app, get_llm_client
from designer.llm.client import LlmClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    monkeypatch.setattr("designer.pipeline.convert.available", lambda: [])
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _mock_llm(payload: dict) -> LlmClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


def _upload_first_template(client: TestClient, templates) -> str:
    path = templates[0]
    with path.open("rb") as f:
        response = client.post(
            "/design-systems",
            files={"file": (path.name, f,
                             "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_import_template_endpoint_places_package_in_store(client, templates):
    ds_id = _upload_first_template(client, templates)

    assert (store.design_system_dir(ds_id) / "manifest.json").is_file()
    listing = client.get("/design-systems")
    assert listing.status_code == 200
    assert ds_id in listing.json()["ids"]


def test_live_slide_returns_scene_with_model_text(client, templates):
    ds_id = _upload_first_template(client, templates)
    payload = {
        "kind": "bullets", "title": "Автоматизация экономит время",
        "key_message": "Скрипты забирают рутину.",
        "items": [{"heading": "Меньше ошибок", "body": "Проверки идут по сценарию."}],
    }
    app.dependency_overrides[get_llm_client] = lambda: _mock_llm(payload)

    response = client.post("/live/slide", json={
        "design_system_id": ds_id, "chunk_text": "мы внедрили автоматизацию", "used_pattern_ids": [],
    })

    assert response.status_code == 200
    body = response.json()
    texts = [el["text"] for el in body["scene"]["elements"] if el.get("text")]
    assert any("Автоматизация экономит время" in text for text in texts)
    assert "<!DOCTYPE html>" in body["html"]


def test_live_slide_returns_204_for_empty_title(client, templates):
    ds_id = _upload_first_template(client, templates)
    payload = {"kind": "title", "title": "", "key_message": "", "items": []}
    app.dependency_overrides[get_llm_client] = lambda: _mock_llm(payload)

    response = client.post("/live/slide", json={
        "design_system_id": ds_id, "chunk_text": "всем привет", "used_pattern_ids": [],
    })

    assert response.status_code == 204


def test_deck_file_dotdot_path_is_rejected(client):
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")

    # Точки закодированы (%2e%2e), иначе http-клиент сам схлопывает ".." в пути ещё до
    # отправки запроса, и до серверной проверки дело не доходит.
    response = client.get(f"/decks/{deck_id}/files/%2e%2e")

    assert response.status_code == 400


def test_deck_file_unknown_name_is_404_not_found(client):
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")

    response = client.get(f"/decks/{deck_id}/files/deck.pptx")

    assert response.status_code == 404
