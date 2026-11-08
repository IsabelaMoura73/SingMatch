"""Contratos Pydantic v2 do SingMatch (MVP de 7 dias).

Os modelos validam formato e algumas invariantes internas. Regras que exigem
acesso ao banco (IDs existentes, vetos, permissões, revisão atual) pertencem
ao backend/matching.py, NUNCA apenas ao prompt da IA.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HealthResponse(ContractModel):
    status: Literal["ok"]
    service: str


# --- Catálogo ---

class SongTag(ContractModel):
    attribute: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=200)


class Song(ContractModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    artists: list[str] = Field(min_length=1)
    genre: str = Field(min_length=1)
    tags: list[SongTag] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, gt=0)
    bpm: float | None = Field(default=None, gt=0)
    energy: int | None = Field(default=None, ge=1, le=5)
    mood: str | None = None
    duet_possible: bool = False
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


VersionKind = Literal["karaoke", "letra_sincronizada"]


class KaraokeVersion(ContractModel):
    id: str = Field(min_length=1)
    song_id: str = Field(min_length=1)
    youtube_video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    duration_seconds: int | None = Field(default=None, gt=0)
    approved: bool = False
    verified_at: date | None = None
    rights_reviewed: bool = False
    # karaoke = vídeo já traz a letra; letra_sincronizada = vídeo original e o
    # player do SingMatch mostra o LRC (ver GET /api/karaoke_versions/{id}/lyrics).
    kind: VersionKind = "karaoke"
    lyrics_source: str | None = Field(default=None, max_length=200)


class LyricsResponse(ContractModel):
    karaoke_version_id: str
    lrc: str = Field(min_length=1)
    source: str | None = None


# --- Preferências; informação ausente NÃO é inferida ---

PreferenceCategory = Literal["genre", "artist", "song", "tag"]
FormatPreference = Literal["solo", "dueto", "indiferente"]


class PreferenceLabel(ContractModel):
    category: PreferenceCategory
    value: str = Field(min_length=1, max_length=150)
    evidence: str = Field(min_length=1, max_length=500)
    origin: Literal["texto", "correcao_usuario"] = "texto"


class ProfileData(ContractModel):
    likes: list[PreferenceLabel] = Field(default_factory=list)
    vetoes: list[PreferenceLabel] = Field(default_factory=list)
    preferred_format: FormatPreference = "indiferente"
    duet_allowed: bool | None = None  # None = usuário não declarou; nunca assumir sim
    questions: list[str] = Field(default_factory=list)


class ProfileDraft(ProfileData):
    """Resposta da tarefa de interpretação do modelo, sujeita a revisão."""


class ProfileConfirmed(ProfileData):
    """Perfil depois de revisado e enviado explicitamente pelo participante."""


class InterpretRequest(ContractModel):
    text: str = Field(min_length=3, max_length=2000)


class InterpretResponse(ContractModel):
    draft: ProfileDraft


class ConfirmProfileRequest(ContractModel):
    profile: ProfileConfirmed


# --- Sessão; tokens não aparecem em SessionPublic/ParticipantPublic ---

SessionStatus = Literal["lobby", "ready", "playing", "finished"]


class CreateSessionRequest(ContractModel):
    genre: str = Field(min_length=1, max_length=80)
    intention: str = Field(default="", max_length=500)


class SessionPublic(ContractModel):
    id: str
    code: str
    genre: str
    intention: str
    status: SessionStatus
    revision: int = Field(ge=0)


class CreateSessionResponse(ContractModel):
    session: SessionPublic
    host_token: str = Field(min_length=1)


class JoinSessionRequest(ContractModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=80)


class JoinSessionResponse(ContractModel):
    session_id: str
    participant_id: str
    participant_token: str = Field(min_length=1)


class ParticipantPublic(ContractModel):
    id: str
    name: str
    profile_confirmed: bool


# --- Roteiro ---

class ScriptItem(ContractModel):
    position: int = Field(ge=1)
    karaoke_version_id: str = Field(min_length=1)
    participant_ids: list[str] = Field(min_length=1, max_length=2)
    justification: str | None = Field(default=None, max_length=500)
    origin: Literal["ia", "manual"] = "ia"

    @field_validator("participant_ids")
    @classmethod
    def unique_participants_in_item(cls, values: list[str]) -> list[str]:
        if not all(v.strip() for v in values) or len(values) != len(set(values)):
            raise ValueError("participant_ids devem ser distintos e não vazios")
        return values


class ScriptProposal(ContractModel):
    """Saída da tarefa de composição LLM ou edição manual, antes da validação no banco."""
    title: str = Field(min_length=1, max_length=160)
    items: list[ScriptItem] = Field(min_length=1)

    @model_validator(mode="after")
    def no_duplicate_positions_songs_or_participants(self) -> "ScriptProposal":
        positions = [i.position for i in self.items]
        video_ids = [i.karaoke_version_id for i in self.items]
        participants = [p for item in self.items for p in item.participant_ids]
        if len(positions) != len(set(positions)):
            raise ValueError("posições não podem se repetir")
        if sorted(positions) != list(range(1, len(positions) + 1)):
            raise ValueError("posições devem ser consecutivas e começar em 1")
        if len(video_ids) != len(set(video_ids)):
            raise ValueError("não repetir versão de karaokê no roteiro")
        if len(participants) != len(set(participants)):
            raise ValueError("cada participante deve aparecer uma única vez na rodada")
        return self


class ScriptSnapshot(ScriptProposal):
    session_id: str
    version: int = Field(ge=1)
    input_revision: int = Field(ge=0)
    approved: bool = False


class EditScriptRequest(ContractModel):
    expected_version: int = Field(ge=1)
    proposal: ScriptProposal


class ApproveScriptRequest(ContractModel):
    expected_version: int = Field(ge=1)
