"""Тесты загрузки скиллов: хеш по файлам, подстановки в промпт, незаполненная подстановка."""
from pathlib import Path

import pytest

from designer.llm.skills import SkillError, load_skill


def _write_skill(root: Path, name: str, version: str, prompt: str) -> None:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skill.yaml").write_text(
        f'name: {name}\nversion: "{version}"\ntemperature: 0.4\nmax_tokens: 2000\n', encoding="utf-8",
    )
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")


def test_hash_changes_when_prompt_is_edited(tmp_path):
    _write_skill(tmp_path, "demo", "1", "Правило номер один.")
    first_hash = load_skill("demo", tmp_path).ref().sha256

    _write_skill(tmp_path, "demo", "1", "Правило номер два.")
    second_hash = load_skill("demo", tmp_path).ref().sha256

    assert first_hash != second_hash


def test_ref_carries_name_version_and_hash(tmp_path):
    _write_skill(tmp_path, "demo", "3", "Текст промпта.")
    ref = load_skill("demo", tmp_path).ref()
    assert ref.name == "demo"
    assert ref.version == "3"
    assert len(ref.sha256) == 64


def test_render_fills_placeholder(tmp_path):
    _write_skill(tmp_path, "demo", "1", "Аудитория: {{audience}}.")
    skill = load_skill("demo", tmp_path)
    assert skill.render(audience="разработчики") == "Аудитория: разработчики."


def test_unfilled_placeholder_raises_error(tmp_path):
    _write_skill(tmp_path, "demo", "1", "Аудитория: {{audience}}, назначение: {{purpose}}.")
    skill = load_skill("demo", tmp_path)
    with pytest.raises(SkillError):
        skill.render(audience="разработчики")
