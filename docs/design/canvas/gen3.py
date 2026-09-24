# Холст «voiceDeck: приложение», круг правок по ред-тиму карты версии 2: недостающие состояния и переходы.
import json, os
from datetime import datetime, timezone
import gen as g
import gen2 as h
from gen import e, svg, icon_btn, section_title, SURF, SURF2, BORDER, TEXT, MUTED, ACC, INK, OK, DANGER, DANGER_SOFT, UI, MONO, WS
from gen2 import (topbar, btn, chip, slide_img, step, DECK, TITLES, BRIEF, AGENT_NOW, DECK_TITLE, I_CHIP, I_SEND, I_STOP,
                  I_SCREEN, I_DOWNLOAD, I_GEAR, I_TERMINAL)
from gen import I_ALERT, I_RETRY, I_MIC, I_UPLOAD, I_CHECK

HERE = h.HERE
OUT = g.OUT


def home_first():
    box = (f'<div style="width: 880px; box-sizing: border-box; border-radius: 14px; background: {SURF}; border: 1px solid {BORDER}; padding: 16px 16px 12px; display: flex; flex-direction: column; gap: 12px">'
           f'<label for="brief0" style="position: absolute; left: -9999px">Бриф, текст или идея презентации</label>'
           f'<textarea id="brief0" rows="6" placeholder="Бриф, текст или одна идея. Например: итоги пилота потоковой загрузки для директоров направлений" '
           f'style="width: 100%; box-sizing: border-box; resize: none; background: transparent; border: 0; color: {TEXT}; font-family: {UI}; font-size: 15px; line-height: 1.55; outline: none"></textarea>'
           f'<div style="display: flex; justify-content: space-between; align-items: center"><div style="display: flex; gap: 8px">'
           f'{btn("Создать дизайн-систему", I_UPLOAD, href="DS-new.dc.html", aria="Дизайн-систем нет: создать из pptx")}'
           f'{btn("Подключить агента", I_GEAR, href="Settings-cli.dc.html", aria="Агент не подключён: открыть настройки")}</div>'
           f'<button type="button" disabled="" aria-label="Создать презентацию" title="Сначала нужны дизайн-система и агент" style="width: 40px; height: 40px; border-radius: 999px; border: 0; '
           f'background: {ACC}; opacity: 0.45; display: flex; align-items: center; justify-content: center">{svg(I_SEND, 20, INK)}</button></div></div>')
    return (f'{topbar("Презентации")}<main style="flex-grow: 1; display: flex; flex-direction: column; align-items: center; gap: 24px; padding: 72px 0 48px">'
            f'<h1 style="margin: 0; font-size: 32px; font-weight: 600; letter-spacing: -0.01em">О чём будет презентация?</h1>{box}</main>')


def gen_left(steps_html):
    return (f'<aside aria-label="Ход работы" style="width: 420px; flex-shrink: 0; box-sizing: border-box; background: {SURF}; border-right: 1px solid {BORDER}; '
            f'padding: 24px; display: flex; flex-direction: column; gap: 24px">'
            f'<div style="display: flex; flex-direction: column; gap: 8px"><span style="font-size: 12px; color: {MUTED}">Запрос</span>'
            f'<p style="margin: 0; font-size: 13px; line-height: 1.5; color: {TEXT}; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden">{e(BRIEF)}</p></div>'
            f'<div style="display: flex; gap: 6px; align-items: center; font-size: 13px; color: {MUTED}">{svg(I_CHIP, 16)}{AGENT_NOW}</div>'
            f'<div style="height: 1px; background: {BORDER}"></div>'
            f'<ol aria-label="Ход работы" style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 18px">{steps_html}</ol></aside>')


def gen_done():
    steps = (step("done", "План из 10 слайдов", "33 с") + step("done", "Вёрстка: готово 10 из 10", "13 с")
             + step("done", "Проверка по правилам шаблона", "&lt;1 с") + step("done", "Файлы pptx, pdf и html", "5 с")
             + step("done", "Проверка смысла", "57 с") + step("done", "Варианты 2 и 3"))
    cells = "".join(f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 8px">{slide_img(DECK[f"a{i}"], 296)}'
                    f'<figcaption style="font-size: 12px; color: {MUTED}">{i}</figcaption></figure>' for i in range(1, 11))
    right = (f'<div style="flex-grow: 1; min-width: 0; padding: 24px 32px; display: flex; flex-direction: column; gap: 20px">'
             f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px">'
             f'<div style="display: flex; flex-direction: column; gap: 6px"><h1 style="margin: 0; font-size: 22px; font-weight: 600">{e(DECK_TITLE)}</h1>'
             f'<span role="status" style="font-size: 13px; color: {TEXT}; display: flex; gap: 6px; align-items: center">{svg(I_CHECK, 16, OK)}Готово: три варианта, 30 замечаний проверки у варианта 1</span></div>'
             f'{btn("Открыть и править", primary=True, href="Edit.dc.html")}</div>'
             f'<div style="display: grid; grid-template-columns: repeat(3, 296px); gap: 24px 20px">{cells}</div></div>')
    return f'{topbar("Презентации")}<div style="display: flex; flex-grow: 1; min-height: 0">{gen_left(steps)}{right}</div>'


def gen_no_images():
    steps = (step("done", "План из 10 слайдов", "33 с") + step("done", "Вёрстка: готово 10 из 10", "13 с")
             + step("done", "Проверка по правилам шаблона", "&lt;1 с") + step("done", "Файлы pptx и html", "&lt;1 с")
             + step("wait", "Картинки слайдов и pdf: нет LibreOffice") + step("wait", "Проверка смысла: нужны картинки слайдов")
             + step("done", "Варианты 2 и 3"))
    cells = "".join(f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 8px">'
                    f'<div style="width: 296px; height: 167px; box-sizing: border-box; border-radius: 6px; border: 1px solid {BORDER}; background: {SURF}; padding: 14px; font-size: 12px; line-height: 1.4; color: {TEXT}">{e(t)}</div>'
                    f'<figcaption style="font-size: 12px; color: {MUTED}">{i}</figcaption></figure>' for i, t in enumerate(TITLES, 1))
    note = (f'<div role="status" style="display: flex; gap: 10px; align-items: flex-start; font-size: 13px; line-height: 1.45; color: {TEXT}">{svg(I_ALERT, 18, MUTED)}'
            f'<span>Презентация готова без картинок слайдов: на машине не найден LibreOffice или PowerPoint. Файлы pptx и html есть, pdf нет, проверки смысла не было. '
            f'<a href="#libreoffice" style="color: {TEXT}; text-decoration: underline">Как установить LibreOffice</a></span></div>')
    right = (f'<div style="flex-grow: 1; min-width: 0; padding: 24px 32px; display: flex; flex-direction: column; gap: 20px">'
             f'<div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px">'
             f'<div style="display: flex; flex-direction: column; gap: 8px; max-width: 640px"><h1 style="margin: 0; font-size: 22px; font-weight: 600">{e(DECK_TITLE)}</h1>{note}</div>'
             f'{btn("Открыть и править", primary=True, href="Edit.dc.html")}</div>'
             f'<div style="display: grid; grid-template-columns: repeat(3, 296px); gap: 24px 20px">{cells}</div></div>')
    return f'{topbar("Презентации")}<div style="display: flex; flex-grow: 1; min-height: 0">{gen_left(steps)}{right}</div>'


def gen_error():
    err = (f'<div role="alert" style="display: flex; flex-direction: column; gap: 10px; padding: 12px; border-radius: 8px; background: {DANGER_SOFT}; border: 1px solid #5A2A2F">'
           f'<span style="font-size: 13px; line-height: 1.45">Qwen3.8 27B в LM Studio не ответила за минуту. Проверьте, что модель загружена, или выберите другого агента.</span>'
           f'<div style="display: flex; gap: 8px">{btn("Повторить", I_RETRY)}{btn("Агенты и модели", I_GEAR, href="Settings-local.dc.html")}</div></div>')
    mark = (f'<li style="display: flex; gap: 12px; align-items: flex-start">'
            f'<span style="width: 22px; height: 22px; border-radius: 999px; background: {DANGER}; display: flex; align-items: center; justify-content: center">{svg(I_ALERT, 14, INK)}</span>'
            f'<div style="flex-grow: 1; display: flex; flex-direction: column; gap: 10px; padding-top: 1px"><span style="font-size: 14px; font-weight: 600">План не составлен</span>{err}</div></li>')
    steps = (mark + step("wait", "Вёрстка") + step("wait", "Проверка по правилам шаблона") + step("wait", "Файлы pptx, pdf и html")
             + step("wait", "Проверка смысла") + step("wait", "Варианты 2 и 3"))
    right = (f'<div style="flex-grow: 1; min-width: 0; padding: 24px 32px; display: flex; flex-direction: column; gap: 20px">'
             f'<h1 style="margin: 0; font-size: 22px; font-weight: 600; color: {MUTED}">Новая презентация</h1>'
             f'<div style="display: grid; grid-template-columns: repeat(3, 296px); gap: 24px 20px">'
             + "".join(f'<div style="width: 296px; height: 167px; box-sizing: border-box; border-radius: 6px; border: 1px dashed {BORDER}"></div>' for _ in range(6)) + '</div></div>')
    return f'{topbar("Презентации")}<div style="display: flex; flex-grow: 1; min-height: 0">{gen_left(steps)}{right}</div>'


def edit(menu=False):
    body = (h.body_edit()
            .replace('href="#v2"', 'href="#v2" title="Проверки смысла у этого варианта не было"')
            .replace('href="#v3"', 'href="#v3" title="Проверки смысла у этого варианта не было"'))
    if menu:
        items = [("pptx", "для правки в PowerPoint"), ("pdf", "для рассылки"), ("html", "для показа в браузере")]
        rows = "".join(f'<li role="menuitem" tabindex="0" style="display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border-radius: 6px{"; background: " + SURF2 if i == 0 else ""}">'
                       f'<span style="font-size: 14px; font-family: {MONO}">{f}</span><span style="font-size: 12px; color: {MUTED}">{d}</span></li>' for i, (f, d) in enumerate(items))
        body += (f'<ul role="menu" aria-label="Формат файла" style="position: absolute; right: 24px; top: 118px; width: 300px; margin: 0; padding: 6px; list-style: none; '
                 f'border-radius: 10px; background: {SURF}; border: 1px solid {BORDER}; box-shadow: 0 12px 32px rgba(0,0,0,0.45)">{rows}</ul>')
    return body


def live_start():
    bar = (f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 24px; border-bottom: 1px solid {BORDER}">'
           f'<div style="display: flex; gap: 8px">{chip(WS["name"], thumb=WS["thumb"], aria="Дизайн-система: " + WS["name"])}{chip(AGENT_NOW, icon=I_CHIP, aria="Агент: " + AGENT_NOW)}</div>'
           f'{btn("Окно для зала", I_SCREEN, href="Hall.dc.html")}</div>')
    center = (f'<div style="flex-grow: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 28px">'
              f'<a href="Live.dc.html" style="display: flex; gap: 12px; align-items: center; height: 56px; padding: 0 28px; border-radius: 999px; background: {ACC}; color: {INK}; font-size: 16px; font-weight: 600">'
              f'{svg(I_MIC, 22, INK)}Начать запись</a>'
              f'<span style="font-size: 13px; color: {MUTED}">Браузер спросит доступ к микрофону</span>'
              f'<div style="display: flex; flex-direction: column; gap: 8px; width: 640px"><label for="typed" style="font-size: 13px; color: {MUTED}">Или введите текст вместо микрофона</label>'
              f'<div style="display: flex; gap: 8px"><input id="typed" type="text" placeholder="Например: пилот на двух витринах занял шесть недель" '
              f'style="flex-grow: 1; height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 8px; border: 1px solid {BORDER}; background: {SURF2}; color: {TEXT}; font-family: {UI}; font-size: 14px">'
              f'<button type="button" aria-label="Отправить текст" style="width: 40px; height: 40px; border-radius: 8px; border: 1px solid {BORDER}; background: {SURF2}; color: {TEXT}; display: flex; align-items: center; justify-content: center; cursor: pointer">{svg(I_SEND, 18)}</button></div></div></div>')
    return f'{topbar("Live-режим")}{bar}{center}'


def settings_cli():
    return h.body_settings_cli().replace(
        '2.1.270, найден в PATH</span>',
        f'2.1.270, найден в PATH</span><span role="status" style="font-size: 13px; color: {OK}; display: flex; gap: 6px; align-items: center">{svg(I_CHECK, 14, OK)}Проверено: отвечает, принимает картинки</span>', 1)


import re

FONT_MAP = {"11px": "12px", "15px": "14px", "18px": "16px", "22px": "20px", "32px": "28px"}
RADIUS_MAP = {"3px": "4px", "8px": "6px", "12px": "10px", "14px": "10px"}


def normalize(html):
    """Кегли и радиусы интерфейса по шкале docs/design/design-system.md; превью шрифта шаблона (Play) не трогаем."""
    def fix(m):
        s = m.group(1)
        if "Play" in s:
            return m.group(0)
        s = re.sub(r"font-size: (\d+px)", lambda x: "font-size: " + FONT_MAP.get(x.group(1), x.group(1)), s)
        s = re.sub(r"border-radius: (\d+px)", lambda x: "border-radius: " + RADIUS_MAP.get(x.group(1), x.group(1)), s)
        return f'style="{s}"'
    return re.sub(r'style="([^"]*)"', fix, html)


GAP_X, ROW_GAP = 80, 120 + 223
ROWS = [
    ("Презентация: запрос, генерация, правка", [
        ("Home-first.dc.html", "Первый запуск", 1440, 900, home_first),
        ("Home.dc.html", "Главная: о чём презентация", 1440, 900, h.body_home),
        ("Home-agent.dc.html", "Главная: выбор агента", 1440, 900, lambda: h.body_home(menu=True)),
        ("Generation.dc.html", "Генерация идёт", 1440, 1040, h.body_generation),
        ("Gen-done.dc.html", "Генерация закончена", 1440, 1010, gen_done),
        ("Gen-error.dc.html", "Генерация: модель не ответила", 1440, 900, gen_error),
        ("Gen-no-images.dc.html", "Генерация без LibreOffice", 1440, 1040, gen_no_images)]),
    ("Правка готовой презентации", [
        ("Edit.dc.html", "Правка слайда", 1440, 1330, edit),
        ("Edit-download.dc.html", "Скачать: выбор формата", 1440, 1330, lambda: edit(menu=True))]),
    ("Дизайн-система из своего pptx", [
        ("DS-new.dc.html", "Шаг 1: файл", 1440, 900, h.body_ds_new),
        ("DS-parsing.dc.html", "Шаг 2: разбор на глазах", 1440, 1990, lambda: g.body_a(WS, "loading")),
        ("DS-ready.dc.html", "Шаг 3: проверка, система готова", 1440, 1950, lambda: g.body_a(WS, focused=5)),
        ("DS-sample.dc.html", "Образец открыт", 1440, 1950, lambda: g.body_a_sample(WS))]),
    ("Дизайн-система: ошибки и крайние случаи", [
        ("DS-model-error.dc.html", "Модель не ответила", 1440, 1290, lambda: g.body_a(WS, "error")),
        ("DS-not-pptx.dc.html", "Файл не pptx", 1440, 900, lambda: h.upload_error("«Итоги_Q3.pdf» не pptx.", "Выберите презентацию PowerPoint с расширением .pptx.")),
        ("DS-broken.dc.html", "Файл повреждён", 1440, 900, lambda: h.upload_error("«Шаблон_2026.pptx» не открылся.", "Файл повреждён или сохранён не до конца. Сохраните его в PowerPoint заново и загрузите ещё раз.")),
        ("DS-empty.dc.html", "Систем нет", 1440, 900, h.body_ds_empty),
        ("DS-edge.dc.html", "55 образцов и три шрифта", 1440, 2850, lambda: g.body_a(g.EDU, active_side=1))]),
    ("Live-режим", [
        ("Live-start.dc.html", "До начала записи", 1440, 900, live_start),
        ("Live.dc.html", "Идёт запись", 1440, 900, h.body_live),
        ("Hall.dc.html", "Окно для зала", 1280, 720, h.body_hall)]),
    ("Агенты и модели", [
        ("Settings-cli.dc.html", "Локальный CLI", 1440, 1210, settings_cli),
        ("Settings-local.dc.html", "Локальная модель", 1440, 900, h.body_settings_local)]),
]

if __name__ == "__main__":
    for f in os.listdir(OUT):
        if f.endswith(".dc.html"):
            os.remove(os.path.join(OUT, f))
    boards, order, notes = {}, [], {}
    y = 0
    for ri, (row_title, items) in enumerate(ROWS):
        x = 0
        for fname, title, w, hh, fn in items:
            html = normalize(fn().replace("A-sample.dc.html", "DS-sample.dc.html").replace("C-file.dc.html", "DS-new.dc.html"))
            open(os.path.join(OUT, fname), "w", encoding="utf-8").write(g.page(title, w, hh, html))
            boards[fname] = {"x": x, "y": y, "w": w, "h": hh, "title": title}
            order.append(fname)
            x += w + GAP_X
        notes[f"row{ri}"] = {"x": 0, "y": y - 300, "text": row_title, "kind": "title1", "maxW": x - GAP_X}
        y += max(it[3] for it in items) + ROW_GAP
    notes["data"] = {"x": -640, "y": 0, "w": 540, "maxH": 1000, "fill": "gray",
                     "text": "Откуда данные. Бриф, план, слайды, замечания проверки и время шагов взяты из настоящей колоды сервиса от 23.09 (qwen3.8-27b, шаблон VK WorkSpace). "
                             "Дизайн-системы: ответ сервиса 23.09. Агенты: Claude Code 2.1.270 и OpenCode 1.18.16 найдены в PATH этой машины, Cursor Agent нашёл Open Design, Codex не установлен. "
                             "LM Studio отдаёт 5 моделей.\n\nПереходы в макете: генерация сама переходит в «Генерация закончена», в макете это клик по слайдам.\n\nПример, придуман для макета: время записи и текст речи на Live, текст ошибок, результат «Проверить».\n\n"
                             "В сервисе пока нет, рисуется по брифу: CLI-агенты через мост на машине, слайды по одному во время генерации, "
                             "правка на слайде и просьба агенту, смена образца у слайда, имя дизайн-системы, флажки образцов, сохранение настроек."}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = os.path.join(OUT, "canvas.json")
    created = json.load(open(path, encoding="utf-8")).get("createdOnFiles", {"v": 1, "at": now}) if os.path.exists(path) else {"v": 1, "at": now}
    idx = {"v": 3, "createdOnFiles": created, "title": "voiceDeck: приложение", "launch": {"view": "canvas"}, "pages": [],
           "boards": boards, "order": order, "notes": notes, "designSystems": []}
    json.dump(idx, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(h.PREVIEW_MAP, open(os.path.join(HERE, "preview_map.json"), "w"), indent=0)
    print("ok", len(order))
