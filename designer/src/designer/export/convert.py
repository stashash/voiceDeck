"""pptx в PDF и в картинки слайдов. Два движка: libreoffice и powerpoint. Владелец: задача T-11.

Выбор движка: явно через переменную окружения DESIGNER_CONVERTER, либо автоматически —
первый найденный среди доступных. libreoffice ищется через soffice в PATH или в переменной
DESIGNER_SOFFICE, powerpoint доступен только на Windows и только по факту регистрации COM.
Ни один движок не запускается на этапе available() — только проверка наличия.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ENGINES = ("libreoffice", "powerpoint")
_TIMEOUT_S = 180


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


def _rasterize_pdf_to_png(pdf_path: Path, out_dir: Path, width_px: int) -> list[Path]:
    """Страницы pdf в png через PyMuPDF, если он установлен. Честная ошибка, если средства нет."""
    try:
        import fitz  # PyMuPDF: не входит в базовый набор пакетов задачи
    except ImportError as exc:
        raise ConverterUnavailable(
            "нет библиотеки для растеризации pdf в png (например, PyMuPDF); "
            "среди разрешённых пакетов задачи такой нет"
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
