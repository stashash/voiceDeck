"""Пиктограммы пунктов слайда: подбор по подсказке модели и цвет значка образца.

Набор это деловые значки lucide (лицензия ISC, текст в icons/LICENSE), отрисованные в PNG чёрным
контуром на прозрачном фоне. Модель пишет в icon_hint имя значка из списка ICON_NAMES; вёрстка ставит
его вместо картинки-значка образца, перекрашенным в цвет этой картинки. Без подсказки остаётся значок образца.
"""
from __future__ import annotations

import io
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"

# Слова, которыми модель называет значок чаще, чем его имя в наборе.
_ALIASES = {
    "money": "banknote", "cost": "coins", "costs": "coins", "price": "banknote", "budget": "wallet", "finance": "landmark",
    "time": "clock", "deadline": "alarm-clock", "schedule": "calendar", "date": "calendar", "speed": "gauge",
    "team": "users", "people": "users", "person": "user", "client": "user", "customer": "user", "partner": "handshake",
    "growth": "trending-up", "increase": "trending-up", "decrease": "trending-down", "decline": "trending-down",
    "chart": "chart-bar", "analytics": "chart-line", "report": "file-text", "document": "file-text", "data": "database",
    "security": "shield-check", "safety": "shield-check", "protection": "shield", "risk": "triangle-alert",
    "warning": "triangle-alert", "error": "circle-x", "problem": "triangle-alert", "success": "circle-check",
    "check": "circle-check", "done": "circle-check", "question": "circle-help", "help": "circle-help",
    "idea": "lightbulb", "goal": "target", "launch": "rocket", "start": "rocket", "ai": "brain", "model": "brain",
    "chat": "message-square", "support": "headphones", "email": "mail", "call": "phone", "home": "house",
    "delivery": "truck", "logistics": "truck", "shop": "store", "sales": "shopping-cart", "education": "graduation-cap",
    "health": "heart-pulse", "energy": "zap", "electricity": "plug", "ecology": "leaf", "location": "map-pin",
    "process": "workflow", "integration": "puzzle", "settings": "settings", "tools": "wrench", "law": "gavel",
    "award": "award", "quality": "badge-check", "win": "trophy", "search": "search", "privacy": "lock",
}


@lru_cache(maxsize=1)
def icon_names() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in ICON_DIR.glob("*.png")))


def names_text() -> str:
    """Список имён для промпта: модель выбирает из него, а не придумывает."""
    return ", ".join(icon_names())


def pick(hint: str | None) -> str | None:
    """Имя значка набора по подсказке модели; None, если подходящего нет."""
    if not hint:
        return None
    names = set(icon_names())
    key = re.sub(r"[^a-z0-9]+", "-", hint.strip().lower()).strip("-")
    if not key:
        return None
    if key in names:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    for word in key.split("-"):
        if word in names:
            return word
        if word in _ALIASES:
            return _ALIASES[word]
    starts = [name for name in icon_names() if name.startswith(key) or key.split("-")[0] in name.split("-")]
    return starts[0] if starts else None


def dominant_color(image_bytes: bytes) -> str | None:
    """Главный цвет картинки-значка образца (без прозрачных и почти белых точек), hex без решётки."""
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception:  # noqa: BLE001 - картинка образца может быть в формате, который Pillow не читает (svg, emf)
        return None
    image.thumbnail((64, 64))
    counts: Counter = Counter()
    for r, g, b, a in image.getdata():
        if a < 128 or (r > 235 and g > 235 and b > 235):
            continue
        counts[(r // 16 * 16, g // 16 * 16, b // 16 * 16)] += 1
    if not counts:
        return None
    r, g, b = counts.most_common(1)[0][0]
    return f"{min(r + 8, 255):02X}{min(g + 8, 255):02X}{min(b + 8, 255):02X}"


def icon_png(name: str, color_hex: str) -> bytes:
    """PNG значка набора в цвете color_hex (контур цветом, фон прозрачный)."""
    from PIL import Image

    image = Image.open(ICON_DIR / f"{name}.png").convert("RGBA")
    color = tuple(int(color_hex[i:i + 2], 16) for i in (0, 2, 4))
    solid = Image.new("RGBA", image.size, (*color, 255))
    solid.putalpha(image.getchannel("A"))
    out = io.BytesIO()
    solid.save(out, format="PNG")
    return out.getvalue()
