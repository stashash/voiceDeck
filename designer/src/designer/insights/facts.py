"""Кандидаты в выводы по таблице: что о ней можно честно сказать, посчитано точной десятичной арифметикой.

Модель кандидатов не считает: она выбирает из них и формулирует. Каждое число кандидата лежит
в `numbers` в той записи, в какой оно пойдёт на слайд, и сверяется с текстом подсказки.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from designer.contracts import ChartSpec, Series, TableSpec
from designer.insights.table import Table

MAX_FACTS = 24
MAX_METRICS = 6
_TOTAL_ROW = re.compile(r"^\s*(итого|всего|total|сумма)\b", re.I)
_PERIOD = re.compile(
    r"\b(19|20)\d{2}\b|\bQ[1-4]\b|\b[IV]{1,3}\s*кв|квартал|\bкв\.|\bH[12]\b|полугоди|\d{2}\.\d{2}\.\d{4}|недел"
    r"|январ|феврал|март|апрел|\bма[йя]\b|июн|июл|август|сентябр|октябр|ноябр|декабр"
    r"|\b(янв|фев|мар|апр|авг|сен|окт|ноя|дек)\b", re.I)
_UNIT = re.compile(r"^(?P<name>.+?)\s*(?:,\s*(?P<a>[^,()]{1,20})|\((?P<b>[^()]{1,20})\))\s*$")
_HUNDRED = Decimal(100)


@dataclass
class Fact:
    id: str
    kind: str
    statement: str
    numbers: list[str]
    formula: str
    source: str
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    big_number: str | None = None
    data_lines: list[str] = field(default_factory=list)
    """Строки «подпись: значение» для брифа: по ним аудит сверяет числа диаграммы с исходником."""


def fmt(value: Decimal) -> str:
    """Русская запись: запятая в дробной части, неразрывный пробел в группах от 10 000."""
    value = value.normalize()
    sign = "−" if value < 0 else ""
    text = format(abs(value), "f")
    whole, _, fraction = text.partition(".")
    if len(whole) > 4:
        groups = []
        while whole:
            groups.insert(0, whole[-3:])
            whole = whole[:-3]
        whole = " ".join(groups)
    return sign + whole + ("," + fraction if fraction else "")


def pct(change: Decimal, signed: bool = True) -> str:
    rounded = change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = fmt(abs(rounded))
    sign = ("+" if rounded > 0 else "−" if rounded < 0 else "") if signed else ""
    return f"{sign}{text} %"


def ratio(a: Decimal, b: Decimal) -> str:
    return fmt((a / b).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def split_unit(header: str) -> tuple[str, str]:
    """«Выручка, млн ₽» -> («Выручка», «млн ₽»); «Доля (%)» -> («Доля», «%»)."""
    match = _UNIT.match(header)
    if not match:
        return header, ""
    return match.group("name").strip(), (match.group("a") or match.group("b") or "").strip()


@dataclass
class _Metric:
    column: int
    name: str
    unit: str
    points: list[tuple[int, str, Decimal]]
    """(номер строки в файле, подпись строки, значение) без строк «Итого»."""


def find_facts(table: Table) -> list[Fact]:
    label_col = _label_column(table)
    labels = [row[label_col] if label_col is not None else f"строка {i + 2}" for i, row in enumerate(table.rows)]
    keep = [i for i, label in enumerate(labels) if not _TOTAL_ROW.match(label)]
    periods = sum(bool(_PERIOD.search(labels[i])) for i in keep) >= max(2, 0.6 * len(keep))
    metrics = _metrics(table, label_col, labels, keep)
    label_header = table.headers[label_col] if label_col is not None else "Строка"

    facts: list[Fact] = []
    for metric in metrics[:MAX_METRICS]:
        if periods:
            facts += _period_facts(metric)
        else:
            facts += _category_facts(metric, label_header)
    facts += _wide_facts(table, metrics, label_header)
    for index, fact in enumerate(facts[:MAX_FACTS], start=1):
        fact.id = f"f{index}"
    return facts[:MAX_FACTS]


def _label_column(table: Table) -> int | None:
    for column in range(len(table.headers)):
        cells = [row[column] for row in table.rows if row[column]]
        numeric = sum(table.numbers[i][column] is not None for i, row in enumerate(table.rows) if row[column])
        if cells and numeric / len(cells) < 0.5:
            return column
    return None


def _metrics(table: Table, label_col: int | None, labels: list[str], keep: list[int]) -> list[_Metric]:
    metrics = []
    for column, header in enumerate(table.headers):
        if column == label_col:
            continue
        filled = [i for i in keep if table.rows[i][column]]
        points = [(i + 2, labels[i], table.numbers[i][column]) for i in filled if table.numbers[i][column] is not None]
        if len(points) >= 2 and len(points) >= 0.8 * len(filled):
            name, unit = split_unit(header)
            metrics.append(_Metric(column=column, name=name, unit=unit, points=points))
    return metrics


def _with_unit(value: Decimal, unit: str) -> str:
    return f"{fmt(value)} {unit}" if unit else fmt(value)


def _rows_text(rows: list[int]) -> str:
    return f"строки {', '.join(str(r) for r in rows)}" if len(rows) <= 4 else f"строки {rows[0]}–{rows[-1]}"


def _chart(kind: str, metric: _Metric, points: list[tuple[int, str, Decimal]]) -> ChartSpec:
    return ChartSpec(type=kind, title=metric.name, categories=[label for _, label, _ in points],
                     series=[Series(name=metric.name, values=[float(v) for _, _, v in points])], unit=metric.unit)


def _data_lines(metric: _Metric, points: list[tuple[int, str, Decimal]]) -> list[str]:
    return [f"{metric.name}, {label}: {_with_unit(value, metric.unit)}" for _, label, value in points]


def _period_facts(metric: _Metric) -> list[Fact]:
    facts: list[Fact] = []
    points = metric.points[-12:]
    chart = _chart("line" if len(points) >= 5 else "column", metric, points)
    lines = _data_lines(metric, points)
    source = f"столбец «{metric.name}», {_rows_text([r for r, _, _ in points])}"
    (_, prev_label, prev), (_, last_label, last) = metric.points[-2], metric.points[-1]
    change_fact = _change(metric, prev, last)
    if change_fact:
        shown, formula = change_fact
        facts.append(Fact(
            id="", kind="change_last",
            statement=f"{metric.name}: {last_label} к {prev_label} {shown} "
                      f"({_with_unit(prev, metric.unit)} → {_with_unit(last, metric.unit)})",
            numbers=[shown, fmt(prev), fmt(last)], formula=formula,
            source=source, chart=chart, big_number=shown, data_lines=lines))
    (_, first_label, first) = metric.points[0]
    change_fact = _change(metric, first, last)
    if len(metric.points) >= 3 and change_fact:
        shown, formula = change_fact
        facts.append(Fact(
            id="", kind="change_total",
            statement=f"{metric.name} за период {first_label} – {last_label}: {shown} "
                      f"({_with_unit(first, metric.unit)} → {_with_unit(last, metric.unit)})",
            numbers=[shown, fmt(first), fmt(last)], formula=formula,
            source=source, chart=chart, big_number=shown, data_lines=lines))
    if len(metric.points) >= 3:
        steps = len(metric.points) - 1
        grew = sum(b[2] > a[2] for a, b in zip(metric.points, metric.points[1:]))
        facts.append(Fact(
            id="", kind="growth_count",
            statement=f"{metric.name}: рост в {grew} из {steps} периодов",
            numbers=[str(grew), str(steps)],
            formula=f"число периодов, где значение больше предыдущего: {grew} из {steps}",
            source=source, chart=chart, big_number=f"{grew} из {steps}", data_lines=lines))
    return facts


def _change(metric: _Metric, old: Decimal, new: Decimal) -> tuple[str, str] | None:
    """Изменение для подписи и формула. Доля в процентах меняется в процентных пунктах, а не в процентах."""
    if metric.unit == "%":
        diff = (new - old).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        sign = "+" if diff > 0 else "−" if diff < 0 else ""
        shown = f"{sign}{fmt(abs(diff))} п. п."
        return shown, f"{fmt(new)} − {fmt(old)} = {shown}"
    if old <= 0:
        return None
    change = (new - old) / old * _HUNDRED
    return pct(change), f"({fmt(new)} − {fmt(old)}) / {fmt(old)} × 100 = {pct(change)}"


def _category_facts(metric: _Metric, label_header: str) -> list[Fact]:
    facts: list[Fact] = []
    ranked = sorted(metric.points, key=lambda p: p[2], reverse=True)
    top = ranked[:8]
    source = f"столбец «{metric.name}», {_rows_text(sorted(r for r, _, _ in metric.points))}"
    lines = _data_lines(metric, top)
    (_, top_label, top_value), (_, low_label, low_value) = ranked[0], ranked[-1]
    total = sum(v for _, _, v in metric.points)
    if all(v >= 0 for _, _, v in metric.points) and total > 0 and metric.unit != "%":
        share = top_value / total * _HUNDRED
        kind = "pie" if len(metric.points) <= 6 else "bar"
        facts.append(Fact(
            id="", kind="share_top",
            statement=f"Доля «{top_label}» в «{metric.name}»: {pct(share, signed=False)} "
                      f"({_with_unit(top_value, metric.unit)} из {_with_unit(total, metric.unit)})",
            numbers=[pct(share, signed=False), fmt(top_value), fmt(total)],
            formula=f"{fmt(top_value)} / {fmt(total)} × 100 = {pct(share, signed=False)}",
            source=source, chart=_chart(kind, metric, top), big_number=pct(share, signed=False),
            data_lines=lines + [f"{metric.name}, всего: {_with_unit(total, metric.unit)}"]))
    if len(metric.points) >= 3:
        numbers = [fmt(top_value), fmt(low_value)]
        statement = (f"{metric.name}: больше всего у «{top_label}» ({_with_unit(top_value, metric.unit)}), "
                     f"меньше всего у «{low_label}» ({_with_unit(low_value, metric.unit)})")
        formula = f"максимум {fmt(top_value)}, минимум {fmt(low_value)}"
        if low_value > 0:
            times = ratio(top_value, low_value)
            statement += f", разница в {times} раза"
            numbers.append(times)
            formula += f"; {fmt(top_value)} / {fmt(low_value)} = {times}"
        facts.append(Fact(
            id="", kind="leader_gap", statement=statement, numbers=numbers, formula=formula, source=source,
            chart=_chart("bar", metric, top), data_lines=lines,
            table=TableSpec(columns=[label_header, metric.name if not metric.unit else f"{metric.name}, {metric.unit}"],
                            rows=[[label, fmt(value)] for _, label, value in top[:7]])))
    return facts


def _wide_facts(table: Table, metrics: list[_Metric], label_header: str) -> list[Fact]:
    """Широкая таблица: два последних числовых столбца это периоды, строки это регионы, продукты, команды."""
    if len(metrics) < 2:
        return []
    before, after = metrics[-2], metrics[-1]
    if not (_PERIOD.search(table.headers[before.column]) and _PERIOD.search(table.headers[after.column])):
        return []
    previous = {row: value for row, _, value in before.points}
    pairs = [(row, label, previous[row], value) for row, label, value in after.points if row in previous]
    if len(pairs) < 2:
        return []
    facts: list[Fact] = []
    # Имя столбца без единицы: «Выручка Q4 2026», единица идёт к числам.
    head_before, head_after = before.name, after.name
    unit = after.unit
    top = sorted(pairs, key=lambda p: p[3], reverse=True)[:8]
    chart = ChartSpec(type="column", title=f"{head_before} и {head_after}", categories=[p[1] for p in top],
                      series=[Series(name=head_before, values=[float(p[2]) for p in top]),
                              Series(name=head_after, values=[float(p[3]) for p in top])], unit=unit)
    lines = [f"{label}: {head_before} {_with_unit(old, unit)}, {head_after} {_with_unit(new, unit)}"
             for _, label, old, new in top]
    source = f"столбцы «{head_before}» и «{head_after}», {_rows_text([p[0] for p in pairs])}"
    grew = sum(new > old for _, _, old, new in pairs)
    facts.append(Fact(
        id="", kind="rows_grew",
        statement=f"{label_header}: рост у {grew} из {len(pairs)}, {head_before} → {head_after}",
        numbers=[str(grew), str(len(pairs))],
        formula=f"строк, где «{head_after}» больше «{head_before}»: {grew} из {len(pairs)}",
        source=source, chart=chart, big_number=f"{grew} из {len(pairs)}", data_lines=lines))
    growing = [(row, label, old, new, (new - old) / old * _HUNDRED) for row, label, old, new in pairs if old > 0]
    if growing:
        row, label, old, new, change = max(growing, key=lambda p: p[4])
        facts.append(Fact(
            id="", kind="fastest_row",
            statement=f"Лучшая динамика: «{label}», {pct(change)} ({fmt(old)} → {fmt(new)})",
            numbers=[pct(change), fmt(old), fmt(new)],
            formula=f"({fmt(new)} − {fmt(old)}) / {fmt(old)} × 100 = {pct(change)}",
            source=f"строка {row}, столбцы «{head_before}» и «{head_after}»", chart=chart,
            big_number=pct(change), data_lines=lines))
    total_old, total_new = sum(p[2] for p in pairs), sum(p[3] for p in pairs)
    if total_old > 0:
        change = (total_new - total_old) / total_old * _HUNDRED
        facts.append(Fact(
            id="", kind="total_change",
            statement=f"Сумма по всем строкам: {head_after} к {head_before} {pct(change)} "
                      f"({_with_unit(total_old, unit)} → {_with_unit(total_new, unit)})",
            numbers=[pct(change), fmt(total_old), fmt(total_new)],
            formula=f"({fmt(total_new)} − {fmt(total_old)}) / {fmt(total_old)} × 100 = {pct(change)}",
            source=source, chart=chart, big_number=pct(change), data_lines=lines))
    return facts
