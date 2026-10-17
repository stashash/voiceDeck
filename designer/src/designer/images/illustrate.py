"""Шаг иллюстраций: до трёх слайдов колоды получают фото от модели text-to-image.

Картинку получает только слайд, для которого в шаблоне есть образец с одним крупным фото
(`layout.match.hero_area`): кадр, которому некуда встать, не рисуется. Описание кадра пишет модель
плана по скиллу `illustrate`, правила кадра взяты из наработок кинодек: мир темы вместо стоковой
ассоциации, люди и свет, без текста и интерфейсов в кадре.
"""
from __future__ import annotations

import zlib
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from designer import store
from designer.contracts import Area, DeckPlan, DesignSystem, SlideImage, SlideIntent, SlideKind
from designer.images.engine import ComfyEngine, image_size
from designer.layout.match import _fits_with_image, choose_pattern, hero_area
from designer.llm.client import LlmClient, LlmResponseError, ModelLoading
from designer.llm.skills import load_skill

SKILL = "illustrate"
IMAGE_LIMIT = 3
_SKIP_KINDS = (SlideKind.title, SlideKind.agenda, SlideKind.thanks, SlideKind.cta,
               SlideKind.chart, SlideKind.table, SlideKind.big_number)


class _Shot(BaseModel):
    prompt: str = Field(max_length=1200)
    alt: str = Field(max_length=300)


def candidates(plan: DeckPlan, ds: DesignSystem) -> list[tuple[SlideIntent, Area]]:
    """Слайды, чьё фото встанет в образец шаблона: сначала «картинка и текст», остальные вразбивку."""
    found: list[tuple[SlideIntent, Area]] = []
    for slide in plan.slides[1:-1]:
        if slide.kind in _SKIP_KINDS or slide.chart is not None or slide.table is not None:
            continue
        probe = slide.model_copy(update={"image": SlideImage(prompt="", path="probe.png")})
        pattern = choose_pattern(probe, ds)
        if _fits_with_image(probe, pattern, ds):
            found.append((slide, hero_area(pattern)))
    first = [c for c in found if c[0].kind == SlideKind.image_text][:IMAGE_LIMIT]
    rest = [c for c in found if c[0].kind != SlideKind.image_text]
    need = min(IMAGE_LIMIT - len(first), len(rest))
    spread = [rest[int(i * len(rest) / need)] for i in range(need)] if need > 0 else []
    order = {id(slide): index for index, slide in enumerate(plan.slides)}
    return sorted(first + spread, key=lambda c: order[id(c[0])])


def _material(slide: SlideIntent) -> str:
    lines = [f"Заголовок: {slide.title}"]
    if slide.key_message:
        lines.append(f"Мысль: {slide.key_message}")
    lines += [f"- {item.heading} {item.body}".strip() for item in slide.items]
    return "\n".join(lines)


def illustrate(plan: DeckPlan, ds: DesignSystem, client: LlmClient, engine: ComfyEngine,
               deck_id: str, audience: str = "") -> list[str]:
    """Ставит картинки слайдам плана и возвращает их id. Сбой сервера картинок пробрасывается
    (ImageEngineError): конвейер собирает колоду без картинок. Сбой модели на одном слайде его пропускает."""
    picked = candidates(plan, ds)
    if not picked:
        return []
    skill = load_skill(SKILL)
    palette = ", ".join(f"#{c.hex}" for c in ds.tokens.colors[:5]) or "нейтральная"
    width_emu, height_emu = ds.slide_size_emu

    def aspect_of(hero: Area) -> float:
        return (hero.box[2] * width_emu) / max(hero.box[3] * height_emu, 1)

    def shot(candidate: tuple[SlideIntent, Area]) -> _Shot | None:
        slide, hero = candidate
        system = skill.render(deck_title=plan.title, audience=audience.strip() or "не задана",
                              palette=palette, aspect=f"{aspect_of(hero):.2f}")
        try:
            data = client.complete_json(system=system, user=_material(slide), schema=_Shot.model_json_schema(),
                                        params=skill.params)
            return _Shot.model_validate(data)
        except (LlmResponseError, ModelLoading, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=len(picked)) as pool:
        shots = list(pool.map(shot, picked))

    folder = store.deck_dir(deck_id) / "images"
    folder.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    # Видеокарта одна: кадры рисуются по очереди.
    for (slide, hero), described in zip(picked, shots):
        if described is None or not described.prompt.strip():
            continue
        width, height = image_size(aspect_of(hero))
        png = engine.generate(described.prompt, width, height, seed=zlib.crc32(f"{deck_id}:{slide.id}".encode()))
        path = folder / f"{slide.id}.png"
        path.write_bytes(png)
        slide.image = SlideImage(prompt=described.prompt, alt=described.alt,
                                 path=path.relative_to(store.data_dir()).as_posix())
        done.append(slide.id)
    return done
