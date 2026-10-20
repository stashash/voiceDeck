import json
from io import BytesIO
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from designer import store
from designer.api.app import app
from designer.api.app import _reference_pages
from designer.contracts import ColorToken, DesignSystem, FontToken, Margins, Tokens, TypeStep


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    package = store.design_system_dir("demo")
    package.mkdir(parents=True)
    design_system = DesignSystem(
        id="demo", source_file="template.pptx", slide_size_emu=(12192000, 6858000),
        tokens=Tokens(
            colors=[ColorToken(hex="112233", role="accent", share=1, source="theme")],
            fonts=[FontToken(family="Template Sans", role="body", share=1)],
            type_scale=[TypeStep(size_pt=18, role="body", share=1)],
            margins=Margins(left=.1, top=.1, right=.1, bottom=.1), guides_x=[.2], guides_y=[.3],
        ),
    )
    store.write_text_atomic(package / "manifest.json", design_system.model_dump_json(indent=2))
    with TestClient(app) as test_client:
        yield test_client


def test_json_brand_tokens_import_priority_change_and_reset(client):
    imported = client.post("/design-systems/demo/brandbook", files={
        "file": ("brand.json", b'{"colors":{"accent":"#aabbcc"},"fontFamilies":{"body":"Inter"}}', "application/json"),
    })
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["priority"] == "brand"
    assert result["brand_fields"] == ["colors", "fonts"]
    tokens = result["design_system"]["tokens"]
    assert tokens["colors"][0]["hex"] == "AABBCC"
    assert tokens["fonts"][0]["family"] == "Inter"
    assert tokens["guides_x"] == [.2]

    switched = client.post("/design-systems/demo/brandbook", data={"priority": "template"})
    assert switched.status_code == 200, switched.text
    assert switched.json()["design_system"]["tokens"]["colors"][0]["hex"] == "112233"
    assert switched.json()["design_system"]["tokens"]["fonts"][0]["family"] == "Template Sans"

    restored_brand = client.post("/design-systems/demo/brandbook", data={"priority": "brand"})
    assert restored_brand.json()["design_system"]["tokens"]["colors"][0]["hex"] == "AABBCC"
    removed = client.delete("/design-systems/demo/brandbook")
    assert removed.status_code == 200
    assert removed.json()["removed"] is True
    assert removed.json()["design_system"]["tokens"]["colors"][0]["hex"] == "112233"


def test_brandbook_reupload_keeps_original_template_fallback(client):
    first = client.post("/design-systems/demo/brandbook", files={
        "file": ("one.json", b'{"colors":{"accent":"AABBCC"}}', "application/json"),
    })
    assert first.status_code == 200
    second = client.post("/design-systems/demo/brandbook", files={
        "file": ("two.json", b'{"fonts":{"body":"Inter"}}', "application/json"),
    })
    assert second.status_code == 200, second.text
    tokens = second.json()["design_system"]["tokens"]
    assert tokens["colors"][0]["hex"] == "112233"
    assert tokens["fonts"][0]["family"] == "Inter"


def test_brandbook_rejects_invalid_and_oversized_inputs(client):
    invalid = client.post("/design-systems/demo/brandbook", files={
        "file": ("bad.json", b'{"colors":{"surprise":"ffffff"}}', "application/json"),
    })
    assert invalid.status_code == 422
    oversized = client.post("/design-systems/demo/brandbook", files={
        "file": ("large.json", json.dumps({"extra": "x" * 270_000}).encode(), "application/json"),
    })
    assert oversized.status_code == 413


def test_brandbook_imports_figma_variables_json_and_reports_skipped_values(client):
    response = client.post("/design-systems/demo/brandbook", files={
        "file": ("variables.json", json.dumps({"variables": [
            {"resolvedType": "COLOR", "valuesByMode": {"light": {"r": 1, "g": 0, "b": 0}}},
            {"resolvedType": "COLOR", "valuesByMode": {"light": {"r": .1, "g": .2, "b": .3}, "dark": {"r": .2, "g": .2, "b": .3}}},
        ]}).encode(), "application/json"),
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source_format"] == "figma_json"
    assert result["design_system"]["tokens"]["colors"][0]["hex"] == "FF0000"
    assert result["warnings"]


def test_brandbook_zip_assets_are_retained_and_removed_safely(client, tmp_path):
    image = BytesIO()
    Image.new("RGB", (8, 8), "red").save(image, format="PNG")
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("tokens.json", b'{"colors":{"accent":"AABBCC"}}')
        bundle.writestr("brand/logo.png", image.getvalue())
    response = client.post("/design-systems/demo/brandbook", files={
        "file": ("brand.zip", archive.getvalue(), "application/zip"),
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source_format"] == "zip"
    assert result["assets"][0]["name"] == "brand/logo.png"
    assets_path = store.design_system_dir("demo") / "brandbook-assets" / "brand" / "logo.png"
    assert assets_path.is_file() and assets_path.read_bytes() == image.getvalue()
    removed = client.delete("/design-systems/demo/brandbook")
    assert removed.status_code == 200
    assert not (store.design_system_dir("demo") / "brandbook-assets").exists()


def test_large_reference_table_materializes_as_readable_complete_pages():
    rows = [[f"REF-{index:03d}", f"Reference item {index:03d}"] for index in range(1, 202)]
    lines = list(range(2, 203))
    suggestion = {"visual": "table", "headline": "Reference", "table": {}, "provenance": {}}
    pages = _reference_pages(suggestion, {"table": {"headers": ["id", "label"], "rows": rows, "row_lines": lines}}, mode="full")
    assert len(pages) == 29
    assert all(1 <= len(page["table"]["rows"]) <= 7 for page in pages)
    assert sum(len(page["table"]["rows"]) for page in pages) == 201
    assert pages[0]["provenance"]["page_count"] == 29
    assert pages[-1]["provenance"]["displayed_row_lines"] == [198, 199, 200, 201, 202]
