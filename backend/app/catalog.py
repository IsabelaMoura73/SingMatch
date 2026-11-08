"""Leitura tipada do catálogo persistido; nada é pesquisado no YouTube durante o roteiro."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KaraokeVersionRow, SongRow
from app.schemas import KaraokeVersion, Song


def get_catalog(db: Session, genre: str | None = None) -> tuple[list[Song], list[KaraokeVersion]]:
    stmt = select(SongRow).order_by(SongRow.id)
    if genre is not None:
        stmt = stmt.where(SongRow.genre == genre)
    rows = db.scalars(stmt).all()
    song_ids = {s.id for s in rows}
    if not song_ids:
        return [], []
    videos = db.scalars(
        select(KaraokeVersionRow)
        .where(KaraokeVersionRow.song_id.in_(song_ids), KaraokeVersionRow.approved.is_(True))
        .order_by(KaraokeVersionRow.id)
    ).all()
    songs = [Song.model_validate({
        "id": row.id, "title": row.title, "artists": row.artists, "genre": row.genre,
        "tags": row.tags or [], "duration_ms": row.duration_ms, "bpm": row.bpm,
        "energy": row.energy, "mood": row.mood, "duet_possible": row.duet_possible,
        "source": row.source, "source_id": row.source_id,
    }) for row in rows]
    versions = [KaraokeVersion.model_validate({
        "id": v.id, "song_id": v.song_id, "youtube_video_id": v.youtube_video_id,
        "duration_seconds": v.duration_seconds, "approved": v.approved,
        "verified_at": v.verified_at, "rights_reviewed": v.rights_reviewed,
        "kind": v.kind or "karaoke", "lyrics_source": v.lyrics_source,
    }) for v in videos]
    return songs, versions


def get_lyrics(db: Session, version_id: str) -> KaraokeVersionRow | None:
    """Letra LRC de uma versão aprovada; None se não existir ou não tiver letra."""
    row = db.get(KaraokeVersionRow, version_id)
    if row is None or not row.approved or not row.lyrics_lrc:
        return None
    return row
