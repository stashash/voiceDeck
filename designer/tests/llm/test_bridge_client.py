"""Тесты BridgeClient: запрос к мосту, выделение JSON из ответа (в т.ч. из блока ```json),
повтор один раз на битый ответ, ошибка моста прокидывается без повтора."""
import json

import httpx
import pytest

from designer.llm.bridge import BridgeClient, LlmResponseError

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def _ok_response(text: str, seconds: float = 1.5) -> httpx.Response:
    return httpx.Response(200, json={"text": text, "seconds": seconds})


def test_request_targets_agent_path_and_omits_model_by_default():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return _ok_response(json.dumps({"ok": True}))

    client = BridgeClient("claude", bridge_url="http://bridge/", transport=httpx.MockTransport(handler))
    data = client.complete_json(system="системный текст", user="текст брифа", schema=SCHEMA)

    assert data == {"ok": True}
    assert captured["url"] == "http://bridge/agents/claude/complete"
    assert captured["body"]["user"] == "текст брифа"
    # без явной модели поле model в тело не кладём: пусть CLI выбирает свою модель по умолчанию
    # (иначе мост передаст ему --model claude, а это не название модели, а имя агента)
    assert "model" not in captured["body"]
    assert client.model == "cli:claude"
    assert "системный текст" in captured["body"]["system"]
    assert client.call_durations_ms == [1500]


def test_explicit_model_is_sent_to_the_bridge():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok_response(json.dumps({"ok": True}))

    client = BridgeClient("cursor-agent", model="sonnet-4-thinking", bridge_url="http://bridge/",
                           transport=httpx.MockTransport(handler))
    client.complete_json(system="s", user="u", schema=SCHEMA)

    assert captured["body"]["model"] == "sonnet-4-thinking"
    assert client.model == "sonnet-4-thinking"


def test_json_is_extracted_from_fenced_block_with_surrounding_text():
    def handler(request: httpx.Request) -> httpx.Response:
        text = "Конечно, вот ответ:\n```json\n" + json.dumps({"ok": True}) + "\n```\nНадеюсь, помогло."
        return _ok_response(text)

    client = BridgeClient("codex", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    assert client.complete_json("s", "u", SCHEMA) == {"ok": True}


def test_json_is_extracted_from_plain_text_with_prose_around_it():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response("Ответ: " + json.dumps({"ok": True}) + " (готово)")

    client = BridgeClient("opencode", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    assert client.complete_json("s", "u", SCHEMA) == {"ok": True}


def test_retries_once_on_missing_json_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return _ok_response("извините, не могу помочь")
        return _ok_response(json.dumps({"ok": True}))

    client = BridgeClient("claude", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    assert client.complete_json("s", "u", SCHEMA) == {"ok": True}
    assert calls["n"] == 2


def test_gives_up_after_one_retry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok_response("совсем не json")

    client = BridgeClient("claude", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    with pytest.raises(LlmResponseError):
        client.complete_json("s", "u", SCHEMA)
    assert calls["n"] == 2


def test_bridge_error_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(502, json={"error": "claude: не ответил за 30 с (таймаут)"})

    client = BridgeClient("claude", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    with pytest.raises(LlmResponseError, match="не ответил за 30"):
        client.complete_json("s", "u", SCHEMA)
    assert calls["n"] == 1


def test_images_are_sent_as_base64():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok_response(json.dumps({"ok": True}))

    client = BridgeClient("opencode", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    client.complete_json("s", "u", SCHEMA, images_png=[b"\x89PNG\r\n\x1a\nfake"])

    assert len(captured["body"]["images_png_b64"]) == 1


def test_default_bridge_url_comes_from_env(monkeypatch):
    monkeypatch.setenv("DESIGNER_AGENT_BRIDGE_URL", "http://myhost:9999")
    client = BridgeClient("claude")
    assert client.bridge_url == "http://myhost:9999"
    client.close()


def test_accepts_skill_params_like_llm_client_and_checks_schema():
    # Генерация зовёт complete_json(..., params=skill.params): клиент моста принимает их, как LlmClient.
    answers = iter(['{"title": 5}', '{"title": "План"}'])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": next(answers), "seconds": 0.1})

    client = BridgeClient("cursor-agent", bridge_url="http://bridge", transport=httpx.MockTransport(handler))
    schema = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
    assert client.complete_json("s", "u", schema, params={"temperature": 0.2}) == {"title": "План"}
