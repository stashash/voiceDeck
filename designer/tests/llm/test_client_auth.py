"""Ключ уходит в Authorization только на адрес, к которому выдан; ключ VK идёт вместе с Project-ID."""
import json

import httpx
import pytest

from designer.llm.client import VK_INFERENCE_URL, LlmClient, auth_headers


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("DESIGNER_LLM_API_KEY", "DESIGNER_LLM_URL", "VK_API_KEY", "VK_PROJECT_ID", "VK_INFERENCE_URL"):
        monkeypatch.delenv(name, raising=False)


def _capture(base_url: str) -> dict:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["project"] = request.headers.get("Project-ID")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"ok": True})}}]})

    client = LlmClient(base_url, "model", transport=httpx.MockTransport(handler))
    try:
        client.complete_json(system="s", user="u", schema={"type": "object"})
    finally:
        client.close()
    return seen


def test_api_key_goes_to_its_own_url(monkeypatch):
    monkeypatch.setenv("DESIGNER_LLM_API_KEY", "secret")
    monkeypatch.setenv("DESIGNER_LLM_URL", "http://test/v1")
    assert _capture("http://test/v1")["auth"] == "Bearer secret"


def test_no_header_without_key():
    assert _capture("http://test/v1")["auth"] is None


def test_vk_key_and_project_go_to_vk_router(monkeypatch):
    monkeypatch.setenv("VK_API_KEY", "vk-secret")
    monkeypatch.setenv("VK_PROJECT_ID", "prj-1")
    seen = _capture(VK_INFERENCE_URL)
    assert seen["auth"] == "Bearer vk-secret"
    assert seen["project"] == "prj-1"
    assert seen["url"] == VK_INFERENCE_URL + "/chat/completions"


@pytest.mark.parametrize("url", [
    "https://evil.example/v1",
    "http://ai-demo.platformpreview.ru/api/inference-providers-router/00000000-0000-0000-0000-000000000001/v1",
    "https://ai-demo.platformpreview.ru:8443/api/inference-providers-router/00000000-0000-0000-0000-000000000001/v1",
    "https://ai-demo.platformpreview.ru/api/inference-providers-router/other-router/v1",
    "https://ai-demo.platformpreview.ru.evil.example/api/inference-providers-router/00000000-0000-0000-0000-000000000001/v1",
    "http://127.0.0.1:1234/v1",
])
def test_vk_key_never_leaves_for_other_address(monkeypatch, url):
    """Адрес модели меняется с экрана настроек: чужой адрес не получает ни ключа, ни Project-ID."""
    monkeypatch.setenv("VK_API_KEY", "vk-secret")
    monkeypatch.setenv("VK_PROJECT_ID", "prj-1")
    assert auth_headers(url) == {}


def test_legacy_key_is_not_sent_to_address_saved_in_app(monkeypatch):
    monkeypatch.setenv("DESIGNER_LLM_API_KEY", "secret")
    monkeypatch.setenv("DESIGNER_LLM_URL", "https://provider.example/v1")
    assert auth_headers("https://attacker.example/v1") == {}
    assert auth_headers("https://provider.example") == {"Authorization": "Bearer secret"}


def test_editor_base_without_v1_matches_vk_router(monkeypatch):
    """Правка голосом хранит адрес без /v1 и сама дописывает /v1/chat/completions."""
    monkeypatch.setenv("VK_API_KEY", "vk-secret")
    assert auth_headers(VK_INFERENCE_URL.removesuffix("/v1"))["Authorization"] == "Bearer vk-secret"
