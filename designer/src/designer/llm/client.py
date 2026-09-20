"""Клиент OpenAI-совместимого сервера с ответом по JSON-схеме. Владелец: задача T-04."""


class LlmClient:
    def __init__(self, base_url: str, model: str, timeout_s: float = 120.0):
        raise NotImplementedError("T-04")

    def complete_json(self, system: str, user: str, schema: dict, images_png: list[bytes] | None = None) -> dict:
        raise NotImplementedError("T-04")
