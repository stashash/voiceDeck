"""Observed semantics survive planning, materialization and deck assembly."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from designer import store
from designer.api.app import app
from designer.contracts import DeckPlan, SlideIntent, SlideKind
from designer.insights.plan import plan_table
from designer.insights.profile import profile_table
from designer.insights.suggest import Suggestion, insert_insight_slides
from designer.insights.table import read_table
from designer.pipeline import _append_reference_pages


FIXTURES = Path(__file__).parent / "fixtures" / "semantic_stage2"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DESIGNER_DATA_DIR", str(tmp_path / "data"))
    return TestClient(app)


def materialize(client, data, filename, goal):
    candidate = plan_table(read_table(data, filename), goal).selected_candidate
    response = client.post("/insights/plan/materialize", files={"file": (filename, data)}, data={
        "goal": goal, "candidate_kind": candidate.kind,
        "required_fields": json.dumps(candidate.required_fields),
    })
    assert response.status_code == 200, response.text
    return store.load_insights(response.json()["id"])["suggestions"][0]


def test_hierarchy_requires_repeated_unambiguous_nested_categories():
    data = "region,city,value\n" + "\n".join(["North,A,1", "North,B,2", "South,C,3", "South,D,4"] * 2)
    profile = profile_table(read_table(data.encode(), "source.csv"))
    assert (profile.dimension_count, profile.metric_count, profile.hierarchy_count) == (2, 1, 1)
    hierarchy, = profile.hierarchy_candidates
    assert (hierarchy.parent, hierarchy.child, hierarchy.parent_count, hierarchy.child_count) == ("region", "city", 2, 4)
    assert hierarchy.row_lines == tuple(range(2, 10))
    for invalid in (data.replace("North,A,1", "South,A,1", 1),
                    data.replace("North,A,1", "North,,1", 1),
                    "region,city\nNorth,A\nNorth,B\nSouth,C\nSouth,D\n",
                    "region,city\nNorth,A\nNorth,A\nSouth,B\nSouth,B\n"):
        assert profile_table(read_table(invalid.encode(), "source.csv")).hierarchy_candidates == ()


def test_partial_pairs_materialize_every_known_value_without_zero_imputation(client):
    data = (FIXTURES / "missing_zero.csv").read_bytes()
    suggestion = materialize(client, data, "missing_zero.csv", "compare actual and target")
    assert suggestion["visual"] == "table"
    assert suggestion["table"]["rows"] == read_table(data, "missing_zero.csv").rows
    assert suggestion["table"]["rows"][2][1:3] == ["8", ""]
    assert suggestion["provenance"]["excluded_row_lines"] == []
    assert suggestion["provenance"]["missing_policy"] == "preserve_all_rows"


def test_missing_category_does_not_hide_known_paired_values(client):
    data = b"week,actual_units,planned_units\nW1,1,2\nW2,2,3\n,8,9\n"
    candidate = plan_table(read_table(data, 'source.csv'), 'compare actual and target').selected_candidate
    assert candidate.kind == 'table'
    assert candidate.row_lines == (2, 3, 4) and candidate.excluded_row_lines == ()
    suggestion = materialize(client, data, 'source.csv', 'compare actual and target')
    assert suggestion['table']['rows'] == [['W1', '1', '2'], ['W2', '2', '3'], ['', '8', '9']]
    assert suggestion['provenance']['row_lines'] == [2, 3, 4]
    assert suggestion['provenance']['missing_policy'] == 'preserve_all_rows'


def test_embedded_period_units_source_and_original_lines_survive(client):
    data = (FIXTURES / "embedded_table.md").read_bytes()
    suggestion = materialize(client, data, "embedded_table.md", "compare")
    assert "Source: synthetic test data." in suggestion["source"]
    assert "counts for April 2026" in suggestion["source"]
    assert suggestion["chart"]["x_axis_title"] == "Requests, шт."
    assert suggestion["chart"]["y_axis_title"] == "Region"
    assert suggestion["provenance"]["row_lines"] == [5, 6, 7]
    assert suggestion["provenance"]["unit"] == "шт."
    changed = data.replace(b"April 2026", b"May 2026")
    assert plan_table(read_table(data, "x.md")).content_hash != plan_table(read_table(changed, "x.md")).content_hash


def test_multiline_csv_last_record_is_never_mistaken_for_source_context():
    data = b'Report\n\nname,value\nA,1\n"B\ncontinued",2\n\nSource: example\n'
    parsed = read_table(data, "x.csv")
    assert parsed.context == ("Report", "Source: example")
    assert parsed.rows[-1] == ["B\ncontinued", "2"]


def test_declared_observed_total_prefers_shares_and_reports_entire_composition(client):
    data = (FIXTURES / "category_shares.json").read_bytes()
    suggestion = materialize(client, data, "category_shares.json", "")
    assert suggestion["visual"] == "pie"
    for share in ("62.00%", "25.00%", "13.00%"):
        assert share in suggestion["statement"]
    assert suggestion["provenance"]["denominator"] == "1000"
    assert not suggestion["by_model"]


def test_relative_endpoint_change_uses_a_positive_baseline_only():
    def trend(first):
        return plan_table(read_table(f"period,value\n2026-01,{first}\n2026-02,150\n".encode(), "x.csv"), "trend").selected_candidate
    assert "+50.00%" in trend(100).headline
    assert "Относительное изменение" in trend(100).formula
    assert "%" not in trend(0).headline
    assert "%" not in trend(-100).headline


def test_histogram_has_readable_bounded_bins_retaining_outlier_and_labels(client):
    data = (FIXTURES / "distribution.csv").read_bytes()
    suggestion = materialize(client, data, "distribution.csv", "distribution")
    chart = suggestion["chart"]
    assert 1 <= len(chart["categories"]) <= 5
    assert sum(chart["series"][0]["values"]) == 25
    assert "95" in chart["categories"][-1]
    assert chart["x_axis_title"] and chart["y_axis_title"] == "Число наблюдений"
    close = b"record_id,value\n1,100001\n2,100002\n3,100003\n4,100004\n5,100005\n"
    labels = materialize(client, close, "source.csv", "distribution")["chart"]["categories"]
    assert len(labels) == len(set(labels))


def test_reference_201_pages_follow_main_messages_with_all_rows_and_provenance(client):
    data = (FIXTURES / "reference_201.csv").read_bytes()
    bundle = client.post("/insights/plan", files={"files": ("reference_201.csv", data)}, data={"goal": "reference"}).json()
    dataset = bundle["datasets"][0]
    response = client.post("/insights/plan/materialize-bundle", data={"bundle_id": bundle["id"], "selections": json.dumps([
        {"dataset_id": dataset["dataset_id"], "candidate_kind": "table", "required_fields": ["reference_id", "label"]}
    ])})
    assert response.status_code == 200, response.text
    suggestions = [Suggestion(**item) for item in store.load_insights(response.json()["id"])["suggestions"]]
    assert len(suggestions) == 30 and suggestions[0].visual == "big_number"
    plan = DeckPlan(title="Report", purpose="Review", audience="Team", slides=[
        SlideIntent(id="s1", kind=SlideKind.title, title="Report"),
        SlideIntent(id="s2", kind=SlideKind.cta, title="Next step"),
    ])
    insert_insight_slides(plan, suggestions)
    _append_reference_pages(plan)
    assert plan.slides[2].title == "Next step"
    pages = plan.slides[3:]
    assert len(pages) == 29 and all(slide.title.startswith("Приложение") for slide in pages)
    assert [row for slide in pages for row in slide.table.rows] == read_table(data, "reference_201.csv").rows
    assert [line for slide in pages for line in slide.provenance.displayed_row_lines] == list(range(2, 203))
    assert len({slide.provenance.source_sha256 for slide in pages}) == 1
    assert [slide.id for slide in plan.slides] == [f"s{i}" for i in range(1, 33)]
