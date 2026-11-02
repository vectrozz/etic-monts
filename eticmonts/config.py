"""Centralised configuration loader."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Optional modules. The MAEC/biodiversity core is always on; everything else is
# opt-in through the FEATURES env var (comma-separated, or "all").
#   cout_revient  — coût de revient par culture (fraise)
#   marketplace   — produits, stocks, clients, commandes, liens clients, tournées
#   whatsapp      — listes des fermes reçues du groupe WhatsApp via l'app Android « EMB Relais »
KNOWN_FEATURES = frozenset({"cout_revient", "marketplace", "whatsapp"})
DEFAULT_FEATURES = "cout_revient"


def _features(raw: str | None) -> frozenset[str]:
    raw = (raw if raw is not None else DEFAULT_FEATURES).strip().lower()
    if raw == "all":
        return KNOWN_FEATURES
    wanted = {f.strip() for f in raw.split(",") if f.strip()}
    return frozenset(wanted & KNOWN_FEATURES)


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
    features: frozenset[str] = frozenset({"cout_revient"})

    @property
    def is_production(self) -> bool:
        return self.flask_env == "production"

    def has(self, feature: str) -> bool:
        return feature in self.features


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
        features=_features(os.environ.get("FEATURES")),
    )
