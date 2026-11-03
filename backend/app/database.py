"""Conexão preguiçosa: não exige banco apenas para importar /api/health."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_db_session_factory():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL ausente. Configure o ambiente local.")
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
