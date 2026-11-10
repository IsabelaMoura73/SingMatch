"""Fluxo HTTP do MVP: sala, participantes, perfis, roteiro e aprovação.

Autorização por Bearer: organizador edita roteiro; cada participante só edita
seu próprio perfil. Nunca retornar textos e tokens privados na sala pública.
"""
from __future__ import annotations

import secrets
import string
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api_schemas import CatalogResponse, ParticipantPrivate, ScriptResponse, SessionState
from app.catalog import get_catalog, get_lyrics
from app.database import get_db
from app.llm import LLMServiceError, compor_roteiro_solo, interpretar_perfil
from app.matching import MatchingError, eligible_candidates, norm, validate_solo_script
from app.models import ParticipantRow, ScriptRow, SessionRow
from app.schemas import (
    ApproveScriptRequest, ConfirmProfileRequest, CreateSessionRequest,
    CreateSessionResponse, EditScriptRequest, InterpretRequest, InterpretResponse,
    JoinSessionRequest, JoinSessionResponse, LyricsResponse, ParticipantPublic, ProfileConfirmed,
    ProfileDraft, ScriptItem, ScriptProposal, ScriptSnapshot, SessionPublic,
)
from app.security import check_token, hash_token, new_token, read_bearer

router = APIRouter(prefix="/api")
DB = Depends(get_db)
BEARER = Depends(read_bearer)


def not_found(message: str = "Registro não encontrado.") -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def _session(db: Session, session_id: str, lock: bool = False) -> SessionRow:
    stmt = select(SessionRow).where(SessionRow.id == session_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if not row:
        raise not_found("Sala não encontrada.")
    return row


def _participant(db: Session, participant_id: str) -> ParticipantRow:
    p = db.get(ParticipantRow, participant_id)
    if not p:
        raise not_found("Participante não encontrado.")
    return p


def _require_host(session: SessionRow, token: str) -> None:
    if not check_token(token, session.host_token_hash):
        raise HTTPException(status_code=403, detail="Somente o organizador pode executar esta ação.")


def _require_owner(participant: ParticipantRow, token: str) -> None:
    if not check_token(token, participant.token_hash):
        raise HTTPException(status_code=403, detail="Somente o próprio participante pode alterar este perfil.")


def _require_room_access(db: Session, session: SessionRow, token: str) -> None:
    if check_token(token, session.host_token_hash):
        return
    for row in db.scalars(select(ParticipantRow).where(ParticipantRow.session_id == session.id)):
        if check_token(token, row.token_hash):
            return
    raise HTTPException(status_code=403, detail="Token não pertence a esta sala.")


def _public(session: SessionRow) -> SessionPublic:
    return SessionPublic(
        id=session.id, code=session.code, genre=session.genre,
        intention=session.intention, status=session.status, revision=session.revision,
    )


def _current_script(db: Session, session_id: str) -> ScriptRow | None:
    return db.scalar(select(ScriptRow).where(ScriptRow.session_id == session_id)
                     .order_by(ScriptRow.version.desc()).limit(1))


def _snapshot(row: ScriptRow) -> ScriptSnapshot:
    return ScriptSnapshot(session_id=row.session_id, title=row.title,
                          version=row.version, input_revision=row.input_revision,
                          approved=row.approved, items=row.items)


def _invalidate(db: Session, session: SessionRow) -> None:
    """Novo participante ou perfil diferente torna qualquer aprovação obsoleta."""
    db.execute(update(ScriptRow).where(ScriptRow.session_id == session.id)
               .values(approved=False))
    session.revision += 1
    session.status = "lobby"


def _all_profiles(db: Session, session_id: str) -> dict[str, ProfileConfirmed]:
    members = db.scalars(select(ParticipantRow).where(ParticipantRow.session_id == session_id)
                         .order_by(ParticipantRow.id)).all()
    if not members:
        raise conflict("A sala ainda não possui participantes.")
    missing = [p.name for p in members if p.profile_confirmed is None]
    if missing:
        raise conflict("Perfis ainda não confirmados: " + ", ".join(missing))
    return {p.id: ProfileConfirmed.model_validate(p.profile_confirmed) for p in members}


def _valid_solo(proposal: ScriptProposal, profiles: dict[str, ProfileConfirmed],
                genre: str, db: Session) -> None:
    songs, videos = get_catalog(db, genre)
    try:
        allowed = eligible_candidates(genre, profiles, songs, videos)
        validate_solo_script(proposal, profiles, allowed)
    except MatchingError as exc:
        raise conflict(str(exc)) from exc


def _add_script(db: Session, session: SessionRow, proposal: ScriptProposal,
                version: int) -> ScriptRow:
    db.execute(update(ScriptRow).where(ScriptRow.session_id == session.id)
               .values(approved=False))
    row = ScriptRow(id=str(uuid4()), session_id=session.id, version=version,
                    input_revision=session.revision, title=proposal.title,
                    items=[item.model_dump() for item in proposal.items], approved=False)
    db.add(row)
    session.status = "lobby"
    db.commit()
    return row


@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(request: CreateSessionRequest, db: Session = DB):
    if norm(request.genre) != "forro":
        raise HTTPException(status_code=422, detail="Piloto: somente gênero 'forro'.")
    token = new_token()
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(8):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if db.scalar(select(SessionRow.id).where(SessionRow.code == code)) is None:
            break
    else:
        raise HTTPException(status_code=503, detail="Não foi possível gerar um código de sala.")
    row = SessionRow(id=str(uuid4()), code=code, genre="forro",
                     intention=request.intention, status="lobby", revision=0,
                     host_token_hash=hash_token(token))
    db.add(row)
    db.commit()
    return CreateSessionResponse(session=_public(row), host_token=token)


@router.post("/join", response_model=JoinSessionResponse, status_code=status.HTTP_201_CREATED)
def join_session(request: JoinSessionRequest, db: Session = DB):
    code = request.code.strip().upper()
    row = db.scalar(select(SessionRow).where(SessionRow.code == code).with_for_update())
    if not row:
        raise not_found("Código de sala não encontrado.")
    if row.status in {"playing", "finished"}:
        raise conflict("Esta sala não recebe mais participantes.")
    # Comparar sem diferenciar maiúsculas e minúsculas.
    names = [p.name.casefold() for p in db.scalars(select(ParticipantRow)
                         .where(ParticipantRow.session_id == row.id))]
    if request.name.casefold() in names:
        raise conflict("Já existe um participante com esse nome na sala.")
    token = new_token()
    participant = ParticipantRow(id=str(uuid4()), session_id=row.id, name=request.name,
                                 token_hash=hash_token(token))
    db.add(participant)
    _invalidate(db, row)
    db.commit()
    return JoinSessionResponse(session_id=row.id, participant_id=participant.id,
                               participant_token=token)


@router.get("/sessions/{session_id}", response_model=SessionState)
def get_session_state(session_id: str, db: Session = DB, token: str = BEARER):
    row = _session(db, session_id)
    _require_room_access(db, row, token)
    members = db.scalars(select(ParticipantRow).where(ParticipantRow.session_id == row.id)
                         .order_by(ParticipantRow.name)).all()
    script = _current_script(db, row.id)
    return SessionState(session=_public(row),
                        participants=[ParticipantPublic(id=p.id, name=p.name,
                                                       profile_confirmed=p.profile_confirmed is not None)
                                      for p in members],
                        script=_snapshot(script) if script else None)


@router.get("/catalog", response_model=CatalogResponse)
def list_catalog(genre: str = "forro", db: Session = DB):
    songs, versions = get_catalog(db, genre)
    return CatalogResponse(songs=songs, karaoke_versions=versions)


@router.get("/karaoke_versions/{version_id}/lyrics", response_model=LyricsResponse)
def version_lyrics(version_id: str, db: Session = DB):
    """LRC da versão 'letra_sincronizada'; o catálogo não carrega as letras para ficar leve."""
    row = get_lyrics(db, version_id)
    if row is None:
        raise not_found("Esta versão não tem letra sincronizada.")
    return LyricsResponse(karaoke_version_id=row.id, lrc=row.lyrics_lrc, source=row.lyrics_source)


@router.get("/participants/{participant_id}/profile", response_model=ParticipantPrivate)
def get_own_profile(participant_id: str, db: Session = DB, token: str = BEARER):
    participant = _participant(db, participant_id)
    _require_owner(participant, token)
    return ParticipantPrivate(id=participant.id, name=participant.name,
                              text=participant.text,
                              draft=ProfileDraft.model_validate(participant.profile_draft)
                              if participant.profile_draft else None,
                              confirmed=ProfileConfirmed.model_validate(participant.profile_confirmed)
                              if participant.profile_confirmed else None)


@router.post("/participants/{participant_id}/interpret", response_model=InterpretResponse)
def interpret_preferences(participant_id: str, request: InterpretRequest,
                          db: Session = DB, token: str = BEARER):
    participant = _participant(db, participant_id)
    _require_owner(participant, token)
    session_id = participant.session_id
    row = _session(db, session_id)
    original_revision = row.revision
    songs, _ = get_catalog(db, row.genre)
    if not songs:
        raise conflict("Catálogo vazio. Execute a importação antes de interpretar perfis.")
    try:
        draft = interpretar_perfil(request.text, songs)
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # A IA roda SEM lock: não sobrescrever atualização feita enquanto respondia.
    db.expire_all()
    row = _session(db, session_id, lock=True)
    if row.revision != original_revision:
        raise conflict("A sala mudou durante a chamada da IA. Tente novamente.")
    participant = _participant(db, participant_id)
    participant.text = request.text
    participant.profile_draft = draft.model_dump(mode="json")
    participant.profile_confirmed = None
    _invalidate(db, row)
    db.commit()
    return InterpretResponse(draft=draft)


@router.put("/participants/{participant_id}/profile", response_model=ParticipantPrivate)
def confirm_profile(participant_id: str, request: ConfirmProfileRequest,
                    db: Session = DB, token: str = BEARER):
    participant = _participant(db, participant_id)
    _require_owner(participant, token)
    row = _session(db, participant.session_id, lock=True)
    if participant.profile_draft is None:
        raise conflict("Interprete as preferências antes de confirmar o perfil.")
    participant.profile_confirmed = request.profile.model_dump(mode="json")
    _invalidate(db, row)
    db.commit()
    return ParticipantPrivate(id=participant.id, name=participant.name,
                              text=participant.text,
                              draft=ProfileDraft.model_validate(participant.profile_draft),
                              confirmed=request.profile)


@router.post("/sessions/{session_id}/script", response_model=ScriptResponse, status_code=201)
def generate_script(session_id: str, db: Session = DB, token: str = BEARER):
    row = _session(db, session_id)
    _require_host(row, token)
    initial_revision = row.revision
    previous_script = _current_script(db, row.id)

    previous_video_ids = []

    if (
        previous_script is not None
        and previous_script.input_revision == row.revision
    ):
        previous_video_ids = [
            item["karaoke_version_id"]
            for item in previous_script.items
        ]
    profiles = _all_profiles(db, row.id)
    songs, videos = get_catalog(db, row.genre)
    try:
        # Validar antes de gastar tokens.
        eligible_candidates(row.genre, profiles, songs, videos)
    except MatchingError as exc:
        raise conflict(str(exc)) from exc
    try:
        proposal = compor_roteiro_solo(row.genre, row.intention, profiles, songs, videos, previous_video_ids=previous_video_ids,)
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.expire_all()
    row = _session(db, session_id, lock=True)
    if row.revision != initial_revision:
        raise conflict("A sala mudou durante a geração; resposta antiga descartada.")
    # Revalidar na persistência para não confiar no modelo.
    _valid_solo(proposal, profiles, row.genre, db)
    current = _current_script(db, row.id)
    new_row = _add_script(db, row, proposal, 1 if current is None else current.version + 1)
    return ScriptResponse(script=_snapshot(new_row))


def _apply_manual_changes(old: ScriptRow, new: ScriptProposal) -> ScriptProposal:
    """Troca de posição/vídeo/pessoa remove justificativa anterior da IA."""
    before = {tuple(item["participant_ids"]): item for item in old.items}
    corrected: list[ScriptItem] = []
    for item in new.items:
        former = before.get(tuple(item.participant_ids))
        if former is None or (former["position"] != item.position or
                              former["karaoke_version_id"] != item.karaoke_version_id):
            corrected.append(item.model_copy(update={"origin": "manual", "justification": None}))
        else:
            corrected.append(item)
    return ScriptProposal(title=new.title, items=corrected)


@router.put("/sessions/{session_id}/script", response_model=ScriptResponse)
def edit_script(session_id: str, request: EditScriptRequest,
                db: Session = DB, token: str = BEARER):
    row = _session(db, session_id, lock=True)
    _require_host(row, token)
    current = _current_script(db, row.id)
    if current is None:
        raise conflict("Gere um roteiro antes de editar.")
    if current.version != request.expected_version:
        raise conflict("Roteiro alterado em outra tela; atualize a versão.")
    if current.input_revision != row.revision:
        raise conflict("Perfis mudaram; gere um roteiro atualizado.")
    profiles = _all_profiles(db, row.id)
    proposal = _apply_manual_changes(current, request.proposal)
    _valid_solo(proposal, profiles, row.genre, db)
    updated = _add_script(db, row, proposal, current.version + 1)
    return ScriptResponse(script=_snapshot(updated))


@router.post("/sessions/{session_id}/script/approve", response_model=ScriptResponse)
def approve_script(session_id: str, request: ApproveScriptRequest,
                   db: Session = DB, token: str = BEARER):
    row = _session(db, session_id, lock=True)
    _require_host(row, token)
    current = _current_script(db, row.id)
    if current is None:
        raise conflict("Não há roteiro para aprovar.")
    if current.version != request.expected_version:
        raise conflict("Esta versão não é a mais recente; atualize antes de aprovar.")
    if current.input_revision != row.revision:
        raise conflict("O perfil da sala mudou; o roteiro precisa ser atualizado.")
    profiles = _all_profiles(db, row.id)
    proposal = ScriptProposal(title=current.title, items=current.items)
    _valid_solo(proposal, profiles, row.genre, db)
    current.approved = True
    row.status = "ready"
    db.commit()
    return ScriptResponse(script=_snapshot(current))
