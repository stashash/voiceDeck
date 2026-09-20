"""Карточка прогона: модель, версии скиллов, времена этапов. Владелец: задача T-04."""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from designer.contracts import RunManifest, SkillRef
from designer.llm.skills import Skill


class RunRecorder:
    """Копит данные одного прогона конвейера и отдаёт RunManifest."""

    def __init__(self, model: str, run_id: str | None = None):
        self.model = model
        self.run_id = run_id or uuid.uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._skills: list[SkillRef] = []
        self._timings_ms: dict[str, int] = {}

    def use_skill(self, skill: Skill) -> None:
        """Отмечает версию и хеш скилла, использованного в прогоне."""
        ref = skill.ref()
        if not any(existing.name == ref.name and existing.version == ref.version for existing in self._skills):
            self._skills.append(ref)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Засекает время этапа с заданным именем, суммирует при повторном вызове."""
        started = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self._timings_ms[name] = self._timings_ms.get(name, 0) + elapsed_ms

    def manifest(self, design_system_id: str | None = None) -> RunManifest:
        return RunManifest(
            run_id=self.run_id,
            started_at=self.started_at,
            model=self.model,
            design_system_id=design_system_id,
            skills=list(self._skills),
            timings_ms=dict(self._timings_ms),
        )
