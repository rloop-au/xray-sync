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
