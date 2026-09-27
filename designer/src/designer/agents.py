"""Агенты: CLI через мост на хосте (llm/bridge.py) и локальные модели LM Studio (llm/client.py)
под одним списком и одним назначением на задачу. Поток 2 карты приложения версии 2
(docs/design/app-v2-contract.md, docs/model.md, раздел «Агенты и модели»)."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

from designer import store
from designer.llm.bridge import BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL, BridgeClient
from designer.llm.client import LlmClient, LlmResponseError, ModelLoading, auth_headers
from designer.settings import SAVED_MODELS_REL, load_settings, read_saved_models
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
        model = cli_model(name)
        response = _bridge_post(f"/agents/{name}/check", {"model": model} if model else {}, timeout=35.0)
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
        return BridgeClient(agent=name, model=cli_model(name))
    settings = load_settings()
    return LlmClient(settings.llm_url, name or settings.llm_model)


# ---------- адрес сервера и модели с экрана настроек ----------

def _saved() -> dict:
    return read_saved_models(data_dir())


def cli_model(agent: str) -> str | None:
    """Модель CLI-агента, заданная на экране настроек; None значит модель по умолчанию у самого CLI."""
    return (_saved().get("cli_models") or {}).get(agent) or None


def _in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _container_url(url: str) -> str:
    """Браузер и человек видят сервер модели на 127.0.0.1, контейнер ходит к хосту через host.docker.internal."""
    if not _in_docker():
        return url
    return re.sub(r"//(localhost|127\.0\.0\.1)([:/]|$)", r"//host.docker.internal\2", url)


def _shown_url(url: str) -> str:
    return url.replace("//host.docker.internal", "//127.0.0.1")


def server_kind(llm_url: str) -> str:
    """ollama | lmstudio | api: Ollama отвечает на /api/version, LM Studio по умолчанию слушает порт 1234."""
    base = re.sub(r"/v1/?$", "", llm_url.rstrip("/"))
    try:
        response = httpx.Client(timeout=2.0).get(f"{base}/api/version")
        if response.status_code == 200 and "version" in response.json():
            return "ollama"
    except (httpx.HTTPError, ValueError):
        pass
    return "lmstudio" if ":1234" in llm_url else "api"


def load_model_settings() -> dict:
    settings = load_settings()
    saved = _saved()
    return {
        "llm_url": saved.get("llm_url_shown") or _shown_url(settings.llm_url),
        "llm_model": settings.llm_model,
        "server": server_kind(settings.llm_url),
        "cli_models": saved.get("cli_models") or {},
    }


def save_model_settings(payload: dict) -> dict:
    """Сохраняет адрес сервера, модель и модели CLI. Новая модель забирает задачи, назначенные локальной модели."""
    saved = _saved()
    url = (payload.get("llm_url") or "").strip().rstrip("/")
    if url:
        if not re.match(r"^https?://[^\s/]+", url):
            raise ValueError("адрес сервера модели начинается с http:// или https://")
        saved["llm_url_shown"] = url
        saved["llm_url"] = _container_url(url)
    model = (payload.get("llm_model") or "").strip()
    if model:
        saved["llm_model"] = model
        assignments = load_assignments()
        save_assignments({task: f"local:{model}" for task, agent in assignments.items() if agent.startswith("local:")})
    for agent, value in (payload.get("cli_models") or {}).items():
        models = saved.setdefault("cli_models", {})
        if value and value.strip():
            models[agent] = value.strip()
        else:
            models.pop(agent, None)
    path = data_dir() / SAVED_MODELS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    store.write_text_atomic(path, json.dumps(saved, ensure_ascii=False, indent=2))
    return load_model_settings()
