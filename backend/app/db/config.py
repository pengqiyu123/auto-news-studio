from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    state_backend: str = "json"

    @property
    def is_database_enabled(self) -> bool:
        return self.state_backend in {"dual_write", "postgres"}


def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_url=str(os.getenv("DATABASE_URL") or "").strip(),
        state_backend=str(os.getenv("STATE_BACKEND") or "json").strip().lower() or "json",
    )
