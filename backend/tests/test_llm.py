"""Testes offline; respostas falsas simulam só a API, não medem qualidade do GPT."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.llm import LLMServiceError, compor_roteiro_solo, interpretar_perfil, _ProfileOut, _ScriptOut
from app.matching import MatchingError, eligible_candidates
from app.schemas import KaraokeVersion, ProfileConfirmed, Song

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def catalog():
    data = json.loads((ROOT / "data" / "catalogo_piloto.json").read_text(encoding="utf-8"))
    return [Song.model_validate(x) for x in data["songs"]], [KaraokeVersion.model_validate(x) for x in data["karaoke_versions"]]


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.responses = SimpleNamespace(parse=self.parse)

    def parse(self, **kwargs):
        self.requests.append(kwargs)
        parsed = kwargs["text_format"].model_validate(self.payload)
        return SimpleNamespace(status="completed", output_parsed=parsed)


def profiles():
    return {
        "P1": ProfileConfirmed(vetoes=[{"category": "tag", "value": "romantica", "evidence": "não gosto de românticas"}]),
        "P2": ProfileConfirmed(likes=[{"category": "tag", "value": "animada", "evidence": "gosto de animadas"}]),
        "P3": ProfileConfirmed(likes=[{"category": "song", "value": "Asa Branca", "evidence": "gosto de Asa Branca"}]),
    }


def test_profile_extracts_veto_with_textual_evidence(catalog):
    songs, _ = catalog
    fake = FakeClient({"likes": [{"category": "genre", "value": "forro", "evidence": "Gosto de forró"}],
                       "vetoes": [{"category": "tag", "value": "romantica", "evidence": "não gosto de românticas"}],
                       "preferred_format": "solo", "duet_allowed": None, "questions": []})
    profile = interpretar_perfil("Gosto de forró, mas não gosto de românticas.", songs, client=fake)
    assert profile.vetoes[0].value == "romantica"
    assert profile.vetoes[0].origin == "texto"
    assert fake.requests[0]["store"] is False


def test_profile_blocks_fabricated_evidence(catalog):
    songs, _ = catalog
    fake = FakeClient({"likes": [], "vetoes": [{"category": "tag", "value": "romantica", "evidence": "odeio forró"}],
                       "preferred_format": "indiferente", "duet_allowed": None, "questions": []})
    with pytest.raises(LLMServiceError, match="evidência"):
        interpretar_perfil("Adoro forró", songs, client=fake)


def test_veto_excludes_romantic_song(catalog):
    songs, versions = catalog
    allowed = eligible_candidates("forro", profiles(), songs, versions)
    assert "KAR-FOR-003" not in allowed["P1"]
    assert "KAR-FOR-003" in allowed["P2"]


def test_script_with_three_unique_solos(catalog):
    songs, versions = catalog
    fake = FakeClient({"title": "Forró em três atos", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P3"], "justification": "Clima tranquilo para abrir."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["P1"], "justification": "Forró festivo."},
        {"position": 3, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["P2"], "justification": "Final animado."},
    ]})
    script = compor_roteiro_solo("forro", "começar calmo, terminar animado", profiles(), songs, versions, client=fake)
    assert len(script.items) == 3
    assert all(len(i.participant_ids) == 1 for i in script.items)
    assert script.items[0].origin == "ia"


def test_script_rejects_hallucinated_id(catalog):
    songs, versions = catalog
    fake = FakeClient({"title": "Roteiro", "items": [
        {"position": 1, "karaoke_version_id": "VIDEO-INVENTADO", "participant_ids": ["P1"], "justification": "X"},
        {"position": 2, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P2"], "justification": "Y"},
        {"position": 3, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["P3"], "justification": "Z"},
    ]})
    with pytest.raises(LLMServiceError, match="não permitido"):
        compor_roteiro_solo("forro", "", profiles(), songs, versions, client=fake)


def test_script_rejects_duet(catalog):
    songs, versions = catalog
    fake = FakeClient({"title": "Roteiro", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P1", "P2"], "justification": "X"},
        {"position": 2, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["P3"], "justification": "Y"},
    ]})
    with pytest.raises(LLMServiceError, match="SOLO"):
        compor_roteiro_solo("forro", "", profiles(), songs, versions, client=fake)


def test_no_candidates_or_not_enough_distinct_videos(catalog):
    songs, versions = catalog
    with pytest.raises(MatchingError, match="Não há vídeos de karaokê aprovados"):
        eligible_candidates("rock", profiles(), songs, versions)
    with pytest.raises(MatchingError, match="Sem solução"):
        eligible_candidates("forro", profiles(), songs, versions[:2])


def test_unknown_tag_veto_blocks_when_no_evidence(catalog):
    songs, versions = catalog
    ps = {"P1": ProfileConfirmed(vetoes=[{"category": "tag", "value": "muito triste", "evidence": "não gosto de triste"}])}
    with pytest.raises(MatchingError, match="nenhuma música elegível"):
        eligible_candidates("forro", ps, songs, versions)
