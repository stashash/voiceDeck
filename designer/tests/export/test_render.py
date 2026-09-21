"""Тесты картинки слайда из pptx: сборка одного слайда, кеш по хешу инструкции. Задача T-26.

Настоящий движок не зовётся: сессия подменяется. Окна на экране не открываются.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pptx import Presentation

from designer.contracts import SlideSpec
from designer.export.render import CACHE_DIR_NAME, cache_key, render_slides, render_spec
from designer.parse.package import SOURCE_NAME, build_package

PNG = b"\x89PNG\r\n\x1a\n"


class _FakeSession:
    """Сессия движка: считает запросы и помнит, сколько слайдов было в присланном файле."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.slide_counts: list[int] = []

    def png(self, pptx_path: Path, slide_index: int, width_px: int = 1600) -> bytes:
        self.calls.append((slide_index, width_px))
        self.slide_counts.append(len(Presentation(str(pptx_path)).slides))
        return PNG + str(slide_index).encode("ascii")

    def close(self) -> None:
        pass


@pytest.fixture
def session(monkeypatch) -> _FakeSession:
    fake = _FakeSession()
    monkeypatch.setattr("designer.export.convert.get_session", lambda: fake)
    return fake


@pytest.fixture(scope="session")
def built_package(templates, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("render-package")
    return out_dir, build_package(templates[0], out_dir)


@pytest.fixture
def package(built_package, tmp_path):
    """Свой пакет на тест: кеш одного теста не виден другому."""
    source_dir, ds = built_package
    work = tmp_path / "package"
    work.mkdir()
    shutil.copyfile(source_dir / SOURCE_NAME, work / SOURCE_NAME)
    return work, ds


def _spec(ds, text: str = "") -> SlideSpec:
    pattern = ds.patterns[0]
    slot_text = {pattern.slots[0].id: text} if text and pattern.slots else {}
    return SlideSpec(slide_id="s1", pattern_id=pattern.id, slot_text=slot_text)


def test_render_spec_builds_one_slide_and_takes_its_picture(package, session):
    package_dir, ds = package

    png = render_spec(_spec(ds), ds, package_dir, width_px=900)

    assert png.startswith(PNG)
    assert session.calls == [(0, 900)]
    assert session.slide_counts == [1]


def test_render_spec_second_call_takes_picture_from_cache(package, session):
    package_dir, ds = package
    spec = _spec(ds)

    first = render_spec(spec, ds, package_dir)
    second = render_spec(spec, ds, package_dir)

    assert first == second
    assert len(session.calls) == 1
    assert (package_dir / CACHE_DIR_NAME / f"{cache_key(spec, ds)}.png").is_file()


def test_changed_spec_gets_its_own_picture(package, session):
    package_dir, ds = package

    render_spec(_spec(ds, "Первый текст"), ds, package_dir)
    render_spec(_spec(ds, "Другой текст"), ds, package_dir)

    assert len(session.calls) == 2
    assert len(list((package_dir / CACHE_DIR_NAME).glob("*.png"))) == 2


def test_cache_key_is_stable_for_same_spec_and_changes_with_width(package):
    _, ds = package
    spec = _spec(ds, "Текст слайда")
    same = SlideSpec.model_validate_json(spec.model_dump_json())

    assert cache_key(spec, ds) == cache_key(same, ds)
    assert cache_key(spec, ds, 900) != cache_key(spec, ds, 1600)


def test_render_slides_asks_session_for_every_slide_once(monkeypatch, tmp_path):
    fake = _FakeSession()
    monkeypatch.setattr(fake, "png", lambda path, index, width: PNG + str(index).encode("ascii"))
    sessions: list[int] = []
    monkeypatch.setattr("designer.export.convert.get_session",
                         lambda: (sessions.append(1), fake)[1])

    pages = render_slides(tmp_path / "deck.pptx", 3, width_px=1200)

    assert len(pages) == 3
    assert pages[0] != pages[2]
    assert len(sessions) == 1  # движок поднимается один раз на всю колоду
