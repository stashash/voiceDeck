"""Shared structural safety boundary for native and SVG charts."""
import math

from designer.contracts import ChartSpec


def chart_data_errors(spec: ChartSpec) -> list[str]:
    if spec.type not in {"column", "bar", "line", "pie", "donut", "scatter", "grouped_column", "stacked_column"}:
        return [f"Unsupported chart type: {spec.type}"]
    errors = []
    if not 1 <= len(spec.series) <= 5:
        errors.append("нужно от одного до пяти рядов")
    if any(not s.values or not all(math.isfinite(v) for v in s.values) for s in spec.series):
        errors.append("значения должны быть непустыми и конечными")
    if spec.type == "scatter":
        if spec.categories or any(s.x_values is None or len(s.x_values) != len(s.values)
                                  or not all(math.isfinite(v) for v in s.x_values) for s in spec.series):
            errors.append("нужны полные числовые пары X/Y")
    elif not spec.categories or any(len(s.values) != len(spec.categories) or s.x_values is not None for s in spec.series):
        errors.append("каждой категории нужно исходное значение каждого ряда; заполнение нулями запрещено")
    if spec.type in {"pie", "donut"}:
        values = [v for s in spec.series for v in s.values]
        total = sum(values)
        if len(spec.series) != 1 or any(v < 0 for v in values) or not math.isfinite(total) or total <= 0:
            errors.append("доли требуют один неотрицательный ряд с конечной положительной суммой")
    if spec.type == "stacked_column" and not errors:
        totals = [sum(s.values[i] for s in spec.series) for i in range(len(spec.categories))]
        if any(v < 0 for s in spec.series for v in s.values) or not all(math.isfinite(v) for v in totals):
            errors.append("накопление требует неотрицательных значений с конечными суммами")
    return errors


def validate_chart_data(spec: ChartSpec) -> None:
    errors = chart_data_errors(spec)
    if errors:
        raise ValueError("; ".join(errors))
