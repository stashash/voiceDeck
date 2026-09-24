"""Тесты designer.agents: список агентов (мост + локальные модели), назначения задач,
выбор клиента по назначению. Мост и LM Studio подменены монкипатчем — сетевые запросы
здесь не нужны, они уже проверены в test_agent_bridge.py и test_bridge_client.py."""
import json

import httpx
import pytest

import designer.agents as agents
from designer.llm.bridge import BridgeClient
from designer.llm.client import LlmClient


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DESIGNER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("DESIGNER_CONFIG", raising=False)
    monkeypatch.setenv("DESIGNER_LLM_URL", "http://llm.local/v1")
    monkeypatch.setenv("DESIGNER_LLM_MODEL", "qwen/qwen3.8-27b")
    return tmp_path


def _response(status: int, **json_body) -> httpx.Response:
    request = httpx.Request("GET", "http://bridge/agents")
    return httpx.Response(status, json=json_body, request=request)


def test_list_agents_merges_bridge_cli_and_local_models(monkeypatch):
    def fake_bridge_get(path, timeout):
        assert path == "/agents"
        return _response(200, items=[
            {"id": "claude", "name": "Claude Code", "version": "2.1.270", "found": True, "path": "/x/claude"},
            {"id": "codex", "name": "Codex", "version": None, "found": False, "path": None},
        ])

    monkeypatch.setattr(agents, "_bridge_get", fake_bridge_get)
    monkeypatch.setattr(agents, "_local_models", lambda llm_url: ["qwen/qwen3.8-27b"])

    result = agents.list_agents()

    ids = {item["id"] for item in result["items"]}
    assert ids == {"cli:claude", "cli:codex", "local:qwen/qwen3.8-27b"}
    assert "bridge_error" not in result
    claude = next(item for item in result["items"] if item["id"] == "cli:claude")
    assert claude == {"id": "cli:claude", "kind": "cli", "name": "Claude Code", "detail": "2.1.270",
                       "found": True, "model": None}


def test_list_agents_reports_bridge_error_and_keeps_local_models(monkeypatch):
    def fake_bridge_get(path, timeout):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", "http://bridge/agents"))

    monkeypatch.setattr(agents, "_bridge_get", fake_bridge_get)
    monkeypatch.setattr(agents, "_local_models", lambda llm_url: ["qwen/qwen3.8-27b"])

    result = agents.list_agents()

    assert result["items"] == [{"id": "local:qwen/qwen3.8-27b", "kind": "local", "name": "qwen/qwen3.8-27b",
                                 "detail": "http://llm.local/v1", "found": True, "model": "qwen/qwen3.8-27b"}]
    assert "не ответил" not in result["bridge_error"]  # причина ошибки, а не выдумка
    assert "connection" in result["bridge_error"].lower() or "connect" in result["bridge_error"].lower()


def test_local_models_filters_out_embedding_models(monkeypatch):
    def fake_get(self, url, **kwargs):
        assert url == "http://llm.local/v1/models"
        return httpx.Response(200, json={"data": [
            {"id": "qwen/qwen3.8-27b"}, {"id": "text-embedding-bge-m3"}, {"id": "nomic-embed-text"},
        ]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    assert agents._local_models("http://llm.local/v1") == ["qwen/qwen3.8-27b"]


def test_check_agent_cli_proxies_bridge_response(monkeypatch):
    def fake_bridge_post(path, body, timeout):
        assert path == "/agents/opencode/check"
        return httpx.Response(200, json={"ok": True, "images": True, "seconds": 2.1, "message": "STUB ответ: OK"})

    monkeypatch.setattr(agents, "_bridge_post", fake_bridge_post)
    assert agents.check_agent("cli:opencode") == {"ok": True, "images": True, "seconds": 2.1,
                                                    "message": "STUB ответ: OK"}


def test_check_agent_cli_reports_bridge_down(monkeypatch):
    def fake_bridge_post(path, body, timeout):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", "http://bridge/x"))

    monkeypatch.setattr(agents, "_bridge_post", fake_bridge_post)
    result = agents.check_agent("cli:claude")
    assert result["ok"] is False
    assert result["images"] is None
    assert "мост недоступен" in result["message"]


def test_check_agent_local_calls_llm_client(monkeypatch):
    def fake_complete_json(self, system, user, schema, images_png=None, params=None):
        return {"ok": True}

    monkeypatch.setattr(LlmClient, "complete_json", fake_complete_json)
    result = agents.check_agent("local:qwen/qwen3.8-27b")
    assert result["ok"] is True
    assert result["images"] is None


def test_load_assignments_defaults_to_local_settings_model():
    assert agents.load_assignments() == {
        "deck": "local:qwen/qwen3.8-27b",
        "live": "local:qwen/qwen3.8-27b",
        "describe": "local:qwen/qwen3.8-27b",
    }


def test_save_assignments_persists_and_merges_partial_update(data_dir):
    agents.save_assignments({"deck": "cli:claude"})
    second = agents.save_assignments({"live": "cli:opencode"})

    assert second == {"deck": "cli:claude", "live": "cli:opencode", "describe": "local:qwen/qwen3.8-27b"}
    on_disk = json.loads((data_dir / "data" / "settings" / "agents.json").read_text(encoding="utf-8"))
    assert on_disk == second
    assert agents.load_assignments() == second


def test_save_assignments_ignores_unknown_keys():
    result = agents.save_assignments({"deck": "cli:claude", "bogus": "whatever"})
    assert "bogus" not in result


def test_client_for_cli_returns_bridge_client():
    agents.save_assignments({"deck": "cli:codex"})
    client = agents.client_for("deck")
    assert isinstance(client, BridgeClient)
    assert client.agent == "codex"
    client.close()


def test_client_for_local_returns_llm_client_with_chosen_model():
    agents.save_assignments({"live": "local:qwen/qwen3.8-27b"})
    client = agents.client_for("live")
    assert isinstance(client, LlmClient)
    assert client.model == "qwen/qwen3.8-27b"
    assert client.base_url == "http://llm.local/v1"
    client.close()


def test_client_for_unknown_task_raises():
    with pytest.raises(ValueError):
        agents.client_for("bogus")
