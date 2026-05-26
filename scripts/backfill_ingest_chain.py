from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import get_database_settings
from backend.app.db.ingest_projection import sync_ingest_projection_from_state_file
from backend.app.store.base import DATA_FILE


def backfill_from_state_file(state_file: Path) -> dict[str, int]:
    settings = get_database_settings()
    return sync_ingest_projection_from_state_file(state_file, database_url=settings.database_url)


def main() -> int:
    settings = get_database_settings()
    if not settings.database_url:
        print("[ERROR] DATABASE_URL is not configured.")
        return 1
    state_file = DATA_FILE
    if not state_file.exists():
        print(f"[ERROR] State file not found: {state_file}")
        return 1
    counts = backfill_from_state_file(state_file)
    print("[OK] Backfill completed.")
    for key, value in counts.items():
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
