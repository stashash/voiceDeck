"""Текст в фигуру слайда с оформлением образца. Владелец: задача T-08.

Шаблон задаёт шрифт, кегль, цвет и начертание первым фрагментом первого абзаца.
Всё остальное содержимое фигуры это текст-образец, он уходит.
"""
from __future__ import annotations

import copy

from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def set_text(shape, text: str, size_pt: float | None = None, wrap: bool = True) -> None:
    """Пишет текст в фигуру, сохраняя оформление первого фрагмента первого абзаца.

    Лишние фрагменты и абзацы убираются, перевод строки даёт новый абзац с тем же оформлением.
    Пустая строка очищает фигуру, сама фигура остаётся на слайде.
    Принимает и фигуру python-pptx, и её XML.

    size_pt — кегль после подгонки вёрстки. Если задан, ставится всем фрагментам,
    а автоподбор кегля PowerPoint у фигуры выключается: иначе размер поплывёт при открытии.
    """
    body = _text_body(shape)
    if body is None:
        return
    run_props, para_props = _sample_props(body)
    if size_pt is not None:
        run_props = _with_size(run_props, size_pt)
        _disable_autofit(body)
    if not wrap:
        # Крупное число на движке с другим шрифтом иначе ломается на две строки и ложится само на себя.
        body_pr = body.find(qn("a:bodyPr"))
        if body_pr is not None:
            body_pr.set("wrap", "none")
            # Кегль числа меньше образца: у нижнего края рамки оно ложится на подпись, по центру нет.
            body_pr.set("anchor", "ctr")
    for para in body.findall(qn("a:p")):
        body.remove(para)
    for line in _lines(text):
        body.append(_paragraph(line, run_props, para_props))


def _text_body(shape):
    element = getattr(shape, "_element", shape)
    return element.find(qn("p:txBody"))


def _sample_props(body):
    """Оформление образца: свойства фрагмента и абзаца, которые переносим на новый текст."""
    paragraphs = body.findall(qn("a:p"))
    if not paragraphs:
        return None, None
    first = paragraphs[0]
    para_props = first.find(qn("a:pPr"))
    run = first.find(qn("a:r"))
    if run is None:
        run = next((r for para in paragraphs for r in para.findall(qn("a:r"))), None)
    if run is not None:
        return run.find(qn("a:rPr")), para_props
    if para_props is not None:
        defaults = para_props.find(qn("a:defRPr"))
        if defaults is not None:
            return _retag(defaults, "a:rPr"), para_props
    tail = first.find(qn("a:endParaRPr"))
    if tail is not None:
        return _retag(tail, "a:rPr"), para_props
    return None, para_props


def _retag(element, tag: str):
    copied = copy.deepcopy(element)
    copied.tag = qn(tag)
    return copied


def _with_size(run_props, size_pt: float):
    """Свойства фрагмента с проставленным кеглем: sz в OOXML это сотые доли пункта."""
    node = copy.deepcopy(run_props) if run_props is not None else parse_xml("<a:rPr %s/>" % nsdecls("a"))
    node.set("sz", str(round(size_pt * 100)))
    return node


def _disable_autofit(body) -> None:
    """Выключает автоподбор кегля PowerPoint у фигуры: заданный размер иначе поплывёт при открытии."""
    body_pr = body.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    for tag in ("a:normAutofit", "a:spAutoFit"):
        node = body_pr.find(qn(tag))
        if node is not None:
            body_pr.remove(node)
    if body_pr.find(qn("a:noAutofit")) is None:
        body_pr.append(parse_xml("<a:noAutofit %s/>" % nsdecls("a")))


def _lines(text: str) -> list[str]:
    """Строки текста: перевод строки в любом виде делит текст на абзацы."""
    if not text:
        return [""]
    plain = text.replace("\r\n", "\n").replace("\r", "\n").replace("\v", "\n")
    plain = "".join(ch if ch >= " " or ch in "\t\n" else " " for ch in plain)
    return plain.split("\n")


def _paragraph(line: str, run_props, para_props):
    para = parse_xml("<a:p %s/>" % nsdecls("a"))
    if para_props is not None:
        para.append(copy.deepcopy(para_props))
    if line:
        run = parse_xml("<a:r %s><a:t/></a:r>" % nsdecls("a"))
        if run_props is not None:
            run.insert(0, copy.deepcopy(run_props))
        text_node = run.find(qn("a:t"))
        text_node.text = line
        text_node.set(_XML_SPACE, "preserve")
        para.append(run)
    elif run_props is not None:
        para.append(_retag(run_props, "a:endParaRPr"))
    return para
