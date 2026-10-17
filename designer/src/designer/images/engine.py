"""Клиент ComfyUI: граф text-to-image из файла скилла, подстановка описания и размера, ответ PNG.

Граф лежит в `skills/illustrate/graph.json`, а не в коде: модель меняется правкой файла. По умолчанию это
FLUX.2 klein 4B (Apache 2.0) с кодировщиком текста Qwen3-4B (Apache 2.0), всего около 8B параметров.
Адрес сервера задаёт DESIGNER_IMAGE_URL; пустой адрес выключает картинки, колода собирается без них.
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from pathlib import Path

import httpx

from designer.llm.skills import _SKILLS_ROOT

GRAPH_PATH = "illustrate/graph.json"
TARGET_PIXELS = 1024 * 1024
STEP = 16
POLL_S = 0.5


class ImageEngineError(RuntimeError):
    """Сервер картинок не ответил или не вернул картинку."""


def image_size(aspect: float, pixels: int = TARGET_PIXELS) -> tuple[int, int]:
    """Ширина и высота около мегапикселя с заданным соотношением сторон, кратные 16."""
    aspect = min(max(aspect, 0.25), 4.0)
    width = math.sqrt(pixels * aspect)
    return int(round(width / STEP)) * STEP, int(round(width / aspect / STEP)) * STEP


def _fill(node: object, values: dict[str, object]) -> object:
    """Подставляет «{{имя}}» в значения графа: строка целиком меняется на значение нужного типа."""
    if isinstance(node, dict):
        return {key: _fill(value, values) for key, value in node.items()}
    if isinstance(node, list):
        return [_fill(value, values) for value in node]
    if isinstance(node, str) and node.startswith("{{") and node.endswith("}}"):
        return values[node[2:-2]]
    return node


class ComfyEngine:
    def __init__(self, base_url: str, graph: dict, timeout_s: float = 240.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.graph = graph
        self.timeout_s = timeout_s
        self._client = httpx.Client(timeout=30.0, transport=transport)

    @classmethod
    def from_env(cls, transport: httpx.BaseTransport | None = None) -> "ComfyEngine | None":
        url = os.environ.get("DESIGNER_IMAGE_URL", "").strip()
        if not url:
            return None
        graph = json.loads((_SKILLS_ROOT / GRAPH_PATH).read_text(encoding="utf-8"))
        return cls(url, graph, transport=transport)

    def close(self) -> None:
        self._client.close()

    def available(self) -> bool:
        try:
            return self._client.get(f"{self.base_url}/system_stats", timeout=3.0).status_code == 200
        except httpx.HTTPError:
            return False

    def generate(self, prompt: str, width: int, height: int, seed: int) -> bytes:
        graph = _fill(self.graph, {"prompt": prompt, "width": width, "height": height, "seed": seed})
        try:
            response = self._client.post(f"{self.base_url}/prompt",
                                         json={"prompt": graph, "client_id": uuid.uuid4().hex})
            response.raise_for_status()
            prompt_id = response.json()["prompt_id"]
            deadline = time.monotonic() + self.timeout_s
            while time.monotonic() < deadline:
                history = self._client.get(f"{self.base_url}/history/{prompt_id}").json().get(prompt_id)
                if history:
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise ImageEngineError(f"граф не выполнился: {json.dumps(status.get('messages', []))[:300]}")
                    for output in history.get("outputs", {}).values():
                        for image in output.get("images", []):
                            view = self._client.get(f"{self.base_url}/view", params={
                                "filename": image["filename"], "subfolder": image.get("subfolder", ""),
                                "type": image.get("type", "output")})
                            view.raise_for_status()
                            return view.content
                    if status.get("completed"):
                        raise ImageEngineError("граф выполнился, но картинки нет")
                time.sleep(POLL_S)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ImageEngineError(f"сервер картинок {self.base_url}: {exc}") from exc
        raise ImageEngineError(f"картинка не готова за {self.timeout_s:.0f} с")
