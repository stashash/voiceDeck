"""Клиент моста агентов (scripts/agent_bridge.py): CLI-агент на хосте вместо OpenAI-совместимого
сервера. Тот же интерфейс, что у llm.client.LlmClient, поэтому designer.agents.client_for может
отдавать любой из двух не глядя на то, кто вызывает."""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

BRIDGE_URL_ENV = "DESIGNER_AGENT_BRIDGE_URL"
DEFAULT_BRIDGE_URL = "http://host.docker.internal:8095"

_MAX_ATTEMPTS = 2  # первая попытка плюс один повтор на битый ответ
_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.S)


class LlmResponseError(RuntimeError):
    """Агент через мост не дал валидный JSON по схеме за все попытки."""


def _default_bridge_url() -> str:
    return os.environ.get(BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL)


class BridgeClient:
    """Клиент CLI-агента через мост на хосте. complete_json просит агента вернуть только JSON
    по схеме и вычленяет его из ответа (агент почти всегда добавляет пояснения или код-блок)."""

    def __init__(self, agent: str, model: str | None = None, bridge_url: str | None = None,
                 timeout_s: float = 180.0, transport: httpx.BaseTransport | None = None):
        self.agent = agent
        self._requested_model = model  # None значит «своя модель по умолчанию у самого CLI»
        self.model = model or f"cli:{agent}"  # для журнала прогона, как LlmClient.model
        self.bridge_url = (bridge_url or _default_bridge_url()).rstrip("/")
        self.timeout_s = timeout_s
        self._client = httpx.Client(timeout=timeout_s, transport=transport)
        self.call_durations_ms: list[int] = []

    def close(self) -> None:
        self._client.close()

    def complete_json(self, system: str, user: str, schema: dict, images_png: list[bytes] | None = None) -> dict:
        full_system = _with_schema_instruction(system, schema)
        errors: list[str] = []
        for _ in range(_MAX_ATTEMPTS):
            text, seconds = self._complete(full_system, user, images_png)
            self.call_durations_ms.append(int(seconds * 1000))
            extracted = _extract_json(text)
            if extracted is None:
                errors.append("в ответе нет JSON")
                continue
            try:
                return json.loads(extracted)
            except json.JSONDecodeError as exc:
                errors.append(f"битый JSON: {exc}")
                continue
        raise LlmResponseError(f"агент {self.agent} не дал JSON по схеме за {_MAX_ATTEMPTS} попытки: "
                                f"{'; '.join(errors)}")

    def _complete(self, system: str, user: str, images_png: list[bytes] | None) -> tuple[str, float]:
        payload: dict = {"system": system, "user": user}
        if self._requested_model:
            payload["model"] = self._requested_model
        if images_png:
            payload["images_png_b64"] = [base64.b64encode(png).decode("ascii") for png in images_png]
        response = self._client.post(f"{self.bridge_url}/agents/{self.agent}/complete", json=payload)
        if response.status_code >= 400:
            raise LlmResponseError(f"мост {self.bridge_url} вернул ошибку для {self.agent}: "
                                    f"{_error_detail(response)}")
        body = response.json()
        return body["text"], float(body.get("seconds", 0.0))


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        return str(body.get("error", body))
    except ValueError:
        return response.text[:300]


def _with_schema_instruction(system: str, schema: dict) -> str:
    instruction = ("Ответь только одним JSON-документом по этой JSON-схеме, без пояснений до или "
                    "после и без блока в тройных кавычках:\n" + json.dumps(schema, ensure_ascii=False))
    return f"{system}\n\n{instruction}" if system else instruction


def _extract_json(text: str) -> str | None:
    """Ищет JSON-объект в ответе: сперва в блоке ```json ... ```, иначе по совпадающим фигурным
    скобкам верхнего уровня в самом тексте (агенты часто добавляют пояснение вокруг JSON)."""
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return candidate[start:index + 1]
    return None
