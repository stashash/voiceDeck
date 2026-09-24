"""Числа в распознанной речи: слова в цифры до вызова модели.

Распознавание речи отдаёт числа словами («к половине девятого», «шесть недель»). Модель
переводит их в цифры сама и ошибается на оборотах времени: «к половине девятого» становилась
«6:00». Код переводит их раньше, и модель получает готовые цифры: «к 8:30», «6 недель».
Цифры во входе заодно позволяют сверить числа на слайде с тем, что сказал докладчик.

Что не переводится:
- «один», «одна» и другие формы единицы без десятков перед ними: «одна из задач» не число;
- «семью» (омоним «семья»), множественные «тысячи», «миллионы» без числа перед ними;
- порядковое слово без числа перед ним: «во втором квартале», «третий слайд».

Порядковый хвост составного числа переводится вместе с ним: «в две тысячи двадцать шестом
году» даёт «в 2026 году».
"""
from __future__ import annotations

import re

_UNITS = {
    2: "два две двух двум двумя",
    3: "три трех трем тремя",
    4: "четыре четырех четырем четырьмя",
    5: "пять пяти пятью",
    6: "шесть шести шестью",
    7: "семь семи",
    8: "восемь восьми восемью восьмью",
    9: "девять девяти девятью",
}
_ONE = "один одна одно одного одной одному одним одном одну одною"
_ZERO = "ноль нуль ноля нуля нолю нулю нолем нулем"
_TEEN_STEMS = {
    10: "десят", 11: "одиннадцат", 12: "двенадцат", 13: "тринадцат", 14: "четырнадцат",
    15: "пятнадцат", 16: "шестнадцат", 17: "семнадцат", 18: "восемнадцат", 19: "девятнадцат",
    20: "двадцат", 30: "тридцат",
}
_TENS = {
    40: "сорок сорока",
    50: "пятьдесят пятидесяти пятьюдесятью",
    60: "шестьдесят шестидесяти шестьюдесятью",
    70: "семьдесят семидесяти семьюдесятью",
    80: "восемьдесят восьмидесяти восемьюдесятью",
    90: "девяносто девяноста",
}
_HUNDREDS = {
    100: "сто ста",
    200: "двести двухсот двумстам двумястами двухстах",
    300: "триста трехсот тремстам тремястами трехстах",
    400: "четыреста четырехсот четыремстам четырьмястами четырехстах",
    500: "пятьсот пятисот пятистам пятьюстами пятистах",
    600: "шестьсот шестисот шестистам шестьюстами шестистах",
    700: "семьсот семисот семистам семьюстами семистах",
    800: "восемьсот восьмисот восьмистам восьмьюстами восьмистах",
    900: "девятьсот девятисот девятистам девятьюстами девятистах",
}
_SCALES = {
    1000: "тысяча тысячи тысяч тысяче тысячу тысячей тысячам тысячами тысячах",
    1_000_000: "миллион миллиона миллионов миллиону миллионом миллионе миллионы миллионам миллионами миллионах",
    1_000_000_000: "миллиард миллиарда миллиардов миллиарду миллиардом миллиарде миллиарды миллиардам миллиардами миллиардах",
}
# Шкала без числа перед ней: «тысячу» это 1000, а «тысячи людей» — «много людей».
_SCALE_ALONE = {"тысяча", "тысячу", "миллион", "миллиард"}
_HALF_ONE = {"полтора", "полторы", "полутора"}

_WORD_VALUE: dict[str, tuple[int, str]] = {}
"""Слово -> (значение, разряд): unit, one, teen, ten, hundred, scale."""
for _value, _forms in _UNITS.items():
    for _form in _forms.split():
        _WORD_VALUE[_form] = (_value, "unit")
for _form in _ONE.split():
    _WORD_VALUE[_form] = (1, "one")
for _form in _ZERO.split():
    _WORD_VALUE[_form] = (0, "unit")
for _value, _stem in _TEEN_STEMS.items():
    for _ending in ("ь", "и", "ью"):
        _WORD_VALUE[_stem + _ending] = (_value, "ten" if _value >= 20 else "teen")
for _value, _forms in _TENS.items():
    for _form in _forms.split():
        _WORD_VALUE[_form] = (_value, "ten")
for _value, _forms in _HUNDREDS.items():
    for _form in _forms.split():
        _WORD_VALUE[_form] = (_value, "hundred")
for _value, _forms in _SCALES.items():
    for _form in _forms.split():
        _WORD_VALUE[_form] = (_value, "scale")

_RANK = {"hundred": 3, "ten": 2, "teen": 1, "unit": 1, "one": 1}

_HOUR_GENITIVE = {
    "первого": 1, "второго": 2, "третьего": 3, "четвертого": 4, "пятого": 5, "шестого": 6,
    "седьмого": 7, "восьмого": 8, "девятого": 9, "десятого": 10, "одиннадцатого": 11,
    "двенадцатого": 12,
}
_HOUR_NOMINATIVE = {
    "час": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12,
}
_ORDINAL_STEMS = {
    "перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7, "восьм": 8,
    "девят": 9, "десят": 10, "одиннадцат": 11, "двенадцат": 12, "тринадцат": 13, "четырнадцат": 14,
    "пятнадцат": 15, "шестнадцат": 16, "семнадцат": 17, "восемнадцат": 18, "девятнадцат": 19,
    "двадцат": 20, "тридцат": 30, "сороков": 40, "пятидесят": 50, "шестидесят": 60,
    "семидесят": 70, "восьмидесят": 80, "девяност": 90, "сот": 100, "двухсот": 200, "трехсот": 300,
    "четырехсот": 400, "пятисот": 500, "шестисот": 600, "семисот": 700, "восьмисот": 800,
    "девятисот": 900, "тысячн": 1000,
}
_ORDINAL_ENDINGS = {
    "ый", "ой", "ий", "ая", "ое", "ого", "ому", "ым", "ом", "ую", "ые", "ых", "ыми", "ой",
    "ей", "ья", "ье", "ьего", "ьему", "ьим", "ьем", "ью", "ьи", "ьих", "ьими", "ьей",
}

_WORD = re.compile(r"[А-Яа-яЁё]+")
_GENITIVE_HOURS = "|".join(_HOUR_GENITIVE)
_HALF_PAST = re.compile(rf"\b(?:половин[аеуы]\s+|пол)({_GENITIVE_HOURS})\b", re.IGNORECASE)
_QUARTER_PAST = re.compile(rf"\bчетверть\s+({_GENITIVE_HOURS})\b", re.IGNORECASE)
_QUARTER_TO = re.compile(rf"\bбез\s+четверти\s+({'|'.join(_HOUR_NOMINATIVE)})\b", re.IGNORECASE)
_HOUR_MINUTES = re.compile(r"\b(в|к|до|с|со|после|около)\s+(\d{1,2})\s+(\d{2})\b(?!\s*(?:%|процент))",
                           re.IGNORECASE)


def _norm(word: str) -> str:
    return word.lower().replace("ё", "е")


def _clock(hour: int, minutes: int) -> str:
    return f"{hour}:{minutes:02d}"


def _previous_hour(hour: int) -> int:
    return 12 if hour == 1 else hour - 1


def _times(text: str) -> str:
    """Обороты времени: «половина девятого» 8:30, «четверть девятого» 8:15, «без четверти девять» 8:45."""
    text = _HALF_PAST.sub(lambda m: _clock(_previous_hour(_HOUR_GENITIVE[_norm(m.group(1))]), 30), text)
    text = _QUARTER_PAST.sub(lambda m: _clock(_previous_hour(_HOUR_GENITIVE[_norm(m.group(1))]), 15), text)
    return _QUARTER_TO.sub(lambda m: _clock(_previous_hour(_HOUR_NOMINATIVE[_norm(m.group(1))]), 45), text)


def _ordinal_value(word: str) -> int | None:
    """«шестом» 6, «двадцатого» 20, «тысячном» 1000; не порядковое слово None."""
    for stem in sorted(_ORDINAL_STEMS, key=len, reverse=True):
        if word.startswith(stem) and word[len(stem):] in _ORDINAL_ENDINGS:
            return _ORDINAL_STEMS[stem]
    return None


def _format(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}".replace(".", ",")


def _parse_run(words: list[str]) -> list[tuple[int, int, float]]:
    """Разбирает подряд идущие числительные на числа: [(начало, конец, значение)] по индексам слов.

    Разряды внутри числа идут по убыванию: «сто двадцать пять». Нарушение порядка начинает
    новое число: «восемь тридцать» это 8 и 30.
    """
    numbers: list[tuple[int, int, float]] = []
    start, total, group, last_rank = 0, 0.0, 0.0, 99
    has_value = False

    def close(end: int) -> None:
        nonlocal start, total, group, last_rank, has_value
        if has_value:
            numbers.append((start, end, total + group))
        start, total, group, last_rank, has_value = end, 0.0, 0.0, 99, False

    for index, word in enumerate(words):
        key = _norm(word)
        if key in _HALF_ONE:
            if has_value:
                close(index)
            group, last_rank, has_value, start = 1.5, 1, True, index
            continue
        value, kind = _WORD_VALUE[key]
        if kind == "scale":
            if not has_value:
                start = index
            total += (group or 1) * value
            group, last_rank, has_value = 0.0, 99, True
            continue
        rank = _RANK[kind]
        # После десятков идут только единицы: «двадцать пять», но «двадцать одиннадцать» это два числа.
        if has_value and (rank >= last_rank or (kind == "teen" and last_rank == 2)):
            close(index)
        if not has_value:
            start = index
        group += value
        # После «-надцати» и единиц число кончается: следующая цифра начнёт новое.
        last_rank = 0 if kind in {"teen", "unit", "one"} else rank
        has_value = True
    close(len(words))
    return numbers


def digits_from_speech(text: str) -> str:
    """Числительные и обороты времени в цифры; остальной текст не меняется."""
    text = _times(text)
    words = list(_WORD.finditer(text))
    out: list[str] = []
    cursor = 0
    index = 0
    while index < len(words):
        key = _norm(words[index].group(0))
        if key not in _WORD_VALUE and key not in _HALF_ONE:
            index += 1
            continue
        # Серия числительных, разделённых только пробелами.
        run_end = index + 1
        while (run_end < len(words)
               and (_norm(words[run_end].group(0)) in _WORD_VALUE or _norm(words[run_end].group(0)) in _HALF_ONE)
               and not text[words[run_end - 1].end():words[run_end].start()].strip()):
            run_end += 1
        run = words[index:run_end]
        next_word = _norm(words[run_end].group(0)) if run_end < len(words) else ""
        gap = text[run[-1].end():words[run_end].start()] if run_end < len(words) else ""
        ordinal = _ordinal_value(next_word) if next_word and not gap.strip() else None
        if ordinal is not None:
            parsed = _parse_run([w.group(0) for w in run])
            head = parsed[0][2] if len(parsed) == 1 else None
            # Хвост дописывает младшие разряды: 2020 и «шестом» дают 2026, 20 и «первого» 21.
            unit = 10 ** len(str(ordinal))
            if head is not None and head == int(head) and head >= unit and int(head) % unit == 0:
                out.append(text[cursor:run[0].start()])
                out.append(str(int(head) + ordinal))
                cursor = words[run_end].end()
                index = run_end + 1
                continue
            # «три первых слайда»: хвост не дописывает разряды, число переводится само по себе.
        for start, end, value in _parse_run([w.group(0) for w in run]):
            piece = run[start:end]
            keys = [_norm(w.group(0)) for w in piece]
            if len(keys) == 1 and _WORD_VALUE.get(keys[0], (0, ""))[1] == "one":
                continue
            if len(keys) == 1 and keys[0] in _WORD_VALUE and _WORD_VALUE[keys[0]][1] == "scale" \
                    and keys[0] not in _SCALE_ALONE:
                continue
            number = _format(value)
            span_end = piece[-1].end()
            # «два с половиной» 2,5
            half = re.match(r"\s+с\s+половиной\b", text[span_end:], re.IGNORECASE)
            if half and value == int(value):
                number = _format(value + 0.5)
                span_end += half.end()
            out.append(text[cursor:piece[0].start()])
            out.append(number)
            cursor = span_end
        index = run_end
    out.append(text[cursor:])
    result = "".join(out)
    return _HOUR_MINUTES.sub(
        lambda m: f"{m.group(1)} {m.group(2)}:{m.group(3)}"
        if int(m.group(2)) <= 23 and int(m.group(3)) <= 59 else m.group(0), result)
