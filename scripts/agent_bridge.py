"""Мост агентов: процесс на машине пользователя, который умеет запускать CLI-агентов
(Claude Code, Codex, Cursor Agent, OpenCode) неинтерактивно и отдавать их ответ по HTTP.

Сервис designer работает в Docker и не видит CLI на хосте (см. docs/model.md, раздел
«Где запускаются CLI-агенты»), поэтому мост запускается отдельно на хосте пользователя:

    python scripts/agent_bridge.py

Слушает 127.0.0.1:8095 (доступен только с этой машины). Только стандартная библиотека —
никаких внешних зависимостей, чтобы не тянуть за собой окружение designer.

Эндпоинты (контракт: docs/design/app-v2-contract.md, поток 2):
    GET  /agents                     -> {"items": [{"id","name","version","found","path"}, ...]}
    POST /agents/{id}/check          -> {"ok","images","seconds","message"}
    POST /agents/{id}/complete       -> {"text","seconds"} или 502 {"error"}

Команды запуска взяты из `--help` каждого CLI на машине разработки (claude 2.1.270,
opencode 1.18.16, cursor-agent 2026.08.11-e8db854, все найдены в PATH через shutil.which
в сентябре 2026). Codex CLI на этой машине не установлен: команда взята из официальной
документации (см. комментарий у _codex_argv), это помечено явно.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from http.server import HTTPServer

HOST = "127.0.0.1"
PORT = 8095

_CHECK_TIMEOUT_S = 30.0
_DEFAULT_COMPLETE_TIMEOUT_S = 180.0


class AgentError(RuntimeError):
    """CLI не найден, вернул ошибку, не ответил за отведённое время, или не умеет то, что просят."""


class Agent:
    """Один CLI-агент: как его найти, умеет ли он принимать картинки и как собрать команду запуска."""

    def __init__(self, agent_id: str, name: str, images: bool, build):
        self.id = agent_id
        self.name = name
        self.images = images
        self.build = build  # (exe, system, user, model, image_paths, workdir) -> (argv, output_file|None)


def _claude_argv(exe: str, system: str, user: str, model: str | None,
                  image_paths: list[Path], workdir: Path) -> tuple[list[str], Path | None]:
    # Источник: `claude --help` (2.1.270). -p/--print — неинтерактивный вывод и выход;
    # --system-prompt — системная подсказка отдельным флагом; --tools "" отключает все инструменты:
    # агенту нужен только текстовый ответ, а в запрос попадает чужой текст (бриф, замечания), и
    # выполнять по нему команды на машине нельзя. Без инструментов вопросов о разрешениях нет,
    # --permission-mode dontAsk отклоняет всё, что всё же попросит разрешение;
    # --model — только если задан явно. У claude нет документированного способа передать картинку
    # файлом (в --help нет такого флага), поэтому агент помечен images=False и картинки в /complete
    # для него отклоняются раньше, до сборки команды.
    argv = [exe, "-p", "--tools", "", "--permission-mode", "dontAsk", "--system-prompt", system]
    if model:
        argv += ["--model", model]
    argv.append(user)
    return argv, None


def _cursor_agent_argv(exe: str, system: str, user: str, model: str | None,
                        image_paths: list[Path], workdir: Path) -> tuple[list[str], Path | None]:
    # Источник: `cursor-agent --help` (2026.08.11-e8db854). -p/--print — неинтерактивный вывод;
    # --output-format text — простой текст в stdout; --mode ask — режим вопросов и ответов только
    # на чтение, --sandbox disabled — песочница на Windows недоступна, защиту даёт режим ask, --trust — не спрашивать о доверии пустому
    # временному каталогу --workspace. --force (выполнять команды без спроса) не используется:
    # в запрос попадает чужой текст. Отдельного флага системной
    # подсказки в --help нет, поэтому системный и пользовательский текст соединяются в один
    # промпт. Отдельного флага для картинок в --help тоже нет, поэтому images=False.
    prompt = f"{system}\n\n{user}" if system else user
    argv = [exe, "--print", "--output-format", "text", "--mode", "ask", "--sandbox", "disabled", "--trust", "--workspace", str(workdir)]
    if model:
        argv += ["--model", model]
    argv.append(prompt)
    return argv, None


def _opencode_argv(exe: str, system: str, user: str, model: str | None,
                    image_paths: list[Path], workdir: Path) -> tuple[list[str], Path | None]:
    # Источник: `opencode run --help` (1.18.16). Позиционный message — неинтерактивный запуск
    # с текстом и выходом; -f/--file — вложение файла в сообщение (используется для картинок,
    # можно указывать несколько раз); -m/--model — модель. Флага системной подсказки нет,
    # соединяем текст сами.
    prompt = f"{system}\n\n{user}" if system else user
    argv = [exe, "run", "--format", "default"]
    if model:
        argv += ["--model", model]
    for path in image_paths:
        argv += ["--file", str(path)]
    argv.append(prompt)
    return argv, None


def _codex_argv(exe: str, system: str, user: str, model: str | None,
                 image_paths: list[Path], workdir: Path) -> tuple[list[str], Path | None]:
    # Codex CLI на машине разработки не установлен (нет в PATH), поэтому команда взята не из
    # локального --help, а из официальной документации: https://learn.chatgpt.com/docs/developer-commands?surface=cli
    # (открыта 2026-09-24). `codex exec PROMPT` — неинтерактивный запуск; --image/-i PATH[,PATH]
    # — картинки первым сообщением (через запятую); --output-last-message/-o PATH — записать
    # финальный ответ в файл (используем вместо разбора stdout); --sandbox read-only и
    # --ask-for-approval never — только чтение и без вопросов; --skip-git-repo-check — запуск во
    # временном каталоге вне репозитория. Отдельного флага системной подсказки документация не называет,
    # соединяем текст сами.
    prompt = f"{system}\n\n{user}" if system else user
    out_file = workdir / "codex-output.txt"
    argv = [exe, "exec", "--sandbox", "read-only", "--ask-for-approval", "never", "--skip-git-repo-check", "--output-last-message", str(out_file)]
    if model:
        argv += ["--model", model]
    if image_paths:
        argv += ["--image", ",".join(str(path) for path in image_paths)]
    argv.append(prompt)
    return argv, out_file


AGENTS: tuple[Agent, ...] = (
    Agent("claude", "Claude Code", images=False, build=_claude_argv),
    Agent("codex", "Codex", images=True, build=_codex_argv),
    Agent("cursor-agent", "Cursor Agent", images=False, build=_cursor_agent_argv),
    Agent("opencode", "OpenCode", images=True, build=_opencode_argv),
)
_AGENTS_BY_ID = {agent.id: agent for agent in AGENTS}


def _version(exe: str) -> str | None:
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10,
                                 encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (result.stdout or result.stderr or "").strip().splitlines()
    return lines[0].strip() if lines else None


def _spawn(argv: list[str], cwd: Path) -> subprocess.Popen:
    # PYTHONIOENCODING заставляет дочерний процесс писать UTF-8 в перенаправленный поток, а не
    # кодировку консоли Windows (cp1251/cp866): без него кириллица в ответе агента бьётся.
    # Безвредно для не-Python CLI — переменную читает только интерпретатор Python.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs: dict = dict(cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace", env=env)
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Убивает процесс вместе со всеми детьми: CLI-агенты сами порождают процессы (npm, node, git)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _run_agent(agent: Agent, exe: str, system: str, user: str, model: str | None,
                images_png_b64: list[str] | None, timeout_s: float) -> tuple[str, float]:
    if images_png_b64 and not agent.images:
        raise AgentError(f"{agent.id} не принимает картинки: в --help этого CLI нет способа их передать")
    # ignore_cleanup_errors: на Windows каталог может держать ещё не умерший потомок CLI.
    with tempfile.TemporaryDirectory(prefix="agent-bridge-", ignore_cleanup_errors=True) as raw_dir:
        workdir = Path(raw_dir)
        image_paths: list[Path] = []
        for index, b64 in enumerate(images_png_b64 or []):
            path = workdir / f"image-{index}.png"
            path.write_bytes(base64.b64decode(b64))
            image_paths.append(path)

        argv, out_file = agent.build(exe, system, user, model, image_paths, workdir)
        started = time.monotonic()
        proc = _spawn(argv, workdir)
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.communicate()
            raise AgentError(f"{agent.id}: не ответил за {timeout_s:.0f} с (таймаут)")
        seconds = time.monotonic() - started
        # OpenCode оставляет после ответа свой сервер: гасим всё дерево, чтобы не копились процессы.
        _kill_tree(proc)
        if proc.returncode != 0:
            detail = (stderr or stdout or "").strip()[-2000:]
            raise AgentError(f"{agent.id}: код возврата {proc.returncode}: {detail or 'нет вывода'}")

        text = ""
        if out_file is not None and out_file.is_file():
            text = out_file.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            text = (stdout or "").strip()
        if not text:
            text = (stderr or "").strip()
        return text, seconds


def _handle_list() -> dict:
    items = []
    for agent in AGENTS:
        exe = shutil.which(agent.id)
        items.append({
            "id": agent.id,
            "name": agent.name,
            "version": _version(exe) if exe else None,
            "found": exe is not None,
            "path": exe,
        })
    return {"items": items}


def _handle_check(agent: Agent, body: dict) -> dict:
    exe = shutil.which(agent.id)
    if not exe:
        return {"ok": False, "images": None, "seconds": 0.0, "message": f"{agent.id} не найден в PATH"}
    model = body.get("model")
    started = time.monotonic()
    try:
        text, seconds = _run_agent(agent, exe, "", "Ответь только словом OK.", model, None, _CHECK_TIMEOUT_S)
    except AgentError as error:
        elapsed = round(time.monotonic() - started, 3)
        return {"ok": False, "images": agent.images, "seconds": elapsed, "message": str(error)}
    ok = "OK" in text.upper()
    message = text[:500] if text else "пустой ответ"
    return {"ok": ok, "images": agent.images, "seconds": round(seconds, 3), "message": message}


def _handle_complete(agent: Agent, body: dict) -> dict:
    exe = shutil.which(agent.id)
    if not exe:
        raise AgentError(f"{agent.id} не найден в PATH")
    system = body.get("system") or ""
    user = body.get("user") or ""
    model = body.get("model")
    images = body.get("images_png_b64")
    timeout_s = float(body.get("timeout_s") or _DEFAULT_COMPLETE_TIMEOUT_S)
    text, seconds = _run_agent(agent, exe, system, user, model, images, timeout_s)
    return {"text": text, "seconds": round(seconds, 3)}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - сигнатура базового класса
        pass  # тихий мост: рабочий процесс не должен засорять терминал пользователя

    def do_GET(self) -> None:  # noqa: N802 - имя метода задаёт http.server
        if self.path == "/agents":
            self._respond(200, _handle_list())
            return
        self._respond(404, {"error": "не найдено"})

    def do_POST(self) -> None:  # noqa: N802
        match = re.match(r"^/agents/([^/]+)/(check|complete)$", self.path)
        if not match:
            self._respond(404, {"error": "не найдено"})
            return
        agent_id, action = match.group(1), match.group(2)
        agent = _AGENTS_BY_ID.get(agent_id)
        if agent is None:
            self._respond(404, {"error": f"неизвестный агент {agent_id!r}"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._respond(400, {"error": "тело запроса не JSON в UTF-8"})
            return
        try:
            if action == "check":
                self._respond(200, _handle_check(agent, body))
            else:
                self._respond(200, _handle_complete(agent, body))
        except AgentError as error:
            self._respond(502, {"error": str(error)})
        except Exception as error:  # защита моста: сбой одного запроса не роняет сервер
            self._respond(502, {"error": f"внутренняя ошибка моста: {error}"})

    def _respond(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Мост агентов: CLI на хосте для сервиса designer")
    parser.add_argument("--host", default=os.environ.get("AGENT_BRIDGE_HOST", HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENT_BRIDGE_PORT", PORT)))
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    print(f"мост агентов слушает http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
