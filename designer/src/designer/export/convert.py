"""pptx в PDF и в картинки слайдов. Два движка: libreoffice и powerpoint. Владелец: задача T-11.

Выбор движка: явно через переменную окружения DESIGNER_CONVERTER, либо автоматически —
первый найденный среди доступных. libreoffice ищется через soffice в PATH или в переменной
DESIGNER_SOFFICE, powerpoint доступен только на Windows и только по факту регистрации COM.
Ни один движок не запускается на этапе available() — только проверка наличия.

Постоянная сессия движка (задача T-26): RenderSession отдаёт картинку одного слайда, а
запуск движка оплачивается один раз. Для powerpoint это долгоживущий дочерний powershell
без окна: он держит COM-объект, принимает команды строкой JSON на stdin и строкой JSON
отвечает. Сессия закрывается вместе с процессом сервиса и по простою; PowerPoint, который
человек запустил до нас, не закрывается.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

_ENGINES = ("libreoffice", "powerpoint")
_TIMEOUT_S = 180

DEFAULT_WIDTH_PX = 1600
"""Ширина картинки слайда по умолчанию: хватает на полный экран и на печать."""

IDLE_TIMEOUT_S = 300.0
"""Простой сессии, после которого движок закрывается."""

_WATCH_INTERVAL_S = 15.0
_CREATE_NO_WINDOW = 0x08000000


class ConverterUnavailable(RuntimeError):
    """Ни один движок конвертации не найден, движок не смог создать файл, либо для растеризации
    PDF в PNG нет средства среди установленных библиотек."""


def _soffice_path() -> str | None:
    env = os.environ.get("DESIGNER_SOFFICE")
    if env and Path(env).is_file():
        return env
    return shutil.which("soffice")


def _powerpoint_registered() -> bool:
    """PowerPoint.Application зарегистрирован как COM-класс. Только чтение реестра, без запуска."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CLSID")
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def available() -> list[str]:
    """Какие движки конвертации есть на этой машине, в порядке предпочтения."""
    engines = []
    if _soffice_path():
        engines.append("libreoffice")
    if _powerpoint_registered():
        engines.append("powerpoint")
    return engines


def _select_engine() -> str:
    requested = os.environ.get("DESIGNER_CONVERTER")
    engines = available()
    if requested:
        if requested not in _ENGINES:
            raise ConverterUnavailable(f"неизвестный движок конвертации: {requested!r}")
        if requested not in engines:
            raise ConverterUnavailable(f"движок {requested} запрошен переменной DESIGNER_CONVERTER, "
                                        f"но недоступен на этой машине")
        return requested
    if not engines:
        raise ConverterUnavailable(
            "ни один движок конвертации pptx не найден: нужен soffice в PATH или в "
            "DESIGNER_SOFFICE, либо PowerPoint на Windows"
        )
    return engines[0]


def to_pdf(pptx_path: Path, out_path: Path) -> Path:
    """Конвертирует pptx в pdf выбранным движком."""
    pptx_path = Path(pptx_path)
    out_path = Path(out_path)
    engine = _select_engine()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if engine == "powerpoint":
        _powerpoint_to_pdf(pptx_path, out_path)
    else:
        _libreoffice_to_pdf(pptx_path, out_path)
    if not out_path.is_file():
        raise ConverterUnavailable(f"движок {engine} не создал pdf: {out_path}")
    return out_path


def to_png(pptx_path: Path, out_dir: Path, width_px: int = 1280) -> list[Path]:
    """По картинке на слайд, имена slide-001.png и далее по порядку."""
    pptx_path = Path(pptx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = _select_engine()
    if engine == "powerpoint":
        return _powerpoint_to_png(pptx_path, out_dir, width_px)
    return _libreoffice_to_png(pptx_path, out_dir, width_px)


# ---------- libreoffice: soffice --headless --convert-to ----------

def _soffice_pdf_command(soffice: str, pptx_path: Path, out_dir: Path, profile_dir: Path) -> list[str]:
    return [
        soffice, "--headless", "--invisible", "--nologo", "--nofirststartwizard",
        "--norestore", "--nolockcheck",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx_path),
    ]


def _libreoffice_to_pdf(pptx_path: Path, out_path: Path) -> None:
    soffice = _soffice_path()
    if not soffice:
        raise ConverterUnavailable("soffice не найден: задайте PATH или DESIGNER_SOFFICE")
    with tempfile.TemporaryDirectory(prefix="designer-soffice-out-") as out_dir_raw:
        out_dir_tmp = Path(out_dir_raw)
        profile_dir = Path(tempfile.mkdtemp(prefix="designer-soffice-profile-"))
        try:
            cmd = _soffice_pdf_command(soffice, pptx_path, out_dir_tmp, profile_dir)
            result = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_S, check=False)
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
        produced = out_dir_tmp / f"{pptx_path.stem}.pdf"
        if not produced.is_file():
            stderr = result.stderr.decode("utf-8", "replace").strip() if result.stderr else ""
            raise ConverterUnavailable(f"soffice не создал pdf: {stderr or 'нет вывода'}")
        shutil.copyfile(produced, out_path)


def _libreoffice_to_png(pptx_path: Path, out_dir: Path, width_px: int) -> list[Path]:
    with tempfile.TemporaryDirectory(prefix="designer-pdf-") as tmp:
        pdf_path = Path(tmp) / f"{pptx_path.stem}.pdf"
        _libreoffice_to_pdf(pptx_path, pdf_path)
        return _rasterize_pdf_to_png(pdf_path, out_dir, width_px)


def _pdftoppm_path() -> str | None:
    return shutil.which("pdftoppm")


def _pdftoppm_rasterize(tool: str, pdf_path: Path, out_dir: Path, width_px: int) -> list[Path]:
    """Страницы pdf в png программой pdftoppm. Имена она даёт свои, поэтому файлы переименовываем."""
    prefix = out_dir / "page"
    cmd = [tool, "-png", "-scale-to-x", str(width_px), "-scale-to-y", "-1",
           str(pdf_path), str(prefix)]
    result = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_S, check=False)
    produced = sorted(out_dir.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    if not produced:
        stderr = result.stderr.decode("utf-8", "replace").strip() if result.stderr else ""
        raise ConverterUnavailable(f"pdftoppm не создал картинки: {stderr or 'нет вывода'}")
    pages: list[Path] = []
    for i, page in enumerate(produced, start=1):
        target = out_dir / f"slide-{i:03d}.png"
        page.replace(target)
        pages.append(target)
    return pages


def _rasterize_pdf_to_png(pdf_path: Path, out_dir: Path, width_px: int) -> list[Path]:
    """Страницы pdf в png: сначала pdftoppm из PATH, иначе PyMuPDF. Честная ошибка, если средства нет."""
    tool = _pdftoppm_path()
    if tool:
        return _pdftoppm_rasterize(tool, pdf_path, out_dir, width_px)
    try:
        import fitz  # PyMuPDF: не входит в базовый набор пакетов задачи
    except ImportError as exc:
        raise ConverterUnavailable(
            "нет средства для растеризации pdf в png: ни pdftoppm в PATH (пакет poppler-utils), "
            "ни библиотеки PyMuPDF"
        ) from exc
    doc = fitz.open(pdf_path)
    try:
        pages: list[Path] = []
        for i, page in enumerate(doc, start=1):
            zoom = width_px / page.rect.width if page.rect.width else 1.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            page_path = out_dir / f"slide-{i:03d}.png"
            pix.save(str(page_path))
            pages.append(page_path)
        return pages
    finally:
        doc.close()


# ---------- powerpoint: COM через powershell, только Windows ----------

_PS_TO_PDF = """
param([string]$InputPath, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$alreadyRunning = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($InputPath, $true, $false, $false)
    try {
        $pres.SaveAs($OutputPath, 32)
    } finally {
        $pres.Close()
    }
} finally {
    if (-not $alreadyRunning) {
        $app.Quit()
    }
}
"""

_PS_TO_PNG = """
param([string]$InputPath, [string]$OutputDir, [int]$Width, [int]$Height)
$ErrorActionPreference = 'Stop'
$alreadyRunning = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($InputPath, $true, $false, $false)
    try {
        # Имена задаём сами: Presentation.Export называет файлы по языку интерфейса («Слайд1.PNG»).
        foreach ($slide in $pres.Slides) {
            $slide.Export((Join-Path $OutputDir ('slide-{0:d3}.png' -f $slide.SlideIndex)), 'PNG', $Width, $Height)
        }
    } finally {
        $pres.Close()
    }
} finally {
    if (-not $alreadyRunning) {
        $app.Quit()
    }
}
"""


def _run_powershell_script(script: str, args: list[str]) -> subprocess.CompletedProcess:
    if sys.platform != "win32":
        raise ConverterUnavailable("движок powerpoint доступен только на Windows")
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", script_path, *args]
        return subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_S, check=False)
    finally:
        Path(script_path).unlink(missing_ok=True)


def _powerpoint_to_pdf(pptx_path: Path, out_path: Path) -> None:
    result = _run_powershell_script(_PS_TO_PDF, ["-InputPath", str(pptx_path), "-OutputPath", str(out_path)])
    if result.returncode != 0 or not out_path.is_file():
        stderr = result.stderr.decode("utf-8", "replace").strip() if result.stderr else ""
        raise ConverterUnavailable(f"PowerPoint не создал pdf: {stderr or 'нет вывода'}")


def _slide_aspect(pptx_path: Path) -> float:
    from pptx import Presentation
    prs = Presentation(str(pptx_path))
    return (prs.slide_height / prs.slide_width) if prs.slide_width else 9 / 16


def _powerpoint_to_png(pptx_path: Path, out_dir: Path, width_px: int) -> list[Path]:
    height_px = round(width_px * _slide_aspect(pptx_path))
    result = _run_powershell_script(
        _PS_TO_PNG,
        ["-InputPath", str(pptx_path), "-OutputDir", str(out_dir),
         "-Width", str(width_px), "-Height", str(height_px)],
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip() if result.stderr else ""
        raise ConverterUnavailable(f"PowerPoint не создал картинки: {stderr or 'нет вывода'}")
    pages = sorted(out_dir.glob("slide-*.png"))
    if not pages:
        raise ConverterUnavailable("PowerPoint не создал картинки слайдов")
    return pages


# ---------- постоянная сессия движка (задача T-26) ----------

_PS_SESSION = """
$ErrorActionPreference = 'Stop'
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
} catch { }
$alreadyRunning = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$app = $null
$pres = $null
$openPath = ''
$running = $true

function Send-Answer($data) {
    [Console]::Out.WriteLine((ConvertTo-Json $data -Compress))
    [Console]::Out.Flush()
}

while ($running) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    if ($line.Trim().Length -eq 0) { continue }
    try {
        $cmd = ConvertFrom-Json $line
        switch ($cmd.command) {
            'png' {
                if ($null -eq $app) { $app = New-Object -ComObject PowerPoint.Application }
                if ($openPath -ne $cmd.path) {
                    if ($null -ne $pres) { $pres.Close(); $pres = $null }
                    $pres = $app.Presentations.Open($cmd.path, $true, $false, $false)
                    $openPath = $cmd.path
                }
                $slide = $pres.Slides.Item([int]$cmd.slide)
                $slide.Export($cmd.out, 'PNG', [int]$cmd.width, [int]$cmd.height)
                Send-Answer @{ ok = $true; out = $cmd.out }
            }
            'close' {
                $running = $false
                Send-Answer @{ ok = $true }
            }
            default {
                Send-Answer @{ ok = $false; error = 'неизвестная команда' }
            }
        }
    } catch {
        Send-Answer @{ ok = $false; error = $_.Exception.Message }
    }
}
if ($null -ne $pres) { try { $pres.Close() } catch { } }
if ($null -ne $app -and -not $alreadyRunning) { try { $app.Quit() } catch { } }
"""


class _SessionBroken(RuntimeError):
    """Процесс сессии не ответил: его надо поднять заново."""


class RenderSession:
    """Движок, поднятый один раз: отдаёт картинку слайда по его номеру с нуля."""

    def png(self, pptx_path: Path, slide_index: int, width_px: int = DEFAULT_WIDTH_PX) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _LibreOfficeSession(RenderSession):
    """soffice зовётся по-прежнему на файл целиком; картинки файла держатся до его правки."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple[str, float, int] | None = None
        self._pages: list[bytes] = []

    def png(self, pptx_path: Path, slide_index: int, width_px: int = DEFAULT_WIDTH_PX) -> bytes:
        pptx_path = Path(pptx_path)
        with self._lock:
            key = (str(pptx_path.resolve()), pptx_path.stat().st_mtime, width_px)
            if key != self._key:
                self._pages = self._convert(pptx_path, width_px)
                self._key = key
            if slide_index < 0 or slide_index >= len(self._pages):
                raise ConverterUnavailable(f"в файле нет слайда с номером {slide_index + 1}")
            return self._pages[slide_index]

    @staticmethod
    def _convert(pptx_path: Path, width_px: int) -> list[bytes]:
        with tempfile.TemporaryDirectory(prefix="designer-session-png-") as tmp:
            return [page.read_bytes() for page in _libreoffice_to_png(pptx_path, Path(tmp), width_px)]

    def close(self) -> None:
        with self._lock:
            self._key = None
            self._pages = []


class _PowerPointSession(RenderSession):
    """Долгоживущий powershell без окна: держит COM-объект и отдаёт слайд по команде."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._script_path: Path | None = None
        self._last_used = time.monotonic()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None

    # -- процесс --

    def _spawn(self) -> subprocess.Popen:
        """Поднимает дочерний powershell. В тестах подменяется целиком."""
        if sys.platform != "win32":
            raise ConverterUnavailable("движок powerpoint доступен только на Windows")
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(_PS_SESSION)
            self._script_path = Path(f.name)
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(self._script_path)]
        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1, creationflags=_CREATE_NO_WINDOW,
        )

    def _ensure(self) -> subprocess.Popen:
        if self._proc is None or self._proc.poll() is not None:
            self._proc = self._spawn()
            self._start_watcher()
        return self._proc

    def _shutdown(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write(json.dumps({"command": "close"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=10)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                proc.terminate()
        if self._script_path is not None:
            self._script_path.unlink(missing_ok=True)
            self._script_path = None

    def _drop(self) -> None:
        """Снимает процесс, который перестал отвечать, не пытаясь с ним договориться."""
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    # -- простой --

    def _start_watcher(self) -> None:
        if self._watcher is not None:
            return
        self._watcher = threading.Thread(target=self._watch, name="designer-render-session", daemon=True)
        self._watcher.start()

    def _watch(self) -> None:
        while not self._stop.wait(_WATCH_INTERVAL_S):
            self._close_if_idle()

    def _close_if_idle(self) -> bool:
        """Закрывает движок, если им давно не пользовались. Возвращает, случилось ли закрытие."""
        with self._lock:
            if self._proc is None:
                return False
            if time.monotonic() - self._last_used < IDLE_TIMEOUT_S:
                return False
            self._shutdown()
            return True

    # -- команды --

    def _ask(self, command: dict) -> dict:
        proc = self._ensure()
        try:
            proc.stdin.write(json.dumps(command, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            answer = proc.stdout.readline()
        except (OSError, ValueError) as exc:
            raise _SessionBroken(str(exc)) from exc
        if not answer.strip():
            raise _SessionBroken("сессия движка не ответила")
        try:
            return json.loads(answer)
        except json.JSONDecodeError as exc:
            raise _SessionBroken(f"непонятный ответ сессии: {answer.strip()[:200]}") from exc

    def png(self, pptx_path: Path, slide_index: int, width_px: int = DEFAULT_WIDTH_PX) -> bytes:
        pptx_path = Path(pptx_path).resolve()
        height_px = round(width_px * _slide_aspect(pptx_path))
        with self._lock:
            self._last_used = time.monotonic()
            last_error = ""
            for attempt in (1, 2):
                try:
                    return self._png_once(pptx_path, slide_index, width_px, height_px)
                except _SessionBroken as exc:
                    last_error = str(exc)
                    self._drop()  # упавший процесс поднимется на следующей попытке
                    if attempt == 2:
                        raise ConverterUnavailable(
                            f"сессия PowerPoint не отвечает: {last_error}"
                        ) from exc
            raise ConverterUnavailable(f"сессия PowerPoint не отвечает: {last_error}")

    def _png_once(self, pptx_path: Path, slide_index: int, width_px: int, height_px: int) -> bytes:
        with tempfile.TemporaryDirectory(prefix="designer-session-slide-") as tmp:
            out_path = Path(tmp) / f"slide-{slide_index + 1:03d}.png"
            answer = self._ask({
                "command": "png", "path": str(pptx_path), "slide": slide_index + 1,
                "out": str(out_path), "width": width_px, "height": height_px,
            })
            if not answer.get("ok"):
                raise ConverterUnavailable(f"PowerPoint не отдал слайд: {answer.get('error', 'нет причины')}")
            if not out_path.is_file():
                raise ConverterUnavailable("PowerPoint не создал файл картинки слайда")
            return out_path.read_bytes()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            self._shutdown()
        self._watcher = None


_session: RenderSession | None = None
_session_lock = threading.Lock()


def get_session() -> RenderSession:
    """Сессия движка на весь процесс сервиса: движок поднимается один раз."""
    global _session
    with _session_lock:
        if _session is None:
            engine = _select_engine()
            _session = _PowerPointSession() if engine == "powerpoint" else _LibreOfficeSession()
        return _session


def close_session() -> None:
    """Закрывает сессию движка. Зовётся при остановке сервиса."""
    global _session
    with _session_lock:
        session, _session = _session, None
    if session is not None:
        session.close()


atexit.register(close_session)
