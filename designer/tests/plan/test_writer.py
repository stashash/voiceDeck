"""Тесты заполнения слотов: лимиты в схеме, повтор и сокращение, число пунктов, числа из намерения."""
import json

import httpx

from designer.contracts import Item, SlideIntent, SlideKind
from designer.llm.client import LlmClient
from designer.plan.writer import fill_slots, speech_to_slide

BASE_INTENT = SlideIntent(
    id="s1",
    kind=SlideKind.cards,
    title="Экономим время команды",
    key_message="Автоматизация сокращает время на 20 процентов.",
    items=[
        Item(heading="Автоматизация", body="Скрипты забирают рутинные шаги."),
        Item(heading="Меньше ошибок", body="Проверки идут по одному сценарию."),
        Item(heading="Быстрее внедрение", body="Новый процесс запускается за день."),
    ],
)


def _client_returning(*responses: dict) -> LlmClient:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(responses[index])}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


def _client_capturing(payload: dict) -> tuple[LlmClient, dict]:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler)), captured


def test_schema_maxlength_matches_limits():
    client, captured = _client_capturing({
        "title": "Короче", "subtitle": "Тоже короче",
        "items": [{"heading": "a", "body": "b"}, {"heading": "c", "body": "d"}],
    })

    fill_slots(BASE_INTENT, {"title": 40, "subtitle": 60}, {"heading": 20, "body": 50}, 2, client)

    schema = captured["body"]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["title"]["maxLength"] == 40
    assert schema["properties"]["subtitle"]["maxLength"] == 60
    assert schema["properties"]["items"]["minItems"] == 2
    assert schema["properties"]["items"]["maxItems"] == 2
    assert schema["properties"]["items"]["items"]["properties"]["heading"]["maxLength"] == 20
    assert schema["properties"]["items"]["items"]["properties"]["body"]["maxLength"] == 50


def test_fill_skill_params_are_sent_in_request_body():
    client, captured = _client_capturing({"title": "Итог", "items": []})
    fill_slots(BASE_INTENT, {"title": 30}, {}, 0, client)

    body = captured["body"]
    assert body["reasoning_effort"] == "none"
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 1200


def test_too_long_response_retries_then_truncates_at_word_boundary():
    responses = [
        {"title": "X" * 50, "items": []},
        {"title": "AAAAA BBBBB CCCCC DDDDD", "items": []},
    ]
    client = _client_returning(*responses)
    result = fill_slots(BASE_INTENT, {"title": 20}, {}, 0, client)

    assert result.title == "AAAAA BBBBB CCCCC"
    assert len(result.title) <= 20
    assert len(client.call_durations_ms) == 2


def test_too_long_response_prefers_sentence_boundary():
    long_title = "Предложение раз. Предложение два, которое не помещается совсем."
    responses = [{"title": "Y" * 60, "items": []}, {"title": long_title, "items": []}]
    client = _client_returning(*responses)
    result = fill_slots(BASE_INTENT, {"title": 20}, {}, 0, client)

    assert result.title == "Предложение раз."


def test_truncate_avoids_word_break_and_strips_trailing_conjunction():
    responses = [
        {"title": "Z" * 60, "items": []},
        {"title": "Потоковая загрузка быстрее и стабильнее пакетной", "items": []},
    ]
    client = _client_returning(*responses)
    result = fill_slots(BASE_INTENT, {"title": 32}, {}, 0, client)

    assert result.title == "Потоковая загрузка быстрее"
    assert len(client.call_durations_ms) == 2


def test_truncate_strips_trailing_comma():
    responses = [
        {"title": "Z" * 30, "items": []},
        {"title": "Быстрее, но дороже вариант с доставкой", "items": []},
    ]
    client = _client_returning(*responses)
    result = fill_slots(BASE_INTENT, {"title": 10}, {}, 0, client)

    assert result.title == "Быстрее"


def test_item_count_is_forced_to_n_units():
    payload = {"title": "Итог", "items": [
        {"heading": "Раз", "body": "Текст"},
        {"heading": "Два", "body": "Текст"},
        {"heading": "Три", "body": "Текст"},
        {"heading": "Четыре", "body": "Текст"},
    ]}
    client = _client_returning(payload)
    result = fill_slots(BASE_INTENT, {"title": 20}, {"heading": 20, "body": 30}, 2, client)

    assert len(result.items) == 2
    assert len(client.call_durations_ms) == 2  # несовпадение числа пунктов — тоже нарушение


def test_known_number_is_kept_unknown_number_is_dropped():
    payload = {"title": "Рост 20 против 42 процента", "items": []}
    client = _client_returning(payload)
    result = fill_slots(BASE_INTENT, {"title": 60}, {}, 0, client)

    assert "20" in result.title
    assert "42" not in result.title


def test_speech_to_slide_returns_empty_title_for_greeting():
    payload = {"kind": "title", "title": "", "key_message": "", "items": []}
    client = _client_returning(payload)
    intent = speech_to_slide("Всем привет, начинаем", [SlideKind.title, SlideKind.bullets], client)

    assert intent.title == ""


def test_speech_to_slide_builds_intent_from_fragment():
    payload = {
        "kind": "bullets", "title": "Автоматизация экономит время",
        "key_message": "Скрипты забирают рутину.",
        "items": [{"heading": "Меньше ошибок", "body": "Проверки идут по сценарию."}],
    }
    client = _client_returning(payload)
    intent = speech_to_slide("Мы внедрили автоматизацию, и стало меньше ошибок",
                              [SlideKind.title, SlideKind.bullets], client)

    assert intent.kind == SlideKind.bullets
    assert intent.title == "Автоматизация экономит время"
    assert len(intent.items) == 1


def test_speech_to_slide_drops_number_not_in_fragment():
    payload = {"kind": "big_number", "title": "Рост на 50 процентов", "key_message": "", "items": []}
    client = _client_returning(payload)
    intent = speech_to_slide("Мы выросли значительно за квартал", [SlideKind.big_number], client)

    assert "50" not in intent.title


def test_speech_schema_restricts_kind_to_given_list():
    client, captured = _client_capturing({"kind": "title", "title": "", "key_message": "", "items": []})
    speech_to_slide("привет", [SlideKind.title, SlideKind.quote], client)

    schema = captured["body"]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["kind"]["enum"] == ["title", "quote"]


def test_speech_skill_params_are_sent_in_request_body():
    client, captured = _client_capturing({"kind": "title", "title": "", "key_message": "", "items": []})
    speech_to_slide("привет", [SlideKind.title], client)

    body = captured["body"]
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == 400
    assert body["temperature"] == 0.2


def test_speech_to_slide_keeps_digits_for_spoken_numerals():
    payload = {"kind": "big_number", "title": "Отчёт готов к 8:30", "key_message": "", "items": []}
    client = _client_returning(payload)
    intent = speech_to_slide("Отчёт стал готов к восьми тридцати", [SlideKind.big_number], client)

    assert "8:30" in intent.title
