"""Conservative display labels; source column names remain in provenance."""
import re

_LABELS = {"revenue": "Выручка", "period": "Период", "month": "Месяц", "year": "Год",
           "value": "Значение", "category": "Категория", "date": "Дата",
           "channel": "Канал", "status": "Статус", "outcome": "Результат", "region": "Регион", "requests": "Запросы",
           "tickets": "Обращения", "leads": "Лиды", "units": "Количество", "note": "Примечание",
           "label": "Наименование", "reference id": "Код записи", "name": "Название",
           "count": "Количество", "sales": "Продажи", "cost": "Затраты", "profit": "Прибыль"}
_UNIT = re.compile(r"(?:^|[_\s(\[,])(?P<unit>USD|EUR|RUB|₽|€|%)(?:[)\]]?)$", re.IGNORECASE)


def field_label(name: str, language: str = "ru") -> tuple[str, str]:
    """Only explicit header suffixes identify a unit; never infer from values."""
    match = _UNIT.search(name.strip())
    unit = match.group("unit").upper() if match else ""
    stem = name[:match.start()].strip() if match else name.strip()
    return display_label(stem, language), unit


def display_label(name: str, language: str = "ru") -> str:
    """An exact, reversible vocabulary, not a translator of arbitrary source text."""
    if language not in {"ru", "en"}:
        raise ValueError("Supported presentation languages: ru, en")
    key = name.strip().replace("_", " ").lower()
    reverse = {value.lower(): source for source, value in _LABELS.items()}
    if language == "en":
        if key in reverse:
            return reverse[key].capitalize()
        for en, ru in (("actual", "факт"), ("target", "цель"), ("planned", "план")):
            if key.endswith(f" ({ru})"):
                return f"{en.capitalize()} {reverse.get(key[:-len(ru)-3], key[:-len(ru)-3])}"
        return name.replace("_", " ")
    if key in _LABELS:
        return _LABELS[key]
    for modifier, translated in (("actual", "факт"), ("target", "цель"), ("planned", "план")):
        if key.startswith(modifier + " ") and key[len(modifier) + 1:] in _LABELS:
            return f"{_LABELS[key[len(modifier) + 1:]]} ({translated})"
    return name
