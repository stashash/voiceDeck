"""Клиент OpenAI-совместимого сервера с ответом по JSON-схеме. Владелец: задача T-04."""
from __future__ import annotations

import base64
import json
import os
import re
import time

import httpx

DEFAULT_BASE_URL = os.environ.get("DESIGNER_LLM_URL", "http://127.0.0.1:1234/v1")
DEFAULT_MODEL = os.environ.get("DESIGNER_LLM_MODEL", "qwen/qwen3.8-27b")

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)
_MAX_ATTEMPTS = 3  # первая попытка плюс два повтора


class LlmResponseError(RuntimeError):
    """Сервер не дал валидный JSON по схеме за все попытки."""


class LlmClient:
    """Клиент чат-эндпоинта OpenAI-совместимого сервера со строгой JSON-схемой ответа."""

    def __init__(self, base_url: str, model: str, timeout_s: float = 120.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._client = httpx.Client(timeout=timeout_s, transport=transport)
        self.call_durations_ms: list[int] = []

    @classmethod
    def from_env(cls, timeout_s: float = 120.0, transport: httpx.BaseTransport | None = None,
                 live: bool = False) -> "LlmClient":
        """Клиент с адресом и моделью из настроек: config.yaml, поверх него переменные окружения.

        live=True берёт модель живого режима (DESIGNER_LIVE_LLM_*), когда она задана: для слайда
        из речи нужна быстрая модель, для колоды точная.
        """
        from designer.settings import SettingsError, load_settings

        try:
            settings = load_settings()
        except SettingsError as error:
            print(f"настройки не прочитаны, взяты значения по умолчанию: {error}", flush=True)
            return cls(DEFAULT_BASE_URL, DEFAULT_MODEL, timeout_s=timeout_s, transport=transport)
        url, model = settings.llm_url, settings.llm_model
        if live:
            url = settings.live_llm_url or url
            model = settings.live_llm_model or model
        return cls(url, model, timeout_s=timeout_s, transport=transport)

    def close(self) -> None:
        self._client.close()

    def complete_json(self, system: str, user: str, schema: dict, images_png: list[bytes] | None = None,
                      params: dict | None = None) -> dict:
        """params это параметры запроса из skill.yaml: temperature, max_tokens, reasoning_effort и другие."""
        payload = self._build_payload(system, user, schema, images_png)
        payload.update(params or {})
        errors: list[str] = []
        for _ in range(_MAX_ATTEMPTS):
            content = self._call(payload)
            cleaned = _strip_think(content)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                errors.append(f"битый JSON: {exc}")
                continue
            defs = schema.get("$defs", {})
            if not _matches_schema(data, schema, defs):
                errors.append("ответ не по схеме")
                continue
            return data
        raise LlmResponseError(f"сервер не дал валидный ответ за {_MAX_ATTEMPTS} попытки: {'; '.join(errors)}")

    def _build_payload(self, system: str, user: str, schema: dict, images_png: list[bytes] | None) -> dict:
        if images_png:
            user_content: object = [{"type": "text", "text": user}]
            for png in images_png:
                data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                user_content.append({"type": "image_url", "image_url": {"url": data_url}})
        else:
            user_content = user
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema, "strict": True},
            },
        }

    def _call(self, payload: dict) -> str:
        started = time.monotonic()
        response = self._client.post(f"{self.base_url}/chat/completions", json=payload)
        response.raise_for_status()
        self.call_durations_ms.append(int((time.monotonic() - started) * 1000))
        body = response.json()
        return body["choices"][0]["message"]["content"]


def _strip_think(text: str) -> str:
    return _THINK_BLOCK.sub("", text).strip()


def _matches_schema(instance: object, schema: dict, defs: dict) -> bool:
    """Лёгкая проверка ответа по JSON-схеме: без внешних зависимостей, покрывает схемы pydantic."""
    if "$ref" in schema:
        target = defs.get(schema["$ref"].rsplit("/", 1)[-1])
        return target is not None and _matches_schema(instance, target, defs)
    if "anyOf" in schema:
        return any(_matches_schema(instance, option, defs) for option in schema["anyOf"])
    if "allOf" in schema:
        return all(_matches_schema(instance, option, defs) for option in schema["allOf"])
    if "enum" in schema:
        return instance in schema["enum"]

    kind = schema.get("type")
    if kind == "object":
        if not isinstance(instance, dict):
            return False
        if any(key not in instance for key in schema.get("required", [])):
            return False
        props = schema.get("properties", {})
        return all(
            _matches_schema(value, props[key], defs)
            for key, value in instance.items() if key in props
        )
    if kind == "array":
        if not isinstance(instance, list):
            return False
        item_schema = schema.get("items")
        return item_schema is None or all(_matches_schema(v, item_schema, defs) for v in instance)
    if kind == "string":
        return isinstance(instance, str)
    if kind == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if kind == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if kind == "boolean":
        return isinstance(instance, bool)
    if kind == "null":
        return instance is None
    return True
