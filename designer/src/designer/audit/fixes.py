"""Починка находок аудита по выбору человека. Владелец: задача T-21."""
from designer.contracts import DesignSystem, Finding, Scene, SlideSpec


def apply_fixes(specs: list[SlideSpec], scenes: list[Scene], findings: list[Finding], chosen_ids: list[str],
                ds: DesignSystem) -> tuple[list[SlideSpec], list[Scene], list[dict]]:
    """Чинит выбранные находки и возвращает новые инструкции, сцены и отчёт.

    Отчёт: по записи на находку: {"finding_id", "status": "fixed" | "skipped", "what": что изменено по-русски}.
    Входные объекты не меняются.
    """
    raise NotImplementedError("T-21")
