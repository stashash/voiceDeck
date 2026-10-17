"""Deterministic ingestion and profiling: provenance, rejection and semantic limits."""
import io
import json
from decimal import Decimal

import pytest

from designer.insights.profile import profile_table
from designer.insights.table import MAX_BYTES, MAX_CELL, MAX_COLS, MAX_ROWS, TableError, read_table, read_tables


def json_table(value):
    return read_table(json.dumps(value, ensure_ascii=False).encode(), "source.json")


def test_json_objects_union_keys_null_zero_and_source_indices():
    table = json_table([{"name": "A", "amount": 0}, {"name": "B", "amount": None},
                        {"name": "C", "note": "=1+1"}])
    assert table.headers == ["name", "amount", "note"]
    assert table.lines == [1, 2, 3] and table.name == "source.json" and table.sheet == ""
    assert table.rows == [["A", "0", ""], ["B", "", ""], ["C", "", "=1+1"]]
    assert table.numbers[0][1] == Decimal(0) and table.numbers[2][2] is None


def test_json_explicit_schema_preserves_all_empty_rows_columns_and_exact_numbers():
    table = read_table(b'{"columns":["value","empty"],"rows":[[123456789.123456789,null],[null,null]]}', "a.json")
    assert table.headers == ["value", "empty"] and table.lines == [1, 2]
    assert table.rows == [["123456789.123456789", ""], ["", ""]]


@pytest.mark.parametrize("payload", [[], [1, 2], [{"a": {"nested": 1}}, {"a": 2}],
    {"columns": ["a", "a"], "rows": [[1, 2], [3, 4]]},
    {"columns": ["a"], "rows": [[1, 2], [3]]},
    {"columns": [1], "rows": [[1], [2]]},
    {"columns": ["a"], "rows": [[1], [2]], "metadata": {}},
    {"columns": [""], "rows": [[1], [2]]}])
def test_json_rejects_unsupported_or_ambiguous_schema(payload):
    with pytest.raises(TableError):
        json_table(payload)


@pytest.mark.parametrize("raw", [b'[{"a":1,"a":2},{"a":3}]', b'[NaN, Infinity]',
    b'[{"a":1e999999999},{"a":2}]', b'[{"a":1e9999999999999999999999999},{"a":2}]',
    b'{bad', b'[' * 1100 + b']' * 1100])
def test_json_malformed_and_expansion_are_bounded(raw):
    with pytest.raises(TableError):
        read_table(raw, "a.json")


@pytest.mark.parametrize("extension", ["csv", "txt"])
def test_embedded_csv_with_prose_and_multiline_cell_preserves_physical_lines(extension):
    data = 'Report title\n\nName;Value\n"A\nline";0\n\nB;2\n\nSource: test\n'
    table = read_table(data.encode(), "report." + extension)
    assert table.headers == ["Name", "Value"]
    assert table.lines == [4, 7] and table.rows == [["A\nline", "0"], ["B", "2"]]


def test_markdown_table_embedded_in_prose_with_escaped_pipe():
    data = '# Revenue\n\n| Region | Sales |\n| :--- | ---: |\n| A\\|B | 0 |\n| C | 20 |\n\nSource text'
    table = read_table(data.encode(), "report.md")
    assert table.headers == ["Region", "Sales"] and table.lines == [5, 6]
    assert table.rows == [["A|B", "0"], ["C", "20"]]


@pytest.mark.parametrize("text", [
    'Name;Value\nA;1\nB;2\n\nOther table\nName;Value\nC;3\nD;4',
    'Name;Value\nA;1\nB;2\nC;3;4',
    'Name;Value\nA;1\nB',
    'Name;Value\nA;1\nB;2\nName;Value\nC;3\nD;4',
    'A,B;C\nx,y;z\nu,v;w',
    'Name;Value\nA;1\n"unfinished;2',
    '| Name | Value |\n| --- | --- |\n| A | 1 |\n| B | 2 | 3 |',
    'This is ordinary text.\nIt has no table.\nAnother sentence.',
])
def test_text_rejects_ambiguity_ragged_rows_and_malformed_quoting(text):
    with pytest.raises(TableError):
        read_table(text.encode(), "a.txt")


def test_multiple_markdown_tables_are_rejected():
    block = '| Name | Value |\n| --- | --- |\n| A | 1 |\n| B | 2 |\n'
    with pytest.raises(TableError, match="несколько"):
        read_table((block + '\n' + block).encode(), "a.md")
    with pytest.raises(TableError, match="несколько"):
        read_table((block + '\nName;Value\nA;1\nB;2\n').encode(), "a.md")


@pytest.mark.parametrize("extension", ["csv", "txt", "md", "json", "xlsx"])
def test_all_formats_keep_byte_limit(extension):
    with pytest.raises(TableError, match="1 МБ"):
        read_table(b"x" * (MAX_BYTES + 1), "a." + extension)


@pytest.mark.parametrize("payload", [
    {"columns": ["a"], "rows": [[1]] * (MAX_ROWS + 1)},
    {"columns": [str(i) for i in range(MAX_COLS + 1)], "rows": [[1] * (MAX_COLS + 1)] * 2},
    {"columns": ["a"], "rows": [["x" * (MAX_CELL + 1)], ["b"]]},
    {"columns": ["x" * (MAX_CELL + 1)], "rows": [[1], [2]]},
])
def test_json_limits(payload):
    with pytest.raises(TableError):
        json_table(payload)


def test_text_row_column_and_header_limits():
    for text in ('Name;Value\n' + 'A;1\n' * (MAX_ROWS + 1),
                 ';'.join('C' + str(i) for i in range(MAX_COLS + 1)) + '\n' + (';'.join(['1'] * (MAX_COLS + 1)) + '\n') * 2,
                 'x' * (MAX_CELL + 1) + ';Value\nA;1\nB;2'):
        with pytest.raises(TableError):
            read_table(text.encode(), "a.txt")


def test_xlsx_multiple_tables_sheet_names_and_formula_cache_only():
    from openpyxl import Workbook
    book = Workbook()
    for sheet in [book.active, book.create_sheet("Second")]:
        sheet.append(["Name", "Amount"])
        sheet.append(["A", "=1+1"])
        sheet.append(["B", 0])
    output = io.BytesIO()
    book.save(output)
    tables = read_tables(output.getvalue(), "folder/book.xlsx")
    assert len(tables) == 2 and tables[1].sheet == "Second"
    assert all(t.name == "book.xlsx" and t.lines == [2, 3] for t in tables)
    assert all(t.rows == [["A", ""], ["B", "0"]] for t in tables)


def test_profile_missing_is_not_zero_or_literal_null_and_is_pure():
    table = json_table({"columns": ["amount", "label"], "rows": [[0, "null"], [None, "NA"], [2, " "]]})
    original = [row[:] for row in table.rows]
    profile = profile_table(table)
    assert (profile.row_count, profile.column_count) == (3, 2)
    assert profile.source_name == "source.json" and profile.source_sheet == ""
    assert profile.columns[0].missing_count == 1 and profile.columns[0].cardinality == 2
    assert profile.columns[1].missing_count == 1 and profile.columns[1].cardinality == 2
    assert profile.numeric_candidates == ("amount",) and profile.category_candidates == ("label",)
    assert table.rows == original and profile == profile_table(table)


@pytest.mark.parametrize("header,values", [("customer_id", [1, 2, 3, 100]),
    ("customerId", [1, 2, 3, 100]), ("Код товара", [1, 2, 3, 100]),
    ("postal", ["001", "002", "003", "999"]),
    ("key", ["f47ac10b-58cc-4372-a567-0e02b2c3d479"] * 4)])
def test_ids_are_not_numeric_measures(header, values):
    profile = profile_table(json_table({"columns": [header], "rows": [[v] for v in values]}))
    assert profile.identifier_candidates == (header,) and not profile.numeric_candidates
    assert profile.columns[0].numeric_outlier_count is None


def test_unique_integer_measure_is_not_automatically_an_id():
    profile = profile_table(json_table({"columns": ["revenue"], "rows": [[1], [2], [3], [4]]}))
    assert profile.numeric_candidates == ("revenue",) and not profile.identifier_candidates


def test_dates_years_and_uncertain_time_axis():
    table = json_table([{"date": "2026-02-01", "amount": 0}, {"date": "2026-01-01", "amount": 5}])
    assert profile_table(table).likely_time_axis == "date"
    two_dates = profile_table(json_table([{"date": "2026-01-01", "year": 2025},
                                         {"date": "2026-01-02", "year": 2026}]))
    assert two_dates.datetime_candidates == ("date", "year") and two_dates.likely_time_axis is None
    assert not profile_table(json_table([{"amount": 2025}, {"amount": 2026}])).datetime_candidates


@pytest.mark.parametrize("values", [["2026-02-30", "2026-13-01"], ["01/02/2026", "03/04/2026"],
                                   ["2026-01-01", "not a date"]])
def test_invalid_ambiguous_or_mixed_dates_do_not_produce_time_axis(values):
    profile = profile_table(json_table({"columns": ["date"], "rows": [[v] for v in values]}))
    assert profile.likely_time_axis is None and not profile.datetime_candidates


def test_numeric_confidence_outliers_and_empty_column():
    rows = [[i, None] for i in [0, 1, 2, 3, 4, 5, 6, 7, 100]] + [["unknown", None]]
    profile = profile_table(json_table({"columns": ["amount", "empty"], "rows": rows}))
    amount, empty = profile.columns
    assert amount.type == "numeric" and amount.confidence == 0.9 and amount.numeric_outlier_count == 1
    assert empty.type == "empty" and empty.confidence == 0 and empty.missing_count == 10


def test_constant_numeric_column_has_no_outliers_and_small_sample_is_unscored():
    profile = profile_table(json_table({"columns": ["amount"], "rows": [[0]] * 10}))
    assert profile.columns[0].numeric_outlier_count == 0
    profile = profile_table(json_table({"columns": ["amount"], "rows": [[0], [1000000]]}))
    assert profile.columns[0].numeric_outlier_count is None


def test_high_cardinality_free_text_is_not_category():
    profile = profile_table(json_table([{"description": f"Long distinct prose {i}"} for i in range(25)]))
    assert profile.columns[0].type == "text" and not profile.category_candidates
