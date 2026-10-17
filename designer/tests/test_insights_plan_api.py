from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from designer.api.app import app


FIXTURES = Path(__file__).parent / "fixtures" / "semantic_stage2"
CLIENT = TestClient(app)


def upload(filename: str) -> tuple[str, tuple[str, bytes, str]]:
    path = FIXTURES / filename
    mime = "application/json" if path.suffix == ".json" else "text/markdown" if path.suffix == ".md" else "text/csv"
    return "files", (path.name, path.read_bytes(), mime)


def test_bundle_plan_profiles_all_seven_sources_and_returns_explainable_candidates():
    names = sorted(path.name for path in FIXTURES.iterdir() if path.is_file() and path.name != "README.md")
    files = [upload(name) for name in names]
    response = CLIENT.post("/insights/plan", files=files, data={"goal": "show trend"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file_count"] == body["table_count"] == 7
    assert body["goal"] == "show trend"
    data = {item["file_name"]: item for item in body["datasets"]}
    assert data["reference_201.csv"]["rows"] == 201
    assert data["reference_201.csv"]["profile"]["numeric_candidates"] == []
    assert data["embedded_table.md"]["sheet"] == ""
    pie = next(c for c in data["category_shares.json"]["plan"]["candidates"] if c["kind"] == "pie")
    assert pie["denominator"] == "1000"
    distribution = next(c for c in data["distribution.csv"]["plan"]["candidates"] if c["kind"] == "histogram")
    assert distribution["renderable"] is False
    trend = next(c for c in data["time_series.csv"]["plan"]["candidates"] if c["kind"] == "line")
    assert "period" in trend["required_fields"]
    assert len(data["time_series.csv"]["preview_rows"]) == 5


def test_bundle_plan_preserves_legacy_single_file_route():
    response = CLIENT.post("/insights/plan", files=[upload("time_series.csv")], data={"goal": ""})
    assert response.status_code == 200
    assert response.json()["file_count"] == response.json()["table_count"] == 1


def test_bundle_plan_rejects_too_many_files_and_bad_table_with_filename():
    too_many = [upload("time_series.csv")] * 8
    response = CLIENT.post("/insights/plan", files=too_many)
    assert response.status_code == 422 and "от 1 до 7" in response.text

    response = CLIENT.post("/insights/plan", files={"files": ("broken.csv", b"not a table", "text/csv")})
    assert response.status_code == 422 and "broken.csv" in response.text


def test_bundle_plan_enforces_per_file_size_limit():
    response = CLIENT.post("/insights/plan", files={"files": ("large.csv", b"x" * (1024 * 1024 + 1), "text/csv")})
    assert response.status_code == 413 and "large.csv" in response.text
