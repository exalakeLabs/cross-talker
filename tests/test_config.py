from cross_talker.config import Settings


def test_parses_comma_separated_providers(monkeypatch) -> None:
    monkeypatch.setenv("CROSS_TALKER_PROVIDERS", "openai, anthropic")

    settings = Settings(_env_file=None)

    assert settings.providers == ["openai", "anthropic"]
