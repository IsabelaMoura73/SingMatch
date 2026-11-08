"""Tabelas SQLAlchemy do MVP: nomes/contratos estáveis, JSONB no PostgreSQL."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB em produção, JSON padrão no SQLite dos testes automatizados.
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class SongRow(Base):
    __tablename__ = "songs"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_song_source_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    artists: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False)
    genre: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tags: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    bpm: Mapped[float | None] = mapped_column(Float)
    energy: Mapped[int | None] = mapped_column(Integer)
    mood: Mapped[str | None] = mapped_column(String(100))
    duet_possible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)


class KaraokeVersionRow(Base):
    __tablename__ = "karaoke_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    song_id: Mapped[str] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True)
    youtube_video_id: Mapped[str] = mapped_column(String(11), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[date | None] = mapped_column(Date)
    rights_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "karaoke": vídeo com letra embutida. "letra_sincronizada": vídeo original +
    # LRC exibido pelo player do SingMatch (migração 0002).
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="karaoke",
                                      server_default="karaoke")
    lyrics_lrc: Mapped[str | None] = mapped_column(Text)
    lyrics_source: Mapped[str | None] = mapped_column(String(200))


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    genre: Mapped[str] = mapped_column(String(80), nullable=False)
    intention: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="lobby")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    host_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ParticipantRow(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("session_id", "name", name="uq_participant_name_per_session"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    profile_draft: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    profile_confirmed: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ScriptRow(Base):
    __tablename__ = "scripts"
    __table_args__ = (UniqueConstraint("session_id", "version", name="uq_script_session_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    items: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
