from __future__ import annotations

from pathlib import Path

import pytest

from xray_sync.config import load_config
from xray_sync.exceptions import ConfigurationError


def test_loads_named_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
environments:
  prod:
    jira:
      url: https://example.atlassian.net
      email_env: JIRA_EMAIL
      token_env: JIRA_TOKEN
    xray:
      client_id_env: XRAY_CLIENT_ID
      client_secret_env: XRAY_CLIENT_SECRET
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JIRA_EMAIL", "person@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("XRAY_CLIENT_ID", "client-id")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "client-secret")

    config = load_config(config_path)

    env = config.environment("prod")
    assert env.jira.url == "https://example.atlassian.net"
    assert env.jira.email == "person@example.com"
    assert env.xray.client_secret == "client-secret"


def test_missing_environment_variable_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
environments:
  prod:
    jira:
      url: https://example.atlassian.net
      email_env: MISSING_EMAIL
      token_env: MISSING_TOKEN
    xray:
      client_id_env: MISSING_CLIENT_ID
      client_secret_env: MISSING_CLIENT_SECRET
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    with pytest.raises(ConfigurationError):
        _ = config.environment("prod").jira.email


def test_loads_dotenv_next_to_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("XRAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("XRAY_CLIENT_SECRET", raising=False)
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
environments:
  prod:
    jira:
      url: https://example.atlassian.net
      email_env: JIRA_EMAIL
      token_env: JIRA_TOKEN
    xray:
      client_id_env: XRAY_CLIENT_ID
      client_secret_env: XRAY_CLIENT_SECRET
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "JIRA_EMAIL=dotenv@example.com",
                "JIRA_TOKEN=dotenv-jira-token",
                "XRAY_CLIENT_ID=dotenv-client-id",
                "XRAY_CLIENT_SECRET=dotenv-client-secret",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    env = config.environment("prod")
    assert env.jira.email == "dotenv@example.com"
    assert env.jira.token == "dotenv-jira-token"
    assert env.xray.client_id == "dotenv-client-id"
    assert env.xray.client_secret == "dotenv-client-secret"


def test_loads_named_dotenv_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("XRAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("XRAY_CLIENT_SECRET", raising=False)
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
env_file: .env.ampol
environments:
  prod:
    jira:
      url: https://example.atlassian.net
      email_env: JIRA_EMAIL
      token_env: JIRA_TOKEN
    xray:
      client_id_env: XRAY_CLIENT_ID
      client_secret_env: XRAY_CLIENT_SECRET
""",
        encoding="utf-8",
    )
    (tmp_path / ".env.ampol").write_text(
        "\n".join(
            [
                "JIRA_EMAIL=ampol@example.com",
                "JIRA_TOKEN=ampol-jira-token",
                "XRAY_CLIENT_ID=ampol-client-id",
                "XRAY_CLIENT_SECRET=ampol-client-secret",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    env = config.environment("prod")
    assert config.env_file == ".env.ampol"
    assert env.jira.email == "ampol@example.com"
    assert env.jira.token == "ampol-jira-token"
    assert env.xray.client_id == "ampol-client-id"
    assert env.xray.client_secret == "ampol-client-secret"


def test_xray_sync_env_file_overrides_config_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("XRAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("XRAY_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("XRAY_SYNC_ENV_FILE", ".env.zenergy")
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
env_file: .env.ampol
environments:
  prod:
    jira:
      url: https://example.atlassian.net
      email_env: JIRA_EMAIL
      token_env: JIRA_TOKEN
    xray:
      client_id_env: XRAY_CLIENT_ID
      client_secret_env: XRAY_CLIENT_SECRET
""",
        encoding="utf-8",
    )
    (tmp_path / ".env.ampol").write_text("JIRA_EMAIL=ampol@example.com", encoding="utf-8")
    (tmp_path / ".env.zenergy").write_text(
        "\n".join(
            [
                "JIRA_EMAIL=zenergy@example.com",
                "JIRA_TOKEN=zenergy-jira-token",
                "XRAY_CLIENT_ID=zenergy-client-id",
                "XRAY_CLIENT_SECRET=zenergy-client-secret",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.environment("prod").jira.email == "zenergy@example.com"


def test_missing_named_dotenv_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
env_file: .env.missing
environments: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="Environment file not found"):
        load_config(config_path)


def test_existing_environment_wins_over_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "xray-sync.yaml"
    config_path.write_text(
        """
environments:
  prod:
    jira:
      url: https://example.atlassian.net
      email_env: JIRA_EMAIL
      token_env: JIRA_TOKEN
    xray:
      client_id_env: XRAY_CLIENT_ID
      client_secret_env: XRAY_CLIENT_SECRET
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "JIRA_EMAIL=dotenv@example.com",
                "JIRA_TOKEN=dotenv-jira-token",
                "XRAY_CLIENT_ID=dotenv-client-id",
                "XRAY_CLIENT_SECRET=dotenv-client-secret",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JIRA_EMAIL", "shell@example.com")

    config = load_config(config_path)

    assert config.environment("prod").jira.email == "shell@example.com"
