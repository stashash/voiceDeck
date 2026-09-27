"""Conservative lexical guards, not a proof of semantic equivalence.

Protect digit-written quantities and English/Russian calendar expressions with
their nearby labels. Rephrasing those labels or changing number/date notation
can be rejected even when equivalent. Spelled-out quantities and arbitrary
natural-language dates are not comprehensively recognized.
"""
import re
from collections import Counter


_NUMBER = re.compile(
    r'(?:[+\-\u2212]\s*)?(?:[$\u20ac\u00a3\u20bd\u00a5]\s*)?(?:[+\-\u2212]\s*)?'
    r'\d+(?:[ \u00a0\u202f]\d{3}(?!\d))*'
    r'(?:[.,:/\-]\d+)*(?:[eE][+\-]?\d+)?'
    r'(?:\s*[%\u2030\u00b0])?'
)
_MONTH = (
    r'jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|'
    r'\u044f\u043d\u0432\u0430\u0440[\u044c\u044f]|'
    r'\u0444\u0435\u0432\u0440\u0430\u043b[\u044c\u044f]|'
    r'\u043c\u0430\u0440\u0442\u0430?|\u0430\u043f\u0440\u0435\u043b[\u044c\u044f]|'
    r'\u043c\u0430[\u0439\u044f]|\u0438\u044e\u043d[\u044c\u044f]|'
    r'\u0438\u044e\u043b[\u044c\u044f]|\u0430\u0432\u0433\u0443\u0441\u0442\u0430?|'
    r'\u0441\u0435\u043d\u0442\u044f\u0431\u0440[\u044c\u044f]|'
    r'\u043e\u043a\u0442\u044f\u0431\u0440[\u044c\u044f]|'
    r'\u043d\u043e\u044f\u0431\u0440[\u044c\u044f]|'
    r'\u0434\u0435\u043a\u0430\u0431\u0440[\u044c\u044f]'
)
_DATE = re.compile(
    rf'\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH})(?:\s+\d{{4}})?|'
    rf'(?:{_MONTH})(?:\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?|\s+\d{{4}})?|'
    r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|'
    r'\d{1,2}[-/.]\d{1,2}(?:[-/.]\d{2,4})?|\d{4})\b', re.I,
)
_WORD = re.compile(
    r'''[^\W\d_]+(?:[/\-][^\W\d_]+)*|[$\u20ac\u00a3\u20bd\u00a5%\u2030"'\u2032\u2033<>\u2264\u2265]'''
)
_BOUNDARY = re.compile(r'[.,;!?\n]')
_CONNECTORS = frozenset((
    'an the is are was were be been of on at for to and with by '
    '\u0432\u043e \u043d\u0430 \u0438 \u0441\u043e \u043a '
    '\u043a\u043e \u043e\u0442 \u0434\u043b\u044f \u0437\u0430 '
    '\u043f\u043e \u044d\u0442\u043e \u0431\u044b\u043b \u0431\u044b\u043b\u0430 '
    '\u0431\u044b\u043b\u0438'
).split())
_SCALE = frozenset((
    'thousand million billion trillion k m bn square cubic '
    '\u0442\u044b\u0441 \u043c\u043b\u043d \u043c\u043b\u0440\u0434 \u0442\u0440\u043b\u043d'
).split())
_ABBREVIATION = re.compile(
    r'\b(\u0442\u044b\u0441|\u043c\u043b\u043d|\u043c\u043b\u0440\u0434|'
    r'\u0442\u0440\u043b\u043d|\u043a\u0432|\u043a\u0443\u0431)\.(?=\s|$)'
)


def _anchor(fragment: str, *, before: bool) -> tuple[str, ...]:
    fragment = _ABBREVIATION.sub(r'\1', fragment)
    fragment = _BOUNDARY.split(fragment)[-1 if before else 0]
    words = [word for word in _WORD.findall(fragment) if word.casefold() not in _CONNECTORS]
    if not words:
        return ()
    # Retain case: mW and MW, for example, are different units. A conservative
    # rejection of a changed label is preferable to silently rebinding a value.
    if before:
        return tuple(words[-2:])
    return tuple(words[:3] if words[0].casefold() in _SCALE or 'per' in words[:2] else words[:2])


def _facts(text: str, pattern: re.Pattern) -> Counter:
    matches = list(pattern.finditer(text))
    facts = Counter()
    for index, match in enumerate(matches):
        left = matches[index - 1].end() if index else 0
        right = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        literal = ' '.join(match[0].split()).replace('\u2212', '-')
        facts[(literal, _anchor(text[left:match.start()], before=True),
               _anchor(text[match.end():right], before=False))] += 1
    return facts


def preservation_violations(original: str, rewritten: str, *, preserve_numbers: bool = False,
                            preserve_dates: bool = False) -> list[str]:
    """Reject changed inventories, multiplicity, signs, units or nearby labels.

    Checks equality, so new facts and removed facts both fail. This deliberately
    allows no value conversions or semantic repairs of a failed model response.
    """
    failed = []
    if preserve_numbers and _facts(original, _NUMBER) != _facts(rewritten, _NUMBER):
        failed.append('preserve_numbers')
    if preserve_dates and _facts(original, _DATE) != _facts(rewritten, _DATE):
        failed.append('preserve_dates')
    return failed
