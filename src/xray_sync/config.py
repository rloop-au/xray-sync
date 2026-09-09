from __future__ import annotations

import os
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from xray_sync.exceptions import ConfigurationError


class JiraEnvironmentConfig(BaseModel):
    url: str
    email_env: str
    token_env: str

    @property
    def email(self) -> str:
        return _required_env(self.email_env)

    @property
    def token(self) -> str:
        return _required_env(self.token_env)


class XrayEnvironmentConfig(BaseModel):
    client_id_env: str
    client_secret_env: str
    auth_url: str = Field(default="https://xray.cloud.getxray.app/api/v2/authenticate")
    graphql_url: str = Field(default="https://xray.cloud.getxray.app/api/v2/graphql")
    rest_url: str = Field(default="https://xray.cloud.getxray.app/api/v2")

    @property
    def client_id(self) -> str:
        return _required_env(self.client_id_env)

    @property
    def client_secret(self) -> str:
        return _required_env(self.client_secret_env)


class EnvironmentConfig(BaseModel):
    jira: JiraEnvironmentConfig
    xray: XrayEnvironmentConfig


class AppConfig(BaseModel):
    env_file: str | None = None
    environments: dict[str, EnvironmentConfig]

    def environment(self, name: str) -> EnvironmentConfig:
        try:
            return self.environments[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.environments)) or "<none>"
            raise ConfigurationError(
                f"Unknown environment '{name}'. Available environments: {available}"
            ) from exc


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"Required environment variable '{name}' is not set")
    return value


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or Path(os.getenv("XRAY_SYNC_CONFIG", "xray-sync.yaml"))
    if not config_path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {config_path}. "
            "Create xray-sync.yaml or set XRAY_SYNC_CONFIG."
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    env_file = os.getenv("XRAY_SYNC_ENV_FILE") or raw.get("env_file")
    env_path = _env_path(config_path, env_file)
    if env_path.exists():
        load_dotenv(env_path, override=False)
    elif env_file:
        raise ConfigurationError(f"Environment file not found: {env_path}")
    return AppConfig.model_validate(raw)


def _env_path(config_path: Path, env_file: str | None) -> Path:
    if not env_file:
        return config_path.parent / ".env"
    path = Path(env_file)
    if path.is_absolute():
        return path
    return config_path.parent / path
