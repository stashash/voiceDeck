# Холст «voiceDeck: приложение», версия 2 по карте брифа, подтверждённой владельцем 2026-09-24.
# Данные: колода 8187c701… (бриф examples/brief.txt, qwen3.8-27b, шаблон VK WorkSpace), ответы сервиса 23–24.09.
import json, os
from datetime import datetime, timezone
import gen as g
from gen import (e, svg, icon_btn, card, section_title, checkbox, BG, SURF, SURF2, BORDER, TEXT, MUTED, ACC, INK,
                 ACC_SOFT, OK, DANGER, DANGER_SOFT, UI, MONO, PLAY, WS, EDU, I_PLUS, I_CHECK, I_DOWN, I_CLOSE, I_INFO,
                 I_ALERT, I_RETRY, I_MIC, I_DECK, I_MORE, I_LEFT, I_RIGHT, I_UPLOAD, I_PEN)

OUT = g.OUT
DECK = {n: f"/_blob/{b}" for n, b in {
    "a1": "263e2b3ec0f8ee1b9b288e306c842b79", "a2": "ec4dac2ffa0f96d3b7991ea59f10cdf5", "a3": "16c378d9fe9b0cd5eebe2abd72926b99",
    "a4": "07cec058b18f59325421d4610affa10f", "a5": "8a649afb2d70a5ebe467a2797304dd3a", "a6": "15ed128cb72c4cf419e0d7329e201949",
    "a7": "cccfd6c3b0e712201a424ea87daf0fe7", "a8": "dba4b426622ef739260dd9efb787c669", "a9": "e37c35eea95c0ee84ba036f213b4d129",
    "a10": "32f264b1240658d55dcedfd43da7024f", "b1": "ef2306d8306308b5ba2183310ea0ac44", "c1": "0507159111703965929564c492ed554e",
    "r1": "a6412e5ec5b5dd3bdf4f6ffab16c66c0", "r2": "04c3bb03a4eb7afd4888da2b442ffdc4", "r3": "257c4cd8fdde98661007349adb314dd6"}.items()}
PREVIEW_MAP = {v.split("/")[-1]: f"../deck/{k}.png" for k, v in DECK.items()}
PREVIEW_MAP.update({DECK["r1"].split("/")[-1]: "../deck/r-2406fe.png", DECK["r2"].split("/")[-1]: "../deck/r-80023d.png",
                    DECK["r3"].split("/")[-1]: "../deck/r-daf2cc.png"})

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = json.load(open(os.path.join(HERE, "deck.json"), encoding="utf-8"))["plan"]
TITLES = [s["title"] for s in PLAN["slides"]]
BRIEF = ("Команда платформы данных предлагает инициативу: перевести ночные отчёты с пакетной загрузки на потоковую. "
         "Сейчас отчёт по продажам готов к 11 утра, после перехода к 8:30. Пилот на двух витринах занял 6 недель, "
         "затраты на инфраструктуру выросли на 12 %, число инцидентов с опозданием отчёта упало с 9 до 2 в месяц. "
         "Нужно решение руководства о переводе остальных 14 витрин до конца квартала. Аудитория: директора направлений.")
DECK_TITLE = PLAN["title"]

I_GEAR = '<circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"></path>'
I_SEND = '<path d="M12 19V5"></path><path d="M6 11l6-6 6 6"></path>'
I_STOP = '<rect x="6" y="6" width="12" height="12" rx="2"></rect>'
I_DOWNLOAD = '<path d="M12 4v12"></path><path d="M7 11l5 5 5-5"></path><path d="M4 20h16"></path>'
I_TERMINAL = '<rect x="3" y="4" width="18" height="16" rx="2"></rect><path d="M7 9l3 3-3 3"></path><path d="M13 15h4"></path>'
I_CHIP = '<rect x="6" y="6" width="12" height="12" rx="2"></rect><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"></path>'
I_COPY = '<rect x="8" y="8" width="12" height="12" rx="2"></rect><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"></path>'
I_TRASH = '<path d="M4 7h16"></path><path d="M9 7V4h6v3"></path><path d="M6 7l1 13h10l1-13"></path>'
I_GRIP = '<circle cx="9" cy="6" r="1"></circle><circle cx="15" cy="6" r="1"></circle><circle cx="9" cy="12" r="1"></circle><circle cx="15" cy="12" r="1"></circle><circle cx="9" cy="18" r="1"></circle><circle cx="15" cy="18" r="1"></circle>'
I_SCREEN = '<rect x="3" y="4" width="18" height="12" rx="2"></rect><path d="M8 20h8"></path><path d="M12 16v4"></path>'
I_REFRESH = I_RETRY

AGENT_NOW = "Qwen3.8 27B в LM Studio"
NAV = {"Презентации": "Home.dc.html", "Дизайн-системы": "DS-ready.dc.html", "Live-режим": "Live-start.dc.html"}


# ---------- общий каркас ----------
def topbar(active):
    tabs = []
    for t in ["Презентации", "Дизайн-системы", "Live-режим"]:
        on = t == active
        cur = ' aria-current="page"' if on else ""
        tabs.append(f'<a href="{NAV[t]}"{cur} style="display: flex; align-items: center; height: 56px; box-sizing: border-box; padding: 0 4px; '
                    f'font-size: 14px; font-weight: {600 if on else 500}; color: {TEXT if on else MUTED}; '
                    f'border-bottom: 2px solid {ACC if on else "transparent"}">{t}</a>')
    gear_on = active == "Настройки"
    gear = (f'<a href="Settings-cli.dc.html" aria-label="Настройки: агенты и модели" title="Агенты и модели" style="width: 36px; height: 36px; display: flex; align-items: center; '
            f'justify-content: center; border-radius: 6px; color: {TEXT if gear_on else MUTED}; background: {SURF2 if gear_on else "transparent"}">{svg(I_GEAR)}</a>')
    return (f'<nav aria-label="Разделы" style="flex-shrink: 0; height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; '
            f'background: {SURF}; border-bottom: 1px solid {BORDER}"><div style="display: flex; gap: 28px">{"".join(tabs)}</div>{gear}</nav>')


def ds_actions(disabled=False):
    op = "0.45" if disabled else "1"
    wait = ": станет доступно, когда модель опишет образцы" if disabled else ""
    return (f'<div style="display: flex; gap: 8px; align-items: center; flex-shrink: 0">'
            f'<a href="Home.dc.html" title="Новая презентация по этой дизайн-системе{wait}" style="display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 16px 0 12px; '
            f'border-radius: 6px; background: {ACC}; color: {INK}; font-size: 14px; font-weight: 600; opacity: {op}">{svg(I_DECK, 18, INK)}Создать презентацию</a>'
            f'<a href="Live.dc.html" title="Live-режим по этой дизайн-системе{wait}" style="display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 16px 0 12px; '
            f'border-radius: 6px; background: {SURF2}; border: 1px solid {BORDER}; color: {TEXT}; font-size: 14px; font-weight: 500; opacity: {op}">{svg(I_MIC, 18)}Выступить</a>'
            f'{icon_btn(I_MORE, "Ещё: удалить дизайн-систему")}</div>')


g.topbar = lambda: topbar("Дизайн-системы")
g.actions = ds_actions


def chip(label, thumb=None, icon=None, open_=False, aria=""):
    lead = (f'<img src="{thumb}" alt="" style="width: 32px; height: 18px; object-fit: cover; border-radius: 3px; border: 1px solid {BORDER}">' if thumb
            else svg(icon, 18) if icon else "")
    return (f'<button type="button" aria-haspopup="listbox" aria-expanded="{"true" if open_ else "false"}" aria-label="{e(aria or label)}" '
            f'style="display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 10px; border-radius: 8px; cursor: pointer; font-size: 13px; '
            f'background: {SURF2 if open_ else "transparent"}; border: 1px solid {BORDER}; color: {TEXT}">{lead}<span>{e(label)}</span>{svg(I_DOWN, 16)}</button>')


def slide_img(src, w, extra=""):
    h = round(w * 9 / 16)
    return f'<img src="{src}" alt="" style="display: block; width: {w}px; height: {h}px; border-radius: 6px; box-shadow: 0 0 0 1px {BORDER}; {extra}">'


def btn(label, icon=None, primary=False, href=None, aria=None, disabled=False):
    st = (f"display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 {14 if icon else 16}px; border-radius: 6px; font-size: 14px; cursor: pointer; "
          + (f"background: {ACC}; color: {INK}; font-weight: 600; border: 0" if primary else f"background: {SURF2}; color: {TEXT}; font-weight: 500; border: 1px solid {BORDER}")
          + (f"; opacity: 0.45" if disabled else ""))
    ic = svg(icon, 18, INK if primary else "currentColor") if icon else ""
    a = f' aria-label="{e(aria)}"' if aria else ""
    if href:
        return f'<a href="{href}"{a} style="{st}">{ic}{label}</a>'
    return f'<button type="button"{a}{" disabled=\"\"" if disabled else ""} style="{st}">{ic}{label}</button>'


# ---------- Презентации: главная ----------
AGENTS = [
    ("Локальный CLI", [("Claude Code", "2.1.270, модель по умолчанию", I_TERMINAL, False),
                       ("OpenCode", "1.18.16, minimax/MiniMax-M3", I_TERMINAL, False),
                       ("Cursor Agent", "2026.08.11, модель по умолчанию", I_TERMINAL, False)]),
    ("Локальная модель", [("Qwen3.8 27B", "LM Studio, загружена", I_CHIP, True),
                          ("Gemma 4 26B", "LM Studio", I_CHIP, False)]),
]


def agent_menu():
    groups = []
    for head, items in AGENTS:
        rows = "".join(
            f'<li role="option" aria-selected="{"true" if sel else "false"}" style="display: flex; gap: 12px; align-items: center; padding: 8px 10px; border-radius: 6px; '
            f'background: {ACC_SOFT if sel else "transparent"}">{svg(ic, 18, TEXT)}'
            f'<span style="display: flex; flex-direction: column; gap: 2px; flex-grow: 1"><span style="font-size: 14px">{n}</span>'
            f'<span style="font-size: 12px; color: {MUTED}">{sub}</span></span>{svg(I_CHECK, 18, TEXT) if sel else ""}</li>'
            for n, sub, ic, sel in items)
        groups.append(f'<div style="display: flex; flex-direction: column; gap: 2px"><span style="font-size: 12px; color: {MUTED}; padding: 4px 10px">{head}</span>'
                      f'<ul role="listbox" aria-label="{head}" style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px">{rows}</ul></div>')
    return (f'<div style="position: absolute; right: 64px; top: 216px; width: 340px; padding: 8px; box-sizing: border-box; border-radius: 10px; background: {SURF}; '
            f'border: 1px solid {BORDER}; box-shadow: 0 12px 32px rgba(0,0,0,0.45); display: flex; flex-direction: column; gap: 8px; z-index: 2">'
            f'{"".join(groups)}<div style="height: 1px; background: {BORDER}"></div>'
            f'<a href="Settings-cli.dc.html" style="display: flex; gap: 10px; align-items: center; padding: 8px 10px; font-size: 13px; color: {TEXT}">{svg(I_GEAR, 18)}Настроить агентов</a></div>')


def prompt_box(menu=False):
    return (f'<div style="position: relative; width: 880px; box-sizing: border-box; border-radius: 14px; background: {SURF}; border: 1px solid {BORDER}; padding: 16px 16px 12px; '
            f'display: flex; flex-direction: column; gap: 12px">'
            f'<label for="brief" style="position: absolute; left: -9999px">Бриф, текст или идея презентации</label>'
            f'<textarea id="brief" rows="6" style="width: 100%; box-sizing: border-box; resize: none; background: transparent; border: 0; color: {TEXT}; font-family: {UI}; font-size: 15px; line-height: 1.55; outline: none">{e(BRIEF)}</textarea>'
            f'<div style="display: flex; justify-content: space-between; align-items: center">'
            f'<div style="display: flex; gap: 8px">{chip(WS["name"], thumb=WS["thumb"], aria="Дизайн-система: " + WS["name"])}'
            f'{chip(AGENT_NOW, icon=I_CHIP, open_=menu, aria="Агент: " + AGENT_NOW)}</div>'
            f'<a href="Generation.dc.html" aria-label="Создать презентацию" title="Создать презентацию" style="width: 40px; height: 40px; border-radius: 999px; border: 0; background: {ACC}; '
            f'display: flex; align-items: center; justify-content: center; cursor: pointer">{svg(I_SEND, 20, INK)}</a></div>'
            f'{agent_menu() if menu else ""}</div>')


def recent():
    items = [(DECK["a1"], DECK_TITLE, "10 слайдов", WS["name"], "Edit.dc.html"),
             (DECK["r1"], "Переход на потоковую загрузку ночных отчётов", "14 слайдов", WS["name"], "Edit.dc.html"),
             (DECK["r2"], "Переход на потоковые отчёты: решение по 14 витринам", "11 слайдов", "VK Tech", "Edit.dc.html"),
             (DECK["r3"], "Дрессировка кошек: мифы и реальность", "5 слайдов", "VK Tech", "Edit.dc.html")]
    cards = "".join(
        f'<a href="{h}" style="display: flex; flex-direction: column; gap: 10px; min-width: 0">{slide_img(src, 248)}'
        f'<span style="font-size: 14px; font-weight: 500; line-height: 1.35; color: {TEXT}">{e(t)}</span>'
        f'<span style="font-size: 12px; color: {MUTED}">{n}, {e(ds)}</span></a>' for src, t, n, ds, h in items)
    return (f'<section style="width: 1056px; display: flex; flex-direction: column; gap: 16px">'
            f'{section_title("Недавние презентации")}'
            f'<div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px">{cards}</div></section>')


def body_home(menu=False):
    return (f'{topbar("Презентации")}<main style="flex-grow: 1; display: flex; flex-direction: column; align-items: center; gap: 56px; padding: 72px 0 48px">'
            f'<div style="display: flex; flex-direction: column; align-items: center; gap: 24px">'
            f'<h1 style="margin: 0; font-size: 32px; font-weight: 600; letter-spacing: -0.01em">О чём будет презентация?</h1>'
            f'{prompt_box(menu)}</div>{recent()}</main>')


# ---------- Генерация ----------
def step(state, title, right="", sub=""):
    mark = {"done": f'<span style="width: 22px; height: 22px; border-radius: 999px; background: {OK}; display: flex; align-items: center; justify-content: center">{svg(I_CHECK, 14, INK)}</span>',
            "run": f'<span style="width: 22px; height: 22px; border-radius: 999px; box-sizing: border-box; border: 2px solid {ACC}; border-right-color: transparent"></span>',
            "wait": f'<span style="width: 22px; height: 22px; border-radius: 999px; box-sizing: border-box; border: 1.5px solid {BORDER}"></span>'}[state]
    return (f'<li{" aria-current=\"step\"" if state == "run" else ""} style="display: flex; gap: 12px; align-items: flex-start">{mark}'
            f'<div style="flex-grow: 1; display: flex; flex-direction: column; gap: 6px; padding-top: 1px">'
            f'<div style="display: flex; justify-content: space-between; gap: 8px"><span style="font-size: 14px; font-weight: {600 if state == "run" else 500}; color: {TEXT if state != "wait" else MUTED}">{title}</span>'
            f'<span style="font-size: 12px; color: {MUTED}; font-family: {MONO}">{right}</span></div>{sub}</div></li>')


def body_generation():
    plan_list = "".join(f'<li style="font-size: 12px; color: {MUTED}; line-height: 1.5">{i}. {e(t)}</li>' for i, t in enumerate(TITLES, 1))
    bar = (f'<div role="progressbar" aria-valuemin="0" aria-valuemax="10" aria-valuenow="5" aria-label="Готово слайдов" style="height: 4px; border-radius: 999px; background: {SURF2}">'
           f'<div style="width: 50%; height: 4px; border-radius: 999px; background: {ACC}"></div></div>'
           f'<span style="font-size: 13px; color: {TEXT}">Агент пишет текст слайда «{e(TITLES[5])}»</span>')
    steps = (f'<ol aria-label="Ход работы" style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 18px">'
             f'{step("done", "План из 10 слайдов", "33 с", f"<ol style=\"margin: 0; padding: 0 0 0 0; list-style: none\">{plan_list}</ol>")}'
             f'{step("run", "Вёрстка: готово 5 из 10", "", bar)}'
             f'{step("wait", "Проверка по правилам шаблона")}'
             f'{step("wait", "Файлы pptx, pdf и html")}'
             f'{step("wait", "Проверка смысла")}'
             f'{step("wait", "Варианты 2 и 3")}</ol>')
    left = (f'<aside aria-label="Ход работы" style="width: 420px; flex-shrink: 0; box-sizing: border-box; background: {SURF}; border-right: 1px solid {BORDER}; '
            f'padding: 24px; display: flex; flex-direction: column; gap: 24px">'
            f'<div style="display: flex; flex-direction: column; gap: 8px"><span style="font-size: 12px; color: {MUTED}">Запрос</span>'
            f'<p style="margin: 0; font-size: 13px; line-height: 1.5; color: {TEXT}; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden">{e(BRIEF)}</p></div>'
            f'<div style="display: flex; gap: 16px; font-size: 13px; color: {MUTED}"><span style="display: flex; gap: 6px; align-items: center">{svg(I_CHIP, 16)}{AGENT_NOW}</span></div>'
            f'<div style="height: 1px; background: {BORDER}"></div>{steps}</aside>')
    cells = []
    for i, t in enumerate(TITLES, 1):
        if i <= 5:
            cells.append(f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 8px">{slide_img(DECK[f"a{i}"], 296)}'
                         f'<figcaption style="font-size: 12px; color: {MUTED}">{i}</figcaption></figure>')
        elif i == 6:
            cells.append(f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 8px">'
                         f'<div style="width: 296px; height: 167px; box-sizing: border-box; border-radius: 6px; border: 2px solid {ACC}; background: {SURF2}; padding: 16px; display: flex; flex-direction: column; gap: 10px">'
                         f'<span style="font-size: 12px; color: {TEXT}">{e(t)}</span>'
                         f'<span style="height: 8px; width: 60%; border-radius: 4px; background: {BORDER}"></span><span style="height: 8px; width: 40%; border-radius: 4px; background: {BORDER}"></span>'
                         f'<span style="margin-top: auto; font-size: 12px; color: {ACC}">верстается</span></div>'
                         f'<figcaption style="font-size: 12px; color: {TEXT}">{i}. {e(t)}</figcaption></figure>')
        else:
            cells.append(f'<figure style="margin: 0; display: flex; flex-direction: column; gap: 8px">'
                         f'<div style="width: 296px; height: 167px; box-sizing: border-box; border-radius: 6px; border: 1px dashed {BORDER}"></div>'
                         f'<figcaption style="font-size: 12px; color: {MUTED}">{i}. {e(t)}</figcaption></figure>')
    right = (f'<div style="flex-grow: 1; min-width: 0; padding: 24px 32px; display: flex; flex-direction: column; gap: 20px">'
             f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px">'
             f'<div style="display: flex; flex-direction: column; gap: 6px"><h1 style="margin: 0; font-size: 22px; font-weight: 600">{e(DECK_TITLE)}</h1>'
             f'<span style="font-size: 13px; color: {MUTED}">Вариант 1 из 3, {e(WS["name"])}</span></div>'
             f'{btn("Остановить", I_STOP)}</div>'
             f'<a href="Gen-done.dc.html" aria-label="Слайды по мере вёрстки" style="display: grid; grid-template-columns: repeat(3, 296px); gap: 24px 20px">{"".join(cells)}</a></div>')
    return f'{topbar("Презентации")}<div style="display: flex; flex-grow: 1; min-height: 0">{left}{right}</div>'


# ---------- Правка ----------
REMARKS = {1: 1, 2: 3, 3: 4, 5: 5, 6: 4, 7: 2, 8: 3, 9: 1, 10: 7}
ERRORS = {2, 5, 10}


def body_edit():
    strip = []
    for i, t in enumerate(TITLES, 1):
        sel = i == 5
        badge = ""
        if i in REMARKS:
            col = DANGER if i in ERRORS else ACC
            badge = (f'<span style="position: absolute; right: 6px; top: 6px; height: 20px; padding: 0 6px; box-sizing: border-box; border-radius: 999px; '
                     f'background: {"#5A2A2F" if i in ERRORS else "rgba(15,17,21,0.88)"}; color: {TEXT}; font-size: 11px; font-weight: 600; display: flex; gap: 4px; align-items: center">'
                     f'{svg(I_ALERT, 12, DANGER) if i in ERRORS else ""}{REMARKS[i]}<span style="position: absolute; left: -9999px">{"есть ошибки, " if i in ERRORS else ""}замечаний: {REMARKS[i]}</span></span>')
        grip = ""
        strip.append(f'<a href="#s{i}"{" aria-current=\"true\"" if sel else ""} aria-label="Слайд {i}: {e(t)}" style="position: relative; display: flex; gap: 8px; align-items: flex-start">'
                     f'<span style="width: 18px; font-size: 12px; color: {MUTED}; font-family: {MONO}; text-align: right; padding-top: 2px">{i}</span>'
                     f'<span style="position: relative; display: block">{slide_img(DECK[f"a{i}"], 176, f"box-shadow: 0 0 0 {2 if sel else 1}px {ACC if sel else BORDER}")}{badge}</span>{grip}</a>')
    left = (f'<aside aria-label="Слайды" style="width: 248px; flex-shrink: 0; box-sizing: border-box; border-right: 1px solid {BORDER}; background: {SURF}; padding: 16px 16px 16px 24px; '
            f'display: flex; flex-direction: column; gap: 14px; overflow: hidden">{"".join(strip)}'
            f'<button type="button" style="display: flex; gap: 8px; align-items: center; justify-content: center; height: 36px; margin-left: 26px; border-radius: 6px; border: 1px dashed {BORDER}; '
            f'background: transparent; color: {TEXT}; font-size: 13px; cursor: pointer">{svg(I_PLUS, 16)}Слайд</button></aside>')
    W = 800
    H = round(W * 9 / 16)
    sel_box = (f'<div style="position: absolute; left: {0.515 * W:.0f}px; top: {0.19 * H:.0f}px; width: {0.33 * W:.0f}px; height: {0.16 * H:.0f}px; box-sizing: border-box; '
               f'border: 2px solid {ACC}; border-radius: 2px"></div>'
               f'<div role="toolbar" aria-label="Текст на слайде" style="position: absolute; left: {0.515 * W:.0f}px; top: {0.35 * H + 8:.0f}px; display: flex; gap: 2px; padding: 3px; '
               f'border-radius: 8px; background: {SURF}; border: 1px solid {BORDER}">'
               f'{icon_btn(I_PEN, "Править текст")}'
               f''
               f'{icon_btn(I_RETRY, "Вернуть как было")}</div>')
    center = (f'<div style="flex-grow: 1; min-width: 0; padding: 72px 32px 32px; display: flex; flex-direction: column; align-items: center; gap: 20px">'
              f'<div style="position: relative; width: {W}px; height: {H}px">{slide_img(DECK["a5"], W)}{sel_box}</div>'
              f'<div style="width: {W}px; display: flex; flex-direction: column; gap: 8px"><label for="notes" style="font-size: 12px; color: {MUTED}">Заметки докладчика</label>'
              f'<textarea id="notes" rows="2" style="box-sizing: border-box; width: 100%; resize: none; border-radius: 8px; border: 1px solid {BORDER}; background: {SURF}; color: {TEXT}; '
              f'font-family: {UI}; font-size: 14px; line-height: 1.5; padding: 10px 12px">Мы провели пилот на двух витринах, что заняло 6 недель.</textarea></div></div>')
    alts = [(g.WS["img"](17), "Большое число", True), (g.WS["img"](5), "Карточки", False),
            (g.WS["img"](8), "Шаги", False), (g.WS["img"](14), "Таблица", False)]
    alt_html = "".join(
        f'<button type="button" aria-pressed="{"true" if cur else "false"}" aria-label="Образец: {k}" style="padding: 0; border: 0; background: transparent; cursor: pointer; '
        f'display: flex; flex-direction: column; gap: 6px; color: {TEXT}; text-align: left">'
        f'<img src="{src}" alt="" style="width: 148px; height: 83px; border-radius: 6px; box-shadow: 0 0 0 {2 if cur else 1}px {ACC if cur else BORDER}">'
        f'<span style="font-size: 12px; color: {TEXT if cur else MUTED}">{"Текущий: " + k.lower() if cur else k}</span></button>' for src, k, cur in alts)
    rem = [("error", "Число «6 недель» не помещается в рамку при кегле 58 пт", "Исправить"),
           ("warn", "Число «6 недель» не стоит на направляющей шаблона", "Исправить"),
           ("warn", "Подпись «Длительность пилота» не стоит на направляющей шаблона", "Исправить"),
           ("warn", "Заголовок сообщает факт, а вывода для руководства нет", "Переписать"),
           ("warn", "Точки и чёрточки оформления не связаны с темой слайда", "Переписать")]
    rem_html = "".join(
        f'<li style="display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; border-top: 1px solid {BORDER}">'
        f'{svg(I_ALERT, 18, DANGER if s == "error" else MUTED)}<span style="flex-grow: 1; font-size: 13px; line-height: 1.45"><span style="display: block; font-size: 12px; color: {DANGER if s == "error" else MUTED}">{"Ошибка" if s == "error" else "Предупреждение"}</span>{e(t)}</span>'
        f'{btn(a) if a else ""}</li>' for s, t, a in rem)
    ask = (f'<div style="display: flex; flex-direction: column; gap: 10px"><label for="ask" style="font-size: 16px; font-weight: 600">Попросить агента</label>'
           f'<div style="display: flex; gap: 8px"><input id="ask" type="text" placeholder="Например: убери вводную фразу из заголовка" '
           f'style="flex-grow: 1; min-width: 0; height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 8px; border: 1px solid {BORDER}; background: {SURF2}; color: {TEXT}; font-family: {UI}; font-size: 14px">'
           f'<button type="button" aria-label="Отправить агенту" style="width: 40px; height: 40px; border-radius: 8px; border: 1px solid {BORDER}; background: {SURF2}; color: {TEXT}; display: flex; align-items: center; justify-content: center; cursor: pointer">{svg(I_SEND, 18)}</button></div>'
           f'<div style="display: flex; gap: 6px; flex-wrap: wrap">'
           + "".join(f'<button type="button" style="height: 32px; padding: 0 10px; border-radius: 999px; border: 1px solid {BORDER}; background: transparent; color: {TEXT}; font-size: 12px; cursor: pointer">{c}</button>'
                     for c in ["Короче", "Сделай диаграммой", "Вынести вывод в заголовок"]) + '</div></div>')
    right = (f'<aside aria-label="Слайд 5" style="width: 360px; flex-shrink: 0; box-sizing: border-box; border-left: 1px solid {BORDER}; background: {SURF}; padding: 20px 24px; '
             f'display: flex; flex-direction: column; gap: 24px; overflow: hidden">'
             f'<div style="display: flex; justify-content: space-between; align-items: center"><h2 style="margin: 0; font-size: 18px; font-weight: 600">Слайд 5</h2>'
             f'<div style="display: flex; gap: 2px">{icon_btn(I_COPY, "Копия слайда")}{icon_btn(I_TRASH, "Удалить слайд")}</div></div>'
             f'<div style="display: flex; flex-direction: column; gap: 10px">{section_title("Образец", "", "h3")}'
             f'<div style="display: grid; grid-template-columns: repeat(2, 148px); gap: 12px 16px">{alt_html}</div></div>'
             f'{ask}'
             f'<div style="display: flex; flex-direction: column">{section_title("Замечания проверки", f"<span style=\"font-size: 13px; color: {MUTED}\">5</span>", "h3")}'
             f'<ul style="list-style: none; margin: 8px 0 0; padding: 0">{rem_html}</ul></div></aside>')
    tabs = "".join(
        f'<a href="#v{i}"{" aria-current=\"page\"" if i == 1 else ""} style="height: 36px; display: flex; align-items: center; padding: 0 12px; border-radius: 6px; font-size: 13px; '
        f'background: {SURF2 if i == 1 else "transparent"}; border: 1px solid {TEXT if i == 1 else BORDER}; color: {TEXT if i == 1 else MUTED}">Вариант {i}</a>' for i in (1, 2, 3))
    head = (f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 24px; border-bottom: 1px solid {BORDER}">'
            f'<div style="display: flex; gap: 8px; align-items: center; min-width: 0"><h1 style="margin: 0; font-size: 18px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{e(DECK_TITLE)}</h1>{icon_btn(I_PEN, "Переименовать")}</div>'
            f'<div role="group" aria-label="Варианты вёрстки" style="display: flex; gap: 6px">{tabs}</div>'
            f'<div style="display: flex; gap: 8px">{btn("Скачать", I_DOWNLOAD, primary=True, href="Edit-download.dc.html", aria="Скачать: pptx, pdf или html")}</div></div>')
    return (f'{topbar("Презентации")}{head}<div style="display: flex; flex-grow: 1; min-height: 0">{left}{center}{right}</div>')


# ---------- Live-режим ----------
TRANSCRIPT = [
    ("Пилот мы запустили на двух витринах, на это ушло шесть недель.", False),
    ("Затраты на инфраструктуру выросли на двенадцать процентов, это цена скорости.", False),
    ("Зато отчёты теперь не опаздывают: было девять таких случаев в месяц, стало два.", True),
]


def body_live():
    tr = "".join(f'<p style="margin: 0; font-size: 15px; line-height: 1.55; color: {TEXT if hl else MUTED}; '
                 f'{f"background: {ACC_SOFT}; border-radius: 6px; padding: 6px 8px; margin: 0 -8px" if hl else ""}">{e(t)}</p>' for t, hl in TRANSCRIPT)
    bar = (f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 24px; border-bottom: 1px solid {BORDER}">'
           f'<div style="display: flex; gap: 8px">{chip(WS["name"], thumb=WS["thumb"], aria="Дизайн-система: " + WS["name"])}{chip(AGENT_NOW, icon=I_CHIP, aria="Агент: " + AGENT_NOW)}</div>'
           f'<div style="display: flex; gap: 12px; align-items: center">'
           f'<span role="status" style="display: flex; gap: 8px; align-items: center; font-size: 14px; font-family: {MONO}"><span style="width: 10px; height: 10px; border-radius: 999px; background: {DANGER}"></span>Запись 04:12</span>'
           f'{btn("Стоп", I_STOP)}{btn("Окно для зала", I_SCREEN, href="Hall.dc.html")}</div></div>')
    now = (f'<section style="display: flex; flex-direction: column; gap: 10px">{section_title("На экране зала", btn("Вернуть прошлый", I_RETRY), "h2")}'
           f'{slide_img(DECK["a6"], 760)}</section>')
    draft = (f'<section style="display: flex; flex-direction: column; gap: 10px">{section_title("Следующий слайд из речи", "", "h2")}'
             f'<div style="position: relative">{slide_img(DECK["a7"], 520, f"box-shadow: 0 0 0 2px {ACC}")}</div>'
             f'<div style="display: flex; gap: 8px">{btn("Показать залу", I_SEND, primary=True)}{btn("Убрать", I_CLOSE)}</div>'
             f'<span style="font-size: 12px; color: {MUTED}">Пробел показывает, Backspace убирает</span></section>')
    words = (f'<section style="display: flex; flex-direction: column; gap: 10px; flex-grow: 1">{section_title("Что вы сказали", "", "h2")}'
             f'<div style="display: flex; flex-direction: column; gap: 8px">{tr}</div></section>')
    body = (f'<div style="display: flex; gap: 32px; padding: 24px; flex-grow: 1; min-height: 0">'
            f'<div style="display: flex; flex-direction: column; gap: 24px">{now}</div>'
            f'<div style="display: flex; flex-direction: column; gap: 24px; flex-grow: 1; min-width: 0">{draft}{words}</div></div>')
    return f'{topbar("Live-режим")}{bar}{body}'


def body_hall():
    return f'<img src="{DECK["a6"]}" alt="Слайд на экране зала" style="display: block; width: 1280px; height: 720px">'


# ---------- Настройки: агенты и модели ----------
def settings_shell(tab, inner):
    tabs = "".join(
        f'<a href="{href}" role="tab" aria-selected="{"true" if t == tab else "false"}" style="flex: 1; height: 40px; display: flex; align-items: center; justify-content: center; border-radius: 8px; '
        f'font-size: 14px; font-weight: {600 if t == tab else 500}; background: {SURF2 if t == tab else "transparent"}; color: {TEXT if t == tab else MUTED}">{t}</a>'
        for t, href in [("Локальный CLI", "Settings-cli.dc.html"), ("Локальная модель", "Settings-local.dc.html")])
    return (f'{topbar("Настройки")}<main style="flex-grow: 1; display: flex; justify-content: center; padding: 40px 0">'
            f'<div style="width: 880px; display: flex; flex-direction: column; gap: 24px">'
            f'<h1 style="margin: 0; font-size: 28px; font-weight: 600">Агенты и модели</h1>'
            f'<div role="tablist" style="display: flex; gap: 4px; padding: 4px; border-radius: 10px; background: {SURF}; border: 1px solid {BORDER}">{tabs}</div>{inner}</div></main>')


def radio(on, label):
    return (f'<span role="radio" aria-checked="{"true" if on else "false"}" aria-label="{e(label)}" tabindex="0" style="width: 20px; height: 20px; flex-shrink: 0; border-radius: 999px; box-sizing: border-box; '
            f'border: 1.5px solid {TEXT if on else MUTED}; display: flex; align-items: center; justify-content: center">'
            f'{f"<span style=\"width: 10px; height: 10px; border-radius: 999px; background: {TEXT}\"></span>" if on else ""}</span>')


def cli_row(name, sub, found, model=None, open_=False):
    head = (f'<div style="display: flex; gap: 14px; align-items: center">'
            f'<span style="width: 36px; height: 36px; border-radius: 8px; background: {SURF2}; display: flex; align-items: center; justify-content: center">{svg(I_TERMINAL, 20)}</span>'
            f'<div style="display: flex; flex-direction: column; gap: 2px; flex-grow: 1"><span style="font-size: 15px; font-weight: 500">{name}</span>'
            f'<span style="font-size: 13px; color: {MUTED}">{sub}</span></div>'
            + (btn("Проверить") if found else f'<a href="#install-{name}" style="font-size: 13px; color: {TEXT}; text-decoration: underline">Как установить</a>') + '</div>')
    body = ""
    if model is not None:
        body = (f'<div style="display: flex; flex-direction: column; gap: 6px; padding-left: 50px"><label for="m-{name}" style="font-size: 12px; color: {MUTED}">Модель</label>'
                f'<input id="m-{name}" type="text" value="{e(model)}" placeholder="модель по умолчанию в CLI" style="height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 6px; border: 1px solid {BORDER}; '
                f'background: {SURF2}; color: {TEXT}; font-family: {MONO}; font-size: 13px"></div>')
    return (f'<div style="display: flex; flex-direction: column; gap: 14px; padding: 16px; border-radius: 10px; background: {SURF}; border: 1px solid {BORDER}">{head}{body}</div>')


def use_for():
    sel = lambda lab, val, idd: (f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px"><label for="{idd}" style="font-size: 14px">{lab}</label>'
                                 f'<select id="{idd}" style="width: 320px; height: 40px; border-radius: 6px; border: 1px solid {BORDER}; background: {SURF2}; color: {TEXT}; font-family: {UI}; font-size: 14px; padding: 0 10px">'
                                 f'<option>{val}</option></select></div>')
    return card(f'{section_title("Какой агент что делает", "", "h2")}{sel("Презентации", AGENT_NOW, "use-deck")}{sel("Live-режим", AGENT_NOW, "use-live")}'
                f'{sel("Описание образцов дизайн-системы", AGENT_NOW, "use-ds")}', gap=14)


def body_settings_cli():
    rows = (cli_row("Claude Code", "2.1.270, найден в PATH", True, "")
            + cli_row("OpenCode", "1.18.16, найден в PATH", True, "minimax/MiniMax-M3").replace("1.18.16, найден в PATH</span>", f'1.18.16, найден в PATH</span><span role="status" style="font-size: 13px; color: {DANGER}">Не ответил за 30 с. Проверьте, что OpenCode вошёл в аккаунт</span>', 1)
            + cli_row("Cursor Agent", "2026.08.11, найден в PATH", True, "").replace("2026.08.11, найден в PATH</span>", f'2026.08.11, найден в PATH</span><span role="status" style="font-size: 13px; color: {TEXT}">Отвечает, картинки не принимает: для описания образцов не подойдёт</span>', 1)
            + cli_row("Codex", "не найден в PATH", False))
    inner = (f'<div style="display: flex; justify-content: space-between; align-items: center"><span style="font-size: 14px; color: {TEXT}">Сервис ищет CLI-агентов в PATH этой машины.</span>'
             f'{btn("Искать снова", I_REFRESH)}</div><div style="display: flex; flex-direction: column; gap: 12px">{rows}</div>{use_for()}')
    return settings_shell("Локальный CLI", inner)


def body_settings_local():
    fld = lambda lab, val, idd, mono=True: (f'<div style="display: flex; flex-direction: column; gap: 6px"><label for="{idd}" style="font-size: 12px; color: {MUTED}">{lab}</label>'
                                            f'<input id="{idd}" type="text" value="{e(val)}" style="height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 6px; border: 1px solid {BORDER}; '
                                            f'background: {SURF2}; color: {TEXT}; font-family: {MONO if mono else UI}; font-size: 13px"></div>')
    sel = lambda lab, opts, idd: (f'<div style="display: flex; flex-direction: column; gap: 6px"><label for="{idd}" style="font-size: 12px; color: {MUTED}">{lab}</label>'
                                  f'<select id="{idd}" style="height: 40px; border-radius: 6px; border: 1px solid {BORDER}; background: {SURF2}; color: {TEXT}; font-family: {MONO}; font-size: 13px; padding: 0 10px">'
                                  + "".join(f"<option>{o}</option>" for o in opts) + '</select></div>')
    lm = card(f'<div style="display: flex; gap: 14px; align-items: center">'
              f'<span style="width: 36px; height: 36px; border-radius: 8px; background: {SURF2}; display: flex; align-items: center; justify-content: center">{svg(I_CHIP, 20)}</span>'
              f'<div style="display: flex; flex-direction: column; gap: 2px; flex-grow: 1"><span style="font-size: 15px; font-weight: 500">LM Studio</span>'
              f'<span role="status" style="font-size: 13px; color: {OK}">Сервер отвечает, моделей: 5</span></div>{btn("Проверить")}</div>'
              f'<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 16px; padding-left: 50px">'
              f'{fld("Адрес сервера", "http://127.0.0.1:1234/v1", "lm-url")}'
              f'{sel("Модель для текста и картинок", ["qwen/qwen3.8-27b", "google/gemma-4-26b-a4b"], "lm-model")}'
              f'{sel("Модель, которая замечает смену темы в речи", ["text-embedding-bge-m3", "text-embedding-qwen3-embedding-0.6b", "text-embedding-nomic-embed-text-v1.5"], "lm-emb")}'
              f'</div>', gap=16)
    inner = (f'<span style="font-size: 14px; color: {TEXT}">Модель работает на этой машине через OpenAI-совместимый сервер.</span>{lm}{use_for()}')
    return settings_shell("Локальная модель", inner)


# ---------- Дизайн-системы: создание ----------
def body_ds_new():
    col = (f'<div style="width: 760px; margin: 0 auto; padding: 48px 0; display: flex; flex-direction: column; gap: 24px">'
           f'<h1 style="margin: 0; font-size: 28px; font-weight: 600">Новая дизайн-система</h1>{g.dropzone()}'
           f'<p style="margin: 0; font-size: 13px; color: {MUTED}">Сервис возьмёт из pptx палитру, шрифты, кегли, поля и слайды-образцы. Сам файл не меняется.</p></div>')
    return (f'{topbar("Дизайн-системы")}<div style="display: flex; flex-grow: 1; min-height: 0">{g.sidebar(active=-1)}'
            f'<main style="flex-grow: 1">{col}</main></div>')


def body_ds_empty():
    return (f'{topbar("Дизайн-системы")}<main style="flex-grow: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px">'
            f'<h1 style="margin: 0; font-size: 20px; font-weight: 600">Дизайн-систем пока нет</h1>'
            f'<a href="DS-new.dc.html" style="display: flex; gap: 8px; align-items: center; height: 40px; padding: 0 18px 0 14px; border-radius: 6px; background: {ACC}; color: {INK}; font-size: 14px; font-weight: 600">'
            f'{svg(I_UPLOAD, 18, INK)}Создать из pptx</a></main>')


def upload_error(title, text):
    col = (f'<div style="width: 760px; margin: 0 auto; padding: 48px 0; display: flex; flex-direction: column; gap: 24px">'
           f'<h1 style="margin: 0; font-size: 28px; font-weight: 600">Новая дизайн-система</h1>{g.dropzone((title, text))}</div>')
    return (f'{topbar("Дизайн-системы")}<div style="display: flex; flex-grow: 1; min-height: 0">{g.sidebar(active=-1)}'
            f'<main style="flex-grow: 1">{col}</main></div>')


# ---------- раскладка холста ----------
GAP_X, ROW_GAP = 80, 120 + 223
ROWS = [
    ("Презентация: запрос, генерация, правка", [
        ("Home.dc.html", "Главная: о чём презентация", 1440, 900, lambda: body_home()),
        ("Home-agent.dc.html", "Главная: выбор агента", 1440, 900, lambda: body_home(menu=True)),
        ("Generation.dc.html", "Генерация: ход работы и слайды", 1440, 1040, body_generation),
        ("Edit.dc.html", "Правка готовой презентации", 1440, 1330, body_edit)]),
    ("Дизайн-система из своего pptx", [
        ("DS-new.dc.html", "Шаг 1: файл", 1440, 900, body_ds_new),
        ("DS-parsing.dc.html", "Шаг 2: разбор на глазах", 1440, 1990, lambda: g.body_a(WS, "loading")),
        ("DS-ready.dc.html", "Шаг 3: проверка, система готова", 1440, 1950, lambda: g.body_a(WS, focused=5)),
        ("DS-sample.dc.html", "Образец открыт", 1440, 1950, lambda: g.body_a_sample(WS))]),
    ("Дизайн-система: ошибки и крайние случаи", [
        ("DS-model-error.dc.html", "Модель не ответила", 1440, 1290, lambda: g.body_a(WS, "error")),
        ("DS-not-pptx.dc.html", "Файл не pptx", 1440, 900, lambda: upload_error("«Итоги_Q3.pdf» не pptx.", "Выберите презентацию PowerPoint с расширением .pptx.")),
        ("DS-broken.dc.html", "Файл повреждён", 1440, 900, lambda: upload_error("«Шаблон_2026.pptx» не открылся.", "Файл повреждён или сохранён не до конца. Сохраните его в PowerPoint заново и загрузите ещё раз.")),
        ("DS-empty.dc.html", "Систем нет", 1440, 900, body_ds_empty),
        ("DS-edge.dc.html", "55 образцов и три шрифта", 1440, 2850, lambda: g.body_a(EDU, active_side=1))]),
    ("Live-режим", [
        ("Live.dc.html", "Пульт выступающего", 1440, 900, body_live),
        ("Hall.dc.html", "Окно для зала", 1280, 720, body_hall)]),
    ("Агенты и модели", [
        ("Settings-cli.dc.html", "Локальный CLI", 1440, 1160, body_settings_cli),
        ("Settings-local.dc.html", "Локальная модель", 1440, 900, body_settings_local)]),
]

if __name__ == "__main__":
    for f in os.listdir(OUT):
        if f.endswith(".dc.html"):
            os.remove(os.path.join(OUT, f))
    boards, order, notes = {}, [], {}
    y = 0
    for ri, (row_title, items) in enumerate(ROWS):
        x = 0
        for fname, title, w, h, fn in items:
            open(os.path.join(OUT, fname), "w", encoding="utf-8").write(g.page(title, w, h, fn().replace("A-sample.dc.html", "DS-sample.dc.html").replace("C-file.dc.html", "DS-new.dc.html")))
            boards[fname] = {"x": x, "y": y, "w": w, "h": h, "title": title}
            order.append(fname)
            x += w + GAP_X
        notes[f"row{ri}"] = {"x": 0, "y": y - 300, "text": row_title, "kind": "title1", "maxW": x - GAP_X}
        y += max(h for *_, h, _ in items) + ROW_GAP
    notes["data"] = {"x": -640, "y": 0, "w": 540, "maxH": 900, "fill": "gray",
                     "text": "Откуда данные. Бриф, план, слайды, замечания проверки и время шагов взяты из настоящей колоды сервиса от 23.09 (qwen3.8-27b, шаблон VK WorkSpace). "
                             "Дизайн-системы: ответ сервиса 23.09. Агенты: Claude Code 2.1.270 и OpenCode 1.18.16 найдены в PATH этой машины, Cursor Agent нашёл Open Design, Codex не установлен. "
                             "LM Studio отдаёт 5 моделей.\n\nВ сервисе пока нет, рисуется по брифу: выбор CLI-агента, слайды по одному во время генерации, "
                             "правка на слайде и просьба агенту, смена образца у слайда, имя дизайн-системы, флажки образцов."}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = os.path.join(OUT, "canvas.json")
    created = json.load(open(path, encoding="utf-8")).get("createdOnFiles", {"v": 1, "at": now}) if os.path.exists(path) else {"v": 1, "at": now}
    idx = {"v": 3, "createdOnFiles": created, "title": "voiceDeck: приложение", "launch": {"view": "canvas"}, "pages": [],
           "boards": boards, "order": order, "notes": notes, "designSystems": []}
    json.dump(idx, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(PREVIEW_MAP, open(os.path.join(HERE, "preview_map.json"), "w"), indent=0)
    print("ok", len(order))
