"""Проверка инференса VK перед переводом сервиса на него: одна команда, ответ по пунктам.

Запуск из корня репозитория: python scripts/vk_inference_check.py
Ключ и Project-ID читаются из .env (VK_API_KEY, VK_PROJECT_ID) или окружения и не печатаются.

Что проверяет, по порядку: простой ответ и скорость; ответ строго по JSON-схеме (response_format
json_schema, им пользуются все скиллы designer); выключение рассуждения (reasoning_effort: none);
картинку в сообщении (аудит слайда по картинке); четыре запроса одновременно (DESIGNER_LLM_PARALLEL).
"""
from __future__ import annotations

import base64
import json
import os
import struct
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

DEFAULT_URL = ("https://ai-demo.platformpreview.ru/api/inference-providers-router/"
               "00000000-0000-0000-0000-000000000001/v1")
MODEL = os.environ.get("VK_MODEL", "qwen38-27b-fp8")


def read_env() -> dict[str, str]:
    values = dict(os.environ)
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values.setdefault(key.strip(), value.strip())
    return values


def png_with_square(color: tuple[int, int, int]) -> bytes:
    """PNG 64×64 одним цветом: модель должна назвать цвет."""
    width = height = 64
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    env = read_env()
    key, project = env.get("VK_API_KEY", ""), env.get("VK_PROJECT_ID", "")
    base = (env.get("VK_INFERENCE_URL") or DEFAULT_URL).rstrip("/")
    if not key or not project:
        print("VK_API_KEY или VK_PROJECT_ID пусты: впишите их в .env")
        return 2
    client = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {key}", "Project-ID": project})

    def ask(messages, **extra) -> tuple[int, dict | str, float]:
        started = time.monotonic()
        response = client.post(f"{base}/chat/completions", json={"model": MODEL, "messages": messages, **extra})
        elapsed = time.monotonic() - started
        try:
            return response.status_code, response.json(), elapsed
        except ValueError:
            return response.status_code, response.text[:300], elapsed

    def content(body) -> str:
        if isinstance(body, dict) and body.get("choices"):
            return body["choices"][0]["message"].get("content") or ""
        return json.dumps(body, ensure_ascii=False)[:300] if isinstance(body, dict) else str(body)

    results: list[tuple[str, bool, str]] = []

    status, body, elapsed = ask([{"role": "user", "content": "Ответь одним словом: столица России?"}], max_tokens=50)
    results.append(("простой ответ", status == 200, f"HTTP {status}, {elapsed:.1f} с, «{content(body)[:80]}»"))
    if status != 200:
        for name, ok, note in results:
            print(f"{'OK  ' if ok else 'FAIL'} {name}: {note}")
        return 1

    status, body, elapsed = ask(
        [{"role": "user", "content": "Напиши связный абзац из 250 слов о том, как готовить отчёт за квартал."}],
        max_tokens=600, temperature=0.3)
    usage = body.get("usage", {}) if isinstance(body, dict) else {}
    tokens = usage.get("completion_tokens") or 0
    results.append(("скорость", status == 200 and tokens > 0,
                    f"{tokens} токенов за {elapsed:.1f} с, {tokens / elapsed:.0f} токенов/с" if tokens else f"HTTP {status}, usage нет"))

    schema = {"type": "object", "additionalProperties": False, "required": ["title", "bullets"],
              "properties": {"title": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}}
    status, body, elapsed = ask(
        [{"role": "system", "content": "Верни только JSON по схеме."},
         {"role": "user", "content": "Слайд про итоги квартала: выручка выросла на 18 %."}],
        max_tokens=400, temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "slide", "strict": True, "schema": schema}})
    try:
        parsed = json.loads(content(body))
        ok = status == 200 and set(parsed) == {"title", "bullets"}
    except ValueError:
        ok = False
    results.append(("JSON по схеме", ok, f"HTTP {status}, {elapsed:.1f} с, «{content(body)[:100]}»"))

    status, body, elapsed = ask([{"role": "user", "content": "Сколько будет 17*23? Только число."}],
                                max_tokens=200, reasoning_effort="none")
    text = content(body)
    reasoning = body["choices"][0]["message"].get("reasoning_content") if isinstance(body, dict) and status == 200 else None
    results.append(("reasoning_effort: none", status == 200 and "<think>" not in text and not reasoning,
                    f"HTTP {status}, {elapsed:.1f} с, ответ «{text[:40]}», рассуждение {'есть' if reasoning or '<think>' in text else 'нет'}"))

    image = "data:image/png;base64," + base64.b64encode(png_with_square((220, 30, 30))).decode()
    status, body, elapsed = ask([{"role": "user", "content": [
        {"type": "text", "text": "Какого цвета квадрат? Одно слово по-русски."},
        {"type": "image_url", "image_url": {"url": image}}]}], max_tokens=50)
    answer = content(body).lower()
    results.append(("картинка в запросе", status == 200 and "красн" in answer, f"HTTP {status}, {elapsed:.1f} с, «{answer[:60]}»"))

    started = time.monotonic()
    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(lambda i: ask([{"role": "user", "content": f"Назови число {i}."}], max_tokens=20)[0], range(4)))
    results.append(("4 запроса одновременно", all(c == 200 for c in codes),
                    f"коды {codes}, {time.monotonic() - started:.1f} с на все"))

    for name, ok, note in results:
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {note}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
