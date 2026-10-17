"""Pure, deterministic analytical choices, independent of presentation styling.

No conclusions, aggregations of business measures or chart data are invented here.
``renderable`` means the visualization family has an existing renderer, not that
this new plan is wired into the application. Grouped/histogram/scatter need adapters.
Source lines are provenance only and intentionally excluded from the content hash.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from typing import Literal

from designer.insights.profile import DatasetProfile, profile_table
from designer.insights.table import Table, parse_number

GoalKind = Literal["auto", "trend", "comparison", "shares", "distribution", "relationship", "reference", "kpi"]
VisualKind = Literal["table", "line", "bar", "column", "pie", "histogram", "scatter", "grouped_column", "kpi"]


@dataclass(frozen=True)
class AnalyticalGoal:
    kind: GoalKind = "auto"
    text: str = ""
    dimensions: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    aggregation: Literal["none", "count_rows"] = "none"

    def __post_init__(self):
        if self.kind not in {"auto", "trend", "comparison", "shares", "distribution", "relationship", "reference", "kpi"}:
            raise ValueError("Unknown analytical goal")
        if not isinstance(self.dimensions, tuple) or not isinstance(self.measures, tuple):
            raise ValueError("Selected fields must be immutable tuples")
        if self.aggregation not in {"none", "count_rows"}:
            raise ValueError("Only explicit row counting is a safe automatic KPI aggregation")


@dataclass(frozen=True)
class VisualizationCandidate:
    kind: VisualKind
    score: int
    reason: str
    required_fields: tuple[str, ...]
    dimension_fields: tuple[str, ...]
    measure_fields: tuple[str, ...]
    row_lines: tuple[int, ...]
    excluded_row_lines: tuple[int, ...]
    warnings: tuple[str, ...]
    renderable: bool
    denominator: Decimal | None = None
    denominator_field: str | None = None
    aggregation: str = "none"
    value: Decimal | None = None


@dataclass(frozen=True)
class AnalyticalPlan:
    content_hash: str
    row_count: int
    column_count: int
    goal: AnalyticalGoal
    selected_fields: tuple[str, ...]
    candidates: tuple[VisualizationCandidate, ...]
    selected_candidate: VisualizationCandidate
    warnings: tuple[str, ...]


_GOALS = (
    ("reference", r"справоч|lookup|reference|найти знач|таблиц.*знач"),
    ("relationship", r"взаимосвяз|корреляц|зависим|correlat|relationship|scatter"),
    ("distribution", r"распределен|распределён|гистограмм|distribution|histogram"),
    ("shares", r"дол[яиюь]|структур|shares?|proportion|composition"),
    ("comparison", r"сравн|compare|comparison|план.*факт|факт.*план|target.*actual|actual.*target"),
    ("trend", r"рост|динамик|изменен|изменён|growth|trend|over time"),
)
_TIME_NAME = re.compile(r"(?:^|[\W_])(?:date|time|period|year|month|дата|время|период|год|месяц)(?:$|[\W_])", re.I)
_PAIR = re.compile(r"(?:^|[\W_])(actual|target|planned|plan|факт|план)(?=$|[\W_])", re.I)
_TOTAL = re.compile(r"(?:^|[\W_])(?:total|всего|итого)(?:$|[\W_])", re.I)


def parse_goal(text: str) -> AnalyticalGoal:
    if re.search(r"count\s+(?:the\s+)?rows|row\s+count|количество\s+строк|число\s+строк", text, re.I):
        return AnalyticalGoal("kpi", text, aggregation="count_rows")
    for kind, pattern in _GOALS:
        if re.search(pattern, text, re.I):
            return AnalyticalGoal(kind, text)
    if re.search(r"\bkpi\b|ключев.*показател|итого|total", text, re.I):
        return AnalyticalGoal("kpi", text)
    return AnalyticalGoal(text=text)


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _content_hash(table: Table, profile: DatasetProfile) -> str:
    def cell(index: int, raw: str):
        value = raw.strip()
        number = parse_number(value)
        if profile.columns[index].type == "numeric" and number is not None:
            # Preserve a cell's unit, even when the numeric parser strips its suffix.
            unit = re.search(r"(?:₽|руб\.?|р\.|\$|€|%)\s*$", value, re.I)
            return ["number", _decimal_text(number), unit.group().strip() if unit else ""]
        return ["text", value]
    payload = [table.headers, [[cell(i, value) for i, value in enumerate(row)] for row in table.rows]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _time_key(value: str) -> tuple[str, str]:
    """Canonical key and precision for the date forms accepted by profile_table."""
    value = value.strip()
    quarter = re.fullmatch(r"(?:Q([1-4]) (\d{4})|(\d{4}) Q([1-4]))", value, re.I)
    if quarter:
        return "quarter", (quarter[2] or quarter[3]) + "-" + (quarter[1] or quarter[4])
    if re.fullmatch(r"\d{4}", value):
        return "year", value
    for pattern, fmt, precision in ((r"\d{4}-\d{2}", "%Y-%m", "month"),
                                   (r"\d{2}\.\d{4}", "%m.%Y", "month"),
                                   (r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y", "day"),
                                   (r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}", "%d.%m.%Y %H:%M", "datetime")):
        if re.fullmatch(pattern, value):
            return precision, dt.datetime.strptime(value, fmt).isoformat()
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if len(value) == 10:
        return "day", parsed.isoformat()
    if parsed.tzinfo is not None:
        return "datetime_utc", parsed.astimezone(dt.timezone.utc).isoformat()
    return "datetime", parsed.isoformat()


def plan_table(table: Table, goal: AnalyticalGoal | str = "") -> AnalyticalPlan:
    """Rank at most three valid choices; no template/theme/model is an input.

    Explicit field requests are validated, never silently replaced. Automatic choices
    prefer the first detected measure/category and disclose ambiguity. No repeated
    labels are aggregated automatically. A pie describes only the observed sum;
    explicit repeated total columns must agree with that sum. Numeric KPI sums are
    deliberately absent because a profile cannot establish measure additivity.
    """
    goal = parse_goal(goal) if isinstance(goal, str) else goal
    if not isinstance(goal, AnalyticalGoal):
        raise TypeError("goal must be text or AnalyticalGoal")
    if len(set(table.headers)) != len(table.headers) or any(not h.strip() for h in table.headers):
        raise ValueError("Column names must be nonempty and unique")
    if len(table.lines) != len(table.rows) or len(set(table.lines)) != len(table.lines):
        raise ValueError("Every source row needs a unique line reference")
    profile = profile_table(table)
    positions = {name: i for i, name in enumerate(table.headers)}
    for name in (*goal.dimensions, *goal.measures):
        if name not in positions:
            raise ValueError(f"Unknown selected field: {name}")
    if len(set(goal.dimensions + goal.measures)) != len(goal.dimensions + goal.measures):
        raise ValueError("Selected fields must be distinct")
    if any(name not in profile.numeric_candidates for name in goal.measures):
        raise ValueError("Selected measures must be numeric, non-identifier profile candidates")
    if any(name not in (*profile.category_candidates, *profile.datetime_candidates) for name in goal.dimensions):
        raise ValueError("Selected dimensions must be category or temporal profile candidates")
    if len(goal.dimensions) > 1:
        raise ValueError("This planner supports one explicitly selected dimension; multiple dimensions need a grouping policy")

    warnings: list[str] = []
    measures = goal.measures or tuple(n for n in profile.numeric_candidates if not _TOTAL.search(n))
    if not measures and not goal.measures:
        measures = profile.numeric_candidates
    categories = tuple(n for n in (goal.dimensions or profile.category_candidates) if n in profile.category_candidates)
    metric = measures[0] if measures else None
    category = categories[0] if categories else None
    if len(measures) > 1 and not goal.measures:
        warnings.append(f"Multiple measures: default primary field is '{metric}'; no mixed-unit sum is assumed.")
    if len(categories) > 1 and not goal.dimensions:
        warnings.append(f"Multiple category axes: default field is '{category}'; other dimensions are not aggregated.")
    time_axes = tuple(n for n in (goal.dimensions or profile.datetime_candidates) if n in profile.datetime_candidates)
    axis = time_axes[0] if len(time_axes) == 1 else None
    if len(time_axes) > 1:
        warnings.append("Ambiguous temporal axis: multiple date columns; select one explicitly.")
    elif axis is None and any(_TIME_NAME.search(n) for n in table.headers):
        warnings.append("No unambiguous parsed temporal axis; text periods are not treated as a time series.")
    for col in profile.columns:
        if col.numeric_outlier_count:
            warnings.append(f"'{col.name}' has {col.numeric_outlier_count} IQR outlier(s); all are retained.")

    def complete(fields: tuple[str, ...]) -> list[int]:
        return [i for i, row in enumerate(table.rows)
                if all(row[positions[n]].strip() and
                       (n not in profile.numeric_candidates or parse_number(row[positions[n]]) is not None)
                       for n in fields)]

    def numbers(field: str, indices: list[int]) -> list[Decimal]:
        return [parse_number(table.rows[i][positions[field]]) for i in indices]

    candidates: list[VisualizationCandidate] = []

    def add(kind: VisualKind, base: int, preferred: tuple[str, ...], reason: str,
            dims: tuple[str, ...] = (), metrics: tuple[str, ...] = (), indices: list[int] | None = None,
            limits: tuple[str, ...] = (), denominator: Decimal | None = None,
            denominator_field: str | None = None, aggregation: str = "none", value: Decimal | None = None,
            required_fields: tuple[str, ...] | None = None):
        denominator_fields = (denominator_field,) if denominator_field else ()
        fields = required_fields if required_fields is not None else tuple(dict.fromkeys((*dims, *metrics, *denominator_fields)))
        indices = complete(fields) if indices is None else indices
        kept = set(indices)
        excluded = tuple(table.lines[i] for i in range(len(table.rows)) if i not in kept)
        if excluded:
            limits += (f"{len(excluded)} row(s) with missing/unparseable selected cells excluded; see excluded_row_lines. No zero filling.",)
        candidates.append(VisualizationCandidate(
            kind, base + (50 if goal.kind in preferred else 0), reason, fields, dims, metrics,
            tuple(table.lines[i] for i in indices), excluded, limits,
            kind not in {"scatter", "grouped_column"}, denominator, denominator_field, aggregation, value))

    if axis and metric:
        indices = complete((axis, metric))
        try:
            keys = [_time_key(table.rows[i][positions[axis]]) for i in indices]
        except ValueError:
            keys = []
        if (profile.columns[positions[axis]].confidence == 1 and len(indices) >= 2 and len(keys) == len(indices)
                and len(set(keys)) == len(keys) and len({k[0] for k in keys}) == 1):
            ordered = [i for _, i in sorted(zip(keys, indices))]
            add("line", 90, ("trend",), f"'{axis}' provides {len(indices)} unique ordered periods for '{metric}'.",
                (axis,), (metric,), ordered, ("Unequal time spacing is possible; do not imply interpolation across missing periods.",))
            add("column", 65, ("comparison",), f"Compare '{metric}' across the {len(indices)} observed '{axis}' periods.",
                (axis,), (metric,), ordered)
        else:
            warnings.append(f"'{axis}': duplicate/mixed-precision periods or fewer than two complete rows; no line chart.")
    elif goal.kind == "trend":
        warnings.append("Trend needs a clear temporal axis and a numeric measure; the requested trend is unsupported.")

    if category and metric:
        indices = complete((category, metric))
        labels = [table.rows[i][positions[category]].strip() for i in indices]
        unique = len(set(labels)) == len(labels)
        if len(indices) >= 2 and unique:
            add("bar", 80, ("comparison",), f"Compare '{metric}' across {len(indices)} unique '{category}' categories.", (category,), (metric,), indices,
                ("Split or paginate many categories before rendering.",) if len(indices) > 12 else ())
            add("column", 70, ("comparison",), f"Vertical comparison of '{metric}' by '{category}', one observation per category.", (category,), (metric,), indices)
            values = numbers(metric, indices)
            with localcontext() as context:
                context.prec = max(32, max(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values) + 12)
                total = sum(values, Decimal(0))
            denominator_fields = [n for n in profile.numeric_candidates if _TOTAL.search(n) and
                                  _TOTAL.sub("", n).strip(" _").casefold() == metric.casefold()]
            denom_field = denominator_fields[0] if len(denominator_fields) == 1 else None
            declared_ok = not denominator_fields or (denom_field is not None and
                len(complete((denom_field,))) == len(table.rows) and
                set(numbers(denom_field, list(range(len(table.rows))))) == {total})
            if len(indices) <= 6 and all(v >= 0 for v in values) and total > 0 and declared_ok:
                add("pie", 55, ("shares",), f"'{metric}' has {len(indices)} nonnegative categories in '{category}'; denominator is the observed sum {_decimal_text(total)}.",
                    (category,), (metric,), indices,
                    ("Shares refer to observed rows only; mutual exclusivity and completeness of the population are not established.",),
                    denominator=total, denominator_field=denom_field, aggregation="share_of_observed_sum")
            elif goal.kind == "shares":
                warnings.append(f"No pie for '{metric}': requires 2–6 categories, nonnegative values, positive sum and agreement with any declared total.")
        else:
            warnings.append(f"'{category}': repeated labels or fewer than two complete rows; choose an explicit grouping/aggregation before category charts.")

        # Only structurally matched actual/target columns are safely comparable here.
        pairs = [(a, b) for j, a in enumerate(measures) for b in measures[j + 1:]
                 if _PAIR.search(a) and _PAIR.search(b) and
                 _PAIR.search(a)[1].lower() != _PAIR.search(b)[1].lower() and
                 _PAIR.sub("", a).strip(" _").casefold() == _PAIR.sub("", b).strip(" _").casefold()]
        if pairs:
            pair = pairs[0]
            indices = complete((category, *pair))
            if len(indices) >= 2 and len({table.rows[i][positions[category]] for i in indices}) == len(indices):
                add("grouped_column", 85, ("comparison",), f"Matched actual/target fields '{pair[0]}' and '{pair[1]}' share '{category}'; compare complete pairs without summing them.",
                    (category,), pair, indices, ("Grouped-column plan adapter is not implemented; verify units before rendering.",))

    if metric:
        indices = complete((metric,))
        if len(indices) >= 5 and len(set(numbers(metric, indices))) >= 2:
            add("histogram", 60 if category or axis else 90, ("distribution",),
                f"'{metric}' has {len(indices)} numeric observations with variation; bin their frequencies, not category totals.",
                metrics=(metric,), indices=indices, limits=("All complete observations, including IQR outliers, are retained in the frequency bins.",))
        elif goal.kind == "distribution":
            warnings.append(f"Histogram needs at least five numeric observations and two distinct values in '{metric}'.")
    if len(measures) >= 2:
        pair = tuple(measures[:2])
        indices = complete(pair)
        if len(indices) >= 5 and all(len(set(numbers(n, indices))) >= 2 for n in pair):
            add("scatter", 75, ("relationship",), f"'{pair[0]}' and '{pair[1]}' have {len(indices)} complete numeric pairs with variation.",
                metrics=pair, indices=indices, limits=("Scatter renderer is not implemented. Association is not causation; no correlation value is asserted.",))
        elif goal.kind == "relationship":
            warnings.append("Scatter needs at least five complete pairs and variation in both distinct numeric measures.")
    elif goal.kind == "relationship":
        warnings.append("Scatter needs two distinct numeric measures; identifiers are not measures.")

    if goal.kind == "kpi" and goal.aggregation == "count_rows" and table.rows:
        add("kpi", 95, ("kpi",), f"Count of source records: {len(table.rows)} rows, including incomplete records; not a sum of business measures.",
            indices=list(range(len(table.rows))), aggregation="count_rows", value=Decimal(len(table.rows)))
    elif goal.kind == "kpi":
        warnings.append("No safe KPI aggregation was specified; numeric business measures are not summed automatically.")

    families = {"trend": {"line"}, "comparison": {"bar", "column", "grouped_column"}, "shares": {"pie"},
                "distribution": {"histogram"}, "relationship": {"scatter"}, "kpi": {"kpi"}}
    if goal.kind in families and not any(c.kind in families[goal.kind] for c in candidates):
        warnings.append(f"Requested '{goal.kind}' is not supported by the detected selected fields; alternatives are shown without inventing data.")

    add("table", 100 if not measures or goal.kind == "reference" else 10, ("reference",),
        f"Reference view of {len(table.rows)} rows and {len(table.headers)} columns; original values are retained, without aggregation.",
        dims=tuple(n for n in table.headers if n not in profile.numeric_candidates), metrics=profile.numeric_candidates,
        required_fields=tuple(table.headers), indices=list(range(len(table.rows))),
        limits=("Paginate the reference table before rendering; never squeeze all rows onto one slide.",) if len(table.rows) > 20 else ())
    shared = tuple(dict.fromkeys(warnings))
    candidates = [replace(c, warnings=tuple(dict.fromkeys((*shared, *c.warnings))),
                          reason=c.reason + (" Limitations: " + " ".join(dict.fromkeys((*shared, *c.warnings)))
                                             if shared or c.warnings else "")) for c in candidates]
    ranked = tuple(sorted(candidates, key=lambda c: (-c.score, c.kind, c.required_fields))[:3])
    return AnalyticalPlan(_content_hash(table, profile), len(table.rows), len(table.headers), goal,
                          ranked[0].required_fields, ranked, ranked[0], shared)
