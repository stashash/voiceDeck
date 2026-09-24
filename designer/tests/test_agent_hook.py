"""Тесты agent_hook: запасное поведение, пока designer.agents (поток 2) не существует.

Задача T-13, поток 1. Прямой импорт designer.agents в этой ветке всегда падает ImportError —
модуль появится только когда поток 2 положит designer/src/designer/agents.py.
"""
from __future__ import annotations

import pytest

from designer import agent_hook, store
from designer.llm.client import LlmClient


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))


def test_client_for_falls_back_to_llm_client_from_env():
    client = agent_hook._client_for("deck")
    assert isinstance(client, LlmClient)
    client.close()


def test_client_for_live_uses_live_flag(monkeypatch):
    seen = {}

    def fake_from_env(live=False, **kwargs):
        seen["live"] = live
        return LlmClient("http://test/v1", "model")

    monkeypatch.setattr(LlmClient, "from_env", fake_from_env)
    agent_hook._client_for("live").close()
    assert seen["live"] is True


def test_list_agents_is_empty_without_module():
    assert agent_hook.list_agents() == {"items": []}


def test_check_agent_raises_without_module():
    with pytest.raises(agent_hook.AgentCheckUnavailable):
        agent_hook.check_agent("cli:claude")


def test_default_assignments_use_local_model(monkeypatch):
    monkeypatch.setenv("DESIGNER_LLM_MODEL", "qwen/qwen3.8-27b")
    assignments = agent_hook.load_assignments()
    assert assignments == {
        "deck": "local:qwen/qwen3.8-27b",
        "live": "local:qwen/qwen3.8-27b",
        "describe": "local:qwen/qwen3.8-27b",
    }


def test_save_assignments_merges_and_persists():
    agent_hook.save_assignments({"deck": "cli:claude"})
    first = agent_hook.load_assignments()
    assert first["deck"] == "cli:claude"

    agent_hook.save_assignments({"live": "cli:codex"})
    second = agent_hook.load_assignments()
    assert second["deck"] == "cli:claude"  # предыдущее значение не потеряно
    assert second["live"] == "cli:codex"

    on_disk = store.data_dir() / "settings" / "agents.json"
    assert on_disk.is_file()
