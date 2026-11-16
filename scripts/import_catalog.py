#!/usr/bin/env python3
"""Importa os catálogos, idempotente por (source, source_id) e id de versão.

Executar depois de `alembic upgrade head`. Importa:
  * data/catalogo_piloto.json — 5 músicas com vídeo de karaokê curado;
  * data/catalogo_forro.json  — catálogo ampliado com letra sincronizada
    (gerado por scripts/build_catalog.py; letras em data/letras/*.lrc).

Não sobrescreve revisões humanas posteriores de approved/verified_at/
rights_reviewed nas versões existentes. Só preenche a letra se estiver vazia.
Exceção: vídeo comprovadamente bloqueado fora do YouTube (lista "bloqueados"
de data/fontes/videos_verificados.json) é trocado pelo substituto do JSON ou,
sem substituto, perde a aprovação.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import csv
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from app.database import create_db_session_factory  # noqa: E402
from app.models import KaraokeVersionRow, SongRow  # noqa: E402
from app.schemas import KaraokeVersion, Song  # noqa: E402

PILOT = ROOT / "data" / "catalogo_piloto.json"
EXPANDED = ROOT / "data" / "catalogo_forro.json"
VERIFIED = ROOT / "data" / "fontes" / "videos_verificados.json"
AUDIT = ROOT / "data" / "fontes" / "auditoria_karaoke.csv"
# Campos do JSON que não fazem parte do contrato KaraokeVersion.
FILE_ONLY_FIELDS = ("lyrics_file", "video_origin")


def _read_lyrics(base: Path, raw: dict) -> str | None:
    rel = raw.get("lyrics_file")
    if not rel:
        return None
    path = (base / rel).resolve()
    if base.resolve() not in path.parents:
        raise ValueError(f"lyrics_file fora da pasta de dados: {rel}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Arquivo de letra vazio: {rel}")
    return text + "\n"

def load_audit(path: Path = AUDIT) -> dict[str, str]:
    """Retorna {version_id: youtube_video_id} para karaokês aprovados."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo de auditoria não encontrado: {path}"
        )

    approved = {}
    seen = set()

    required = {
        "version_id",
        "youtube_url",
        "instrumental",
        "letra_correta",
        "reproducao",
        "status",
    }

    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV de auditoria sem colunas obrigatórias.")

        for row in reader:
            version_id = row["version_id"].strip()
            status = row["status"].strip().lower()

            if not version_id or version_id in seen:
                raise ValueError(
                    f"ID vazio ou duplicado na auditoria: {version_id!r}"
                )

            seen.add(version_id)

            if status not in {"aprovado", "rejeitado", "pendente"}:
                raise ValueError(
                    f"Status inválido para {version_id}: {status}"
                )

            if status != "aprovado":
                continue

            checks = (
                "instrumental",
                "letra_correta",
                "reproducao",
            )

            if any(row[field].strip().lower() != "sim" for field in checks):
                raise ValueError(
                    f"{version_id}: aprovado sem passar em todas as verificações."
                )

            parsed = urlparse(row["youtube_url"].strip())
            video_id = parse_qs(parsed.query).get("v", [""])[0]

            if not video_id or parsed.hostname not in {
                "youtube.com",
                "www.youtube.com",
                "m.youtube.com",
            }:
                raise ValueError(
                    f"URL do YouTube inválida para {version_id}"
                )

            approved[version_id] = video_id

    return approved

def seed_catalog(db: Session, path: Path | None = None, blocked: set[str] | None = None) -> tuple[int, int]:
    path = path or PILOT
    payload = json.loads(path.read_text(encoding="utf-8"))
    songs = [Song.model_validate(s) for s in payload["songs"]]
    raw_versions = payload["karaoke_versions"]
    versions = [KaraokeVersion.model_validate({k: v for k, v in raw.items() if k not in FILE_ONLY_FIELDS})
                for raw in raw_versions]
    lyrics = {raw["id"]: _read_lyrics(path.parent, raw) for raw in raw_versions}
    counter_song = counter_video = 0
    ids = {s.id for s in songs}
    if any(v.song_id not in ids for v in versions):
        raise ValueError(f"Versão referencia música inexistente em {path.name}")
    if any(v.kind == "letra_sincronizada" and not lyrics[v.id] for v in versions):
        raise ValueError(f"Versão com letra sincronizada sem lyrics_file em {path.name}")
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
        existing = db.get(KaraokeVersionRow, v.id)
        if existing:
            # Única exceção à regra de não sobrescrever: o vídeo antigo foi comprovadamente
            # bloqueado (/verificar.html) e o JSON traz um substituto verificado.
            if (blocked and existing.youtube_video_id in blocked and v.youtube_video_id not in blocked
                    and existing.youtube_video_id != v.youtube_video_id):
                existing.youtube_video_id = v.youtube_video_id
                existing.approved = existing.approved and v.approved
                existing.verified_at, existing.duration_seconds = v.verified_at, v.duration_seconds
            if existing.lyrics_lrc is None and lyrics[v.id]:
                existing.lyrics_lrc, existing.lyrics_source = lyrics[v.id], v.lyrics_source
            continue
        db.add(KaraokeVersionRow(**v.model_dump(), lyrics_lrc=lyrics[v.id]))
        counter_video += 1
    db.flush()
    return counter_song, counter_video


def load_blocked(path: Path = VERIFIED) -> set[str]:
    if not path.is_file():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("bloqueados", []))


def revoke_blocked(db: Session, blocked: set[str]) -> list[str]:
    """Bloqueio comprovado no player (erro 150) revoga a aprovação, mesmo de linha antiga.

    Aprovações nunca são concedidas aqui; só retiradas, com base em /verificar.html.
    """
    if not blocked:
        return []
    rows = db.scalars(select(KaraokeVersionRow).where(KaraokeVersionRow.approved.is_(True),
                                                      KaraokeVersionRow.youtube_video_id.in_(blocked))).all()
    for row in rows:
        row.approved = False
    db.flush()
    return [row.id for row in rows]

def revoke_unreviewed(
    db: Session,
    audited: dict[str, str],
    blocked: set[str],
) -> list[str]:
    """Desabilita karaokês sem auditoria válida."""

    rows = db.scalars(select(KaraokeVersionRow)).all()
    revoked = []

    for row in rows:
        kind = row.kind or "karaoke"

        # As versões com letra sincronizada não são karaokês.
        if kind != "karaoke":
            continue

        # Não reativar vídeos desabilitados anteriormente.
        if not row.approved:
            continue

        audited_video_id = audited.get(row.id)

        valid_audit = (
            audited_video_id == row.youtube_video_id
            and row.youtube_video_id not in blocked
        )

        if not valid_audit:
            row.approved = False
            revoked.append(row.id)

    db.flush()

    return revoked


def seed_all(db: Session, blocked: set[str] | None = None) -> dict[str, tuple[int, int]]:
    result = {PILOT.name: seed_catalog(db, PILOT, blocked)}
    if EXPANDED.is_file():
        result[EXPANDED.name] = seed_catalog(db, EXPANDED, blocked)
    return result


def main() -> None:
    factory = create_db_session_factory()
    blocked = load_blocked()
    with factory.begin() as db:
        inserted = seed_all(db, blocked)
        revoked = revoke_blocked(db, blocked)
    for name, (songs, videos) in inserted.items():
        print(f"{name}: {songs} músicas novas, {videos} versões novas.")
    if revoked:
        print(f"Aprovação revogada (vídeo bloqueado fora do YouTube): {', '.join(revoked)}")
    print("Atenção: aprovado NÃO garante incorporação atual ou direitos de uso; conferir no site.")


if __name__ == "__main__":
    main()
