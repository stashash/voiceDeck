"""Тесты моста scripts/agent_bridge.py: поднимаем его как настоящий процесс на свободном порту,
CLI подменены скриптами-заглушками в изолированном PATH (реальные claude/opencode на машине
разработки не трогаем и не зовём). Проверяем список агентов, /check и /complete, таймаут с
убийством дерева процессов и отказ картинок агенту без способа их принять."""
import ast
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

_BRIDGE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "agent_bridge.py"

_STUB_BODY = '''\
import os
import sys
import time

args = sys.argv[1:]
log_path = os.environ.get("STUB_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(repr(args) + "\\n")

if "--version" in args:
    print("9.9.9-stub")
    sys.exit(0)

prompt = args[-1] if args else ""
if "SLOW" in prompt:
    time.sleep(5)
if "FAIL" in prompt:
    print("заглушка: намеренный сбой", file=sys.stderr)
    sys.exit(1)
print("STUB ответ: " + prompt[:80])
'''


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _write_stub(bin_dir: Path, name: str) -> None:
    py_path = bin_dir / f"_{name.replace('-', '_')}_stub.py"
    py_path.write_text(_STUB_BODY, encoding="utf-8")
    if os.name == "nt":
        (bin_dir / f"{name}.cmd").write_text(
            f'@echo off\r\n"{sys.executable}" "{py_path}" %*\r\n', encoding="utf-8")
    else:
        script = bin_dir / name
        script.write_text(f'#!/usr/bin/env python3\nimport subprocess, sys\n'
                           f'sys.exit(subprocess.call([{sys.executable!r}, {str(py_path)!r}] + sys.argv[1:]))\n',
                           encoding="utf-8")
        script.chmod(0o755)


@pytest.fixture
def bridge(tmp_path):
    """Только claude и opencode находятся (в изолированном PATH), codex и cursor-agent — нет:
    это проверяет found=false, а не то, что установлено у разработчика."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub(bin_dir, "claude")
    _write_stub(bin_dir, "opencode")
    log_path = tmp_path / "stub.log"

    port = _free_port()
    env = dict(os.environ)
    env["PATH"] = str(bin_dir)
    env["STUB_LOG"] = str(log_path)
    env.pop("PATHEXT", None)  # оставить умолчание Windows (.COM;.EXE;.BAT;.CMD;...)

    proc = subprocess.Popen([sys.executable, str(_BRIDGE_PATH), "--port", str(port)],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base_url = f"http://127.0.0.1:{port}"
    _wait_until_up(base_url)
    try:
        yield base_url, log_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def _wait_until_up(base_url: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base_url}/agents", timeout=1.0)
            return
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(0.1)
    raise RuntimeError(f"мост не поднялся за {timeout_s} с: {last_error}")


def test_agents_list_shows_found_stubs_and_missing_real_cli(bridge):
    base_url, _ = bridge
    body = httpx.get(f"{base_url}/agents", timeout=5.0).json()
    by_id = {item["id"]: item for item in body["items"]}

    assert set(by_id) == {"claude", "codex", "cursor-agent", "opencode"}
    assert by_id["claude"]["found"] is True
    assert by_id["claude"]["version"] == "9.9.9-stub"
    assert by_id["claude"]["path"] is not None
    assert by_id["codex"]["found"] is False
    assert by_id["codex"]["path"] is None
    assert by_id["cursor-agent"]["found"] is False


def test_check_ok_reports_images_capability_from_help(bridge):
    base_url, _ = bridge
    claude = httpx.post(f"{base_url}/agents/claude/check", json={}, timeout=35.0).json()
    assert claude["ok"] is True
    assert claude["images"] is False  # у claude нет флага картинок в --help

    opencode = httpx.post(f"{base_url}/agents/opencode/check", json={}, timeout=35.0).json()
    assert opencode["ok"] is True
    assert opencode["images"] is True  # у opencode есть -f/--file


def test_check_reports_real_elapsed_time_on_immediate_failure(tmp_path):
    # Отдельный мост с CLI, которое всегда падает: seconds в ответе должен быть временем самого
    # запуска, а не константой таймаута проверки (было так: сбой за доли секунды показывал 30.0).
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "_claude_stub.py").write_text(
        'import sys\nprint("сбой", file=sys.stderr)\nsys.exit(1)\n', encoding="utf-8")
    if os.name == "nt":
        (bin_dir / "claude.cmd").write_text(
            f'@echo off\r\n"{sys.executable}" "{bin_dir / "_claude_stub.py"}" %*\r\n', encoding="utf-8")
    else:
        script = bin_dir / "claude"
        script.write_text(f'#!/usr/bin/env python3\nimport subprocess, sys\n'
                           f'sys.exit(subprocess.call([{sys.executable!r}, '
                           f'{str(bin_dir / "_claude_stub.py")!r}] + sys.argv[1:]))\n', encoding="utf-8")
        script.chmod(0o755)

    port = _free_port()
    env = dict(os.environ)
    env["PATH"] = str(bin_dir)
    proc = subprocess.Popen([sys.executable, str(_BRIDGE_PATH), "--port", str(port)],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(base_url)
        started = time.monotonic()
        result = httpx.post(f"{base_url}/agents/claude/check", json={}, timeout=35.0).json()
        elapsed = time.monotonic() - started
        assert result["ok"] is False
        assert result["seconds"] < 5.0  # не 30 (таймаут проверки), процесс упал сразу
        assert elapsed < 10.0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def test_check_unknown_agent_is_404(bridge):
    base_url, _ = bridge
    response = httpx.post(f"{base_url}/agents/bogus/check", json={}, timeout=5.0)
    assert response.status_code == 404


def test_check_missing_cli_reports_not_found_without_running_anything(bridge):
    base_url, _ = bridge
    result = httpx.post(f"{base_url}/agents/codex/check", json={}, timeout=35.0).json()
    assert result == {"ok": False, "images": None, "seconds": 0.0, "message": "codex не найден в PATH"}


def test_complete_returns_stub_text_and_seconds(bridge):
    base_url, _ = bridge
    response = httpx.post(f"{base_url}/agents/claude/complete",
                           json={"system": "s", "user": "верни {\"ok\": true}"}, timeout=35.0)
    assert response.status_code == 200
    body = response.json()
    assert body["text"].startswith("STUB ответ:")
    assert body["seconds"] >= 0


def test_complete_rejects_images_for_agent_without_a_way_to_send_them(bridge):
    base_url, _ = bridge
    response = httpx.post(f"{base_url}/agents/claude/complete",
                           json={"system": "s", "user": "u", "images_png_b64": ["aGVsbG8="]}, timeout=35.0)
    assert response.status_code == 502
    assert "не принимает картинки" in response.json()["error"]


def test_complete_forwards_image_files_to_opencode_via_dash_f(bridge):
    base_url, log_path = bridge
    response = httpx.post(f"{base_url}/agents/opencode/complete",
                           json={"system": "s", "user": "опиши картинку", "images_png_b64": ["aGVsbG8="]},
                           timeout=35.0)
    assert response.status_code == 200
    calls = [ast.literal_eval(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    complete_call = calls[-1]
    assert "--file" in complete_call
    image_arg = complete_call[complete_call.index("--file") + 1]
    assert image_arg.endswith("image-0.png")


def test_complete_times_out_and_kills_the_process(bridge):
    base_url, _ = bridge
    started = time.monotonic()
    response = httpx.post(f"{base_url}/agents/claude/complete",
                           json={"system": "s", "user": "SLOW", "timeout_s": 1}, timeout=15.0)
    elapsed = time.monotonic() - started
    assert response.status_code == 502
    assert "не ответил" in response.json()["error"]
    assert elapsed < 10  # заглушка спит 5с, таймаут 1с: процесс должен быть убит, а не досижен

    # мост остаётся живым и отвечает на следующий запрос
    assert httpx.get(f"{base_url}/agents", timeout=5.0).status_code == 200


def test_malformed_body_is_400_not_a_crash(bridge):
    base_url, _ = bridge
    response = httpx.post(f"{base_url}/agents/claude/complete", content=b"\xd2\xee\xf1\xf2",
                           headers={"Content-Type": "application/json"}, timeout=5.0)
    assert response.status_code == 400
    # мост остаётся живым после кривого тела запроса
    assert httpx.get(f"{base_url}/agents", timeout=5.0).status_code == 200


def test_complete_reports_non_zero_exit_as_502(bridge):
    base_url, _ = bridge
    response = httpx.post(f"{base_url}/agents/claude/complete", json={"system": "s", "user": "FAIL"}, timeout=35.0)
    assert response.status_code == 502
    assert "код возврата" in response.json()["error"]
