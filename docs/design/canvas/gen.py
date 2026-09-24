# Генератор артбордов холста «voiceDeck: дизайн-система», круг 2: правки по сводке ред-тима.
# Данные: ответы сервиса GET /design-systems/<id> 2026-09-23 (ds.json, ds-edu.json), превью из pptx.
import html, json, os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "canvas", "project")
os.makedirs(OUT, exist_ok=True)
e = html.escape

WS_BLOBS = ["b0368afd9fdc96b41ff1d3c4c23e6e3f", "25c1fcdb2839d31c2fee54a136930192", "2d5b92d115e0acfae3a4f28042c6e011",
 "e5bd8f4fc2b963bbba2c5ffd083b9418", "3de8b00a0478d3765a4d0ab90e41e907", "f962fdea1bcaae874df8cba9b6cfc285",
 "2f3310348d215a351b9e4489616afd9f", "ad577e35ce67134bc685c1c496228dba", "1de34c20f76ddd28074a5bd409cd1f94",
 "fb9aab0cbe846d19addc9531a3b1c792", "3582922599777c699a27462e6d7b586c", "044a62b0e20ebbcb3f7e6f82fa82d8b9",
 "db97cf53b03082cac897209efbc6b2b0", "e03acdca378a4c47cfe152e228c4fccd", "730fcce142d43e6c0d143de0cc790198",
 "a79a7865fbabc1b571f852d6f8e39a29", "7d2b792a42ed85201fedcfd3ad7031dd", "d59b90a8276ba4f625bf87599a66612f",
 "e5133221f4bfe7ddd29ba0b0215cb457", "308703d2fcaafb3970ecdc1551f3e386", "3b4f5df27f291ca667766ac360a727d0",
 "ff0baf991f78926da8e13656e56583d2", "4698501105f950666a58fb9d3230706e", "8ae085dc370f7b123aa23026a051c89e",
 "8b3d7af4293f1803391f2a3d62d682b9", "9441a5ba45ee1306ef14369051fd783d", "4129c638ae3946fb85a0b4cec4973449",
 "3b06f72b1c2c2304d7c8f0d4a07f72af", "f16c94f2d38663720a3db60659bdd525"]
EDU_BLOBS = ["be517ded5e7f127fcf17f0de0cbfe13d", "6aed9fb34536d25b26a02ae3481f0ea7", "20322177f15c521ca934256a2132de95",
 "ef39509a1d5933b4a69edc4393171f78", "7edf9cab02c55582d7033fdd87c626f9", "d0747bc3640eae9506e7751b0b6303f9",
 "579e00859a5f2fccc3d5068ca1e81451", "56221dfa339c94acd6d00557490a31ad", "70af13a9baad9a71e38ba6d0bbe9843a",
 "c4c2e0a721f7e05f886dd718986f21c8", "a561fe547467e802361a0400e074c813", "277ff7b14c8ccd8d6437b1a6d952f796",
 "099e6f4dbd780eb577bf5f69b02436ed", "8a996e05aa976e269ec6d48e8c49787d", "a7e5e0a4243505a51fbb258034be3ec3",
 "6a3e785a405b808b9343f311535879b6", "57dfe36515ed094db884c0ca6b3fc074", "fc1d70064e70a58ae026a205906b1ab6",
 "bf8820ca9b99959073150acd1be1c645", "21e7058a6c5146d407f739d6e29ef20d", "16fce3fa2eacd1119e78b97e765a89e0",
 "e26688f9b1a81cc95eb9e2e10e3b3f68", "fd7f72031b9525ecc31d6bdcca6633dd", "eb45d123fcaf79901904265ba21f1653",
 "64d9c3b06f51c34135b971b48aee1363", "de82d89e04889daffcc5d8d6bb2a7bdf", "2dc18cb9abc8da871be65b494a6aa5e6",
 "49541a34ca660b95166fba73f8b47b2f", "f0a25be2b440d2eaeff803473d08d903", "f2676619a4a968f5e4e784fabeb04b90",
 "292d5c72757b1823d85b5ff0a6d4fb61", "4ff3b82329faa73429d0c0b34121e990", "a1f533261338bc6702f5b68f368a5684",
 "346d9057f6a1df6db93694ddf187da22", "400305f4a0c6592a2340dc4dd3a4d232", "d4e0a8c9988a9447a4cc4c3595a92da5",
 "ae9bc37ea900d3f518350f100c3d5b77", "8b94f0f08457ae680a8d392dd38a0f8c", "7613c4c52077fbab3968fedde4e84c75",
 "88de5ae8295ffb64fd8f3d39e48fa376", "a7afaff0d657478914aee5f3478c5441", "f718c525fc3f371c847f1574e86bf23c",
 "5fed517bcbdf5d4a60f273dc7175d18f", "53360de5487d7467a9cc05c463cf88a9", "404c1143c832763f6f4cef20d7ed8305",
 "e75a5aa644f4764d33b5de615daf2a3f", "e3333b7d7cb14068fe2345b999ec37e5", "c1a7df342ea4caae88671309a9e07ff9",
 "e4fe1915cb6b7b02bd61ea032ecb8d84", "42c0eb0377b1195c1ec83adf6056ab8c", "398c2ea889dfb61713b05e17c9872914",
 "810567766fdeb146fa31c555e1c5fe4a", "486569c2041bb70e85da0279e607a35d", "02748f5951cf024cc8358e773ad05177",
 "c00f1bd6e04852b85ef4afdf2f6d802d"]
THUMB_TECH = "/_blob/aee8d1dabc3436c489acb99b8f94ef7b"

BG, SURF, SURF2, BORDER = "#0F1115", "#171A20", "#1F232B", "#2B303A"
TEXT, MUTED, FAINT = "#E9EBEF", "#9BA3B0", "#7D8594"
ACC, INK, ACC_SOFT = "#F0A63C", "#16120A", "#3A2C16"
OK, DANGER, DANGER_SOFT = "#4FC98A", "#FF6B6B", "#3A1D20"
UI = "'Onest', 'Segoe UI', system-ui, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, Consolas, monospace"
PLAY = "'Play', 'Segoe UI', sans-serif"

KIND = {"title": "Титульный", "steps": "Шаги", "image_text": "Картинка и текст", "cards": "Карточки",
        "other": "Другое", "table": "Таблица", "big_number": "Большое число", "chart": "Диаграмма",
        "bullets": "Список", "cta": "Призыв", "timeline": "Хронология", "section": "Раздел", "thanks": "Финальный",
        "team": "Команда", "code": "Код", "quote": "Цитата", "compare": "Сравнение", "agenda": "Содержание"}
ROLE_RU = [("background", "Фон"), ("surface", "Подложка"), ("text", "Текст"),
           ("text_muted", "Второстепенный текст"), ("accent", "Акцент"), ("accent_alt", "Второй акцент")]
STEP_RU = {"display": "Титул", "title": "Заголовок", "heading": "Подзаголовок", "body": "Текст", "caption": "Подпись"}


def load_system(path, blobs, name, embedded_fonts):
    d = json.load(open(os.path.join(HERE, path), encoding="utf-8"))
    cols = d["tokens"]["colors"]
    roles = []
    for key, ru in ROLE_RU:
        # правило модели: цвет роли с наибольшей долей в замере слайдов; тема, только если в замере роли нет
        usage = [c for c in cols if c["role"] == key and c["source"] == "usage"]
        theme = [c for c in cols if c["role"] == key and c["source"] == "theme"]
        pick = max(usage or theme, key=lambda c: c["share"])
        roles.append((ru, pick["hex"]))
    uniq = {c["hex"] for c in cols}
    fonts = [(f["family"], f["role"], f["share"], f["family"] in embedded_fonts) for f in d["tokens"]["fonts"]]
    scale, seen = [], set()
    for s in d["tokens"]["type_scale"]:
        ru = STEP_RU[s["role"]]
        if ru in seen:
            ru = "Мелкая подпись" if ru == "Подпись" else ru + ", меньше"
        seen.add(ru)
        scale.append((s["size_pt"], ru))
    pats = d["patterns"]
    return {"name": name, "file": d["source_file"], "roles": roles, "more": len(uniq) - len({h for _, h in roles}),
            "fonts": fonts, "scale": scale, "margins": d["tokens"]["margins"], "patterns": pats,
            "img": lambda n: f"/_blob/{blobs[n - 1]}", "thumb": f"/_blob/{blobs[0]}", "n": len(pats),
            "removed": [p["source_slide"] for p in pats if p["needs_images"]]}


WS = load_system("ds.json", WS_BLOBS, "VK WorkSpace, конференция", {"Play"})
EDU = load_system("ds-edu.json", EDU_BLOBS, "VK Education", {"Play"})
AUTO_NAME = "VK WorkSpace Клиентская конференция Шаблон 03"


def plural(n, one, few, many):
    n10, n100 = n % 10, n % 100
    return one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many


def svg(path, size=20, color="currentColor"):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>')
I_PLUS = '<path d="M12 5v14"></path><path d="M5 12h14"></path>'
I_PEN = '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z"></path><path d="M13.5 6.5l4 4"></path>'
I_DECK = '<rect x="3" y="6" width="14" height="10" rx="1.5"></rect><path d="M7 3h13a1 1 0 0 1 1 1v10"></path><path d="M8 20h8"></path>'
I_MIC = '<rect x="9" y="3" width="6" height="11" rx="3"></rect><path d="M5 11a7 7 0 0 0 14 0"></path><path d="M12 18v3"></path>'
I_MORE = '<circle cx="5" cy="12" r="1"></circle><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle>'
I_DOWN = '<path d="M6 9l6 6 6-6"></path>'
I_CHECK = '<path d="M5 12.5l4.5 4.5L19 7.5"></path>'
I_RETRY = '<path d="M20 11a8 8 0 1 0-2.3 5.7"></path><path d="M20 5v6h-6"></path>'
I_UPLOAD = '<path d="M12 16V4"></path><path d="M7 9l5-5 5 5"></path><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"></path>'
I_ALERT = '<path d="M12 3l9.5 17h-19z"></path><path d="M12 10v4"></path><path d="M12 17.5v.01"></path>'
I_INFO = '<circle cx="12" cy="12" r="9"></circle><path d="M12 11v5"></path><path d="M12 8v.01"></path>'
I_CLOSE = '<path d="M6 6l12 12"></path><path d="M18 6L6 18"></path>'
I_FILE = '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"></path><path d="M14 3v5h5"></path>'
I_LEFT = '<path d="M15 6l-6 6 6 6"></path>'
I_RIGHT = '<path d="M9 6l6 6-6 6"></path>'

FOCUS = f"outline: 2px solid {ACC}; outline-offset: 3px"


def page(title, w, h, body):
    return f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{e(title)}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600&amp;family=JetBrains+Mono:wght@400&amp;family=Play:wght@400;700&amp;display=swap">
<style>
body{{margin:0;background:{BG};font-family:{UI};color:{TEXT}}}
a{{color:{TEXT};text-decoration:none}}a:hover{{color:{ACC}}}
button{{font-family:{UI}}}
a:focus-visible,button:focus-visible,input:focus-visible,label:focus-within{{outline:2px solid {ACC};outline-offset:3px}}
</style>
</helmet>
<div style="position: relative; width: {w}px; height: {h}px; box-sizing: border-box; overflow: hidden; background: {BG}; color: {TEXT}; font-family: {UI}; display: flex; flex-direction: column">
{body}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":{w},"height":{h}}}}}'>
class Component extends DCLogic {{
renderVals() {{
return {{}};
}}
}}
</script>
</body>
</html>
'''


def topbar():
    tabs = []
    for t in ["Дизайн-системы", "Колода", "Сцена"]:
        on = t == "Дизайн-системы"
        cur = ' aria-current="page"' if on else ""
        tabs.append(f'<a href="#{t}"{cur} style="display: flex; align-items: center; height: 56px; box-sizing: border-box; padding: 0 4px; '
                    f'font-size: 14px; font-weight: {600 if on else 500}; color: {TEXT if on else MUTED}; '
                    f'border-bottom: 2px solid {ACC if on else "transparent"}">{t}</a>')
    return (f'<nav aria-label="Разделы" style="flex-shrink: 0; height: 56px; display: flex; gap: 28px; padding: 0 24px; '
            f'background: {SURF}; border-bottom: 1px solid {BORDER}">{"".join(tabs)}</nav>')


def icon_btn(icon, label, color=MUTED, bg="transparent", border="transparent", disabled=False):
    dis = ' disabled=""' if disabled else ""
    return (f'<button type="button" aria-label="{e(label)}" title="{e(label)}"{dis} style="width: 36px; height: 36px; flex-shrink: 0; '
            f'display: flex; align-items: center; justify-content: center; padding: 0; border-radius: 6px; cursor: pointer; '
            f'background: {bg}; border: 1px solid {border}; color: {color}; opacity: {0.45 if disabled else 1}">{svg(icon)}</button>')


def sidebar(active=0, loading=False):
    items = ([(AUTO_NAME, WS["thumb"], "идёт разбор")] if loading else []) + [
             (WS["name"], WS["thumb"], f'{WS["n"]} образцов'),
             (EDU["name"], EDU["thumb"], f'{EDU["n"]} образцов'),
             ("VK Tech", THUMB_TECH, "54 образца")]
    links = (["DS-parsing.dc.html"] if loading else []) + ["DS-ready.dc.html", "DS-edge.dc.html", "#ds-tech"]
    rows = []
    for i, (n, src, meta) in enumerate(items):
        on = i == active
        cur = ' aria-current="page"' if on else ""
        meta_html = (f'<span style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: {TEXT}">'
                     f'<span style="width: 8px; height: 8px; border-radius: 999px; background: {ACC}"></span>{meta}</span>'
                     if loading and i == 0 else f'<span style="font-size: 12px; color: {MUTED}">{meta}</span>')
        rows.append(f'<a href="{links[i]}"{cur} style="display: flex; gap: 12px; align-items: center; padding: 8px; border-radius: 8px; '
                    f'background: {ACC_SOFT if on else "transparent"}">'
                    f'<img src="{src}" alt="" style="width: 72px; height: 40px; flex-shrink: 0; object-fit: cover; border-radius: 4px; border: 1px solid {BORDER}">'
                    f'<span style="display: flex; flex-direction: column; gap: 2px; min-width: 0">'
                    f'<span style="font-size: 14px; font-weight: 500; color: {TEXT}; line-height: 1.3">{e(n)}</span>{meta_html}</span></a>')
    return (f'<aside style="width: 264px; flex-shrink: 0; box-sizing: border-box; background: {SURF}; border-right: 1px solid {BORDER}; '
            f'padding: 16px 12px; display: flex; flex-direction: column; gap: 12px">'
            f'<div style="display: flex; align-items: center; justify-content: space-between; padding: 0 4px 0 8px">'
            f'<h2 style="margin: 0; font-size: 13px; font-weight: 500; color: {MUTED}">Дизайн-системы</h2>'
            f'<a href="DS-new.dc.html" aria-label="Создать из pptx" title="Создать из pptx" style="width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 6px; background: {SURF2}; color: {TEXT}">{svg(I_PLUS)}</a></div>'
            f'<div style="display: flex; flex-direction: column; gap: 4px">{"".join(rows)}</div></aside>')


def meta_item(k, v):
    return (f'<div style="display: flex; flex-direction: column; gap: 2px; min-width: 0">'
            f'<span style="font-size: 12px; color: {MUTED}">{k}</span>'
            f'<span style="font-size: 13px; color: {TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{e(v)}</span></div>')


def actions(disabled=False):
    op = "0.45" if disabled else "1"
    wait = ": станет доступно, когда модель опишет образцы" if disabled else ""
    return (f'<div style="display: flex; gap: 8px; align-items: center; flex-shrink: 0">'
            f'<a href="#deck" title="Собрать колоду по брифу на этой системе{wait}" style="display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 16px 0 12px; '
            f'border-radius: 6px; background: {ACC}; color: {INK}; font-size: 14px; font-weight: 600; opacity: {op}">{svg(I_DECK, 18, INK)}Колода</a>'
            f'<a href="#stage" title="Слайды из речи на этой системе{wait}" style="display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 16px 0 12px; '
            f'border-radius: 6px; background: {SURF2}; border: 1px solid {BORDER}; color: {TEXT}; font-size: 14px; font-weight: 500; opacity: {op}">{svg(I_MIC, 18)}Сцена</a>'
            f'{icon_btn(I_MORE, "Ещё: удалить систему")}</div>')


def header(S, name=None, loading=False, pad=40):
    return (f'<header style="display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; padding: 32px {pad}px 24px">'
            f'<div style="display: flex; flex-direction: column; gap: 16px; min-width: 0">'
            f'<div style="display: flex; align-items: center; gap: 8px">'
            f'<h1 style="margin: 0; font-size: 28px; font-weight: 600; line-height: 1.2; letter-spacing: -0.01em">{e(name or S["name"])}</h1>'
            f'{icon_btn(I_PEN, "Переименовать")}</div>'
            f'<div style="display: flex; gap: 32px">{meta_item("Файл", S["file"])}{meta_item("Размер слайда", "16:9")}</div></div>'
            f'{actions(loading)}</header>')


def section_title(t, right="", tag="h2"):
    return (f'<div style="display: flex; justify-content: space-between; align-items: center; min-height: 36px; gap: 16px">'
            f'<{tag} style="margin: 0; font-size: 16px; font-weight: 600">{t}</{tag}>{right}</div>')


def more_btn(n, short=False):
    label = f"Ещё {n}" if short else f"Ещё {n} {plural(n, 'цвет', 'цвета', 'цветов')}"
    return (f'<button type="button" aria-expanded="false" style="display: flex; gap: 6px; align-items: center; height: 36px; padding: 0 12px; border-radius: 6px; '
            f'background: transparent; border: 1px solid {BORDER}; color: {TEXT}; font-size: 13px; cursor: pointer">{label}{svg(I_DOWN, 16)}</button>')


def palette(S):
    cards = "".join(
        f'<button type="button" aria-label="{r} #{h}: показать все цвета роли" title="Все цвета роли «{r}»" style="display: flex; flex-direction: column; gap: 10px; padding: 0; background: transparent; border: 0; text-align: left; cursor: pointer; color: {TEXT}">'
        f'<span style="display: block; width: 100%; height: 88px; border-radius: 10px; background: #{h}; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10)"></span>'
        f'<span style="display: flex; flex-direction: column; gap: 2px"><span style="font-size: 13px; font-weight: 500">{r}</span>'
        f'<span style="font-size: 12px; color: {MUTED}; font-family: {MONO}">#{h}</span></span></button>' for r, h in S["roles"])
    return (f'<section style="display: flex; flex-direction: column; gap: 16px">{section_title("Палитра", more_btn(S["more"]))}'
            f'<div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px">{cards}</div></section>')


def card(inner, gap=16, pad=20):
    return f'<div style="background: {SURF}; border: 1px solid {BORDER}; border-radius: 10px; padding: {pad}px; display: flex; flex-direction: column; gap: {gap}px">{inner}</div>'


FONT_TIP_EMB = "Шрифт лежит в pptx в сжатом виде (EOT), сервис его не достал. Установите шрифт на машине, где будете показывать, иначе текст слайдов откроется другим шрифтом"
FONT_TIP_NO = "Шрифта нет внутри pptx. Установите его на машине, где будете показывать, иначе текст слайдов откроется другим шрифтом"


def font_state(emb):
    txt, tip = ("встроен, сервис не извлёк", FONT_TIP_EMB) if emb else ("в файле нет", FONT_TIP_NO)
    return (f'<span style="display: flex; gap: 6px; align-items: center; font-size: 13px; color: {TEXT}">{svg(I_INFO, 16, MUTED)}{txt}'
            f'<span style="position: absolute; left: -9999px">{tip}</span></span>'), tip


FROLE = {"body": "основной текст", "heading": "заголовки", "mono": "код", "other": "прочий текст"}


def font_block(S):
    rows = []
    for fam, role, share, emb in S["fonts"]:
        st, tip = font_state(emb)
        label = (f'<span style="font-family: \'{fam}\', {PLAY}; font-size: 22px">{fam}</span>' if len(S["fonts"]) > 1
                 else f'<span style="font-size: 13px; color: {MUTED}">Доля текста</span>')
        rows.append(f'<div title="{e(tip)}" style="display: flex; flex-direction: column; gap: 6px; padding: 10px 0; border-top: 1px solid {BORDER}">'
                    f'<div style="display: flex; justify-content: space-between; align-items: baseline">'
                    f'{label}'
                    f'<span style="font-size: 13px; color: {MUTED}">{FROLE.get(role, role)}, {round(share * 100)}&#160;%</span></div>{st}</div>')
    first = S["fonts"][0][0]
    return card(f'{section_title("Шрифт" if len(S["fonts"]) == 1 else "Шрифты")}'
                f'<div style="font-family: \'{first}\', {PLAY}; font-size: 40px; line-height: 1.1">{first}</div>'
                f'<div style="display: flex; flex-direction: column">{"".join(rows)}</div>', gap=12)


def scale_block(S):
    rows = "".join(
        f'<div style="display: grid; grid-template-columns: 36px 104px minmax(0, 1fr); align-items: baseline; gap: 8px">'
        f'<span style="font-family: {MONO}; font-size: 12px; color: {MUTED}">{s:g}</span>'
        f'<span style="font-size: 13px; color: {MUTED}">{r}</span>'
        f'<span style="font-family: {PLAY}; font-size: {min(s, 30):g}px; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">Итоги года</span></div>'
        for s, r in S["scale"])
    return card(f'{section_title("Кегли, пт")}<div style="display: flex; flex-direction: column; gap: 12px">{rows}</div>')


def pct(v):
    return f"{v * 100:.1f}".replace(".", ",") + " %"


def frame(S, w, labels=True):
    m = S["margins"]; h = round(w * 9 / 16)
    l, t, r, b = (m["left"] * w, m["top"] * h, m["right"] * w, m["bottom"] * h)
    lab = f"font-size: 11px; color: {MUTED}; font-family: {MONO}; position: absolute"
    marks = (f'<span style="{lab}; left: {l + 6:.0f}px; top: {h / 2 - 7:.0f}px">{pct(m["left"])}</span>'
             f'<span style="{lab}; right: {r + 6:.0f}px; top: {h / 2 - 7:.0f}px">{pct(m["right"])}</span>'
             f'<span style="{lab}; left: {w / 2 - 20:.0f}px; top: {t + 4:.0f}px">{pct(m["top"])}</span>'
             f'<span style="{lab}; left: {w / 2 - 20:.0f}px; bottom: {b + 4:.0f}px">{pct(m["bottom"])}</span>') if labels else ""
    return (f'<div role="img" aria-label="Поля слайда: слева {pct(m["left"])}, сверху {pct(m["top"])}, справа {pct(m["right"])}, снизу {pct(m["bottom"])}" '
            f'style="position: relative; width: {w}px; height: {h}px; background: #000000; border-radius: 4px; box-shadow: inset 0 0 0 1px {BORDER}">'
            f'<div style="position: absolute; left: {l:.0f}px; top: {t:.0f}px; right: {r:.0f}px; bottom: {b:.0f}px; border: 1px dashed {MUTED}"></div>{marks}</div>')


def margins_block(S):
    return card(f'{section_title("Поля слайда")}<div style="display: flex; justify-content: center; padding-top: 8px">{frame(S, 300)}</div>'
                f'<div style="font-size: 13px; color: {MUTED}; text-align: center">доли ширины и высоты слайда</div>')


def checkbox(on, label, disabled=False):
    mark = svg(I_CHECK, 14, INK) if on else ""
    dis = ' disabled=""' if disabled else ""
    return (f'<button type="button" role="checkbox" aria-checked="{"true" if on else "false"}" aria-label="{e(label)}" title="{e(label)}"{dis} '
            f'style="width: 36px; height: 36px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; padding: 0; '
            f'background: transparent; border: 0; cursor: pointer; opacity: {0.4 if disabled else 1}">'
            f'<span style="width: 18px; height: 18px; border-radius: 4px; box-sizing: border-box; border: 1.5px solid {TEXT if on else MUTED}; '
            f'background: {TEXT if on else "transparent"}; display: flex; align-items: center; justify-content: center">{mark}</span></button>')


REMOVE_TIP = "Модель убрала образец из вёрстки: без фото он не работает, в презентации осталась бы пустая рамка. Флажок вернёт его"


def sample(S, p, w, state="done", selected=False, focused=False, href="A-sample.dc.html"):
    n = p["source_slide"]
    removed = p["needs_images"] and state == "done"
    kind = KIND.get(p["kind"], p["kind"]) if state != "wait" else "Образец"
    ih = round(w * 9 / 16)
    tag = ""
    if removed:
        tag = (f'<span style="position: absolute; left: 8px; top: 8px; padding: 3px 8px; border-radius: 999px; font-size: 12px; '
               f'background: rgba(15,17,21,0.9); color: {TEXT}">убран моделью</span>')
    if state == "wait":
        tag = (f'<span style="position: absolute; left: 8px; top: 8px; padding: 3px 8px; border-radius: 999px; font-size: 12px; '
               f'background: rgba(15,17,21,0.9); color: {TEXT}">ждёт описания</span>')
    ring = f"box-shadow: 0 0 0 2px {ACC}" if selected else f"box-shadow: 0 0 0 1px {BORDER}"
    tip = REMOVE_TIP if removed else (p["purpose"] if state == "done" else "Модель ещё не описала образец")
    fstyle = f"; {FOCUS}; border-radius: 6px" if focused else ""
    cur = ' aria-current="true"' if selected else ""
    link = (f'<a href="{href}"{cur} title="{e(tip)}" aria-label="Образец {n}: {e(kind)}. Открыть" style="display: flex; flex-direction: column; gap: 8px; min-width: 0{fstyle}">'
            f'<span style="position: relative; display: block; width: {w}px; height: {ih}px">'
            f'<img src="{S["img"](n)}" alt="" style="display: block; width: {w}px; height: {ih}px; border-radius: 6px; {ring}; opacity: {0.45 if removed else 1}">{tag}</span>'
            f'<span style="display: flex; gap: 8px; align-items: baseline; min-width: 0; padding-right: 36px">'
            f'<span style="font-size: 13px; font-weight: 500; color: {MUTED if removed else TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{e(kind)}</span>'
            f'<span style="font-size: 12px; color: {MUTED}; font-family: {MONO}">{n}</span></span></a>')
    return (f'<div style="position: relative; display: flex; flex-direction: column">{link}'
            f'<div style="position: absolute; right: -6px; bottom: -8px">{checkbox(not removed, f"Образец {n} в вёрстке", disabled=(state == "wait"))}</div></div>')


def filters(total, used, removed, active=0):
    labels = [f"Все {total}", f"В вёрстке {used}", f"Убраны {removed}"]
    btns = "".join(
        f'<button type="button" aria-pressed="{"true" if i == active else "false"}" style="height: 36px; padding: 0 12px; border-radius: 6px; font-size: 13px; cursor: pointer; '
        f'background: {SURF2 if i == active else "transparent"}; color: {TEXT if i == active else MUTED}; border: 1px solid {TEXT if i == active else BORDER}">{l}</button>'
        for i, l in enumerate(labels))
    return f'<div role="group" aria-label="Показать образцы" style="display: flex; gap: 8px">{btns}</div>'


def proposal_strip(S):
    k = len(S["removed"])
    return (f'<div role="status" style="display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 12px 12px 16px; '
            f'border-radius: 10px; background: {SURF}; border: 1px solid {BORDER}">'
            f'<span style="display: flex; gap: 12px; align-items: center; font-size: 14px; line-height: 1.45">{svg(I_INFO, 20, MUTED)}'
            f'<span>Модель убрала из вёрстки образцы, которые без фото не работают: своих фото у сервиса нет. '
            f'<span style="color: {MUTED}">Флажок у образца вернёт его.</span></span></span>'
            f'<button type="button" style="height: 36px; padding: 0 16px; flex-shrink: 0; border-radius: 6px; background: {SURF2}; border: 1px solid {BORDER}; color: {TEXT}; font-size: 14px; cursor: pointer">Согласен</button></div>')


def samples_section(S, cols, w, state_of=lambda p: "done", limit=None, flt=None, strip=None, selected=None, focused=None, href="A-sample.dc.html"):
    ps = S["patterns"][:limit] if limit else S["patterns"]
    cells = "".join(sample(S, p, w, state_of(p), selected == p["source_slide"], focused == p["source_slide"], href) for p in ps)
    k = len(S["removed"])
    head = section_title("Образцы", flt if flt is not None else filters(S["n"], S["n"] - k, k))
    return (f'<section style="display: flex; flex-direction: column; gap: 16px">{head}{strip or ""}'
            f'<div style="display: grid; grid-template-columns: repeat({cols}, minmax(0, 1fr)); gap: 28px 16px">{cells}</div></section>')


def loading_strip():
    return (f'<div role="status" style="margin: 0 40px; padding: 14px 16px; border-radius: 10px; background: {SURF}; border: 1px solid {BORDER}; '
            f'display: flex; flex-direction: column; gap: 10px">'
            f'<div style="display: flex; gap: 24px; font-size: 13px">'
            f'<span style="color: {TEXT}; display: flex; gap: 6px; align-items: center">{svg(I_CHECK, 16, OK)}Палитра, шрифт, кегли, поля готовы</span>'
            f'<span style="color: {TEXT}">Модель описывает образцы: 12 из 29</span></div>'
            f'<div role="progressbar" aria-valuemin="0" aria-valuemax="29" aria-valuenow="12" aria-label="Описано образцов" style="height: 4px; border-radius: 999px; background: {SURF2}">'
            f'<div style="width: 41%; height: 4px; border-radius: 999px; background: {ACC}"></div></div></div>')


def error_strip():
    return (f'<div role="alert" style="margin: 0 40px; padding: 12px 12px 12px 16px; border-radius: 10px; background: {DANGER_SOFT}; border: 1px solid #5A2A2F; '
            f'display: flex; align-items: center; justify-content: space-between; gap: 16px">'
            f'<span style="display: flex; gap: 12px; align-items: center; font-size: 14px; line-height: 1.45">{svg(I_ALERT, 20, DANGER)}'
            f'<span><span style="font-weight: 600">Qwen3.8 27B в LM Studio не ответила, образцы без описания.</span> '
            f'<span style="color: {TEXT}">Палитра, шрифт, кегли и поля готовы. Какие образцы держатся на фото, не проверено, поэтому все пока в вёрстке. </span><a href="Settings-local.dc.html" style="color: {TEXT}; text-decoration: underline">Агенты и модели</a></span></span>'
            f'<button type="button" style="display: flex; gap: 8px; align-items: center; height: 36px; padding: 0 14px; flex-shrink: 0; border-radius: 6px; '
            f'background: {SURF2}; border: 1px solid {BORDER}; color: {TEXT}; font-size: 14px; cursor: pointer">{svg(I_RETRY, 18)}Описать заново</button></div>')


def shell(main, active_side=0, loading=False):
    return (f'{topbar()}<div style="display: flex; flex-grow: 1; min-height: 0">{sidebar(active_side, loading)}'
            f'<main style="flex-grow: 1; min-width: 0; display: flex; flex-direction: column">{main}</main></div>')


def body_a(S, state="done", active_side=0, focused=None):
    strip = loading_strip() if state == "loading" else error_strip() if state == "error" else ""
    row3 = (f'<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px">'
            f'{font_block(S)}{scale_block(S)}{margins_block(S)}</div>')
    if state == "loading":
        grid = samples_section(S, 5, 206, state_of=lambda p: "done" if p["source_slide"] <= 12 else "wait",
                               flt=f'<span style="font-size: 13px; color: {MUTED}">флажки станут доступны, когда модель опишет все образцы</span>')
    elif state == "error":
        grid = samples_section(S, 5, 206, state_of=lambda p: "raw", limit=10, flt=filters(S["n"], S["n"], 0))
    else:
        grid = samples_section(S, 5, 206, strip=proposal_strip(S), focused=focused)
    return shell(
        f'{header(S, AUTO_NAME if state == "loading" else None, loading=(state == "loading"))}{strip}'
        f'<div style="display: flex; flex-direction: column; gap: 40px; padding: {32 if strip else 8}px 40px 48px">'
        f'{palette(S)}{row3}{grid}</div>', active_side=active_side, loading=(state == "loading"))


def slot_overlay(S, p, w):
    h = round(w * 9 / 16)
    boxes = [("Заголовок" if s["role"] == "title" else s["role"], s["box"]) for s in p["slots"]]
    for g in p["groups"]:
        boxes += [(f"Карточка {i + 1}", u["box"]) for i, u in enumerate(g["units"])]
    out = []
    for lab, (x, y, bw, bh) in boxes:
        out.append(f'<div style="position: absolute; left: {x * w:.0f}px; top: {y * h:.0f}px; width: {bw * w:.0f}px; height: {bh * h:.0f}px; '
                   f'box-sizing: border-box; border: 1.5px dashed {ACC}; border-radius: 4px">'
                   f'<span style="position: absolute; right: 4px; top: 4px; padding: 2px 6px; border-radius: 4px; font-size: 11px; background: {ACC}; color: {INK}; font-weight: 600; white-space: nowrap">{lab}</span></div>')
    return (f'<div style="position: relative; width: {w}px; height: {h}px">'
            f'<img src="{S["img"](p["source_slide"])}" alt="Образец {p["source_slide"]}: {KIND.get(p["kind"])}, места под текст отмечены" style="display: block; width: {w}px; height: {h}px; border-radius: 8px">{"".join(out)}</div>')


def capacity(p):
    if not p["groups"]:
        return "Места под текст отмечены на картинке"
    g = p["groups"][0]
    parts = {"heading": "заголовок", "body": "текст", "caption": "подпись", "number": "число", "title": "заголовок", "label": "метка"}
    what = ", ".join(dict.fromkeys(parts.get(s["role"], "текст") for s in g["unit_slots"])) or "текст"
    return f'Заголовок слайда и карточки: от {g["min_units"]} до {g["max_units"]}, в каждой {what}'


def sample_detail(S, p, w, close=True):
    n = p["source_slide"]
    top = (f'<div style="display: flex; justify-content: space-between; align-items: center">'
           f'<div style="display: flex; gap: 10px; align-items: baseline"><h2 style="margin: 0; font-size: 20px; font-weight: 600">{KIND.get(p["kind"])}</h2>'
           f'<span style="font-size: 13px; color: {MUTED}; font-family: {MONO}">образец {n} из {S["n"]}</span></div>'
           f'<div style="display: flex; gap: 4px">{icon_btn(I_LEFT, "Предыдущий образец")}{icon_btn(I_RIGHT, "Следующий образец")}'
           f'{icon_btn(I_CLOSE, "Закрыть") if close else ""}</div></div>')
    return (f'{top}{slot_overlay(S, p, w)}'
            f'<p style="margin: 0; font-size: 14px; line-height: 1.5; color: {TEXT}">{e(p["purpose"])}</p>'
            f'<p style="margin: 0; font-size: 13px; color: {MUTED}">{capacity(p)}</p>'
            f'<label style="display: flex; gap: 10px; align-items: center; font-size: 14px; min-height: 36px; cursor: pointer">'
            f'<input type="checkbox" checked="" style="width: 18px; height: 18px; accent-color: {TEXT}; margin: 0">В вёрстке</label>')


def body_a_sample(S):
    p = S["patterns"][4]
    drawer = (f'<div style="position: absolute; left: 0; top: 0; right: 0; bottom: 0; background: rgba(8,9,12,0.62)"></div>'
              f'<aside role="dialog" aria-modal="true" aria-label="Образец {p["source_slide"]}" style="position: absolute; top: 0; right: 0; bottom: 0; width: 600px; box-sizing: border-box; '
              f'background: {SURF}; border-left: 1px solid {BORDER}; padding: 24px; display: flex; flex-direction: column; gap: 16px">'
              f'{sample_detail(S, p, 552)}</aside>')
    return body_a(S) + drawer


def tokens_panel(S):
    rows = "".join(
        f'<button type="button" aria-label="{r} #{h}: показать все цвета роли" style="display: flex; gap: 12px; align-items: center; height: 36px; padding: 0 4px; background: transparent; border: 0; color: {TEXT}; cursor: pointer; text-align: left">'
        f'<span style="width: 28px; height: 28px; border-radius: 6px; background: #{h}; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12); flex-shrink: 0"></span>'
        f'<span style="flex-grow: 1; font-size: 13px">{r}</span><span style="font-size: 12px; font-family: {MONO}; color: {MUTED}">#{h}</span></button>'
        for r, h in S["roles"])
    sc = "".join(
        f'<div style="display: flex; justify-content: space-between; align-items: baseline"><span style="font-family: {PLAY}; font-size: {min(s, 22):g}px">{r}</span>'
        f'<span style="font-family: {MONO}; font-size: 12px; color: {MUTED}">{s:g}</span></div>' for s, r in S["scale"])
    fam, role, share, emb = S["fonts"][0]
    st, tip = font_state(emb)
    m = S["margins"]
    return (f'<section style="display: flex; flex-direction: column; gap: 4px">{section_title("Палитра", more_btn(S["more"], True), "h3")}{rows}</section>'
            f'<section title="{e(tip)}" style="display: flex; flex-direction: column; gap: 6px">{section_title("Шрифт", "", "h3")}'
            f'<div style="display: flex; justify-content: space-between; align-items: baseline"><span style="font-family: {PLAY}; font-size: 26px">{fam}</span>{st}</div></section>'
            f'<section style="display: flex; flex-direction: column; gap: 8px">{section_title("Кегли, пт", "", "h3")}{sc}</section>'
            f'<section style="display: flex; flex-direction: column; gap: 8px">{section_title("Поля слайда", "", "h3")}{frame(S, 352, labels=False)}'
            f'<span style="font-size: 12px; color: {MUTED}; font-family: {MONO}">слева {pct(m["left"])}, сверху {pct(m["top"])}, справа {pct(m["right"])}, снизу {pct(m["bottom"])}</span></section>')


def body_b(S, loading=False):
    p = S["patterns"][4]
    center_w = 1440 - 264 - 400 - 64
    cols = 4
    cw = (center_w - 16 * (cols - 1)) // cols
    if loading:
        grid = samples_section(S, cols, cw, state_of=lambda q: "done" if q["source_slide"] <= 12 else "wait",
                               flt=f'<span style="font-size: 13px; color: {MUTED}">флажки станут доступны, когда модель опишет все образцы</span>',
                               selected=p["source_slide"], href="#sample")
    else:
        grid = samples_section(S, cols, cw, strip=proposal_strip(S), selected=p["source_slide"], href="#sample")
    status = loading_strip().replace("margin: 0 40px", "margin: 0") if loading else ""
    center = f'<div style="flex-grow: 1; min-width: 0; padding: 24px 32px 48px; display: flex; flex-direction: column; gap: 24px">{status}{grid}</div>'
    panel = (f'<aside aria-label="Выбранный образец и токены" style="width: 400px; flex-shrink: 0; box-sizing: border-box; border-left: 1px solid {BORDER}; background: {SURF}; '
             f'padding: 24px; display: flex; flex-direction: column; gap: 16px">'
             f'{sample_detail(S, p, 352, close=False)}'
             f'<div style="height: 1px; background: {BORDER}; margin: 8px 0"></div>{tokens_panel(S)}</aside>')
    return (f'{topbar()}<div style="display: flex; flex-grow: 1; min-height: 0">{sidebar(loading=loading)}'
            f'<main style="flex-grow: 1; min-width: 0; display: flex; flex-direction: column">'
            f'{header(S, AUTO_NAME if loading else None, loading=loading, pad=32)}'
            f'<div style="display: flex; flex-grow: 1; min-height: 0; border-top: 1px solid {BORDER}">{center}{panel}</div></main></div>')


def stepper(active):
    steps = ["Файл", "Проверка", "Готово"]
    out = []
    for i, s in enumerate(steps, 1):
        done, on = i < active, i == active
        dot_bg = OK if done else (ACC if on else "transparent")
        dot_bd = OK if done else (ACC if on else BORDER)
        inner = svg(I_CHECK, 14, INK) if done else str(i)
        cur = ' aria-current="step"' if on else ""
        out.append(f'<li{cur} style="display: flex; gap: 10px; align-items: center">'
                   f'<span style="width: 26px; height: 26px; border-radius: 999px; box-sizing: border-box; background: {dot_bg}; border: 1.5px solid {dot_bd}; '
                   f'color: {INK if (done or on) else MUTED}; font-size: 13px; font-weight: 600; display: flex; align-items: center; justify-content: center">{inner}</span>'
                   f'<span style="font-size: 14px; font-weight: {600 if on else 500}; color: {TEXT if (on or done) else MUTED}">{s}</span></li>')
        if i < 3:
            out.append(f'<li aria-hidden="true" style="width: 48px; height: 1px; background: {BORDER}"></li>')
    return f'<ol aria-label="Шаги создания" style="list-style: none; margin: 0; padding: 0; display: flex; gap: 12px; align-items: center">{"".join(out)}</ol>'


def wizard_head(active):
    tip = "Закрыть" if active == 1 else "Закрыть: система останется в списке с тем, что уже разобрано"
    return f'<div style="display: flex; justify-content: space-between; align-items: center">{stepper(active)}{icon_btn(I_CLOSE, tip)}</div>'


def dropzone(error=None):
    err = ""
    if error:
        title, text = error
        err = (f'<div role="alert" style="display: flex; gap: 12px; align-items: flex-start; padding: 12px 16px; border-radius: 10px; background: {DANGER_SOFT}; border: 1px solid #5A2A2F; font-size: 14px; line-height: 1.45">'
               f'{svg(I_ALERT, 20, DANGER)}<span><span style="font-weight: 600">{title}</span> <span style="color: {TEXT}">{text}</span></span></div>')
    zone = (f'<div style="height: 300px; border-radius: 12px; border: 1.5px dashed {MUTED}; background: {SURF}; display: flex; flex-direction: column; '
            f'align-items: center; justify-content: center; gap: 16px">'
            f'<span style="width: 56px; height: 56px; border-radius: 12px; background: {SURF2}; display: flex; align-items: center; justify-content: center">{svg(I_UPLOAD, 28, ACC)}</span>'
            f'<span style="font-size: 16px; font-weight: 500">Перетащите pptx сюда</span>'
            f'<a href="DS-parsing.dc.html" style="display: flex; gap: 8px; align-items: center; height: 40px; padding: 0 18px; border-radius: 6px; background: {ACC}; color: {INK}; font-size: 14px; font-weight: 600">'
            f'{svg(I_FILE, 18, INK)}{"Выбрать другой файл" if error else "Выбрать файл"}</a></div>')
    return err + zone


def body_c1(error=None):
    col = (f'<div style="width: 760px; margin: 0 auto; padding: 40px 0; display: flex; flex-direction: column; gap: 24px">'
           f'{wizard_head(1)}<h1 style="margin: 0; font-size: 28px; font-weight: 600">Новая дизайн-система</h1>{dropzone(error)}'
           f'<p style="margin: 0; font-size: 13px; color: {MUTED}">Сервис возьмёт из файла палитру, шрифты, кегли, поля и слайды-образцы. Сам файл не меняется.</p></div>')
    return f'{topbar()}<main style="flex-grow: 1">{col}</main>'


def name_field():
    return (f'<div style="display: flex; flex-direction: column; gap: 8px"><label for="dsname" style="font-size: 13px; color: {MUTED}">Имя системы</label>'
            f'<input id="dsname" type="text" value="{WS["name"]}" style="height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 6px; '
            f'background: {SURF2}; border: 1px solid {BORDER}; color: {TEXT}; font-family: {UI}; font-size: 15px"></div>')


def c_tokens(S):
    sw = "".join(
        f'<div style="display: flex; flex-direction: column; gap: 6px"><span style="height: 48px; border-radius: 8px; background: #{h}; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12)"></span>'
        f'<span style="font-size: 12px; color: {MUTED}">{r}</span><span style="font-size: 12px; color: {MUTED}; font-family: {MONO}">#{h}</span></div>' for r, h in S["roles"])
    pal = card(f'{section_title("Палитра")}<div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px">{sw}</div>', gap=12)
    fam, role, share, emb = S["fonts"][0]
    st, tip = font_state(emb)
    sizes = ", ".join(f"{s:g}" for s, _ in S["scale"])
    fnt = card(f'{section_title("Шрифт и кегли")}'
               f'<div title="{e(tip)}" style="display: flex; gap: 24px; align-items: baseline"><span style="font-family: {PLAY}; font-size: 32px">{fam}</span>'
               f'<span style="font-size: 13px; color: {MUTED}">{sizes} пт</span><span style="margin-left: auto">{st}</span></div>', gap=12)
    return pal + fnt


def removed_thumbs(S, which):
    return "".join(
        f'<figure title="{e(p["purpose"])}" style="margin: 0; display: flex; flex-direction: column; gap: 6px">'
        f'<img src="{S["img"](p["source_slide"])}" alt="Образец {p["source_slide"]}" style="width: 100%; aspect-ratio: 16 / 9; border-radius: 6px; box-shadow: 0 0 0 1px {BORDER}; opacity: 0.45">'
        f'<figcaption style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: {TEXT}">'
        f'<span>{KIND.get(p["kind"])}, {p["source_slide"]}</span>{checkbox(False, "Оставить образец " + str(p["source_slide"]) + " в вёрстке")}</figcaption></figure>'
        for p in S["patterns"] if p["source_slide"] in which)


def body_c2(S, waiting=False):
    if waiting:
        found = [n for n in S["removed"] if n <= 12]
        right = f'<span style="font-size: 13px; color: {TEXT}">Модель описывает образцы: 12 из 29</span>'
        smp = card(f'{section_title("Образцы", right)}'
                   f'<div role="progressbar" aria-valuemin="0" aria-valuemax="29" aria-valuenow="12" aria-label="Описано образцов" style="height: 4px; border-radius: 999px; background: {SURF2}"><div style="width: 41%; height: 4px; border-radius: 999px; background: {ACC}"></div></div>'
                   f'<p style="margin: 0; font-size: 14px; color: {TEXT}">Пока убраны {len(found)}: без фото они не работают.</p>'
                   f'<div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px">{removed_thumbs(S, found)}</div>', gap=12)
    else:
        k = len(S["removed"])
        smp = card(f'{section_title(f"Модель убрала {k} из {S["n"]} образцов")}'
                   f'<p style="margin: 0; font-size: 14px; color: {TEXT}">Без фото они не работают, а своих фото у сервиса нет. Флажок оставит образец в вёрстке.</p>'
                   f'<div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px">{removed_thumbs(S, S["removed"])}</div>', gap=12)
    dis = ' disabled="" title="Станет доступно, когда модель опишет все образцы"' if waiting else ""
    foot = (f'<div style="display: flex; justify-content: space-between; align-items: center">'
            f'<button type="button" style="height: 40px; padding: 0 18px; border-radius: 6px; background: transparent; border: 1px solid {BORDER}; color: {TEXT}; font-size: 14px; cursor: pointer">Назад</button>'
            f'<button type="button"{dis} style="height: 40px; padding: 0 22px; border-radius: 6px; background: {ACC}; border: 0; color: {INK}; font-size: 14px; font-weight: 600; cursor: pointer; opacity: {0.45 if waiting else 1}">Готово</button></div>')
    col = (f'<div style="width: 960px; margin: 0 auto; padding: 40px 0; display: flex; flex-direction: column; gap: 24px">'
           f'{wizard_head(2)}<h1 style="margin: 0; font-size: 28px; font-weight: 600">Так сервис понял шаблон</h1>'
           f'{name_field()}{c_tokens(S)}{smp}{foot}</div>')
    return f'{topbar()}<main style="flex-grow: 1">{col}</main>'


def body_empty():
    return (f'{topbar()}<main style="flex-grow: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px">'
            f'<h1 style="margin: 0; font-size: 20px; font-weight: 600">Дизайн-систем пока нет</h1>'
            f'<a href="C-file.dc.html" style="display: flex; gap: 8px; align-items: center; height: 40px; padding: 0 18px 0 14px; border-radius: 6px; background: {ACC}; color: {INK}; font-size: 14px; font-weight: 600">'
            f'{svg(I_UPLOAD, 18, INK)}Создать из pptx</a></main>')


ROW_GAP = 120 + 223
H = {"Main": 1950, "A-loading": 1960, "A-sample": 1950, "B": 1630, "B-loading": 1630, "C-file": 900, "C-wait": 1040, "C-check": 1040,
     "Empty": 900, "Error": 1290, "Upload-not-pptx": 900, "Upload-broken": 900, "Edge": 2850}
yA = 0
yS = yA + max(H["Main"], H["A-loading"], H["A-sample"]) + ROW_GAP
yE = yS + max(H["Error"], H["Upload-not-pptx"], H["Empty"]) + ROW_GAP
yB = yE + H["Edge"] + ROW_GAP
yC = yB + max(H["B"], H["B-loading"]) + ROW_GAP
X = [0, 1520, 3040, 4560]
BOARDS = [
    ("Main.dc.html", "А. Система готова", H["Main"], body_a(WS, focused=5), X[0], yA),
    ("A-loading.dc.html", "А. Идёт разбор", H["A-loading"], body_a(WS, "loading"), X[1], yA),
    ("A-sample.dc.html", "А. Образец открыт", H["A-sample"], body_a_sample(WS), X[2], yA),
    ("Error.dc.html", "А. Ошибка: модель не ответила", H["Error"], body_a(WS, "error"), X[0], yS),
    ("Upload-not-pptx.dc.html", "Ошибка загрузки: не pptx", H["Upload-not-pptx"],
     body_c1(("«Итоги_Q3.pdf» не pptx.", "Выберите презентацию PowerPoint с расширением .pptx.")), X[1], yS),
    ("Upload-broken.dc.html", "Ошибка загрузки: файл повреждён", H["Upload-broken"],
     body_c1(("«Шаблон_2026.pptx» не открылся.", "Файл повреждён или сохранён не до конца. Сохраните его в PowerPoint заново и загрузите ещё раз.")), X[2], yS),
    ("Empty.dc.html", "Пусто: систем нет", H["Empty"], body_empty(), X[3], yS),
    ("Edge.dc.html", "Край: 55 образцов, три шрифта", H["Edge"], body_a(EDU, active_side=1), X[0], yE),
    ("B.dc.html", "Б. Образцы в центре", H["B"], body_b(WS), X[0], yB),
    ("B-loading.dc.html", "Б. Идёт разбор", H["B-loading"], body_b(WS, loading=True), X[1], yB),
    ("C-file.dc.html", "В. Шаг 1: файл", H["C-file"], body_c1(), X[0], yC),
    ("C-wait.dc.html", "В. Шаг 2: модель описывает образцы", H["C-wait"], body_c2(WS, waiting=True), X[1], yC),
    ("C-check.dc.html", "В. Шаг 2: проверка", H["C-check"], body_c2(WS), X[2], yC),
]

if __name__ == "__main__":
    for f in os.listdir(OUT):
        if f.endswith(".dc.html"):
            os.remove(os.path.join(OUT, f))
    boards, order = {}, []
    for fname, title, h, body, x, y in BOARDS:
        open(os.path.join(OUT, fname), "w", encoding="utf-8").write(page(title, 1440, h, body))
        boards[fname] = {"x": x, "y": y, "w": 1440, "h": h, "title": title}
        order.append(fname)
    notes = {
        "rowA": {"x": 0, "y": yA - 300, "text": "А. Разбор по частям", "kind": "title1", "maxW": 4480},
        "rowS": {"x": 0, "y": yS - 300, "text": "Состояния: ошибки и пусто", "kind": "title1", "maxW": 5920},
        "rowB": {"x": 0, "y": yB - 300, "text": "Б. Образцы в центре", "kind": "title1", "maxW": 2960},
        "rowC": {"x": 0, "y": yC - 300, "text": "В. Три шага; после «Готово» страница как в А", "kind": "title1", "maxW": 4480},
        "data": {"x": 4560, "y": yA, "w": 520, "maxH": 760, "fill": "gray",
                 "text": "Откуда данные. Палитра, шрифты, кегли, поля и образцы взяты из ответа сервиса GET /design-systems/<id> 23.09.2026 для VK WorkSpace и VK Education, картинки образцов отрисованы из их pptx.\n\nЦвет роли: наибольшая доля в замере слайдов; цвет темы, только если в замере роли нет.\n«Снят моделью»: needs_images из описания образцов.\nСтатус шрифта: Play лежит в pptx как .fntdata, сервис его не извлёк.\n\nПо брифу, в коде пока нет: имя системы, флажок «в вёрстке», подтверждение снятия, показ по частям, «Описать заново», удаление."},
    }
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = os.path.join(OUT, "canvas.json")
    created = {"v": 1, "at": now}
    if os.path.exists(path):
        created = json.load(open(path, encoding="utf-8")).get("createdOnFiles", created)
    idx = {"v": 3, "createdOnFiles": created, "title": "voiceDeck: дизайн-система",
           "launch": {"view": "canvas"}, "pages": [], "boards": boards, "order": order, "notes": notes, "designSystems": []}
    json.dump(idx, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok", order)
