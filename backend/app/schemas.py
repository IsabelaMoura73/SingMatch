"""Contratos Pydantic compartilhados pela API.

ETAPA 2: definir ProfileDraft, ProfileConfirmed, Song,
KaraokeVersion, ScriptItem e Script junto com toda a equipe.
"""
from typing import Literal
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
