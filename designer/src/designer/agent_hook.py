"""Клиент модели через агентов потока 2, с запасным поведением, пока модуля нет.

designer.agents (мост на хосте и выбор агента) — задача потока 2, в этой ветке его ещё нет.
app.py и pipeline.py не проверяют его наличие сами: они зовут функции этого файла, а здесь
и только здесь лежит try/except ImportError. Когда designer.agents появится, ничего в app.py
и pipeline.py менять не придётся.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from designer import store
from designer.llm.client import DEFAULT_MODEL, LlmClient

_TASKS = ("deck", "live", "describe")
_SETTINGS_REL = Path("settings") / "agents.json"


class AgentCheckUnavailable(RuntimeError):
    """Мост агентов (поток 2) не подключён: проверить агента нечем."""


def _client_for(task: str) -> LlmClient:
    """Клиент модели для задачи "deck" | "live" | "describe".

    Пока designer.agents.client_for нет — обычный LlmClient.from_env(), как было раньше.
    """
    try:
        from designer.agents import client_for
    except ImportError:
        return LlmClient.from_env(live=(task == "live"))
    return client_for(task)


def list_agents() -> dict:
    """designer.agents.list_agents(), запасной ответ — пустой список."""
    try:
        from designer.agents import list_agents as _impl
    except ImportError:
        return {"items": []}
    return _impl()


def check_agent(agent_id: str) -> dict:
    """designer.agents.check_agent(agent_id); модуля нет — AgentCheckUnavailable (app.py даёт 503)."""
    try:
        from designer.agents import check_agent as _impl
    except ImportError as error:
        raise AgentCheckUnavailable("мост агентов не подключён: designer.agents ещё нет") from error
    return _impl(agent_id)


def _settings_path() -> Path:
    path = store.data_dir() / _SETTINGS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_assignments() -> dict:
    default = f"local:{os.environ.get('DESIGNER_LLM_MODEL', DEFAULT_MODEL)}"
    return {task: default for task in _TASKS}


def load_assignments() -> dict:
    """designer.agents.load_assignments(); запасной путь — свой файл data/settings/agents.json."""
    try:
        from designer.agents import load_assignments as _impl
    except ImportError:
        pass
    else:
        return _impl()

    path = _settings_path()
    if path.is_file():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            saved = {}
    else:
        saved = {}
    defaults = _default_assignments()
    return {task: saved.get(task) or defaults[task] for task in _TASKS}


def save_assignments(payload: dict) -> dict:
    """designer.agents.save_assignments(payload); запасной путь — пишет тот же файл сам."""
    try:
        from designer.agents import save_assignments as _impl
    except ImportError:
        pass
    else:
        return _impl(payload)

    current = load_assignments()
    for task in _TASKS:
        value = payload.get(task)
        if value:
            current[task] = value
    _settings_path().write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
