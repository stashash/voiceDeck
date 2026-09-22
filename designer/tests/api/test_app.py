"""Тесты HTTP API: импорт шаблона через /design-systems, живой слайд, путь с ".." в имени файла.

Задача T-13. Клиент модели подменяется через app.dependency_overrides[get_llm_client] —
живых вызовов нет. Конвертер отключается монки-патчем — окна на экране не открываются.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from designer import store
from designer.api.app import app, get_llm_client
from designer.llm.client import LlmClient

PNG = b"\x89PNG\r\n\x1a\nfake"


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


# ---------- T-12: варианты вёрстки, аудит и починка по запросу ----------

def _plan_payload(n: int) -> dict:
    slides = [{"id": "s1", "kind": "title", "title": "Сервис записи к врачу", "items": []}]
    for i in range(1, n - 1):
        slides.append({
            "id": f"s{i + 1}", "kind": "bullets", "title": f"Итог этапа {i}",
            "key_message": "Конверсия выросла до 20 процентов.",
            "items": [{"heading": "Пункт", "body": "Конверсия записи выросла до 20 процентов."}],
        })
    slides.append({"id": f"s{n}", "kind": "thanks", "title": "Спасибо"})
    return {"title": "План", "purpose": "показать эффект пилота", "audience": "регистратура", "slides": slides}


def _fill_value(prop: dict):
    kind = prop.get("type")
    if kind == "string":
        limit = prop.get("maxLength")
        text = "Готовый текст слайда"
        return text[:limit] if limit else text
    if kind == "array":
        count = prop.get("minItems", 0)
        return [_fill_value(prop.get("items", {})) for _ in range(count)]
    if kind == "object":
        return {key: _fill_value(value) for key, value in prop.get("properties", {}).items()}
    if kind == "boolean":
        return True
    if kind == "integer":
        return 0
    return ""


def _fill_for_schema(schema: dict) -> dict:
    return {key: _fill_value(prop) for key, prop in schema.get("properties", {}).items()}


def _mock_deck_client(plan_response: dict) -> LlmClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        schema = payload["response_format"]["json_schema"]["schema"]
        if "slides" in schema.get("properties", {}):
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan_response)}}]})
        content = _fill_for_schema(schema)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


def _create_deck_with_variants(client: TestClient, templates, variant_codes: list[str]) -> str:
    ds_id = _upload_first_template(client, templates)
    app.dependency_overrides[get_llm_client] = lambda: _mock_deck_client(_plan_payload(5))

    response = client.post("/decks", json={
        "design_system_id": ds_id, "brief": "Сервис записи к врачу, конверсия выросла до 20 процентов.",
        "purpose": "показать эффект пилота", "audience": "регистратура", "slide_count": 5,
        "variants": variant_codes,
    })
    assert response.status_code == 200, response.text
    return response.json()["deck_id"]


def test_create_deck_with_variants_and_old_paths_still_respond(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a", "b", "c"])

    state = client.get(f"/decks/{deck_id}")
    assert state.status_code == 200
    body = state.json()
    assert set(body["variants"]) == {"a", "b", "c"}
    assert body["status"] == "done"  # верхний уровень — вариант a, для старых клиентов

    for variant in ("a", "b", "c"):
        response = client.get(f"/decks/{deck_id}/{variant}/files/deck.pptx")
        assert response.status_code == 200

    # прежний путь без варианта отвечает тем же файлом, что и вариант a
    old = client.get(f"/decks/{deck_id}/files/deck.pptx")
    new_a = client.get(f"/decks/{deck_id}/a/files/deck.pptx")
    assert old.status_code == 200
    assert old.content == new_a.content


def test_deck_variant_fix_endpoint_rebuilds_and_returns_report(client, templates, monkeypatch):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    def fake_apply_fixes(specs, scenes, findings, finding_ids, ds):
        report = [{"finding_id": fid, "status": "skipped", "what": "не нашлось похожего исправления"}
                   for fid in finding_ids]
        return specs, scenes, report

    monkeypatch.setattr("designer.pipeline.audit_fixes.apply_fixes", fake_apply_fixes)

    response = client.post(f"/decks/{deck_id}/a/fix", json={"finding_ids": ["fake.finding.0"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report"] == [{"finding_id": "fake.finding.0", "status": "skipped",
                                "what": "не нашлось похожего исправления"}]
    assert isinstance(body["findings"], list)


# ---------- T-26: картинки слайдов ----------

def _fake_slide_images(monkeypatch) -> None:
    """Движок подменён: картинки фейковые, окно PowerPoint/LibreOffice не открывается."""
    monkeypatch.setattr("designer.pipeline.convert.available", lambda: ["fake"])
    monkeypatch.setattr("designer.pipeline.convert.to_pdf",
                         lambda pptx_path, out_path: out_path.write_bytes(b"%PDF-1.4 fake"))
    monkeypatch.setattr("designer.pipeline.render.render_slides",
                         lambda pptx_path, count, width_px=1600: [PNG] * count)
    monkeypatch.setattr("designer.pipeline.render.render_spec",
                         lambda spec, ds, package_dir: PNG)


def test_deck_state_lists_slide_images_and_serves_them(client, templates, monkeypatch):
    _fake_slide_images(monkeypatch)
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    state = client.get(f"/decks/{deck_id}")
    assert state.status_code == 200
    addresses = state.json()["slide_images"]
    # В адресе метка времени файла: после починки картинка перерисована, браузер не берёт прежнюю из кэша.
    assert [a.split("?")[0] for a in addresses] == [f"/decks/{deck_id}/a/slides/{n}.png" for n in range(1, 6)]
    assert all(a.split("?v=")[1].isdigit() for a in addresses)
    assert state.json()["variants"]["a"]["slide_images"] == addresses

    image = client.get(addresses[0])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == PNG


def test_live_slide_returns_picture_of_the_slide(client, templates, monkeypatch):
    _fake_slide_images(monkeypatch)
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
    assert body["image_png_base64"] == base64.b64encode(PNG).decode("ascii")
    assert 'class="slide-image"' in body["html"]


def test_live_slide_without_engine_has_no_picture(client, templates):
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
    assert response.json()["image_png_base64"] is None


def test_slide_image_dotdot_path_is_rejected(client):
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")

    # Точки закодированы (%2e%2e): иначе http-клиент схлопнет ".." ещё до отправки запроса.
    assert client.get(f"/decks/{deck_id}/a/slides/%2e%2e.png").status_code == 400
    assert client.get(f"/decks/{deck_id}/%2e%2e/slides/1.png").status_code == 400


def test_slide_image_that_was_not_rendered_is_404(client):
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")

    assert client.get(f"/decks/{deck_id}/a/slides/7.png").status_code == 404
