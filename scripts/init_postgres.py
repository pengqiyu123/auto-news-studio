from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import Base, build_engine, get_database_settings
from backend.app.db import models  # noqa: F401


def main() -> int:
    settings = get_database_settings()
    if not settings.database_url:
        print("[ERROR] DATABASE_URL is not configured.")
        return 1
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    print("[OK] PostgreSQL schema initialized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
