#!/usr/bin/env python3
"""Importa o catálogo piloto, idempotente por (source, source_id) e id de versão.

Executar depois de `alembic upgrade head`. Não sobrescreve revisões humanas
posteriores de approved/verified_at/rights_reviewed nas versões existentes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from app.database import create_db_session_factory  # noqa: E402
from app.models import KaraokeVersionRow, SongRow  # noqa: E402
from app.schemas import KaraokeVersion, Song  # noqa: E402


def seed_catalog(db: Session, path: Path | None = None) -> tuple[int, int]:
    path = path or ROOT / "data" / "catalogo_piloto.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    songs = [Song.model_validate(s) for s in payload["songs"]]
    versions = [KaraokeVersion.model_validate(v) for v in payload["karaoke_versions"]]
    counter_song = counter_video = 0
    ids = {s.id for s in songs}
    if any(v.song_id not in ids for v in versions):
        raise ValueError("Versão referencia música inexistente no catálogo piloto")
    for s in songs:
        existing = db.scalar(select(SongRow).where(SongRow.source == s.source, SongRow.source_id == s.source_id))
        if existing:
            if existing.id != s.id:
                raise ValueError(f"Fonte/ID {s.source}/{s.source_id} já pertence a {existing.id}")
            continue  # Não apagar edições curatoriais com reimportação
        if db.get(SongRow, s.id):
            raise ValueError(f"ID {s.id} já existe em outra fonte")
        db.add(SongRow(**s.model_dump()))
        counter_song += 1
    db.flush()
    for v in versions:
        if db.get(KaraokeVersionRow, v.id):
            continue
        db.add(KaraokeVersionRow(**v.model_dump()))
        counter_video += 1
    db.flush()
    return counter_song, counter_video


def main() -> None:
    factory = create_db_session_factory()
    with factory.begin() as db:
        inserted = seed_catalog(db)
    print(f"Catálogo importado: {inserted[0]} músicas novas, {inserted[1]} versões novas.")
    print("Atenção: aprovado no piloto NÃO garante incorporação atual ou direitos de uso.")


if __name__ == "__main__":
    main()
