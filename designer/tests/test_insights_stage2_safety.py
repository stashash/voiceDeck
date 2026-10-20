"""Source-grounded conclusions and safe fallbacks at the planner/API boundary."""
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from designer import store
from designer.api.app import app
from designer.insights.plan import plan_table
from designer.insights.table import read_table


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DESIGNER_DATA_DIR", str(tmp_path / "data"))
    return TestClient(app)


def table(text):
    return read_table(text.encode(), "source.csv")


def materialize(client, text, goal, candidate):
    return client.post("/insights/plan/materialize", files={"file": ("source.csv", text.encode(), "text/csv")},
                       data={"goal": goal, "candidate_kind": candidate.kind,
                             "required_fields": json.dumps(candidate.required_fields)})


@pytest.mark.parametrize("values,change", [("0,10", "+10"), ("10,0", "-10"), ("10,10", "0")])
def test_trend_describes_endpoints_without_claiming_monotonic_growth(values, change):
    first, last = values.split(",")
    candidate = plan_table(table(f"period,revenue_usd\n2026-03,{last}\n2026-01,{first}\n2026-02,100\n"), "trend").selected_candidate
    assert candidate.number == change
    assert candidate.row_lines == (3, 4, 2)
    assert f"{change} USD" in candidate.headline
    assert "Промежуточные значения могут колебаться" in candidate.statement
    assert "последнее − первое" in candidate.formula


def test_comparison_reports_tied_maxima_and_excludes_missing_rows(client):
    text = "category,value\nA,10\nB,10\nC,\nD,0\n"
    candidate = plan_table(table(text), "compare").selected_candidate
    response = materialize(client, text, "compare", candidate)
    assert response.status_code == 200, response.text
    suggestion = store.load_insights(response.json()["id"])["suggestions"][0]
    assert suggestion["headline"] == "Значение: максимум 10 — 2 категории"
    assert "Среди 3 полных наблюдений" in suggestion["statement"]
    assert suggestion["provenance"]["row_lines"] == [2, 3, 5]
    assert suggestion["provenance"]["excluded_row_lines"] == [4]
    assert suggestion["provenance"]["formula"] == suggestion["formula"]
    assert not suggestion["by_model"]


def test_shares_disclose_observed_denominator_and_rounding(client):
    text = "category,value\nA,1\nB,2\n"
    candidate = plan_table(table(text), "shares").selected_candidate
    response = materialize(client, text, "shares", candidate)
    assert response.status_code == 200, response.text
    suggestion = store.load_insights(response.json()["id"])["suggestions"][0]
    assert "66.67% показанной суммы" in suggestion["headline"]
    assert "2 из 3" in suggestion["statement"]
    assert "округлено до 2 знаков" in suggestion["statement"]
    assert suggestion["provenance"]["denominator"] == "3"
    assert "2 / 3" in suggestion["formula"]


def test_distribution_summary_keeps_outlier_and_matches_frequency_total(client):
    text = "record_id,value\n1,1\n2,2\n3,3\n4,4\n5,95\n"
    candidate = plan_table(table(text), "distribution").selected_candidate
    response = materialize(client, text, "distribution", candidate)
    assert response.status_code == 200, response.text
    suggestion = store.load_insights(response.json()["id"])["suggestions"][0]
    assert "от 1 до 95" in suggestion["headline"]
    assert "5 полных наблюдений" in suggestion["statement"]
    assert sum(suggestion["chart"]["series"][0]["values"]) == 5
    assert "max(value) = 95" in suggestion["formula"]
    assert "сумма частот = 5" in suggestion["formula"]


@pytest.mark.parametrize("goal,header,rows,kind", [
    ("trend", "period,value", "2026-01,9007199254740993\n2026-02,9007199254740995", "line"),
    ("compare", "category,value", "A,9007199254740993\nB,9007199254740995", "bar"),
    ("compare", "period,value", "2026-01,9007199254740993\n2026-02,9007199254740995", "column"),
    ("shares", "category,value", "A,0.1234567890123456789\nB,0.2", "pie"),
    ("distribution", "record_id,value", "1,9007199254740993\n2,1\n3,2\n4,3\n5,4", "histogram"),
])
def test_unsupported_decimal_precision_selects_exact_table_and_rejects_chart(client, goal, header, rows, kind):
    text = f"{header}\n{rows}\n"
    plan = plan_table(table(text), goal)
    assert plan.selected_candidate.kind == "table"
    unsafe = next(candidate for candidate in plan.candidates if candidate.kind == kind)
    assert not unsafe.renderable
    assert "диапазон чисел" in unsafe.reason
    assert materialize(client, text, goal, unsafe).status_code == 422
    response = materialize(client, text, goal, plan.selected_candidate)
    assert response.status_code == 200, response.text
    saved = store.load_insights(response.json()["id"])["suggestions"][0]
    assert saved["table"]["rows"] == table(text).rows
    assert saved["provenance"]["row_lines"] == list(plan.selected_candidate.row_lines)
    assert "диапазон чисел" in response.json()["note"]


def test_conclusion_arithmetic_does_not_round_large_decimal_endpoint_difference():
    plan = plan_table(table("period,value\n2026-01,123456789012345678901234567890.1\n2026-02,123456789012345678901234567890.2\n"), "trend")
    trend = next(candidate for candidate in plan.candidates if candidate.kind == "line")
    assert Decimal(trend.number) == Decimal("0.1")
    assert "123456789012345678901234567890.1" in trend.statement


@pytest.mark.parametrize("goal,headers", [("compare", "category,value"),
    ("compare", "category,actual,target"), ("stacked", "category,a_usd,b_usd")])
def test_large_categorical_charts_fall_back_without_silent_truncation(client, goal, headers):
    width = len(headers.split(",")) - 1
    text = headers + "\n" + "\n".join(f"C{i}," + ",".join(str(i + j + 1) for j in range(width)) for i in range(20))
    plan = plan_table(table(text), goal)
    assert plan.selected_candidate.kind == "table"
    assert any("Больше 12 категорий" in warning for warning in plan.warnings)
    assert all(not candidate.renderable for candidate in plan.candidates if candidate.kind != "table")
    bundle = client.post("/insights/plan", files={"files": ("source.csv", text.encode(), "text/csv")}, data={"goal": goal}).json()
    dataset = bundle["datasets"][0]
    response = client.post("/insights/plan/materialize-bundle", data={"bundle_id": bundle["id"], "selections": json.dumps([
        {"dataset_id": dataset["dataset_id"], "candidate_kind": "table", "required_fields": headers.split(",")}
    ])})
    assert response.status_code == 200, response.text
    suggestions = store.load_insights(response.json()["id"])["suggestions"]
    assert suggestions[0]["visual"] == "big_number"
    pages = suggestions[1:]
    assert len(pages) == 3
    assert [row for page in pages for row in page["table"]["rows"]] == table(text).rows
    assert [line for page in pages for line in page["provenance"]["displayed_row_lines"]] == list(range(2, 22))
    assert all(len(page["table"]["rows"]) <= 7 for page in pages)


def test_high_cardinality_comparison_uses_paginated_reference_instead_of_unrelated_distribution(client):
    text = "category,value\n" + "\n".join(f"Category {i},{i}" for i in range(25))
    plan = plan_table(table(text), "compare")
    assert plan.selected_candidate.kind == "table"
    assert any("Для запрошенного анализа нет диаграммы" in warning for warning in plan.warnings)
    response = client.post("/insights/plan", files={"files": ("source.csv", text.encode(), "text/csv")}, data={"goal": "compare"})
    bundle = response.json()
    dataset = bundle["datasets"][0]
    response = client.post("/insights/plan/materialize-bundle", data={"bundle_id": bundle["id"], "selections": json.dumps([
        {"dataset_id": dataset["dataset_id"], "candidate_kind": "table", "required_fields": ["category", "value"]}
    ])})
    assert response.status_code == 200, response.text
    suggestions = store.load_insights(response.json()["id"])["suggestions"]
    assert suggestions[0]["visual"] == "big_number"
    pages = suggestions[1:]
    assert len(pages) == 4
    assert [row for page in pages for row in page["table"]["rows"]] == table(text).rows
    assert [line for page in pages for line in page["provenance"]["displayed_row_lines"]] == list(range(2, 27))
