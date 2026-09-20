"""Скиллы как файлы с версией. Владелец: задача T-04."""
from pathlib import Path

from designer.contracts import SkillRef


class Skill:
    name: str
    version: str
    prompt: str
    params: dict

    def ref(self) -> SkillRef:
        raise NotImplementedError("T-04")


def load_skill(name: str, skills_dir: Path | None = None) -> Skill:
    raise NotImplementedError("T-04")
