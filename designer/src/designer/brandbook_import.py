"""Bounded, in-memory brandbook imports. Never extracts ZIP paths to disk.

PDF extraction is evidence recovery, not visual/OCR inference. Figma support is
for exported Variables or typed token JSON; native .fig binaries are unsupported.
Raster ZIP assets are verified with Pillow; active SVG/HTML are not accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import math
from pathlib import PurePosixPath
import re
import stat
import struct
from typing import Any, Literal
import warnings
import zipfile
import zlib

from PIL import Image, UnidentifiedImageError

from designer.brandbook_json import BrandTokenError, parse_brand_tokens
from designer.contracts import Tokens

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_ZIP_ENTRIES = 128
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_TEXT_CHARS = 1_000_000
_RASTER_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".gif": "GIF"}


class BrandbookImportError(BrandTokenError):
    """Unsupported, unsafe, or unreadable source."""


@dataclass(frozen=True)
class BrandbookAsset:
    name: str
    data: bytes


@dataclass(frozen=True)
class BrandbookImportResult:
    tokens: Tokens
    source_format: Literal["json", "figma_json", "pdf", "zip"]
    raw_sha256: str
    assets: tuple[BrandbookAsset, ...] = ()
    warnings: tuple[str, ...] = ()
    rules: dict | None = None
    source: dict | None = None


def _rgb(value: Any, *, normalized: bool = False) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        return value.lstrip("#").upper()
    if not isinstance(value, dict) or not all(k in value for k in ("r", "g", "b")):
        return None
    channels = [value[k] for k in ("r", "g", "b")]
    limit = 1 if normalized else 255
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
           or not 0 <= x <= limit for x in channels):
        return None
    # The current token model cannot represent transparency. Do not discard it.
    if value.get("a", 1) != 1:
        return None
    return "".join(f"{round(x * 255 if normalized else x):02X}" for x in channels)


def _validated_rules(root: dict) -> dict:
    from designer.brandbook_rules import read_rules
    try:
        return read_rules(root)
    except ValueError as exc:
        raise BrandbookImportError(str(exc)) from exc


def _json_tokens(raw: bytes) -> tuple[Tokens, str, tuple[str, ...]]:
    try:
        root = json.loads(raw)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BrandbookImportError("Invalid brandbook JSON") from exc
    if not isinstance(root, dict):
        raise BrandbookImportError("Brandbook JSON must be an object")
    root = {key: value for key, value in root.items() if key not in {"rules", "source"}}
    if "variables" not in root and not _has_typed_tokens(root):
        return parse_brand_tokens(root), "json", ()
    colors: list[dict[str, str]] = []
    fonts: list[dict[str, str]] = []
    skipped = 0

    def add(kind: str, value: Any) -> None:
        nonlocal skipped
        if kind in ("COLOR", "color"):
            color = _rgb(value, normalized=kind == "COLOR")
            if color:
                colors.append({"role": "other", "hex": color})
                return
        if kind in ("fontFamily", "fontFamilies") and isinstance(value, str) and value.strip():
            fonts.append({"role": "other", "family": value.strip()})
            return
        skipped += 1

    if "variables" in root:
        variables = root["variables"]
        if not isinstance(variables, list) or len(variables) > 4096:
            raise BrandbookImportError("Figma variables must be an array of at most 4096 entries")
        for variable in variables:
            if not isinstance(variable, dict):
                raise BrandbookImportError("Invalid Figma variable")
            modes = variable.get("valuesByMode")
            # No automatic choice of mode and no unresolved alias traversal.
            if not isinstance(modes, dict) or not modes or len(modes) > 64:
                skipped += 1
                continue
            values = list(modes.values())
            if any(v != values[0] for v in values[1:]):
                skipped += 1
                continue
            add(variable.get("resolvedType", ""), values[0])
    else:
        def walk(node: dict[str, Any], inherited: str = "", depth: int = 0) -> None:
            if depth > 24:
                raise BrandbookImportError("Token JSON nesting exceeds 24 levels")
            kind = node.get("$type", node.get("type", inherited))
            if "$value" in node or ("value" in node and "type" in node):
                add(kind, node.get("$value", node.get("value")))
                return
            for key, child in node.items():
                if not key.startswith("$") and isinstance(child, dict):
                    walk(child, kind, depth + 1)
        walk(root)
    if not colors and not fonts:
        raise BrandbookImportError("No supported concrete colors or font families in exported Figma JSON")
    notes = (f"Skipped {skipped} unsupported, aliased, transparent, or ambiguous tokens.",) if skipped else ()
    return parse_brand_tokens({"colors": colors, "fonts": fonts}), "figma_json", notes


def _has_typed_tokens(root: dict[str, Any], depth: int = 0) -> bool:
    if depth > 24:
        raise BrandbookImportError("Token JSON nesting exceeds 24 levels")
    if "$value" in root or ("type" in root and "value" in root):
        return True
    return any(_has_typed_tokens(v, depth + 1) for v in root.values() if isinstance(v, dict))


def _pdf_tokens(raw: bytes) -> tuple[Tokens, tuple[str, ...], dict, tuple[BrandbookAsset, ...]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise BrandbookImportError("Encrypted PDF brandbooks are unsupported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise BrandbookImportError(f"PDF exceeds {MAX_PDF_PAGES} pages")
        parts: list[str] = []
        pdf_colors: set[str] = set()
        pdf_fonts: set[str] = set()
        images: list[BrandbookAsset] = []
        text_size = 0
        for page in reader.pages:
            def operand(op, args, *_):
                if op in (b"rg", b"RG") and len(args) == 3:
                    color = _rgb(dict(zip(("r", "g", "b"), [float(v) for v in args])), normalized=True)
                    if color:
                        pdf_colors.add(color)
            def visitor(_text, _cm, _tm, font, _size):
                if font and font.get("/BaseFont"):
                    family = re.sub(r"^[A-Z]{6}\+", "", str(font["/BaseFont"]).lstrip("/"))
                    family = re.sub(r"-(Bold|Italic|Regular|Oblique).*", "", family)
                    if family:
                        pdf_fonts.add(family)
            text = page.extract_text(visitor_operand_before=operand, visitor_text=visitor) or ""
            text_size += len(text)
            if text_size > MAX_TEXT_CHARS:
                raise BrandbookImportError("PDF extracted text exceeds limit")
            parts.append(text)
            if len(images) < 12:
                for image in page.images:
                    if len(image.data) <= MAX_ENTRY_BYTES and len(images) < 12:
                        try:
                            with Image.open(BytesIO(image.data)) as decoded:
                                if decoded.width < 64 or decoded.height < 16:
                                    continue
                            images.append(_asset(f"pdf-image-{len(images) + 1}.png", _png_bytes(image.data)))
                        except (OSError, BrandbookImportError):
                            continue
        text = "\n".join(parts)
    except BrandbookImportError:
        raise
    except Exception as exc:
        raise BrandbookImportError("Unable to extract text from PDF") from exc
    colors = set(re.findall(r"(?<![\w#])#([0-9a-fA-F]{6})(?![\w])", text))
    for match in re.finditer(r"\bRGB\s*[:=]?\s*\(?\s*(\d{1,3})\s*[,;]\s*(\d{1,3})\s*[,;]\s*(\d{1,3})(?![\w.%])\s*\)?", text, re.I):
        color = _rgb(dict(zip(("r", "g", "b"), map(int, match.groups()))))
        if color:
            colors.add(color)
    families = set()
    for match in re.finditer(r"(?im)^\s*(?:font(?:\s+family)?|typeface|шрифт|гарнитура)\s*[:=]\s*([^\n\r;]{1,100})\s*$", text):
        family = match.group(1).strip().strip('"\'')
        if re.fullmatch(r"[\w][\w .+'’\-]{0,98}", family) and not family.isnumeric():
            families.add(family)
    if not colors:
        colors = pdf_colors
    if not families and (colors or images):
        families = pdf_fonts
    if not colors and not families and not images:
        raise BrandbookImportError("PDF has no explicit hex/RGB colors or labeled font families; OCR is unsupported")
    def role_of(color):
        for role in ("background", "surface", "text_muted", "accent_alt", "text", "accent"):
            if re.search(rf"(?im)^\s*{role}\s*[:=]\s*#?{color}\b", text):
                return role
        return "other"
    payload = {"colors": [{"role": role_of(c), "hex": c.upper()} for c in sorted(colors)],
               "fonts": [{"role": "heading" if re.search(rf"(?im)^heading\s+font\s*[:=]\s*{re.escape(f)}", text) else "body" if re.search(rf"(?im)^body\s+font\s*[:=]\s*{re.escape(f)}", text) else "other", "family": f} for f in sorted(families)]}
    for role in ("heading", "body"):
        match = re.search(rf"(?im)^\s*{role}\s+font\s*[:=]\s*([^\r\n]+)", text)
        if match:
            payload["fonts"].append({"role": role, "family": match[1].strip()[:100]})
    sizes = [{"role": role, "size_pt": float(value)} for role, value in re.findall(r"(?im)^\s*(title|heading|body|caption)\s+size\s*[:=]\s*(\d+(?:\.\d+)?)", text)]
    if sizes:
        payload["type_scale"] = sizes
    margin = re.search(r"(?im)^\s*margins\s*[:=]\s*([\d., ]+)", text)
    if margin:
        values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", margin[1])]
        if len(values) == 4 and all(0 <= value <= 0.3 for value in values):
            payload["margins"] = dict(zip(("left", "top", "right", "bottom"), values))
    rules = {}
    grid = re.search(r"(?im)^\s*grid columns\s*[:=]\s*(\d+)", text)
    if grid and 1 <= int(grid[1]) <= 24:
        rules["grid_columns"] = int(grid[1])
    if images and re.search(r"logo|логотип", text, re.I):
        rules["logo"] = images[0].name
    tokens = parse_brand_tokens(payload) if colors or families else _asset_palette(tuple(images))
    return tokens, ("PDF values recovered from text, embedded fonts, RGB operations and images; ambiguous typography/grid rules are not invented.",), rules, tuple(images)


def _png_bytes(raw: bytes) -> bytes:
    output = BytesIO()
    with Image.open(BytesIO(raw)) as image:
        image.convert("RGBA").save(output, format="PNG")
    return output.getvalue()


def _safe_zip_name(info: zipfile.ZipInfo) -> str:
    # ZipInfo normalizes Windows backslashes and truncates NULs; inspect the
    # original archive spelling before accepting its normalized filename.
    name = info.orig_filename
    if "\x00" in name:
        raise BrandbookImportError("Unsafe ZIP entry path")
    stripped = name[:-1] if info.is_dir() else name
    parts = stripped.split("/")
    if (not stripped or len(parts) > 8 or any(p in ("", ".", "..") for p in parts)
            or "\\" in name or ":" in name or any(ord(c) < 32 for c in name)
            or any(p.endswith((" ", ".")) for p in parts)
            or any(re.fullmatch(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts)):
        raise BrandbookImportError("Unsafe ZIP entry path")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise BrandbookImportError("ZIP symlinks and special files are unsupported")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise BrandbookImportError("Unsupported ZIP compression")
    if info.flag_bits & 1:
        raise BrandbookImportError("Encrypted ZIP entries are unsupported")
    if info.file_size > MAX_ENTRY_BYTES or info.file_size > max(1, info.compress_size) * 200:
        raise BrandbookImportError("ZIP entry exceeds size or compression ratio limit")
    return stripped


def _asset(name: str, data: bytes) -> BrandbookAsset:
    expected = _RASTER_FORMATS.get(PurePosixPath(name).suffix.lower())
    if not expected:
        raise BrandbookImportError("ZIP assets must be PNG, JPEG, WEBP or GIF images; SVG is unsupported")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != expected or image.width * image.height > 25_000_000:
                    raise BrandbookImportError("ZIP image format or pixel limit is invalid")
                image.verify()
    except BrandbookImportError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, struct.error, zlib.error, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise BrandbookImportError("Invalid or oversized ZIP image") from exc
    return BrandbookAsset(name, data)


def _zip_tokens(raw: bytes) -> tuple[Tokens, tuple[BrandbookAsset, ...], tuple[str, ...], dict]:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ZIP_ENTRIES:
                raise BrandbookImportError("ZIP entry count exceeds limit or ZIP is empty")
            seen: set[str] = set()
            files = []
            total = 0
            for info in infos:
                name = _safe_zip_name(info)
                if name.casefold() in seen:
                    raise BrandbookImportError("Duplicate ZIP entry name")
                seen.add(name.casefold())
                total += info.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise BrandbookImportError("ZIP expanded size exceeds limit")
                if not info.is_dir():
                    files.append((name, info))
            jsons = [(name, info) for name, info in files if PurePosixPath(name).suffix.lower() == ".json"]
            if len(jsons) > 1 or (jsons and len(PurePosixPath(jsons[0][0]).parts) > 2):
                raise BrandbookImportError("ZIP requires at most one root or near-root tokens JSON")
            if not jsons:
                assets = tuple(_asset(name, archive.read(info)) for name, info in files)
                if not assets:
                    raise BrandbookImportError("ZIP contains no brand materials")
                tokens = _asset_palette(assets)
                logos = [a.name for a in assets if re.search(r"logo|логотип", a.name, re.I)]
                return tokens, assets, ("Palette recovered from images; typography falls back to the template.",), ({"logo": logos[0]} if logos else {})
            json_name, json_info = jsons[0]
            token_raw = archive.read(json_info)
            tokens, inner_format, notes = _json_tokens(token_raw)
            rules = _validated_rules(json.loads(token_raw))
            assets = tuple(_asset(name, archive.read(info)) for name, info in files if name != json_name)
            return tokens, assets, notes + (f"Token JSON format: {inner_format}.",), rules
    except BrandbookImportError:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error) as exc:
        raise BrandbookImportError("Unreadable ZIP archive") from exc


def parse_brandbook_source(raw: bytes, filename: str) -> BrandbookImportResult:
    """Parse uploaded bytes; caller owns persistence and upload/request limits.

    Absent groups stay empty. ``Tokens`` requires margins, so the existing zero
    margins sentinel represents omission. Never treat it as recovered evidence.
    ZIP asset names are validated relative names, not filesystem destinations.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SOURCE_BYTES:
        raise BrandbookImportError("Source must be nonempty bytes within the 20 MiB limit")
    suffix = PurePosixPath(filename).suffix.lower()
    assets: tuple[BrandbookAsset, ...] = ()
    rules: dict = {}
    if suffix == ".fig":
        raise BrandbookImportError("Native .fig binaries are unsupported; export Variables/tokens JSON")
    if suffix == ".json":
        tokens, source_format, notes = _json_tokens(raw)
        rules = _validated_rules(json.loads(raw))
    elif suffix == ".pdf":
        tokens, notes, rules, assets = _pdf_tokens(raw)
        source_format = "pdf"
    elif suffix == ".zip":
        tokens, assets, notes, rules = _zip_tokens(raw)
        source_format = "zip"
    else:
        raise BrandbookImportError("Unsupported brandbook source; use JSON, PDF or ZIP")
    from designer.brandbook_rules import apply_grid
    try:
        tokens = apply_grid(tokens, rules)
    except ValueError as exc:
        raise BrandbookImportError(str(exc)) from exc
    source = json.loads(raw).get("source") if suffix == ".json" else None
    if not isinstance(source, dict):
        source = None
    return BrandbookImportResult(tokens, source_format, hashlib.sha256(raw).hexdigest(), assets, notes, rules, source)


def _asset_palette(assets: tuple[BrandbookAsset, ...]) -> Tokens:
    from collections import Counter
    from designer.contracts import ColorToken, Margins
    import colorsys
    counts = Counter()
    for asset in assets:
        with Image.open(BytesIO(asset.data)) as image:
            image = image.convert("RGB")
            image.thumbnail((160, 100))
            quantized = image.quantize(colors=12)
            palette = quantized.getpalette()
            for count, index in quantized.getcolors(16000) or []:
                rgb = palette[index * 3:index * 3 + 3]
                counts[tuple(rgb)] += count
    accents = [(rgb, n) for rgb, n in counts.items() if colorsys.rgb_to_hls(*(v / 255 for v in rgb))[2] >= 0.35]
    accents.sort(key=lambda pair: pair[1], reverse=True)
    colors = [ColorToken(hex="".join(f"{v:02X}" for v in rgb), role="accent" if i == 0 else "accent_alt" if i == 1 else "other", share=n / max(1, sum(counts.values())), source="usage") for i, (rgb, n) in enumerate(accents[:6])]
    if not colors:
        colors = [ColorToken(hex="".join(f"{v:02X}" for v in rgb), role="other", share=n / sum(counts.values()), source="usage") for rgb, n in counts.most_common(3)]
    return Tokens(colors=colors, fonts=[], type_scale=[], margins=Margins(left=0, top=0, right=0, bottom=0))
