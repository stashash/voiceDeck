"""Описание паттерна по картинке слайда. Живых вызовов нет: сервер подменён MockTransport."""
import json

import httpx

from designer.contracts import DesignSystem, Margins, Pattern, SlideKind, Tokens
from designer.llm.client import LlmClient
from designer.parse.describe import describe_patterns

_PNG = b"\x89PNG\r\n\x1a\nkartinka-slayda"


def _design_system(patterns: list[Pattern]) -> DesignSystem:
    tokens = Tokens(
        colors=[], fonts=[], type_scale=[],
        margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05),
    )
    return DesignSystem(
        id="ds", source_file="shablon.pptx", slide_size_emu=(9144000, 5143500),
        tokens=tokens, patterns=patterns,
    )


def _pattern(kind: SlideKind = SlideKind.cards, confidence: float = 0.5,
             needs_images: bool = False) -> Pattern:
    return Pattern(
        id="p001", source_slide=1, layout_name="Свободный дизайн", kind=kind,
        kind_confidence=confidence, theme="light", needs_images=needs_images,
    )


def _answer(kind: str = "team", purpose: str = "Слайд под фотографии людей и их должности",
            needs_images: bool = True) -> dict:
    return {"kind": kind, "purpose": purpose, "needs_images": needs_images}


def _client_returning(content: dict) -> tuple[LlmClient, dict]:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler)), captured


def test_unsure_kind_is_taken_from_the_model():
    client, _ = _client_returning(_answer())
    ds = _design_system([_pattern(kind=SlideKind.cards, confidence=0.5)])

    described = describe_patterns(ds, {"p001": _PNG}, client)

    assert described.patterns[0].kind is SlideKind.team
    assert described.patterns[0].purpose == "Слайд под фотографии людей и их должности"


def test_confident_kind_is_left_as_the_parse_found_it():
    client, _ = _client_returning(_answer(kind="quote"))
    ds = _design_system([_pattern(kind=SlideKind.table, confidence=0.95)])

    described = describe_patterns(ds, {"p001": _PNG}, client)

    assert described.patterns[0].kind is SlideKind.table
    assert described.patterns[0].purpose


def test_kind_outside_the_list_leaves_the_pattern_as_it_was():
    client, _ = _client_returning({"kind": "инфографика", "purpose": "что-то своё", "needs_images": False})
    ds = _design_system([_pattern(kind=SlideKind.cards, confidence=0.4)])

    assert describe_patterns(ds, {"p001": _PNG}, client).patterns[0] == ds.patterns[0]


def test_needs_images_of_the_parse_survives_an_answer_without_photos():
    client, _ = _client_returning(_answer(needs_images=False))
    ds = _design_system([_pattern(confidence=0.9, needs_images=True)])

    assert describe_patterns(ds, {"p001": _PNG}, client).patterns[0].needs_images


def test_answer_adds_needs_images_to_the_parse():
    client, _ = _client_returning(_answer(needs_images=True))
    ds = _design_system([_pattern(confidence=0.9, needs_images=False)])

    assert describe_patterns(ds, {"p001": _PNG}, client).patterns[0].needs_images


def test_slide_picture_goes_into_the_request():
    client, captured = _client_returning(_answer())
    describe_patterns(_design_system([_pattern()]), {"p001": _PNG}, client)

    content = captured["body"]["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["reasoning_effort"] == "none"


def test_server_failure_leaves_the_pattern_as_it_was():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="упал")

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    ds = _design_system([_pattern(kind=SlideKind.cards, confidence=0.3)])

    described = describe_patterns(ds, {"p001": _PNG}, client)

    assert described.patterns[0] == ds.patterns[0]


def test_pattern_without_a_picture_is_left_alone():
    client, captured = _client_returning(_answer())
    ds = _design_system([_pattern(kind=SlideKind.cards, confidence=0.3)])

    described = describe_patterns(ds, {}, client)

    assert described.patterns[0] == ds.patterns[0]
    assert "body" not in captured
