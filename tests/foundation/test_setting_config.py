"""Configuration behavior after migrating Settings to Pydantic v2 style."""

from siada.foundation.setting import Settings


def test_settings_preserve_environment_and_unknown_variable_behavior(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_TURNS", "23")
    monkeypatch.setenv("max_turns", "99")
    settings = Settings(_env_file=None)
    assert settings.MAX_TURNS == 23
    assert settings.model_config["case_sensitive"] is True
    assert settings.model_config["env_file"] == ".env"
    assert settings.model_config["extra"] == "ignore"

    env_file = tmp_path / ".env"
    env_file.write_text("MAX_TURNS=31\nUNKNOWN_LEGACY_SETTING=ignored\n", encoding="utf-8")
    monkeypatch.delenv("MAX_TURNS")
    assert Settings(_env_file=env_file).MAX_TURNS == 31
