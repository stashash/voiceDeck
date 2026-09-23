"""Тесты LlmClient: схема и текст в запросе, обрезка <think>, повтор на битом JSON, картинка как data URL."""
import base64
import json

import httpx
import pytest

from designer.llm.client import LlmClient, LlmResponseError

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def _ok_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_request_has_schema_and_prompt_text():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok_response(json.dumps({"ok": True}))

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    client.complete_json(system="системный текст", user="текст брифа", schema=SCHEMA)

    body = captured["body"]
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][0] == {"role": "system", "content": "системный текст"}
    assert body["messages"][1] == {"role": "user", "content": "текст брифа"}


def test_think_block_is_stripped_before_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response("<think>рассуждаю долго</think>" + json.dumps({"ok": True}))

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    data = client.complete_json(system="s", user="u", schema=SCHEMA)
    assert data == {"ok": True}


def test_retries_on_broken_json_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return _ok_response("это не json")
        return _ok_response(json.dumps({"ok": True}))

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    data = client.complete_json(system="s", user="u", schema=SCHEMA)
    assert data == {"ok": True}
    assert calls["n"] == 2


def test_gives_up_after_two_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok_response("это не json")

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    with pytest.raises(LlmResponseError):
        client.complete_json(system="s", user="u", schema=SCHEMA)
    assert calls["n"] == 3


def test_image_is_sent_as_data_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok_response(json.dumps({"ok": True}))

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    png_bytes = b"\x89PNG\r\n\x1a\nfake-image-bytes"
    client.complete_json(system="s", user="u", schema=SCHEMA, images_png=[png_bytes])

    content = captured["body"]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "u"}
    expected_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    assert content[1] == {"type": "image_url", "image_url": {"url": expected_url}}


def test_waits_while_the_model_loads(monkeypatch):
    monkeypatch.setattr("designer.llm.client._LOAD_POLL_S", 0)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(400, json={"error": 'Failed to load model "m". Error: Operation canceled.'})
        return _ok_response('{"title": "готово"}')

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler), load_wait_s=30)
    schema = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
    assert client.complete_json("s", "u", schema) == {"title": "готово"}
    assert calls["n"] == 3


def test_model_that_never_loads_is_reported():
    import pytest
    from designer.llm.client import ModelLoading

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": 'Failed to load model "m".'})

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler), load_wait_s=0)
    with pytest.raises(ModelLoading):
        client.complete_json("s", "u", {"type": "object"})
