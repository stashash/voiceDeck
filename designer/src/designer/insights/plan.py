"""Pure, deterministic analytical choices, independent of presentation styling.

Conclusions describe observed values only; no business causes are inferred.
``renderable`` means the visualization has a materializer and both export renderers.
Source lines are provenance only and intentionally excluded from the content hash.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from typing import Literal

from designer.insights.profile import DatasetProfile, profile_table
from designer.insights.labels import field_label
from designer.insights.table import Table, parse_number

GoalKind = Literal["auto", "trend", "comparison", "shares", "distribution", "relationship", "reference", "kpi"]
VisualKind = Literal["table", "line", "bar", "column", "pie", "histogram", "scatter", "grouped_column", "stacked_column", "kpi"]


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
    headline: str = ""
    statement: str = ""
    number: str = ""
    formula: str = ""


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
MAX_CATEGORY_POINTS = 12


def chart_number_supported(value: Decimal) -> bool:
    """The float-backed chart contract must retain the source decimal value."""
    converted = float(value)
    return math.isfinite(converted) and Decimal(str(converted)) == value


def _describe(table: Table, candidate: VisualizationCandidate) -> VisualizationCandidate:
    """Attach deterministic observations with the same row scope as the chart."""
    if not candidate.measure_fields or candidate.kind in {"table", "kpi", "scatter", "stacked_column"}:
        return candidate
    positions = {name: i for i, name in enumerate(table.headers)}
    rows = dict(zip(table.lines, table.rows))
    selected = [rows[line] for line in candidate.row_lines]
    metric = candidate.measure_fields[0]
    values = [parse_number(row[positions[metric]]) for row in selected]
    if not values or any(value is None for value in values):
        return candidate
    label, unit = field_label(metric)
    suffix = f" {unit}" if unit else ""
    # Subtraction of mixed-scale decimals can require more than the default 28 digits.
    with localcontext() as context:
        context.prec = max(32, max(v.adjusted() for v in values) - min(v.as_tuple().exponent for v in values) + 16)
        if candidate.kind == "line":
            dimension = candidate.dimension_fields[0]
            first, last = (selected[i][positions[dimension]] for i in (0, -1))
            change = values[-1] - values[0]
            number = ("+" if change > 0 else "") + _decimal_text(change)
            change_suffix = " п. п." if unit == "%" else suffix
            headline = f"{label}: {number}{change_suffix} между {first} и {last}"
            statement = (f"{label}: от {_decimal_text(values[0])}{suffix} ({first}) до "
                         f"{_decimal_text(values[-1])}{suffix} ({last}); изменение между крайними "
                         f"наблюдениями {number}{change_suffix}. Промежуточные значения могут колебаться.")
            formula = f"{metric}: последнее − первое = {_decimal_text(values[-1])} − {_decimal_text(values[0])} = {number}{change_suffix}; без агрегации."
            if values[0] > 0:
                relative = change * 100 / values[0]
                relative_text = ("+" if relative > 0 else "") + format(relative, ".2f")
                headline += f" ({relative_text}%)"
                statement += f" Относительно первого наблюдения: {relative_text}% (округлено до 2 знаков)."
                formula += f" Относительное изменение = ({number}) / {_decimal_text(values[0])} × 100 = {relative_text}%."
        elif candidate.kind == "histogram":
            low, high = min(values), max(values)
            number = _decimal_text(high)
            headline = f"Распределение {label}: от {_decimal_text(low)} до {number}{suffix}"
            statement = (f"{len(values)} полных наблюдений {label}: минимум {_decimal_text(low)}{suffix}, "
                         f"максимум {number}{suffix}; все наблюдения, включая выбросы, сохранены.")
            formula = f"min({metric}) = {_decimal_text(low)}; max({metric}) = {number}; n = {len(values)}."
        else:
            maximum = max(values)
            leaders = [selected[i][positions[candidate.dimension_fields[0]]] for i, value in enumerate(values) if value == maximum]
            leader = f"«{leaders[0]}»" if len(leaders) == 1 else f"{len(leaders)} категории"
            number = _decimal_text(maximum)
            if candidate.kind == "pie":
                denominator = candidate.denominator
                share = maximum * 100 / denominator
                percentage = format(share, ".2f")
                headline = f"{label}: {leader} — {percentage}% показанной суммы"
                statement = (f"Максимальная доля: {leader}, {number}{suffix} из {_decimal_text(denominator)}{suffix} "
                             f"({percentage}%, округлено до 2 знаков). Доли относятся только к показанным строкам.")
                formula = f"{number} / {_decimal_text(denominator)} × 100 = {percentage}% (округлено до 2 знаков); знаменатель — сумма показанных значений."
                composition = "; ".join(
                    f"«{row[positions[candidate.dimension_fields[0]]]}»: {format(value * 100 / denominator, '.2f')}%"
                    for row, value in zip(selected, values))
                statement += f" Структура показанной суммы: {composition}."
                number = percentage
            else:
                headline = f"{label}: максимум {number}{suffix} — {leader}"
                statement = (f"Среди {len(values)} полных наблюдений по полю «{metric}» максимальное значение "
                             f"{number}{suffix}: {leader}." + (" Максимум разделяют несколько категорий." if len(leaders) > 1 else ""))
                formula = f"max({metric}) = {number}; совпадений максимума: {len(leaders)}; без суммирования категорий."
    return replace(candidate, headline=headline, statement=statement, number=number, formula=formula)


def parse_goal(text: str) -> AnalyticalGoal:
    """Recognize analytical intent without treating appendix placement as analysis.

    A mixed-content brief can contain several legitimate analytical tasks. Its
    datasets need their own profile-based choices instead of the first regex win.
    Raw wording remains attached to the goal for provenance and other constraints.
    """
    count_rows = bool(re.search(r"count\s+(?:the\s+)?rows|row\s+count|количество\s+строк|число\s+строк", text, re.I))
    kinds = {"kpi"} if count_rows else set()
    for kind, pattern in _GOALS:
        for match in re.finditer(pattern, text, re.I):
            if kind == "reference":
                # Scope the mention to its sentence/clause. "Move the reference
                # table to the appendix" is a layout constraint, not a request
                # to replace every analytical view with a reference table.
                left = max((text.rfind(mark, 0, match.start()) for mark in ".!?;\n"), default=-1) + 1
                right = min((position for mark in ".!?;\n"
                             if (position := text.find(mark, match.end())) != -1), default=len(text))
                clause = text[left:right]
                appendix = re.search(r"приложени|appendix|appendices", clause, re.I)
                placement = re.search(r"вынес|вынеси|перенес|перенеси|помест|размест|постав|остав|отнес|\bmove\b|\bput\b|\bplace\b|relegat", clause, re.I)
                display = re.search(r"покаж|показ|show|анализ|найд|найт|lookup|рассмотр", clause, re.I)
                if appendix and (placement or not display):
                    continue
            kinds.add(kind)
    if re.search(r"\bkpi\b|ключев.*показател", text, re.I):
        kinds.add("kpi")
    if len(kinds) == 1:
        kind = next(iter(kinds))
        return AnalyticalGoal(kind, text, aggregation="count_rows" if kind == "kpi" and count_rows else "none")
    if not kinds and re.search(r"итого|\btotal\b", text, re.I):
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
    payload = [table.headers, [[cell(i, value) for i, value in enumerate(row)] for row in table.rows], table.context]
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
        renderable = True
        if kind in {"line", "bar", "column", "pie", "histogram", "scatter", "grouped_column", "stacked_column"}:
            exact = [v for field in metrics for v in numbers(field, indices)]
            renderable = all(chart_number_supported(v) for v in exact)
            if kind == "stacked_column":
                renderable = renderable and all(math.isfinite(sum(float(numbers(field, [i])[0]) for field in metrics)) for i in indices)
            if kind == "pie":
                renderable = renderable and math.isfinite(sum(float(v) for v in exact))
            if not renderable:
                limits += ("Numeric precision/range exceeds the export format; choose the reference table.",)
            if goal.measures and set(metrics) != set(goal.measures):
                renderable = False
                limits += ("This view omits explicitly selected measures; choose a view that preserves all selected fields.",)
            # parse_number deliberately accepts suffixes, but stripping them is
            # not a unit conversion. Preserve currency/rate cells in a table if
            # the chart header cannot faithfully label every selected value.
            aliases = {"$": "USD", "€": "EUR", "₽": "RUB", "руб": "RUB", "руб.": "RUB", "р.": "RUB"}
            for field in metrics:
                declared = field_label(field)[1]
                declared = aliases.get(declared, declared)
                suffixes = [match.group().strip().casefold() for i in indices
                            if (match := re.search(r"(?:₽|руб\.?|р\.|\$|€|%)\s*$", table.rows[i][positions[field]], re.I))]
                if any(aliases.get(suffix, suffix.upper()) != declared for suffix in suffixes):
                    renderable = False
                    limits += (f"'{field}' has cell units missing from or conflicting with its header; the reference table preserves the literal units without conversion.",)
        if kind in {"bar", "column", "grouped_column", "stacked_column"} and len(indices) > MAX_CATEGORY_POINTS:
            renderable = False
            limits += (f"More than {MAX_CATEGORY_POINTS} categories cannot be read safely on one slide; choose the paginated reference table. No categories are dropped or grouped.",)
        candidates.append(VisualizationCandidate(
            kind, base + (50 if goal.kind in preferred else 0), reason, fields, dims, metrics,
            tuple(table.lines[i] for i in indices), excluded, limits,
            renderable, denominator, denominator_field, aggregation, value))

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
            add("bar", 80, ("comparison",), f"Compare '{metric}' across {len(indices)} unique '{category}' categories.", (category,), (metric,), indices)
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
            # Percent levels with an observed sum other than 100 are not a
            # complete percentage composition; normalizing 20% and 30% into
            # 40% and 60% silently changes their denominator.
            percentage_ok = field_label(metric)[1] != "%" or total == 100
            if len(indices) <= 6 and all(v >= 0 for v in values) and total > 0 and declared_ok and percentage_ok:
                add("pie", 95 if denom_field else 55, ("shares",), f"'{metric}' has {len(indices)} nonnegative categories in '{category}'; denominator is the observed sum {_decimal_text(total)}.",
                    (category,), (metric,), indices,
                    ("Shares refer to observed rows only; mutual exclusivity and completeness of the population are not established.",),
                    denominator=total, denominator_field=denom_field, aggregation="share_of_observed_sum")
            elif goal.kind == "shares":
                warnings.append(f"No pie for '{metric}': requires 2–6 categories, nonnegative values, positive sum and agreement with any declared total.")
                if not percentage_ok:
                    warnings.append("Percentage values do not sum to 100; their original denominator must not be replaced by normalization of the observed sum.")
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
            # A paired chart drops known single-series values if either partner is
            # missing. Prefer a readable all-row table; never turn absence into zero.
            incomplete_pair = len(indices) < len(table.rows)
            if incomplete_pair and goal.kind in {"auto", "comparison"}:
                warnings.append("Incomplete paired measures: use the reference table to preserve every known value and every missing cell. No zero filling.")
                add("table", 200, (), "Paired comparison has missing cells; the table preserves all rows and each available series value.",
                    dims=tuple(n for n in table.headers if n not in profile.numeric_candidates),
                    metrics=profile.numeric_candidates, required_fields=tuple(table.headers),
                    indices=list(range(len(table.rows))))
            elif not incomplete_pair and len(indices) >= 2 and len({table.rows[i][positions[category]] for i in indices}) == len(indices):
                add("grouped_column", 85, ("comparison",), f"Matched actual/target fields '{pair[0]}' and '{pair[1]}' share '{category}'; compare complete pairs without summing them.",
                    (category,), pair, indices, ("Compare paired measures without summing them; verify units before interpretation.",))

        # A shared unit is necessary but does not prove additivity. Only a literal
        # stacking request authorizes this composition view, never a generic shares goal.
        if re.search(r"stacked|\bсостав\b|накопительн", goal.text, re.I):
            units = [field_label(n)[1] for n in measures]
            indices = complete((category, *measures))
            valid = (2 <= len(measures) <= 5 and len(set(units)) == 1 and bool(units[0])
                     and len(indices) >= 2 and len({table.rows[i][positions[category]].strip() for i in indices}) == len(indices)
                     and all(v >= 0 for n in measures for v in numbers(n, indices)) and not pairs)
            if valid:
                add("stacked_column", 150, (), "Explicit stacked composition request with matching declared units; no normalization.",
                    (category,), measures, indices,
                    ("Values are stacked as components; additivity and mutual exclusivity are user assumptions, not inferred facts.",),
                    aggregation="stack_components")
            else:
                warnings.append("Stacked composition requires 2–5 nonnegative component measures with matching explicit units and unique categories; actual/target pairs are not components.")

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
                metrics=pair, indices=indices, limits=("Association is not causation; no correlation value is asserted.",))
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

    if not any(c.kind == "table" for c in candidates):
        add("table", 100 if not measures or goal.kind == "reference" else 10, ("reference",),
            f"Reference view of {len(table.rows)} rows and {len(table.headers)} columns; original values are retained, without aggregation.",
            dims=tuple(n for n in table.headers if n not in profile.numeric_candidates), metrics=profile.numeric_candidates,
            required_fields=tuple(table.headers), indices=list(range(len(table.rows))),
            limits=("Paginate the reference table before rendering; never squeeze all rows onto one slide.",) if len(table.rows) > 20 else ())
    best = max(candidates, key=lambda c: c.score)
    # High-cardinality text is not a categorical axis in the conservative profile.
    # An explicit comparison must not silently become a histogram in that case.
    unsupported_goal = goal.kind == "comparison" and not any(c.renderable and c.kind in families[goal.kind] for c in candidates)
    if not best.renderable or unsupported_goal:
        if not best.renderable:
            warnings.extend(best.warnings)
            warnings.append("The preferred chart is unsafe to render; the reference table preserves all source values.")
        else:
            warnings.append("The requested analysis has no safe chart; the reference table preserves all source values.")
        candidates = [replace(c, score=best.score + 1) if c.kind == "table" else c for c in candidates]
    shared = tuple(dict.fromkeys(warnings))
    candidates = [replace(c, warnings=tuple(dict.fromkeys((*shared, *c.warnings))),
                          reason=c.reason + (" Limitations: " + " ".join(dict.fromkeys((*shared, *c.warnings)))
                                             if shared or c.warnings else "")) for c in candidates]
    ranked = tuple(_describe(table, c) for c in sorted(candidates, key=lambda c: (-c.score, c.kind, c.required_fields))[:3])
    return AnalyticalPlan(_content_hash(table, profile), len(table.rows), len(table.headers), goal,
                          ranked[0].required_fields, ranked, ranked[0], shared)
