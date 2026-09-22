import pytest

from designer.settings import Settings, SettingsError, load_settings


def test_reads_yaml_file(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("llm_model: my-model\nport: 9000\nvariants: [a, b]\n", encoding="utf-8")
    monkeypatch.setenv("DESIGNER_CONFIG", str(config))
    monkeypatch.delenv("DESIGNER_LLM_MODEL", raising=False)
    monkeypatch.delenv("DESIGNER_PORT", raising=False)

    settings = load_settings()

    assert settings.llm_model == "my-model"
    assert settings.port == 9000
    assert settings.variants == ["a", "b"]
    assert settings.llm_url == Settings().llm_url  # не тронуто файлом — значение по умолчанию


def test_missing_file_gives_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("DESIGNER_CONFIG", str(tmp_path / "no-such-config.yaml"))
    for var in ("DESIGNER_LLM_URL", "DESIGNER_LLM_MODEL", "DESIGNER_PORT"):
        monkeypatch.delenv(var, raising=False)

    settings = load_settings()

    assert settings == Settings()


def test_env_var_overrides_file(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("llm_url: http://from-file:1234/v1\nallowed_origins: [http://file.example]\n",
                       encoding="utf-8")
    monkeypatch.setenv("DESIGNER_CONFIG", str(config))
    monkeypatch.setenv("DESIGNER_LLM_URL", "http://from-env:1234/v1")
    monkeypatch.setenv("DESIGNER_ALLOWED_ORIGINS", "http://a.example, http://b.example")

    settings = load_settings()

    assert settings.llm_url == "http://from-env:1234/v1"
    assert settings.allowed_origins == ["http://a.example", "http://b.example"]


def test_unknown_field_in_file_raises_clear_error(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("llm_url: http://x:1234/v1\ntypo_field: 1\n", encoding="utf-8")
    monkeypatch.setenv("DESIGNER_CONFIG", str(config))

    with pytest.raises(SettingsError, match="typo_field"):
        load_settings()


def test_wrong_type_raises_clear_error(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("port: not-a-number\n", encoding="utf-8")
    monkeypatch.setenv("DESIGNER_CONFIG", str(config))

    with pytest.raises(SettingsError, match="port"):
        load_settings()


def test_client_takes_live_model_from_settings(monkeypatch, tmp_path):
    """Живой режим берёт свою модель, если она задана; иначе общую."""
    from designer.llm.client import LlmClient

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DESIGNER_LLM_URL", "http://deck:1/v1")
    monkeypatch.setenv("DESIGNER_LLM_MODEL", "deck-model")
    monkeypatch.delenv("DESIGNER_LIVE_LLM_URL", raising=False)
    monkeypatch.setenv("DESIGNER_LIVE_LLM_MODEL", "fast-model")
    deck = LlmClient.from_env()
    live = LlmClient.from_env(live=True)
    assert (deck.base_url, deck.model) == ("http://deck:1/v1", "deck-model")
    assert (live.base_url, live.model) == ("http://deck:1/v1", "fast-model")
