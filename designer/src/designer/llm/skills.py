"""Скиллы как файлы с версией. Владелец: задача T-04."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import yaml

from designer.contracts import SkillRef

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# В установленном пакете рядом с кодом каталога skills нет: образ кладёт его отдельно и называет путь переменной.
_SKILLS_ROOT = Path(os.environ.get("DESIGNER_SKILLS_DIR") or Path(__file__).resolve().parents[3] / "skills")


class SkillError(Exception):
    """Ошибка загрузки скилла или подстановки в промпт."""


class Skill:
    """Промпт скилла с версией, хешем и параметрами модели (temperature, max_tokens и т.п.)."""

    def __init__(self, name: str, version: str, prompt: str, params: dict, sha256: str):
        self.name = name
        self.version = version
        self.prompt = prompt
        self.params = params
        self.sha256 = sha256

    def ref(self) -> SkillRef:
        return SkillRef(name=self.name, version=self.version, sha256=self.sha256)

    def render(self, **values: str) -> str:
        """Подставляет {{имя}} в промпт. Незаполненная подстановка — ошибка."""

        def _sub(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                raise SkillError(f"скилл {self.name}: не заполнена подстановка {{{{{key}}}}}")
            return str(values[key])

        return _PLACEHOLDER.sub(_sub, self.prompt)


def load_skill(name: str, skills_dir: Path | None = None) -> Skill:
    root = Path(skills_dir) if skills_dir is not None else _SKILLS_ROOT
    folder = root / name
    yaml_path = folder / "skill.yaml"
    prompt_path = folder / "prompt.md"
    if not yaml_path.is_file() or not prompt_path.is_file():
        raise SkillError(f"скилл {name}: нет skill.yaml или prompt.md в {folder}")

    meta = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if "version" not in meta:
        raise SkillError(f"скилл {name}: в skill.yaml нет version")

    prompt = prompt_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(yaml_path.read_bytes() + prompt_path.read_bytes()).hexdigest()
    params = {k: v for k, v in meta.items() if k not in {"name", "version"}}
    return Skill(name=str(meta.get("name", name)), version=str(meta["version"]), prompt=prompt,
                 params=params, sha256=digest)
