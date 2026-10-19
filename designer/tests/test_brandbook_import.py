from io import BytesIO
import hashlib
import json
import stat
import zipfile

from PIL import Image
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from designer import brandbook_import as importer
from designer.brandbook_import import BrandbookImportError, parse_brandbook_source
from designer.brandbook_json import BrandTokenError


def _zip(entries, compression=zipfile.ZIP_DEFLATED):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in entries:
            if isinstance(name, str) and "\\" in name:
                info = zipfile.ZipInfo("placeholder")
                info.filename = name
                name = info
            archive.writestr(name, data)
    return buffer.getvalue()


def _png():
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(600, 800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    lines = ["BT /F1 12 Tf 20 760 Td"]
    for line in text.splitlines():
        line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"({line}) Tj 0 -18 Td")
    lines.append("ET")
    stream.set_data("\n".join(lines).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_json_reuses_validated_existing_schema_and_raw_hash():
    raw = b'{"colors":{"accent":"#ab12cd"},"fonts":{"body":"Inter"}}'
    result = parse_brandbook_source(raw, "brand.JSON")
    assert result.tokens.colors[0].hex == "AB12CD"
    assert result.tokens.colors[0].role == "accent"
    assert result.tokens.fonts[0].family == "Inter"
    assert result.source_format == "json"
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert not result.assets
    assert result.tokens.type_scale == []


@pytest.mark.parametrize("raw", [b'{"colors":{"accent":"red"}}', b'{"unknown":true}', b"[]", b"{bad"])
def test_json_invalid_schema_is_rejected(raw):
    with pytest.raises(BrandTokenError):
        parse_brandbook_source(raw, "brand.json")


def test_pdf_recovers_only_explicit_values_without_guessed_roles():
    raw = _pdf("Brand blue #1234ab\nRGB: 255, 128, 0\nRGB: 999, 0, 0\nFont family: IBM Plex Sans\nFont: Inter\nBody size 24pt\nLeft margin 10%\nPurple is primary")
    result = parse_brandbook_source(raw, "brand.pdf")
    assert {c.hex for c in result.tokens.colors} == {"1234AB", "FF8000"}
    assert {f.family for f in result.tokens.fonts} == {"IBM Plex Sans", "Inter"}
    assert {c.role for c in result.tokens.colors} == {"other"}
    assert result.tokens.type_scale == []
    assert result.tokens.margins.left == 0
    assert result.source_format == "pdf"
    assert result.warnings


@pytest.mark.parametrize("text", ["Use blue and Arial", "#1234567", "RGB: 999, 0, 0", "RGB: 1, 2, 3.5", "RGB: 1, 2, 3%", ""])
def test_pdf_without_explicit_tokens_is_not_guessed(text):
    with pytest.raises(BrandbookImportError, match="no explicit"):
        parse_brandbook_source(_pdf(text), "brand.pdf")


def test_pdf_malformed_encrypted_and_page_limit(monkeypatch):
    with pytest.raises(BrandbookImportError, match="extract"):
        parse_brandbook_source(b"%PDF-broken", "brand.pdf")
    writer = PdfWriter()
    writer.add_blank_page(600, 800)
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(BrandbookImportError, match="Encrypted"):
        parse_brandbook_source(buffer.getvalue(), "brand.pdf")
    monkeypatch.setattr(importer, "MAX_PDF_PAGES", 0)
    with pytest.raises(BrandbookImportError, match="pages"):
        parse_brandbook_source(_pdf("#112233"), "brand.pdf")


def test_pdf_text_limit(monkeypatch):
    monkeypatch.setattr(importer, "MAX_TEXT_CHARS", 3)
    with pytest.raises(BrandbookImportError, match="text exceeds"):
        parse_brandbook_source(_pdf("#112233"), "brand.pdf")


def test_zip_preserves_verified_assets_in_memory():
    png = _png()
    raw = _zip([("brand/", b""), ("brand/tokens.json", b'{"fonts":{"body":"Inter"}}'),
                ("brand/logos/logo.png", png)])
    result = parse_brandbook_source(raw, "brand.zip")
    assert result.source_format == "zip"
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.tokens.fonts[0].family == "Inter"
    assert result.assets[0].name == "brand/logos/logo.png"
    assert result.assets[0].data == png


@pytest.mark.parametrize("name", ["../logo.png", "/logo.png", "C:/logo.png", "x\\logo.png", "a/../logo.png", "a//logo.png", "./logo.png", "a./logo.png", "NUL.png", "a/logo.png:evil", "a/\nlogo.png"])
def test_zip_rejects_unsafe_paths(name):
    raw = _zip([("tokens.json", b"{}"), (name, _png())])
    with pytest.raises(BrandbookImportError, match="Unsafe"):
        parse_brandbook_source(raw, "brand.zip")


def test_zip_rejects_symlink():
    link = zipfile.ZipInfo("logo.png")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(BrandbookImportError, match="symlink"):
        parse_brandbook_source(_zip([("tokens.json", b"{}"), (link, b"/etc/passwd")]), "brand.zip")


@pytest.mark.parametrize("entries", [[], [("a/b/tokens.json", b"{}")], [("a.json", b"{}"), ("b.json", b"{}")], [("logo.png", b"fake")]])
def test_zip_requires_exactly_one_near_root_json(entries):
    with pytest.raises(BrandbookImportError):
        parse_brandbook_source(_zip(entries), "brand.zip")


@pytest.mark.parametrize("name,data", [("logo.svg", b"<svg/>"), ("logo.png", b"not png"), ("script.js", b"alert(1)"), ("logo.jpg", _png())])
def test_zip_rejects_active_unsupported_or_spoofed_assets(name, data):
    with pytest.raises(BrandbookImportError):
        parse_brandbook_source(_zip([("tokens.json", b"{}"), (name, data)]), "brand.zip")


def test_zip_rejects_unsupported_compression_and_duplicates():
    with pytest.raises(BrandbookImportError, match="compression"):
        parse_brandbook_source(_zip([("tokens.json", b"{}")], zipfile.ZIP_BZIP2), "brand.zip")
    with pytest.raises(BrandbookImportError, match="Duplicate"):
        parse_brandbook_source(_zip([("tokens.json", b"{}"), ("TOKENS.JSON", b"{}")]), "brand.zip")


def test_zip_resource_limits(monkeypatch):
    raw = _zip([("tokens.json", b"{}"), ("logo.png", _png())])
    monkeypatch.setattr(importer, "MAX_ZIP_ENTRIES", 1)
    with pytest.raises(BrandbookImportError, match="count"):
        parse_brandbook_source(raw, "brand.zip")
    monkeypatch.setattr(importer, "MAX_ZIP_ENTRIES", 128)
    monkeypatch.setattr(importer, "MAX_ENTRY_BYTES", 2)
    with pytest.raises(BrandbookImportError, match="size"):
        parse_brandbook_source(raw, "brand.zip")
    monkeypatch.setattr(importer, "MAX_ENTRY_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(importer, "MAX_EXPANDED_BYTES", 2)
    with pytest.raises(BrandbookImportError, match="expanded"):
        parse_brandbook_source(raw, "brand.zip")


def test_zip_rejects_compression_bomb():
    with pytest.raises(BrandbookImportError, match="compression ratio"):
        parse_brandbook_source(_zip([("tokens.json", b" " * 300_000)]), "brand.zip")


def test_figma_variables_export_skips_ambiguous_modes_aliases_alpha_and_strings():
    raw = json.dumps({"variables": [
        {"resolvedType": "COLOR", "valuesByMode": {"light": {"r": 1, "g": 0, "b": .5}}},
        {"resolvedType": "COLOR", "valuesByMode": {"light": {"r": 0, "g": 0, "b": 0}, "dark": {"r": 1, "g": 1, "b": 1}}},
        {"resolvedType": "COLOR", "valuesByMode": {"x": {"type": "VARIABLE_ALIAS", "id": "ref"}}},
        {"resolvedType": "COLOR", "valuesByMode": {"x": {"r": 1, "g": 0, "b": 0, "a": .5}}},
        {"resolvedType": "STRING", "valuesByMode": {"x": "not necessarily a font"}},
    ]}).encode()
    result = parse_brandbook_source(raw, "figma.json")
    assert result.source_format == "figma_json"
    assert [c.hex for c in result.tokens.colors] == ["FF0080"]
    assert not result.tokens.fonts
    assert "Skipped 4" in result.warnings[0]


def test_typed_token_export_normalizes_font_family_and_color_only():
    raw = json.dumps({"brand": {"color": {"$type": "color", "primary": {"$value": "#abcdef"}},
                                "font": {"$type": "fontFamily", "$value": "Inter"},
                                "size": {"$type": "dimension", "$value": "24px"}}}).encode()
    result = parse_brandbook_source(raw, "tokens.json")
    assert result.source_format == "figma_json"
    assert result.tokens.colors[0].hex == "ABCDEF"
    assert result.tokens.fonts[0].family == "Inter"
    assert result.tokens.type_scale == []


def test_unsupported_native_fig_bad_zip_and_raw_limit(monkeypatch):
    for filename, raw in [("design.fig", b"fig-kiwi"), ("brand.zip", b"broken"), ("brand.docx", b"PK")]:
        with pytest.raises(BrandbookImportError):
            parse_brandbook_source(raw, filename)
    monkeypatch.setattr(importer, "MAX_SOURCE_BYTES", 1)
    with pytest.raises(BrandbookImportError, match="limit"):
        parse_brandbook_source(b"{}", "brand.json")


def test_typed_tokens_reject_excessive_nesting():
    data = {"$type": "color", "$value": "#112233"}
    for _ in range(26):
        data = {"group": data}
    with pytest.raises(BrandbookImportError, match="nesting"):
        parse_brandbook_source(json.dumps(data).encode(), "brand.json")
