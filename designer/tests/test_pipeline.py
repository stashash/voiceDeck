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
PNG = b"\x89PNG\r\n\x1a\nfake"


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
    result = pipeline.live_slide(ds_id, "всем привет, начинаем", [], client=client)

    assert result is None


def test_deck_file_path_rejects_dotdot():
    deck_id = store.new_deck_id()
    store.init_deck(deck_id, "any-ds")

    assert store.deck_file_path(deck_id, "..") is None
    assert store.deck_file_path(deck_id, "../secret.txt") is None
    assert store.deck_file_path(deck_id, "..\\secret.txt") is None
    assert store.deck_file_path(deck_id, "deck.pptx") is not None


# ---------- T-12: варианты вёрстки, аудит и починка по запросу ----------

def _fake_convert(monkeypatch, png_count: int = 5) -> None:
    """Конвертер подменён: файлы фейковые, окно PowerPoint/LibreOffice не открывается."""

    def fake_to_pdf(pptx_path, out_path):
        out_path.write_bytes(b"%PDF-1.4 fake")
        return out_path

    def fake_render_slides(pptx_path, count, width_px=1600):
        return [PNG + str(i).encode("ascii") for i in range(png_count)]

    monkeypatch.setattr("designer.pipeline.convert.available", lambda: ["fake"])
    monkeypatch.setattr("designer.pipeline.convert.to_pdf", fake_to_pdf)
    monkeypatch.setattr("designer.pipeline.render.render_slides", fake_render_slides)


def test_generate_deck_with_three_variants_produces_three_pptx(templates):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   lambda e: None, client=client, variants=["a", "b", "c"])

    assert deck.variant == "a"
    for variant in ("a", "b", "c"):
        pptx_path = store.deck_variant_file_path(deck.id, variant, "deck.pptx")
        assert pptx_path is not None and pptx_path.is_file()
        prs = Presentation(str(pptx_path))
        assert len(prs.slides) >= 1

    # прежний путь без варианта отвечает и указывает на вариант a
    old_path = store.deck_file_path(deck.id, "deck.pptx")
    assert old_path == store.deck_variant_file_path(deck.id, "a", "deck.pptx")
    assert old_path.is_file()


def test_contextual_audit_runs_once_per_deck(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    _fake_convert(monkeypatch, png_count=5)

    calls = {"slide": 0, "deck": 0}

    def fake_audit_slide(scene, png, source_text, client):
        calls["slide"] += 1
        return []

    def fake_audit_deck(scenes, client):
        calls["deck"] += 1
        return []

    monkeypatch.setattr("designer.pipeline.audit_slide", fake_audit_slide)
    monkeypatch.setattr("designer.pipeline.audit_deck", fake_audit_deck)

    pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                            lambda e: None, client=client, variants=["a", "b", "c"])

    # audit_deck зовётся строго на колоду, не на вариант: три варианта — один вызов.
    assert calls["deck"] == 1
    assert calls["slide"] == 5


def test_run_contextual_audit_for_other_variant_on_request(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    _fake_convert(monkeypatch, png_count=3)
    monkeypatch.setattr("designer.pipeline.audit_slide", lambda *a, **k: [])
    monkeypatch.setattr("designer.pipeline.audit_deck", lambda *a, **k: [])

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   lambda e: None, client=client, variants=["a", "b"])

    state_b_before = store.load_deck_state(deck.id, "b")
    assert all(f["kind"] != "contextual" for f in state_b_before["findings"])  # b ещё не аудирован

    calls = {"slide": 0}
    monkeypatch.setattr(
        "designer.pipeline.audit_slide",
        lambda scene, png, text, client: (calls.__setitem__("slide", calls["slide"] + 1), [])[1],
    )

    new_findings = pipeline.run_contextual_audit(deck.id, "b", client=client)

    assert calls["slide"] > 0
    assert isinstance(new_findings, list)


def test_run_contextual_audit_without_rendered_slides_raises(templates):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   lambda e: None, client=client)

    with pytest.raises(RuntimeError):
        pipeline.run_contextual_audit(deck.id, "a", client=client)


def test_apply_fixes_rebuilds_files_and_returns_report(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   lambda e: None, client=client)

    def fake_apply_fixes(specs, scenes, findings, finding_ids, ds):
        report = [{"finding_id": fid, "status": "fixed", "what": "передвинут в поля"} for fid in finding_ids]
        return specs, scenes, report

    monkeypatch.setattr("designer.pipeline.audit_fixes.apply_fixes", fake_apply_fixes)

    report, findings = pipeline.apply_fixes(deck.id, "a", ["fake.finding.0"])

    assert report == [{"finding_id": "fake.finding.0", "status": "fixed", "what": "передвинут в поля"}]
    assert isinstance(findings, list)

    pptx_path = store.deck_variant_file_path(deck.id, "a", "deck.pptx")
    assert pptx_path.is_file()
    prs = Presentation(str(pptx_path))
    assert len(prs.slides) == 5

    new_state = store.load_deck_state(deck.id, "a")
    assert new_state["status"] == "done"


def test_apply_fixes_unknown_deck_raises():
    with pytest.raises(ValueError):
        pipeline.apply_fixes("no-such-deck", "a", ["x"])


# ---------- T-26: картинки слайдов и два вида HTML ----------

def _live_client(payload: dict) -> LlmClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


_LIVE_PAYLOAD = {
    "kind": "bullets", "title": "Автоматизация экономит время",
    "key_message": "Скрипты забирают рутину.",
    "items": [{"heading": "Меньше ошибок", "body": "Проверки идут по сценарию."}],
}


def test_deck_puts_slide_images_and_both_kinds_of_html(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    _fake_convert(monkeypatch, png_count=5)

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   lambda e: None, client=client)

    assert store.deck_variant_slide_numbers(deck.id, "a") == [1, 2, 3, 4, 5]

    files_dir = store.deck_files_dir(deck.id)
    picture_html = (files_dir / "deck.html").read_text(encoding="utf-8")
    markup_html = (files_dir / "deck.markup.html").read_text(encoding="utf-8")
    assert 'class="slide-image"' in picture_html
    assert 'class="slide-image"' not in markup_html


def test_deck_without_engine_keeps_markup_html(templates):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    events: list[pipeline.PipelineEvent] = []

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   events.append, client=client)

    files_dir = store.deck_files_dir(deck.id)
    assert (files_dir / "deck.html").read_text(encoding="utf-8") == \
        (files_dir / "deck.markup.html").read_text(encoding="utf-8")
    assert store.deck_variant_slide_numbers(deck.id, "a") == []
    assert any(event.step == "slide-images-skipped" for event in events)


def test_deck_keeps_markup_html_when_engine_fails_on_pictures(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    _fake_convert(monkeypatch, png_count=5)

    def fail(pptx_path, count, width_px=1600):
        raise pipeline.convert.ConverterUnavailable("движок отказал")

    monkeypatch.setattr("designer.pipeline.render.render_slides", fail)
    events: list[pipeline.PipelineEvent] = []

    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   events.append, client=client)

    files_dir = store.deck_files_dir(deck.id)
    assert 'class="slide-image"' not in (files_dir / "deck.html").read_text(encoding="utf-8")
    assert any(event.step == "slide-images-failed" for event in events)


def test_new_slide_images_replace_the_old_ones(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    client = _mock_client(_plan_json(5))
    _fake_convert(monkeypatch, png_count=5)
    deck = pipeline.generate_deck(ds_id, BRIEF, "показать эффект пилота", "регистратура", 5,
                                   lambda e: None, client=client)

    monkeypatch.setattr("designer.pipeline.audit_fixes.apply_fixes",
                         lambda specs, scenes, findings, finding_ids, ds: (specs, scenes, []))
    _fake_convert(monkeypatch, png_count=2)

    pipeline.apply_fixes(deck.id, "a", [])

    assert store.deck_variant_slide_numbers(deck.id, "a") == [1, 2]


def test_live_slide_returns_picture_and_html_with_it(templates, monkeypatch):
    ds_id = _import_first_template(templates)
    monkeypatch.setattr("designer.pipeline.convert.available", lambda: ["fake"])
    monkeypatch.setattr("designer.pipeline.render.render_spec",
                         lambda spec, ds, package_dir: PNG)

    result = pipeline.live_slide(ds_id, "мы внедрили автоматизацию", [],
                                  client=_live_client(_LIVE_PAYLOAD))

    assert result.png == PNG
    assert 'class="slide-image"' in result.html
    assert result.scene.elements


def test_live_slide_without_engine_gives_markup_html(templates):
    ds_id = _import_first_template(templates)

    result = pipeline.live_slide(ds_id, "мы внедрили автоматизацию", [],
                                  client=_live_client(_LIVE_PAYLOAD))

    assert result.png is None
    assert "<!DOCTYPE html>" in result.html
    assert 'class="slide-image"' not in result.html
