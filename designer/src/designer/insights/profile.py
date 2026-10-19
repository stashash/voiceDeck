"""Deterministic dataset description, not statistical or causal conclusions.

Confidence is the matching fraction of nonempty cells, not a calibrated probability.
Only empty/whitespace cells are missing: zero, 'NA' and literal 'null' are data.
Roles and category dependencies are candidates, never proof of aggregation safety.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext

from designer.insights.table import Table, parse_number


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    type: str
    confidence: float
    role_candidates: tuple[str, ...]
    missing_count: int
    cardinality: int
    numeric_outlier_count: int | None
    """Tukey 1.5 IQR rule, linearly interpolated quartiles; None when not applicable."""


@dataclass(frozen=True)
class HierarchyCandidate:
    """Observed child -> parent dependency, not a confirmed business hierarchy."""
    parent: str
    child: str
    parent_count: int
    child_count: int
    row_lines: tuple[int, ...]
    evidence: str = "Every repeated child maps to exactly one parent; no missing pairs."


@dataclass(frozen=True)
class DatasetProfile:
    source_name: str
    source_sheet: str
    row_count: int
    column_count: int
    columns: tuple[ColumnProfile, ...]
    numeric_candidates: tuple[str, ...]
    category_candidates: tuple[str, ...]
    datetime_candidates: tuple[str, ...]
    identifier_candidates: tuple[str, ...]
    likely_time_axis: str | None
    hierarchy_candidates: tuple[HierarchyCandidate, ...] = ()
    dimension_count: int = 0
    metric_count: int = 0
    hierarchy_count: int = 0


_ID = re.compile(r"(?:^|[\W_])(?:id|uuid|guid|code|sku|zip|postcode|phone|ид|код|артикул|инн|снилс|телефон|индекс|номер)(?:$|[\W_])", re.I)
_TIME = re.compile(r"(?:^|[\W_])(?:year|month|date|time|period|год|годы|месяц|дата|время|период)(?:$|[\W_])", re.I)
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
_BOOLEAN = {"true", "false", "yes", "no", "да", "нет"}


def _datetime(value: str, header: str) -> bool:
    # Slash dates such as 01/02/2026 are ambiguous across locales and stay text.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].+)?", value):
        try:
            dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    for pattern, fmt in ((r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y"),
                         (r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}", "%d.%m.%Y %H:%M"),
                         (r"\d{4}-\d{2}", "%Y-%m"),
                         (r"\d{2}\.\d{4}", "%m.%Y")):
        if re.fullmatch(pattern, value):
            try:
                dt.datetime.strptime(value, fmt)
                return True
            except ValueError:
                return False
    if re.fullmatch(r"(?:Q[1-4] \d{4}|\d{4} Q[1-4])", value, re.I):
        return True
    return bool(_TIME.search(header) and re.fullmatch(r"(?:19|20)\d{2}", value))


def _identifier(header: str, values: list[str]) -> bool:
    # CamelCase IDs are common in JSON; distinct integers alone are NOT evidence of an ID.
    words = re.sub(r"([a-zа-я])([A-ZА-Я])", r"\1_\2", header)
    if _ID.search(words):
        return True
    return bool(values) and (all(_UUID.fullmatch(v) for v in values)
                             or all(re.fullmatch(r"\d+", v) for v in values)
                             and any(len(v) > 1 and v.startswith("0") for v in values))


def _outliers(numbers: list[Decimal]) -> int | None:
    if len(numbers) < 4:
        return None
    ordered = sorted(numbers)
    # Input cells may have up to 2000 digits. Avoid rounding fence comparisons.
    with localcontext() as context:
        context.prec = max(32, max(len(n.as_tuple().digits) + abs(n.as_tuple().exponent) for n in numbers) + 12)

        def quartile(numerator: int) -> Decimal:
            position = Decimal(len(ordered) - 1) * numerator / 4
            index = int(position)
            fraction = position - index
            return ordered[index] + fraction * (ordered[min(index + 1, len(ordered) - 1)] - ordered[index])

        q1, q3 = quartile(1), quartile(3)
        spread = (q3 - q1) * Decimal("1.5")
        return sum(n < q1 - spread or n > q3 + spread for n in ordered)


def profile_table(table: Table) -> DatasetProfile:
    """Describe a Table without mutation, model calls, formula evaluation or row reordering.

    A typed candidate needs >=90% matching nonempty values. A likely time axis is
    emitted only for a single fully parsed date/period column with >=2 distinct values.
    Category roles exclude identifiers and high-cardinality free text (>20 distinct
    values and >20% distinct). Numeric ID cells retain numeric storage type but never
    receive a numeric measure candidate or outlier count.
    """
    if any(len(row) != len(table.headers) for row in table.rows):
        raise ValueError("Table rows must have exactly one cell per header")
    columns = []
    axes = []
    for index, name in enumerate(table.headers):
        values = [row[index].strip() for row in table.rows if row[index].strip()]
        count = len(values)
        cardinality = len(set(values))
        identifier = _identifier(name, values)
        numbers = [number for value in values if (number := parse_number(value)) is not None]
        dates = sum(_datetime(value, name) for value in values)
        booleans = sum(value.casefold() in _BOOLEAN for value in values)
        roles: tuple[str, ...] = ()
        outliers = None
        if not count:
            kind, confidence = "empty", 0.0
        else:
            matches, kind = max(((dates, "datetime"), (len(numbers), "numeric"), (booleans, "boolean")),
                                key=lambda pair: pair[0])
            if matches / count >= 0.9:
                confidence = matches / count
            elif matches:
                kind, confidence = "mixed", matches / count
            else:
                kind, confidence = "text", 1.0
            if identifier:
                roles = ("identifier",)
            elif kind == "datetime":
                roles = ("datetime",)
                if dates == count and cardinality >= 2:
                    axes.append(name)
            elif kind == "numeric":
                roles = ("numeric",)
                outliers = _outliers(numbers)
            elif kind in {"text", "boolean"} and (cardinality <= 20 or cardinality / count <= 0.2):
                roles = ("category",)
        columns.append(ColumnProfile(name, kind, confidence, roles, len(table.rows) - count, cardinality, outliers))

    def candidates(role: str) -> tuple[str, ...]:
        return tuple(column.name for column in columns if role in column.role_candidates)

    hierarchies = []
    for parent in candidates("category"):
        for child in candidates("category"):
            if parent == child:
                continue
            pi, ci = table.headers.index(parent), table.headers.index(child)
            pairs = [(row[pi].strip(), row[ci].strip()) for row in table.rows]
            if not pairs or any(not p or not c for p, c in pairs):
                continue
            parents, children, counts = set(), {}, {}
            for p, c in pairs:
                parents.add(p)
                children.setdefault(c, set()).add(p)
                counts[c] = counts.get(c, 0) + 1
            # Unique labels make any functional dependency vacuously true. Require
            # repeat observations and genuine nesting, rejecting one-to-one aliases.
            if (2 <= len(parents) < len(children) and all(len(ps) == 1 for ps in children.values())
                    and all(n >= 2 for n in counts.values())):
                hierarchies.append(HierarchyCandidate(parent, child, len(parents), len(children), tuple(table.lines)))
    return DatasetProfile(table.name, table.sheet, len(table.rows), len(table.headers), tuple(columns),
                          candidates("numeric"), candidates("category"), candidates("datetime"),
                          candidates("identifier"), axes[0] if len(axes) == 1 else None,
                          tuple(hierarchies), len(candidates("category")) + len(candidates("datetime")),
                          len(candidates("numeric")), len(hierarchies))
