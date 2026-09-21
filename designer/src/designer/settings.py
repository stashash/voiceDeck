"""Настройки сервиса: файл YAML плюс переменные окружения поверх него. Владелец: задача T-24.

Источник — YAML-файл, путь к нему в переменной DESIGNER_CONFIG (по умолчанию config.yaml
рядом с запуском). Файла может не быть: тогда используются только значения по умолчанию
и переменные окружения. Каждое поле можно перекрыть переменной окружения DESIGNER_* — та
же переменная, что уже читают другие модули напрямую (llm.client, store, __main__,
export.convert, api.app), так что уже существующие переменные продолжают работать без
этого файла настроек.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_PATH_ENV = "DESIGNER_CONFIG"
_DEFAULT_CONFIG_PATH = "config.yaml"

# Имя поля настроек -> переменная окружения, которая его перекрывает.
_ENV_MAP: dict[str, str] = {
    "llm_url": "DESIGNER_LLM_URL",
    "llm_model": "DESIGNER_LLM_MODEL",
    "live_llm_url": "DESIGNER_LIVE_LLM_URL",
    "live_llm_model": "DESIGNER_LIVE_LLM_MODEL",
    "data_dir": "DESIGNER_DATA_DIR",
    "port": "DESIGNER_PORT",
    "allowed_origins": "DESIGNER_ALLOWED_ORIGINS",
    "converter": "DESIGNER_CONVERTER",
    "slide_count": "DESIGNER_SLIDE_COUNT",
    "variants": "DESIGNER_VARIANTS",
}

# Поля-списки: значение из переменной окружения режется по запятой, как в остальном сервисе.
_LIST_FIELDS = frozenset({"allowed_origins", "variants"})


class SettingsError(ValueError):
    """Файл настроек или переменные окружения не годятся: неизвестное поле или неверный тип."""


class Settings(BaseModel):
    """Настройки сервиса. Неизвестное поле запрещено: опечатка в файле не проходит тихо."""

    model_config = ConfigDict(extra="forbid")

    llm_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "qwen/qwen3.8-27b"
    live_llm_url: str | None = Field(default=None, description="пусто — берётся llm_url")
    live_llm_model: str | None = Field(default=None, description="пусто — берётся llm_model")
    data_dir: str = "./data"
    port: int = 8090
    allowed_origins: list[str] = Field(default_factory=list)
    converter: str | None = Field(default=None, description="пусто — автовыбор первого доступного движка")
    slide_count: int = 12
    variants: list[str] = Field(default_factory=lambda: ["a"])


def config_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get(CONFIG_PATH_ENV, _DEFAULT_CONFIG_PATH))


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Читает config.yaml (если есть), накладывает переменные окружения, проверяет поля."""
    env = os.environ if env is None else env
    path = config_path(env)
    raw: dict = _read_yaml(path)
    for field, var in _ENV_MAP.items():
        if var in env:
            value = env[var]
            raw[field] = _split_list(value) if field in _LIST_FIELDS else value
    try:
        return Settings(**raw)
    except ValidationError as exc:
        raise SettingsError(_format_error(path, exc)) from exc


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise SettingsError(f"файл настроек {path} должен быть словарём полей, а не {type(loaded).__name__}")
    return loaded


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _format_error(path: Path, exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "?"
        if err["type"] == "extra_forbidden":
            parts.append(f"неизвестное поле {field!r}")
        else:
            parts.append(f"поле {field!r}: {err['msg']}")
    return f"настройки из {path} не приняты: " + "; ".join(parts)
