"""Centralised configuration loader."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    secret_key: str
    register_token: str
    flask_env: str
    db_name: str
    db_host: str
    db_user: str
    db_password: str
    db_port: str
    timezone: str
    bootstrap_admin_user: str | None
    bootstrap_admin_password: str | None

    @property
    def is_production(self) -> bool:
        return self.flask_env == "production"


def load_config() -> Config:
    return Config(
        secret_key=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        register_token=os.environ.get("REGISTER_TOKEN", ""),
        flask_env=os.environ.get("FLASK_ENV", "production"),
        db_name=os.environ.get("POSTGRES_DB", "eticmont"),
        db_host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        db_user=os.environ.get("POSTGRES_USER", "eticmont"),
        db_password=os.environ.get("POSTGRES_PASSWORD", "eticmont"),
        db_port=os.environ.get("POSTGRES_PORT", "5433"),
        timezone=os.environ.get("APP_TIMEZONE", "Europe/Paris"),
        bootstrap_admin_user=os.environ.get("BOOTSTRAP_ADMIN_USER") or None,
        bootstrap_admin_password=os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or None,
    )
