"""Analytical semantics are data/goal-dependent and independent of styling or transport."""
from __future__ import annotations

import copy
import inspect
import json
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from designer.insights.plan import AnalyticalGoal, parse_goal, plan_table
from designer.insights.table import Table, read_table

FIXTURES = Path(__file__).parent / "fixtures" / "semantic_stage2"


def fixture(name):
    path = FIXTURES / name
    return read_table(path.read_bytes(), path.name)


def data(columns, rows):
    return read_table(json.dumps({"columns": columns, "rows": rows}).encode(), "input.json")


def kinds(plan):
    return {c.kind for c in plan.candidates}


@pytest.mark.parametrize("filename,goal,expected", [
    ("time_series.csv", "показать рост", "line"),
    ("category_comparison.csv", "сравнить план и факт", "grouped_column"),
    ("category_shares.json", "структура долей", "pie"),
    ("distribution.csv", "показать распределение", "histogram"),
    ("reference_201.csv", "справочные значения", "table"),
    ("missing_zero.csv", "compare actual and target", "grouped_column"),
    ("embedded_table.md", "сравнить регионы", "bar"),
])
def test_all_seven_fixture_goals(filename, goal, expected):
    table = fixture(filename)
    before = copy.deepcopy(table)
    plan = plan_table(table, goal)
    assert plan.selected_candidate.kind == expected
    assert 1 <= len(plan.candidates) <= 3
    assert list(plan.candidates) == sorted(plan.candidates, key=lambda c: (-c.score, c.kind, c.required_fields))
    assert plan.selected_candidate == plan.candidates[0]
    assert plan.selected_fields == plan.selected_candidate.required_fields
    assert (plan.row_count, plan.column_count) == (len(table.rows), len(table.headers))
    for candidate in plan.candidates:
        assert candidate.reason
        assert set(candidate.required_fields) <= set(table.headers)
        assert set(candidate.row_lines) | set(candidate.excluded_row_lines) == set(table.lines)
        assert not set(candidate.row_lines) & set(candidate.excluded_row_lines)
        assert all(w in candidate.reason for w in candidate.warnings)
    assert table == before
    assert plan == plan_table(table, goal)


@pytest.mark.parametrize("text,kind", [
    ("show growth", "trend"), ("динамика продаж", "trend"),
    ("compare regions", "comparison"), ("сравнить регионы", "comparison"),
    ("shares by channel", "shares"), ("показать долю", "shares"),
    ("distribution", "distribution"), ("распределение", "distribution"),
    ("relationship between measures", "relationship"), ("корреляция величин", "relationship"),
    ("reference lookup", "reference"), ("справочная таблица", "reference"),
    ("count rows", "kpi"), ("количество строк", "kpi"), ("KPI", "kpi"),
])
def test_simple_author_goals(text, kind):
    assert parse_goal(text).kind == kind


def test_goal_changes_ranking_without_changing_data_hash():
    table = fixture("time_series.csv")
    growth = plan_table(table, "growth")
    comparison = plan_table(table, "compare periods")
    distribution = plan_table(table, "distribution")
    reference = plan_table(table, "reference")
    assert [p.selected_candidate.kind for p in (growth, comparison, distribution, reference)] == ["line", "column", "histogram", "table"]
    assert len({p.content_hash for p in (growth, comparison, distribution, reference)}) == 1


def test_equivalent_csv_json_content_hash_and_semantics_ignore_source_lines():
    csv = read_table(b"category,value\nA,10.00\nB,20.0\nC,30\n", "red-template.csv")
    js = data(["category", "value"], [["A", 10], ["B", 20], ["C", 30]])
    first, second = plan_table(csv, "shares"), plan_table(js, "shares")
    assert first.content_hash == second.content_hash
    assert [(c.kind, c.score, c.required_fields, c.denominator) for c in first.candidates] == [
        (c.kind, c.score, c.required_fields, c.denominator) for c in second.candidates]
    assert first.selected_candidate.row_lines == (2, 3, 4)
    assert second.selected_candidate.row_lines == (1, 2, 3)
    changed = data(["category", "value"], [["A", 11], ["B", 20], ["C", 30]])
    assert first.content_hash != plan_table(changed, "shares").content_hash


def test_hash_retains_cell_units_and_large_decimal_precision():
    plain = data(["value"], [["10"], ["20"]])
    percentage = data(["value"], [["10 %"], ["20 %"]])
    assert plan_table(plain).content_hash != plan_table(percentage).content_hash
    a = data(["value"], [["123456789012345678901234567890.1"], ["2"]])
    b = data(["value"], [["123456789012345678901234567890.2"], ["2"]])
    assert plan_table(a).content_hash != plan_table(b).content_hash


def test_style_is_not_an_input_and_filename_sheet_do_not_change_semantics():
    assert tuple(inspect.signature(plan_table).parameters) == ("table", "goal")
    table = fixture("time_series.csv")
    assert plan_table(table) == plan_table(replace(table, name="different-template.json", sheet="Dark theme"))
    with pytest.raises(TypeError):
        plan_table(table, theme="blue")


def test_plan_goal_and_nested_candidates_are_immutable():
    plan = plan_table(fixture("time_series.csv"))
    with pytest.raises(FrozenInstanceError):
        plan.content_hash = "changed"
    with pytest.raises(FrozenInstanceError):
        plan.goal.kind = "shares"
    with pytest.raises(FrozenInstanceError):
        plan.selected_candidate.score = 999
    with pytest.raises(ValueError, match="tuples"):
        AnalyticalGoal(measures=["value"])


def test_share_denominator_is_full_and_matches_explicit_total():
    plan = plan_table(fixture("category_shares.json"), "shares")
    pie = plan.selected_candidate
    assert pie.denominator == Decimal(1000)
    assert pie.denominator_field == "total_tickets"
    assert pie.measure_fields == ("tickets",)
    assert pie.aggregation == "share_of_observed_sum"
    assert pie.required_fields == ("outcome", "tickets", "total_tickets")
    assert "1000" in pie.reason and "сумма" in pie.reason


@pytest.mark.parametrize("rows", [
    [["A", -1], ["B", 3]], [["A", 0], ["B", 0]],
    [[f"C{i}", i] for i in range(7)], [["A", 1], ["A", 2]],
])
def test_invalid_share_domains_never_propose_pie(rows):
    plan = plan_table(data(["category", "value"], rows), "shares")
    assert "pie" not in kinds(plan)
    assert plan.warnings


def test_declared_population_mismatch_does_not_create_misleading_pie():
    plan = plan_table(data(["category", "tickets", "total_tickets"],
                          [["A", 20, 100], ["B", 30, 100]]), "shares")
    assert "pie" not in kinds(plan)
    assert any("совпадение с итогом" in w for w in plan.warnings)


def test_missing_zero_and_actual_target_pair_are_not_summed_or_imputed():
    table = fixture("missing_zero.csv")
    plan = plan_table(table, "compare actual and target")
    selected = plan.selected_candidate
    assert selected.measure_fields == ("actual_units", "planned_units")
    assert selected.row_lines == (2, 5)
    assert selected.excluded_row_lines == (3, 4)
    assert selected.aggregation == "none" and selected.value is None
    assert "Нулями пропуски не заполняются" in selected.reason
    assert any("времени" in w for w in plan.warnings)


def test_explicit_measure_selection_not_default_mixed_units():
    table = fixture("category_comparison.csv")
    default = plan_table(table, "compare")
    assert default.selected_candidate.measure_fields == ("actual_leads", "target_leads")
    explicit = plan_table(table, AnalyticalGoal("comparison", dimensions=("channel",), measures=("actual_spend_usd",)))
    assert explicit.selected_candidate.kind == "bar"
    assert explicit.selected_fields == ("channel", "actual_spend_usd")
    assert "grouped_column" not in kinds(explicit)


def test_distribution_retains_outlier_and_is_not_available_renderer():
    table = fixture("distribution.csv")
    plan = plan_table(table, "distribution")
    histogram = plan.selected_candidate
    assert histogram.kind == "histogram" and histogram.renderable
    assert histogram.row_lines == tuple(table.lines)
    assert "выброс" in histogram.reason
    assert histogram.aggregation == "none"  # No invented bins/counts at plan stage.


def test_scatter_complete_pairs_and_no_correlation_claim():
    table = data(["x", "y"], [[0, 0], [1, 2], [2, None], [3, 6], [4, 8], [5, 10]])
    plan = plan_table(table, "relationship")
    scatter = plan.selected_candidate
    assert scatter.kind == "scatter" and scatter.renderable
    assert scatter.measure_fields == ("x", "y")
    assert scatter.row_lines == (1, 2, 4, 5, 6) and scatter.excluded_row_lines == (3,)
    assert "5 полных пар чисел" in scatter.reason
    assert "не значит причину" in scatter.reason and scatter.value is None


@pytest.mark.parametrize("rows", [[[i, i * 2] for i in range(4)], [[i, 1] for i in range(6)],
                                  [[i, None if i < 2 else i] for i in range(6)]])
def test_scatter_rejects_insufficient_pairs_and_constant_columns(rows):
    plan = plan_table(data(["x", "y"], rows), "relationship")
    assert "scatter" not in kinds(plan)
    assert any("пять полных пар" in w for w in plan.warnings)


def test_id_is_not_a_relationship_measure():
    plan = plan_table(data(["record_id", "amount"], [[i, i * 2] for i in range(6)]), "relationship")
    assert "scatter" not in kinds(plan)
    assert any("идентификаторы" in w for w in plan.warnings)


@pytest.mark.parametrize("dates", [["2026-01", "2026-01"], ["2026-01", "2026-02-01"],
                                   ["01/02/2026", "03/04/2026"], ["Week 1", "Week 2"]])
def test_ambiguous_duplicate_or_mixed_time_axes_do_not_propose_lines(dates):
    plan = plan_table(data(["period", "value"], [[d, i] for i, d in enumerate(dates)]), "growth")
    assert "line" not in kinds(plan)
    assert plan.warnings


def test_two_date_axes_require_selection_and_selected_dates_are_ordered():
    table = data(["start_date", "end_date", "value"],
                 [["2026-03-01", "2026-03-02", 3], ["2026-01-01", "2026-01-02", 1]])
    ambiguous = plan_table(table, "trend")
    assert "line" not in kinds(ambiguous)
    explicit = plan_table(table, AnalyticalGoal("trend", dimensions=("start_date",)))
    assert explicit.selected_candidate.kind == "line"
    assert explicit.selected_candidate.row_lines == (2, 1)


def test_partially_parseable_date_column_cannot_be_used_as_clear_axis():
    table = data(["date", "value"], [[f"2026-01-{i:02d}", i] for i in range(1, 10)] + [["bad", 10]])
    assert "line" not in kinds(plan_table(table, "trend"))


@pytest.mark.parametrize("rows", [[[1], [2], [3], [4]], [[1]] * 6])
def test_histogram_needs_enough_nonconstant_observations(rows):
    plan = plan_table(data(["value"], rows), "distribution")
    assert "histogram" not in kinds(plan)
    assert any("пять чисел" in w for w in plan.warnings)


def test_reference_covers_all_201_rows_with_pagination_warning():
    table = fixture("reference_201.csv")
    plan = plan_table(table)
    assert kinds(plan) == {"table"}
    assert plan.selected_candidate.row_lines == tuple(table.lines)
    assert "на страницы" in plan.selected_candidate.reason


def test_only_explicit_record_count_is_automatic_kpi():
    table = fixture("missing_zero.csv")
    safe = plan_table(table, "count rows").selected_candidate
    assert safe.kind == "kpi" and safe.value == Decimal(4)
    assert safe.aggregation == "count_rows" and safe.row_lines == tuple(table.lines)
    assert "неполные тоже" in safe.reason
    unsafe = plan_table(table, "KPI")
    assert "kpi" not in kinds(unsafe)
    assert any("не суммируются" in w for w in unsafe.warnings)
    with pytest.raises(ValueError, match="Only explicit row"):
        AnalyticalGoal("kpi", aggregation="sum")


def test_renderer_flags_distinguish_existing_and_future_families():
    assert plan_table(fixture("category_comparison.csv"), "compare").selected_candidate.renderable
    assert plan_table(fixture("time_series.csv"), "growth").selected_candidate.renderable
    assert plan_table(fixture("category_shares.json"), "shares").selected_candidate.renderable
    assert plan_table(fixture("reference_201.csv")).selected_candidate.renderable


@pytest.mark.parametrize("goal", [AnalyticalGoal(measures=("unknown",)),
    AnalyticalGoal(measures=("category",)), AnalyticalGoal(measures=("value", "value")),
    AnalyticalGoal(dimensions=("value",))])
def test_bad_explicit_field_selection_fails_without_silent_fallback(goal):
    with pytest.raises(ValueError):
        plan_table(data(["category", "value"], [["A", 1], ["B", 2]]), goal)


def test_empty_untyped_input_has_explanatory_table_and_no_fabricated_chart():
    empty = Table("empty", ["note"], [], [], [])
    plan = plan_table(empty, "growth")
    assert kinds(plan) == {"table"} and plan.row_count == 0
    assert plan.selected_candidate.value is None
    assert "0 строк" in plan.selected_candidate.reason
