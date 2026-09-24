"""Ключ внешнего OpenAI-совместимого API уходит в заголовке Authorization; без ключа заголовка нет."""
import json

import httpx

from designer.llm.client import LlmClient


def _capture(monkeypatch, key: str | None) -> dict:
    if key is None:
        monkeypatch.delenv("DESIGNER_LLM_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DESIGNER_LLM_API_KEY", key)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"ok": True})}}]})

    client = LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))
    client.complete_json(system="s", user="u", schema={"type": "object"})
    return seen


def test_api_key_goes_to_authorization_header(monkeypatch):
    assert _capture(monkeypatch, "secret")["auth"] == "Bearer secret"


def test_no_header_without_key(monkeypatch):
    assert _capture(monkeypatch, None)["auth"] is None
