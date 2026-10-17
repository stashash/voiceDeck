"""Советы по колоде из наработок кинодек и переходы слайдов в pptx."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pptx import Presentation
from pptx.oxml.ns import qn

from designer.audit.advice import READ_WORDS, advise_deck, check_same_view, check_three_seconds
from designer.audit.deterministic import run_checks
from designer.contracts import Element, Scene, SlideSpec
from designer.export.pptx_deck import export_pptx
from designer.llm.client import LlmClient
from designer.parse.package import load_package

DEMO = Path(__file__).resolve().parents[2] / "demo" / "design-systems" / "shablon-prezentacii-vk-education"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


def _scene(slide_id: str, pattern_id: str, *texts: str) -> Scene:
    elements = [Element(id="t", type="text", role="title", box=(0, 0, 1, 0.1), text="Заголовок слайда")]
    elements += [Element(id=f"b{i}", type="text", role="body", box=(0, 0.2, 1, 0.1), text=t) for i, t in enumerate(texts)]
    return Scene(slide_id=slide_id, pattern_id=pattern_id, elements=elements)


def test_long_slide_gets_three_seconds_advice():
    long = " ".join(["слово"] * (READ_WORDS + 1))
    findings = check_three_seconds([_scene("s1", "p1", long), _scene("s2", "p1", "коротко")], None)
    assert [f.slide_id for f in findings] == ["s1"] and "заметки" in findings[0].message


def test_third_slide_of_same_view_gets_advice():
    scenes = [_scene("s1", "p1"), _scene("s2", "p1"), _scene("s3", "p1"), _scene("s4", "p2")]
    assert [f.slide_id for f in check_same_view(scenes, None)] == ["s3"]


def test_advice_is_registered_in_deterministic_audit():
    ds = load_package(DEMO) if (DEMO / "manifest.json").is_file() else pytest.skip("нет демо-пакета")
    scenes = [_scene("s1", "p1"), _scene("s2", "p1"), _scene("s3", "p1")]
    assert any(f.check_id == "advice.same_view" for f in run_checks(scenes, ds))


def test_model_advice_keeps_known_slides_and_rules():
    answer = {"items": [
        {"slide_id": "s2", "rule": "lonely_number", "advice": "Добавьте к 18 % базу: к III кварталу."},
        {"slide_id": "s2", "rule": "lonely_number", "advice": "повтор того же совета"},
        {"slide_id": "s9", "rule": "not_distinct", "advice": "слайда нет в колоде"},
        {"slide_id": "s3", "rule": "make_it_pop", "advice": "правила нет в списке"},
        {"slide_id": "s3", "rule": "no_function", "advice": "Слейте этот слайд со следующим."},
    ]}

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}]})

    scenes = [_scene("s1", "p1"), _scene("s2", "p2", "18 %"), _scene("s3", "p3", "текст")]
    findings = advise_deck(scenes, LlmClient("http://test/v1", "m", transport=httpx.MockTransport(handler)))
    assert [(f.slide_id, f.check_id) for f in findings] == [("s2", "advice.lonely_number"), ("s3", "advice.no_function")]
    assert all(f.kind == "contextual" and f.id for f in findings)


def test_model_failure_gives_no_advice():
    def handler(request):
        return httpx.Response(500, text="boom")
    client = LlmClient("http://test/v1", "m", transport=httpx.MockTransport(handler), load_wait_s=0)
    assert advise_deck([_scene("s1", "p1")], client) == []


def test_pptx_slides_fade_and_morph_within_one_scene(tmp_path):
    if not (DEMO / "manifest.json").is_file():
        pytest.skip("нет демо-пакета")
    ds = load_package(DEMO)
    pattern = next(p for p in ds.patterns if any(s.role == "title" for s in p.slots) and not p.needs_images)
    title = next(s for s in pattern.slots if s.role == "title")
    specs = [SlideSpec(slide_id="s1", pattern_id=pattern.id, slot_text={title.id: "Итоги года"}),
             SlideSpec(slide_id="s2", pattern_id=pattern.id, slot_text={title.id: "Итоги года"}),
             SlideSpec(slide_id="s3", pattern_id=pattern.id, slot_text={title.id: "Что дальше"})]
    out = export_pptx(specs, ds, DEMO, tmp_path / "deck.pptx")
    kinds = []
    for slide in Presentation(str(out)).slides:
        blocks = slide._element.findall(f"{MC}AlternateContent")
        assert len(blocks) == 1
        choice = blocks[0].find(f"{MC}Choice")
        kinds.append("morph" if "morph" in choice[0][0].tag else "fade")
        assert blocks[0].find(f"{MC}Fallback").find(qn("p:transition")) is not None
    assert kinds == ["fade", "morph", "fade"]
