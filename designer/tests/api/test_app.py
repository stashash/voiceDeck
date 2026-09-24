"""Тесты HTTP API: импорт шаблона через /design-systems, живой слайд, путь с ".." в имени файла.

Задача T-13. Клиент модели подменяется через app.dependency_overrides[get_llm_client] —
живых вызовов нет. Конвертер отключается монки-патчем — окна на экране не открываются.
"""
from __future__ import annotations

import base64
import sys
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from designer import store
from designer.api.app import app, get_live_llm_client, get_llm_client
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


def _loading_llm() -> LlmClient:
    """Сервер модели, у которого модель грузится: LM Studio отвечает 400 «Failed to load model»."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": 'Failed to load model "qwen". Error: Engine protocol startup was aborted.'})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler), load_wait_s=0)


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
    app.dependency_overrides[get_live_llm_client] = lambda: _mock_llm(payload)

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
    app.dependency_overrides[get_live_llm_client] = lambda: _mock_llm(payload)

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
    app.dependency_overrides[get_live_llm_client] = lambda: _mock_llm(payload)

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
    app.dependency_overrides[get_live_llm_client] = lambda: _mock_llm(payload)

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


def test_live_slide_answers_503_while_the_model_loads(client, templates):
    _upload_first_template(client, templates)
    app.dependency_overrides[get_live_llm_client] = lambda: _loading_llm()
    response = client.post("/live/slide", json={"design_system_id": "", "chunk_text": "Число инцидентов упало с 9 до 2.",
                                                "used_pattern_ids": []})
    assert response.status_code == 503
    assert "загружается" in response.json()["detail"]


# ---------- поток 1: загрузка — проверки файла ----------

def test_upload_non_pptx_file_is_400(client):
    response = client.post("/design-systems", files={"file": ("template.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"] == "Файл не pptx"


def test_upload_corrupted_pptx_is_400(client):
    response = client.post("/design-systems", files={
        "file": ("template.pptx", b"this is not a real pptx", "application/octet-stream"),
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Файл повреждён или сохранён не до конца"


# ---------- поток 1: список, правка и удаление дизайн-систем ----------

def test_list_design_systems_returns_items_with_summary(client, templates):
    ds_id = _upload_first_template(client, templates)

    response = client.get("/design-systems")

    assert response.status_code == 200
    body = response.json()
    assert ds_id in body["ids"]
    item = next(i for i in body["items"] if i["id"] == ds_id)
    assert item["patterns"] > 0
    assert item["describe_status"] in ("pending", "running", "done", "failed")
    assert "created_at" in item and item["created_at"]


def test_patch_design_system_updates_name_and_overrides(client, templates):
    ds_id = _upload_first_template(client, templates)
    ds = client.get(f"/design-systems/{ds_id}").json()
    pattern_id = ds["patterns"][0]["id"]

    response = client.patch(f"/design-systems/{ds_id}", json={
        "name": "Моя система", "pattern_overrides": {pattern_id: False}, "removal_confirmed": True,
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Моя система"
    assert body["pattern_overrides"] == {pattern_id: False}
    assert body["removal_confirmed"] is True


def test_patch_unknown_design_system_is_404(client):
    response = client.patch("/design-systems/no-such-system", json={"name": "х"})
    assert response.status_code == 404


def test_delete_design_system_removes_the_folder(client, templates):
    ds_id = _upload_first_template(client, templates)

    response = client.delete(f"/design-systems/{ds_id}")

    assert response.status_code == 204
    assert not store.design_system_dir(ds_id).is_dir()
    assert ds_id not in client.get("/design-systems").json()["ids"]


def test_describe_endpoint_restarts_progress_in_background(client, templates, monkeypatch):
    ds_id = _upload_first_template(client, templates)
    ds = client.get(f"/design-systems/{ds_id}").json()
    payload = {"kind": ds["patterns"][0]["kind"], "purpose": "Новое назначение", "needs_images": False}
    monkeypatch.setattr("designer.pipeline._client_for", lambda task: _mock_llm(payload))

    response = client.post(f"/design-systems/{ds_id}/describe")

    assert response.status_code == 200, response.text
    # Фоновая задача в TestClient уже отработала синхронно к моменту ответа.
    after = client.get(f"/design-systems/{ds_id}").json()
    assert after["describe"]["status"] == "done"


def test_preview_missing_pattern_is_404(client, templates):
    ds_id = _upload_first_template(client, templates)
    response = client.get(f"/design-systems/{ds_id}/previews/no-such-pattern.png")
    assert response.status_code == 404


# ---------- поток 1: список колод ----------

def test_list_decks_returns_summary(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    response = client.get("/decks")

    assert response.status_code == 200
    items = response.json()["items"]
    item = next(i for i in items if i["id"] == deck_id)
    assert item["slides"] == 5
    assert item["status"] == "done"
    assert item["title"] == "План"


def test_create_deck_defaults_to_three_variants(client, templates):
    ds_id = _upload_first_template(client, templates)
    app.dependency_overrides[get_llm_client] = lambda: _mock_deck_client(_plan_payload(5))

    response = client.post("/decks", json={
        "design_system_id": ds_id, "brief": "Сервис записи к врачу, конверсия выросла до 20 процентов.",
        "purpose": "показать эффект пилота", "audience": "регистратура", "slide_count": 5,
    })

    assert response.status_code == 200, response.text
    deck_id = response.json()["deck_id"]
    state = client.get(f"/decks/{deck_id}").json()
    assert set(state["variants"]) == {"a", "b", "c"}


# ---------- поток 1: правка варианта ----------

def _first_text_element(scene: dict) -> dict:
    return next(el for el in scene["elements"] if el["type"] == "text" and el["text"])


def test_patch_slide_text_updates_scene_and_pptx(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    state = client.get(f"/decks/{deck_id}").json()
    element = _first_text_element(state["scenes"][0])

    response = client.patch(f"/decks/{deck_id}/a/slides/1/text",
                             json={"element_id": element["id"], "text": "Новый текст слайда"})

    assert response.status_code == 200, response.text
    body = response.json()
    updated = next(el for el in body["scenes"][0]["elements"] if el["id"] == element["id"])
    assert updated["text"] == "Новый текст слайда"
    # история правки сохранена, откат возможен
    assert client.post(f"/decks/{deck_id}/a/revert").status_code == 200


def test_patch_slide_text_unknown_element_is_404(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    response = client.patch(f"/decks/{deck_id}/a/slides/1/text",
                             json={"element_id": "no-such-element", "text": "х"})

    assert response.status_code == 404


def test_slide_number_out_of_range_is_404(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    response = client.patch(f"/decks/{deck_id}/a/slides/999/text",
                             json={"element_id": "x", "text": "х"})

    assert response.status_code == 404


def test_get_slide_patterns_lists_current_pattern(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    state = client.get(f"/decks/{deck_id}").json()
    current_pattern_id = state["specs"][0]["pattern_id"]

    response = client.get(f"/decks/{deck_id}/a/slides/1/patterns")

    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["pattern_id"] == current_pattern_id and item["current"] for item in items)
    assert len(items) <= 6


def test_post_slide_pattern_unknown_id_is_404(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    response = client.post(f"/decks/{deck_id}/a/slides/1/pattern", json={"pattern_id": "no-such-pattern"})

    assert response.status_code == 404


def test_post_slide_pattern_same_id_rebuilds_slide(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    state = client.get(f"/decks/{deck_id}").json()
    pattern_id = state["specs"][0]["pattern_id"]

    response = client.post(f"/decks/{deck_id}/a/slides/1/pattern", json={"pattern_id": pattern_id})

    assert response.status_code == 200, response.text
    assert response.json()["specs"][0]["pattern_id"] == pattern_id


def test_post_slide_ask_rewrites_content_via_agent(client, templates, monkeypatch):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    draft = {"title": "Переписанный заголовок", "key_message": "", "items": [], "notes": ""}
    monkeypatch.setattr("designer.edit._client_for", lambda task: _mock_llm(draft))

    response = client.post(f"/decks/{deck_id}/a/slides/1/ask", json={"instruction": "сделай короче"})

    assert response.status_code == 200, response.text
    assert response.json()["plan"]["slides"][0]["title"] == "Переписанный заголовок"


def test_patch_slide_notes_updates_plan_and_spec(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    response = client.patch(f"/decks/{deck_id}/a/notes/1", json={"notes": "Сказать про пилот"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["slides"][0]["notes"] == "Сказать про пилот"
    assert body["specs"][0]["notes"] == "Сказать про пилот"


def test_slide_action_add_copy_move_delete(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])

    added = client.post(f"/decks/{deck_id}/a/slides", json={"action": "add", "index": 1})
    assert added.status_code == 200, added.text
    assert len(added.json()["plan"]["slides"]) == 6

    copied = client.post(f"/decks/{deck_id}/a/slides", json={"action": "copy", "index": 1})
    assert copied.status_code == 200, copied.text
    assert len(copied.json()["plan"]["slides"]) == 7

    moved = client.post(f"/decks/{deck_id}/a/slides", json={"action": "move", "index": 1, "to": 3})
    assert moved.status_code == 200, moved.text

    deleted = client.post(f"/decks/{deck_id}/a/slides", json={"action": "delete", "index": 1})
    assert deleted.status_code == 200, deleted.text
    assert len(deleted.json()["plan"]["slides"]) == 6


def test_slide_action_unknown_action_is_400(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    response = client.post(f"/decks/{deck_id}/a/slides", json={"action": "fly", "index": 1})
    assert response.status_code == 422  # схема отклоняет значение вне Literal


def test_revert_without_history_is_409(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    response = client.post(f"/decks/{deck_id}/a/revert")
    assert response.status_code == 409


def test_revert_restores_previous_text(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    state = client.get(f"/decks/{deck_id}").json()
    element = _first_text_element(state["scenes"][0])
    original_text = element["text"]

    client.patch(f"/decks/{deck_id}/a/slides/1/text", json={"element_id": element["id"], "text": "Правка"})
    reverted = client.post(f"/decks/{deck_id}/a/revert")

    assert reverted.status_code == 200, reverted.text
    restored = next(el for el in reverted.json()["scenes"][0]["elements"] if el["id"] == element["id"])
    assert restored["text"] == original_text


def test_rewrite_finding_calls_agent_and_drops_the_finding(client, templates, monkeypatch):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    state_path = store.deck_variant_state_path(deck_id, "a")
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    finding = {
        "id": "manual.finding.1", "slide_id": raw["specs"][0]["slide_id"], "check_id": "contextual.wordy",
        "kind": "contextual", "severity": "warning", "message": "Слишком много слов на слайде.",
        "element_ids": [], "box": None, "fixable": False, "fix_hint": "",
    }
    raw["findings"].append(finding)
    state_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    draft = {"title": "Короче", "key_message": "", "items": [], "notes": ""}
    monkeypatch.setattr("designer.edit._client_for", lambda task: _mock_llm(draft))

    response = client.post(f"/decks/{deck_id}/a/rewrite", json={"finding_id": "manual.finding.1"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["slides"][0]["title"] == "Короче"
    assert all(f["id"] != "manual.finding.1" for f in body["findings"])


def test_rewrite_unknown_finding_is_404(client, templates):
    deck_id = _create_deck_with_variants(client, templates, ["a"])
    response = client.post(f"/decks/{deck_id}/a/rewrite", json={"finding_id": "no-such-finding"})
    assert response.status_code == 404


# ---------- поток 1: агенты и настройки (запасное поведение без designer.agents) ----------

def test_agents_list_is_empty_without_bridge_module(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "designer.agents", None)
    response = client.get("/agents")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_agent_check_is_503_without_bridge_module(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "designer.agents", None)
    response = client.post("/agents/cli:claude/check")
    assert response.status_code == 503


def test_agent_settings_default_and_roundtrip(client):
    defaults = client.get("/settings/agents")
    assert defaults.status_code == 200
    body = defaults.json()
    assert set(body) == {"deck", "live", "describe"}
    assert all(value.startswith("local:") for value in body.values())

    saved = client.put("/settings/agents", json={"deck": "cli:claude"})
    assert saved.status_code == 200
    assert saved.json()["deck"] == "cli:claude"

    again = client.get("/settings/agents")
    assert again.json()["deck"] == "cli:claude"
    assert again.json()["live"] == body["live"]  # не тронуто частичным PUT
