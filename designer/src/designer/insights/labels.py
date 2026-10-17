"""Conservative display labels; source column names remain in provenance."""
import re

_LABELS = {"revenue": "Выручка", "period": "Период", "month": "Месяц", "year": "Год",
           "value": "Значение", "category": "Категория", "date": "Дата"}
_UNIT = re.compile(r"(?:^|[_\s(\[,])(?P<unit>USD|EUR|RUB|₽|€|%)(?:[)\]]?)$", re.IGNORECASE)


def field_label(name: str) -> tuple[str, str]:
    """Only explicit header suffixes identify a unit; never infer from values."""
    match = _UNIT.search(name.strip())
    unit = match.group("unit").upper() if match else ""
    stem = name[:match.start()].strip() if match else name.strip()
    return _LABELS.get(stem.lower(), stem.replace("_", " ")), unit
