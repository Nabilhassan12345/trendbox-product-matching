"""Database engine and transactional session management."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def _require_session_factory() -> sessionmaker:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    session_factory = _require_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_path: str) -> None:
    """Create the SQLite engine, tables, and session factory."""
    global _engine, _SessionLocal

    if db_path.startswith("sqlite"):
        url = db_path
    else:
        url = f"sqlite:///{db_path}"

    logger.info("Initialising database at %s", url)
    _engine = create_engine(url, echo=False, future=True)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    logger.info("Database tables ready")
