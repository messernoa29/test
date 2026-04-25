"""SQLAlchemy engine + session factory.

Supports SQLite (dev default) and Postgres (prod). The engine is a module-
level singleton created lazily on first use so `import api.db.session` is
cheap and the actual DB connection only happens when the app really needs it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import get_settings

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None
_lock = Lock()


def get_engine() -> Engine:
    global _engine, _SessionLocal
    with _lock:
        if _engine is not None:
            return _engine
        url = get_settings().database_url
        # Render / Heroku give DATABASE_URL=postgres://... but SQLAlchemy
        # 2.x needs the explicit driver. Rewrite transparently so the user
        # never has to think about it.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            # SQLite needs to know we share the connection across threads
            # (FastAPI handlers + the audit worker pool).
            kwargs["connect_args"] = {"check_same_thread": False}
            _ensure_sqlite_parent(url)
        _engine = create_engine(url, **kwargs)
        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False,
        )
        logger.info("DB engine created: %s", _mask_url(url))
        return _engine


def get_session() -> Session:
    """Open a new session. Caller is responsible for closing it."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def create_all_tables() -> None:
    """Create the schema if it does not exist. Safe to call repeatedly."""
    from api.db.models import Base

    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def _ensure_sqlite_parent(url: str) -> None:
    """`sqlite:///relative/or/absolute/path.db` — make sure the folder exists."""
    path_part = url.removeprefix("sqlite:///")
    if not path_part:
        return
    p = Path(path_part)
    p.parent.mkdir(parents=True, exist_ok=True)


def _mask_url(url: str) -> str:
    """Hide credentials when logging the connection string."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        return f"{scheme}://***@{host}"
    return url
