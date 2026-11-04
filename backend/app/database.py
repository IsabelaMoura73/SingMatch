"""Uma sessão de banco por request. Migrações devem rodar antes do servidor."""
from __future__ import annotations

import os
from functools import lru_cache
from collections.abc import Iterator

from sqlalchemy import create_engine


def normalize_database_url(url: str) -> str:
    """Use o driver psycopg 3 com URL padrão do Render ou local."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def create_db_session_factory() -> sessionmaker[Session]:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL ausente. Configure o ambiente local.")
    engine = create_engine(normalize_database_url(url), pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    factory = create_db_session_factory()
    with factory() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
