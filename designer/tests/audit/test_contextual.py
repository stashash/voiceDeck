"""Тесты контекстных проверок: картинка как data URL, находки по ответам «нет»,
сбой сервера не роняет аудит, реестр без пересечений с детерминированными id.
"""
import json

import httpx

from designer.audit.contextual import CONTEXT_CHECKS, audit_deck, audit_slide
from designer.audit.deterministic import CHECKS as DETERMINISTIC_CHECKS
from designer.contracts import Element, Scene
from designer.llm.client import LlmClient

_SLIDE_KEYS = [
    "title_is_conclusion", "body_matches_title", "one_sentence", "facts_in_source",
    "has_content", "visuals_on_topic", "no_service_text", "no_typos", "table_rows_work",
]
_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-slide-picture"


def _scene(slide_id: str = "s1") -> Scene:
    return Scene(
        slide_id=slide_id, pattern_id="p1",
        elements=[
            Element(id="t1", type="text", role="title", box=(0.1, 0.1, 0.6, 0.1), text="Итоги квартала"),
            Element(id="b1", type="text", role="body", box=(0.1, 0.25, 0.7, 0.4), text="Конверсия выросла до 20%"),
        ],
    )


def _all_yes_slide_answer() -> dict:
    return {key: {"answer": True, "reason": "соответствует"} for key in _SLIDE_KEYS}


def _client_returning(content: dict) -> tuple[LlmClient, dict]:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler)), captured


def test_registry_ids_are_unique_and_do_not_overlap_deterministic():
    context_ids = [c.id for c in CONTEXT_CHECKS]
    deterministic_ids = [c.id for c in DETERMINISTIC_CHECKS]
    assert len(context_ids) == len(set(context_ids))
    assert set(context_ids).isdisjoint(deterministic_ids)


def test_slide_image_is_sent_as_data_url():
    client, captured = _client_returning(_all_yes_slide_answer())
    audit_slide(_scene(), _PNG_BYTES, "исходный бриф", client)

    content = captured["body"]["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_two_no_answers_give_two_findings_with_check_ids():
    answer = _all_yes_slide_answer()
    answer["title_is_conclusion"] = {"answer": False, "reason": "заголовок называет тему"}
    answer["no_typos"] = {"answer": False, "reason": "опечатка в слове"}
    client, _ = _client_returning(answer)

    findings = audit_slide(_scene(), _PNG_BYTES, "исходный бриф", client)

    check_ids = {f.check_id for f in findings}
    assert check_ids == {"context.title_is_conclusion", "context.no_typos"}
    assert all(f.kind == "contextual" and f.severity == "warning" for f in findings)
    assert all(f.slide_id == "s1" for f in findings)


def test_all_yes_answers_give_empty_list():
    client, _ = _client_returning(_all_yes_slide_answer())
    assert audit_slide(_scene(), _PNG_BYTES, "исходный бриф", client) == []


def test_server_failure_gives_unavailable_finding_not_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="упал")

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    findings = audit_slide(_scene(), _PNG_BYTES, "исходный бриф", client)

    assert len(findings) == 1
    assert findings[0].check_id == "context.unavailable"
    assert findings[0].slide_id == "s1"


def test_deck_no_answer_attaches_to_named_break_slide():
    answer = {
        "one_language": {"answer": True, "reason": "", "break_slide_id": ""},
        "neighbors_linked": {"answer": False, "reason": "разрыв темы", "break_slide_id": "s2"},
    }
    client, _ = _client_returning(answer)
    scenes = [_scene("s1"), _scene("s2"), _scene("s3")]

    findings = audit_deck(scenes, client)

    assert len(findings) == 1
    assert findings[0].check_id == "context.neighbors_linked"
    assert findings[0].slide_id == "s2"


def test_deck_all_yes_gives_empty_list():
    answer = {
        "one_language": {"answer": True, "reason": "", "break_slide_id": ""},
        "neighbors_linked": {"answer": True, "reason": "", "break_slide_id": ""},
    }
    client, _ = _client_returning(answer)
    assert audit_deck([_scene("s1"), _scene("s2")], client) == []
