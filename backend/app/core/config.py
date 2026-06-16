from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "API Contract & Developer Experience Toolkit"
    environment: str = os.getenv("ENVIRONMENT", "local")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./api_toolkit.db")
    current_schema_version: str = os.getenv("CURRENT_SCHEMA_VERSION", "2025-02-01")
    supported_schema_versions: tuple[str, ...] = ("2024-09-01", "2025-02-01")
    deprecated_schema_versions: tuple[str, ...] = ("2024-09-01",)
    p95_latency_target_ms: int = 120
    seed_on_startup: bool = os.getenv("SEED_ON_STARTUP", "false").lower() == "true"

    @property
    def api_key_roles(self) -> dict[str, tuple[str, str]]:
        raw = os.getenv(
            "API_KEYS",
            "admin-key:admin:platform-admin,"
            "analyst-key:analyst:reconciliation-analyst,"
            "integration-key:integration:dashboard-integration",
        )
        roles: dict[str, tuple[str, str]] = {}
        for item in raw.split(","):
            parts = item.strip().split(":")
            if len(parts) != 3:
                continue
            key, role, actor = parts
            roles[key] = (role, actor)
        return roles


settings = Settings()
