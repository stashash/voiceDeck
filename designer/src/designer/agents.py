"""Агенты: CLI через мост на хосте (llm/bridge.py) и локальные модели LM Studio (llm/client.py)
под одним списком и одним назначением на задачу. Поток 2 карты приложения версии 2
(docs/design/app-v2-contract.md, docs/model.md, раздел «Агенты и модели»)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from designer import store
from designer.llm.bridge import BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL, BridgeClient
from designer.llm.client import LlmClient, LlmResponseError, ModelLoading, auth_headers
from designer.settings import load_settings
from designer.store import data_dir

_TASKS = ("deck", "live", "describe")
_OK_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def bridge_url() -> str:
    return os.environ.get(BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL).rstrip("/")


def _bridge_get(path: str, timeout: float) -> httpx.Response:
    with httpx.Client(timeout=timeout) as client:
        return client.get(f"{bridge_url()}{path}")


def _bridge_post(path: str, body: dict, timeout: float) -> httpx.Response:
    with httpx.Client(timeout=timeout) as client:
        return client.post(f"{bridge_url()}{path}", json=body)


def _bridge_error_message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", response.text))
    except ValueError:
        return response.text[:300]


def _local_models(llm_url: str) -> list[str]:
    try:
        response = httpx.Client(timeout=5.0, headers=auth_headers()).get(f"{llm_url.rstrip('/')}/models")
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    names = [str(row.get("id", "")) for row in response.json().get("data", [])]
    return [name for name in names if name and "embed" not in name.lower()]


def list_agents() -> dict:
    """CLI из моста плюс локальные модели LM Studio, одним списком выбора для настроек."""
    items: list[dict] = []
    bridge_error: str | None = None
    try:
        response = _bridge_get("/agents", timeout=5.0)
        response.raise_for_status()
        for item in response.json().get("items", []):
            found = bool(item.get("found"))
            items.append({
                "id": f"cli:{item['id']}",
                "kind": "cli",
                "name": item.get("name", item["id"]),
                "detail": item.get("version") or ("найден в PATH" if found else "не найден в PATH"),
                "found": found,
                "model": None,
            })
    except httpx.HTTPError as error:
        bridge_error = f"мост агентов недоступен на {bridge_url()}: {error}"

    settings = load_settings()
    for model in _local_models(settings.llm_url):
        items.append({
            "id": f"local:{model}",
            "kind": "local",
            "name": model,
            "detail": settings.llm_url,
            "found": True,
            "model": model,
        })

    result: dict = {"items": items}
    if bridge_error is not None:
        result["bridge_error"] = bridge_error
    return result


def check_agent(agent_id: str) -> dict:
    """{ok, images, seconds, message}: короткая проверка связи с агентом."""
    kind, _, name = agent_id.partition(":")
    if kind != "cli":
        return _check_local(name)
    try:
        response = _bridge_post(f"/agents/{name}/check", {}, timeout=35.0)
    except httpx.HTTPError as error:
        return {"ok": False, "images": None, "seconds": 0.0, "message": f"мост недоступен: {error}"}
    if response.status_code >= 400:
        return {"ok": False, "images": None, "seconds": 0.0, "message": _bridge_error_message(response)}
    return response.json()


def _check_local(model: str) -> dict:
    settings = load_settings()
    client = LlmClient(settings.llm_url, model, timeout_s=30.0, load_wait_s=0.0)
    started = time.monotonic()
    try:
        data = client.complete_json("Отвечай только запрошенным JSON.", 'Ответь {"ok": true}.', _OK_SCHEMA)
        ok = bool(data.get("ok"))
        message = "модель ответила" if ok else "модель ответила, но не тем, что просили"
    except (ModelLoading, LlmResponseError, httpx.HTTPError) as error:
        ok = False
        message = str(error)
    finally:
        client.close()
    return {"ok": ok, "images": None, "seconds": round(time.monotonic() - started, 3), "message": message}


def _assignments_path() -> Path:
    path = data_dir() / "settings" / "agents.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_assignments() -> dict:
    default_id = f"local:{load_settings().llm_model}"
    return {task: default_id for task in _TASKS}


def load_assignments() -> dict:
    path = _assignments_path()
    defaults = _default_assignments()
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return defaults
    defaults.update({task: raw[task] for task in _TASKS if task in raw})
    return defaults


def save_assignments(data: dict) -> dict:
    current = load_assignments()
    current.update({task: data[task] for task in _TASKS if task in data})
    store.write_text_atomic(_assignments_path(), json.dumps(current, ensure_ascii=False, indent=2))
    return current


def client_for(task: str):
    """Клиент модели для задачи ('deck' | 'live' | 'describe'): BridgeClient для cli:, LlmClient
    для local:. Единственное место, откуда конвейер и правка берут клиент модели."""
    if task not in _TASKS:
        raise ValueError(f"неизвестная задача агента: {task!r}")
    agent_id = load_assignments()[task]
    kind, _, name = agent_id.partition(":")
    if kind == "cli":
        return BridgeClient(agent=name)
    settings = load_settings()
    return LlmClient(settings.llm_url, name or settings.llm_model)
