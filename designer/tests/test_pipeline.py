"""Тесты конвейера: импорт шаблона, генерация колоды, события, устойчивость к сбою модели, живой слайд.

Задача T-13. Живых вызовов модели нет: клиент подменяется через httpx.MockTransport,
конвертер в pdf/png отключается монки-патчем (окна на экране не открываются).
"""
from __future__ import annotations

import json

import httpx
import pytest
from pptx import Presentation

from designer import pipeline, store
from designer.llm.client import LlmClient

BRIEF = (
    "Сервис записи к врачу для клиники. За квартал конверсия записи выросла до 20 процентов. "
    "Аудитория — администраторы регистратуры, назначение — показать эффект пилота."
)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def _no_converter(monkeypatch):
    # Окна на экране не открываем и в тестах, и в бою на этой машине без конвертера:
    # реальный soffice/PowerPoint тесты не зовут.
    monkeypatch.setattr("designer.pipeline.convert.available", lambda: [])


def _plan_json(n: int) -> dict:
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


def _mock_client(plan_response: dict, *, fail_marker: str | None = None) -> LlmClient:
    """Клиент, различающий вызов плана и вызов заполнения слотов по форме схемы ответа.

    fail_marker — если подстрока встречается в тексте запроса заполнения слотов, сервер
    отвечает 500: так проверяется устойчивость колоды к сбою модели на одном слайде.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        schema = payload["response_format"]["json_schema"]["schema"]
        if "slides" in schema.get("properties", {}):
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan_response)}}]})
        if fail_marker is not None and fail_marker in json.dumps(payload["messages"], ensure_ascii=False):
            return httpx.Response(500, text="модель недоступна")
        content = _fill_for_schema(schema)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


def _import_first_template(templates) -> str:
    path = templates[0]
    ds = pipeline.import_template(path.read_bytes(), path.name)
    return ds.id


def test_import_template_places_package_in_store(templates):
    path = templates[0]
    ds = pipeline.import_template(path.read_bytes(), path.name)

    package_dir = store.design_system_dir(ds.id)
    assert (package_dir / "manifest.json").is_file()
    assert (package_dir / "source.pptx").is_file()
    assert ds.id in store.list_design_system_ids()


def test_generate_deck_produces_files_and_run_manifest(templates):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    events: list[pipeline.PipelineEvent] = []

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   events.append, client=client)

    assert len(deck.scenes) == 5

    files_dir = store.deck_files_dir(deck.id)
    prs = Presentation(str(files_dir / "deck.pptx"))
    assert len(prs.slides) == 5

    html_text = (files_dir / "deck.html").read_text(encoding="utf-8")
    assert html_text.count('class="slide"') == 5

    manifest = store.load_run(deck.id)
    assert manifest is not None
    names = {skill.name for skill in manifest.skills}
    assert {"plan-deck", "fill-slots"} <= names

    state = store.load_deck_state(deck.id)
    assert state is not None
    assert state["status"] == "done"
    assert len(state["scenes"]) == 5


def test_events_are_ordered_and_end_with_done(templates):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    events: list[pipeline.PipelineEvent] = []

    pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                            events.append, client=client)

    assert events[0].step == "plan"
    assert events[-1].step == "done"
    slide_indices = [event.slide_index for event in events if event.step == "slide"]
    assert slide_indices == sorted(slide_indices)
    assert slide_indices == [0, 1, 2, 3, 4]


def test_slide_model_failure_does_not_break_deck(templates):
    ds_id = _import_first_template(templates)
    plan = _plan_json(5)
    plan["slides"][2]["title"] = "Маркер сбоя модели"
    client = _mock_client(plan, fail_marker="Маркер сбоя модели")
    events: list[pipeline.PipelineEvent] = []

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   events.append, client=client)

    assert len(deck.scenes) == 5
    assert any(event.step == "slide-fallback" for event in events)
    state = store.load_deck_state(deck.id)
    assert state["status"] == "done"


def test_live_slide_returns_none_for_empty_title(templates):
    ds_id = _import_first_template(templates)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"kind": "title", "title": "", "key_message": "", "items": []}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    scene = pipeline.live_slide(ds_id, "всем привет, начинаем", [], client=client)

    assert scene is None


def test_deck_file_path_rejects_dotdot():
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")

    assert store.deck_file_path(deck_id, "..") is None
    assert store.deck_file_path(deck_id, "../secret.txt") is None
    assert store.deck_file_path(deck_id, "..\\secret.txt") is None
    assert store.deck_file_path(deck_id, "deck.pptx") is not None
