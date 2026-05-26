from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import get_database_settings
from backend.app.db.content_projection import sync_content_projection_from_state_file
from backend.app.store.base import DATA_FILE


def main() -> int:
    settings = get_database_settings()
    if not settings.database_url:
        print("[ERROR] DATABASE_URL is not configured.")
        return 1
    if not DATA_FILE.exists():
        print(f"[ERROR] State file not found: {DATA_FILE}")
        return 1
    counts = sync_content_projection_from_state_file(DATA_FILE, database_url=settings.database_url)
    print("[OK] Content asset backfill completed.")
    for key, value in counts.items():
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
