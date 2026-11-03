"""Respostas HTTP complementares aos contratos existentes em schemas.py."""
from __future__ import annotations

from pydantic import Field

from app.schemas import (
    ContractModel, KaraokeVersion, ParticipantPublic, ProfileConfirmed,
    ProfileDraft, ScriptSnapshot, SessionPublic, Song,
)


class SessionState(ContractModel):
    session: SessionPublic
    participants: list[ParticipantPublic]
    script: ScriptSnapshot | None = None


class ParticipantPrivate(ContractModel):
    id: str
    name: str
    text: str | None = None
    draft: ProfileDraft | None = None
    confirmed: ProfileConfirmed | None = None


class CatalogResponse(ContractModel):
    songs: list[Song]
    karaoke_versions: list[KaraokeVersion]


class ScriptResponse(ContractModel):
    script: ScriptSnapshot


class DeleteScriptWarning(ContractModel):
    # Campo reservado para extensões de interface, nunca utilizado como autorização.
    detail: str = Field(min_length=1)
