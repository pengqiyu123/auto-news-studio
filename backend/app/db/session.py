from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_database_settings


def build_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    settings = get_database_settings()
    url = str(database_url or settings.database_url).strip()
    if not url:
        raise ValueError("DATABASE_URL is required when initializing the PostgreSQL state backend.")
    return create_engine(url, future=True, pool_pre_ping=True, echo=echo)


def build_session_factory(database_url: str | None = None, *, echo: bool = False) -> sessionmaker[Session]:
    engine = build_engine(database_url, echo=echo)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
