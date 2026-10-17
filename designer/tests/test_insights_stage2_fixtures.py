from __future__ import annotations

import json
from pathlib import Path

from designer.insights.profile import profile_table
from designer.insights.table import read_table


FIXTURES = Path(__file__).parent / "fixtures" / "semantic_stage2"
DATA_FILES = {
    "category_comparison.csv",
    "category_shares.json",
    "distribution.csv",
    "embedded_table.md",
    "missing_zero.csv",
    "reference_201.csv",
    "time_series.csv",
}


def load_profile(filename: str):
    path = FIXTURES / filename
    table = read_table(path.read_bytes(), path.name)
    return table, profile_table(table)


def test_all_stage2_fixture_datasets_parse_and_profile():
    assert {path.name for path in FIXTURES.iterdir() if path.is_file() and path.name != "README.md"} == DATA_FILES
    for filename in sorted(DATA_FILES):
        table, profile = load_profile(filename)
        assert table.rows
        assert profile.row_count == len(table.rows)
        assert profile.source_name == filename


def test_reference_table_is_a_non_metric_lookup():
    table, profile = load_profile("reference_201.csv")
    assert len(table.rows) == 201
    assert table.headers == ["reference_id", "label"]
    assert profile.numeric_candidates == ()


def test_distribution_has_one_numeric_iqr_outlier():
    table, profile = load_profile("distribution.csv")
    value_index = table.headers.index("value")
    value_profile = profile.columns[value_index]
    assert profile.numeric_candidates == ("value",)
    assert value_profile.numeric_outlier_count == 1
    assert sum(row[value_index] == "95" for row in table.rows) == 1


def test_missing_cells_remain_distinct_from_real_zeros():
    table, profile = load_profile("missing_zero.csv")
    actual_index = table.headers.index("actual_units")
    planned_index = table.headers.index("planned_units")
    assert table.rows[0][actual_index] == "0"
    assert table.rows[1][actual_index] == ""
    assert table.rows[3][actual_index] == "0"
    assert table.rows[2][planned_index] == ""
    assert profile.columns[actual_index].missing_count == 1
    assert profile.columns[planned_index].missing_count == 1


def test_markdown_table_rows_and_source_filename_are_preserved():
    table, profile = load_profile("embedded_table.md")
    assert len(table.rows) == 3
    assert table.name == "embedded_table.md"
    assert profile.source_name == "embedded_table.md"
    assert "Source: synthetic test data" in (FIXTURES / "embedded_table.md").read_text(encoding="utf-8-sig")


def test_category_shares_preserve_exact_full_denominator():
    table, profile = load_profile("category_shares.json")
    payload = json.loads((FIXTURES / "category_shares.json").read_text(encoding="utf-8-sig"))
    assert table.rows and profile.row_count == len(table.rows)
    assert payload["columns"] == ["outcome", "tickets", "total_tickets"]
    denominator_index = table.headers.index("total_tickets")
    count_index = table.headers.index("tickets")
    assert {int(row[denominator_index]) for row in table.rows} == {1000}
    assert sum(int(row[count_index]) for row in table.rows) == 620 + 250 + 130 == 1000


def test_time_series_has_six_ordered_periods():
    table, profile = load_profile("time_series.csv")
    periods = [row[table.headers.index("period")] for row in table.rows]
    assert len(periods) == 6
    assert periods == sorted(periods)
    assert profile.datetime_candidates == ("period",)
