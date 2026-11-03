"""Testes rápidos dos contratos: pytest -q backend/tests"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import (
    ApproveScriptRequest,
    CreateSessionResponse,
    KaraokeVersion,
    ProfileDraft,
    ScriptProposal,
    SessionPublic,
    Song,
)


ROOT = Path(__file__).resolve().parents[2]


def test_pilot_catalog_matches_contracts():
    data = json.loads((ROOT / "data" / "catalogo_piloto.json").read_text(encoding="utf-8"))
    songs = [Song.model_validate(s) for s in data["songs"]]
    versions = [KaraokeVersion.model_validate(v) for v in data["karaoke_versions"]]
    assert len(songs) == len(versions) == 5
    song_ids = {s.id for s in songs}
    assert all(v.song_id in song_ids for v in versions)
    assert all(s.genre == "forro" for s in songs)
    assert all(v.approved for v in versions)


def test_veto_requires_evidence():
    with pytest.raises(ValidationError):
        ProfileDraft(vetoes=[{"category": "tag", "value": "romantica", "evidence": ""}])


def test_unknown_duet_permission_is_not_yes():
    profile = ProfileDraft.model_validate({})
    assert profile.duet_allowed is None
    assert profile.preferred_format == "indiferente"


def test_solo_and_duet_are_both_valid_shapes():
    sample = ScriptProposal(title="Noite de forró", items=[
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P1"]},
        {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["P2", "P3"]},
    ])
    assert len(sample.items) == 2


def test_reject_duplicate_participant_across_songs():
    with pytest.raises(ValidationError):
        ScriptProposal(title="Noite", items=[
            {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P1"]},
            {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["P1"]},
        ])


def test_reject_duplicate_song_and_out_of_order_positions():
    with pytest.raises(ValidationError):
        ScriptProposal(title="Noite", items=[
            {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P1"]},
            {"position": 3, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P2"]},
        ])


def test_public_session_does_not_expose_token():
    session = SessionPublic(id="s1", code="ABC123", genre="forro", intention="", status="lobby", revision=0)
    response = CreateSessionResponse(session=session, host_token="secret-host-token")
    assert "host_token" not in response.session.model_dump()
    assert "host_token" in response.model_dump()


def test_approval_needs_version():
    assert ApproveScriptRequest(expected_version=2).expected_version == 2
    with pytest.raises(ValidationError):
        ApproveScriptRequest(expected_version=0)
