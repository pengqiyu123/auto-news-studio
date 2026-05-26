from __future__ import annotations

from sqlalchemy import text

from .config import get_database_settings
from .session import build_engine


def check_database_health() -> tuple[bool, str]:
    settings = get_database_settings()
    if not settings.database_url:
        return False, "未配置 DATABASE_URL"
    try:
        engine = build_engine(settings.database_url)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
            tables = connection.execute(
                text(
                    """
                    select count(*)
                    from information_schema.tables
                    where table_schema = 'public'
                    """
                )
            ).scalar_one()
            alembic_version = connection.execute(
                text(
                    """
                    select version_num
                    from alembic_version
                    limit 1
                    """
                )
            ).scalar_one_or_none()
        return True, f"数据库已连通，STATE_BACKEND={settings.state_backend}，public 表={tables}，alembic={alembic_version or 'missing'}"
    except Exception as exc:
        return False, f"数据库不可用：{exc}"
