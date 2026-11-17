"""Testes offline; respostas falsas simulam só a API, não medem qualidade do GPT."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.llm import (LLMServiceError, compor_roteiro_misto, compor_roteiro_solo,
                     interpretar_perfil, _ProfileOut, _ScriptOut)
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


def test_matching_prioriza_novidade_em_caso_de_empate(catalog):
    songs, versions = catalog

    profiles = {
        "P1": ProfileConfirmed()
    }

    original = eligible_candidates(
        "forro",
        profiles,
        songs,
        versions,
    )["P1"]

    primeiro_video = original[0]

    novo = eligible_candidates(
        "forro",
        profiles,
        songs,
        versions,
        previous_video_ids=[primeiro_video],
    )["P1"]

    # Um vídeo diferente passa a ser prioridade.
    assert novo[0] != primeiro_video

    # O vídeo antigo continua permitido.
    assert primeiro_video in novo

def test_llm_recebe_historico_do_roteiro(catalog):
    songs, versions = catalog

    fake = FakeClient({
        "title": "Forró renovado",
        "items": [
            {
                "position": 1,
                "karaoke_version_id": "KAR-FOR-002",
                "participant_ids": ["P1"],
                "justification": "Nova escolha para a rodada.",
            }
        ],
    })

    compor_roteiro_solo(
        "forro",
        "",
        {"P1": ProfileConfirmed()},
        songs,
        versions,
        previous_video_ids=["KAR-FOR-001"],
        client=fake,
    )

    enviado = json.loads(fake.requests[0]["input"])

    assert enviado["previous_script_karaoke_version_ids"] == [
        "KAR-FOR-001"
    ]

    assert enviado["participants"]["P1"][
        "allowed_karaoke_version_ids"
    ][0] != "KAR-FOR-001"

def test_llm_envia_pontuacoes_de_afinidade(catalog):
    songs, versions = catalog

    ps = profiles()

    ps["P1"] = ProfileConfirmed(
        likes=[
            {
                "category": "genre",
                "value": "forro",
                "evidence": "gosto de forró",
            },
            {
                "category": "tag",
                "value": "animada",
                "evidence": "músicas animadas",
            },
        ],
        vetoes=[
            {
                "category": "tag",
                "value": "romantica",
                "evidence": "não gosto de românticas",
            },
        ],
    )

    fake = FakeClient({
        "title": "Forró personalizado",
        "items": [
            {
                "position": 1,
                "karaoke_version_id": "KAR-FOR-001",
                "participant_ids": ["P3"],
                "justification": "Preferência por Asa Branca.",
            },
            {
                "position": 2,
                "karaoke_version_id": "KAR-FOR-002",
                "participant_ids": ["P1"],
                "justification": "Música de forró.",
            },
            {
                "position": 3,
                "karaoke_version_id": "KAR-FOR-004",
                "participant_ids": ["P2"],
                "justification": "Música animada.",
            },
        ],
    })

    compor_roteiro_solo(
        "forro",
        "Começar tranquilo e terminar animado",
        ps,
        songs,
        versions,
        client=fake,
    )

    enviado = json.loads(fake.requests[0]["input"])

    p1 = enviado["participants"]["P1"]

    # Música de forró animada atende duas preferências.
    assert p1["affinity_scores"]["KAR-FOR-004"] == 2

    # Asa Branca atende à preferência pelo gênero.
    assert p1["affinity_scores"]["KAR-FOR-001"] == 1

    # O veto a músicas românticas permanece obrigatório.
    assert "KAR-FOR-003" not in p1["allowed_karaoke_version_ids"]

    # Pontuações individuais dos demais participantes.
    assert enviado["participants"]["P2"][
        "affinity_scores"
    ]["KAR-FOR-004"] == 1

    assert enviado["participants"]["P3"][
        "affinity_scores"
    ]["KAR-FOR-001"] == 1

def test_mixed_script_composes_one_duet_and_fallback_solo(catalog):
    songs, versions = catalog
    songs = [song.model_copy(update={"duet_possible": True}) for song in songs]
    ps = {
        "A": ProfileConfirmed(duet_allowed=True),
        "B": ProfileConfirmed(duet_allowed=True),
        "C": ProfileConfirmed(duet_allowed=None),
    }
    fake = FakeClient({"title": "Roteiro misto", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["A", "B"], "justification": "Afinidade."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["C"], "justification": "Solo."},
    ]})
    proposal = compor_roteiro_misto("forro", "", ps, songs, versions, client=fake)
    assert [item.participant_ids for item in proposal.items] == [["A", "B"], ["C"]]
    data = json.loads(fake.requests[0]["input"])
    # O backend já define a dupla e o solo; o modelo só escolhe música e ordem.
    assert [slot["participant_ids"] for slot in data["slots"]] == [["A", "B"], ["C"]]
    assert data["slots"][0]["format"] == "dueto" and data["required_item_count"] == 2


def test_mixed_script_rejects_duet_without_bilateral_consent(catalog):
    songs, versions = catalog
    songs = [song.model_copy(update={"duet_possible": True}) for song in songs]
    ps = {"A": ProfileConfirmed(duet_allowed=True), "B": ProfileConfirmed(duet_allowed=None)}
    fake = FakeClient({"title": "Roteiro inválido", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["A", "B"], "justification": "X."},
    ]})
    # Sem consentimento dos dois não há dupla: a rodada segue o fluxo solo, que recusa o dueto.
    with pytest.raises(LLMServiceError, match="SOLO"):
        compor_roteiro_misto("forro", "", ps, songs, versions, client=fake)


class SequenceClient:
    """Devolve uma resposta diferente a cada chamada (simula reparo do modelo)."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []
        self.responses = SimpleNamespace(parse=self.parse)

    def parse(self, **kwargs):
        self.requests.append(kwargs)
        parsed = kwargs["text_format"].model_validate(self.payloads[len(self.requests) - 1])
        return SimpleNamespace(status="completed", output_parsed=parsed)


REPEATED_PARTICIPANT = {"title": "Forró", "items": [
    {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["P1"], "justification": "Início."},
    {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["P1"], "justification": "De novo."},
]}
ONE_SONG = {"title": "Forró", "items": [
    {"position": 1, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["P1"], "justification": "Uma música."},
]}


def test_roteiro_repara_participante_repetido_com_uma_nova_tentativa(catalog):
    songs, versions = catalog
    fake = SequenceClient(REPEATED_PARTICIPANT, ONE_SONG)
    proposal = compor_roteiro_solo("forro", "", {"P1": ProfileConfirmed()}, songs, versions, client=fake)

    assert [item.participant_ids for item in proposal.items] == [["P1"]]
    assert len(fake.requests) == 2
    primeira = json.loads(fake.requests[0]["input"])
    segunda = json.loads(fake.requests[1]["input"])
    assert primeira["required_item_count"] == 1
    assert primeira["required_participant_ids"] == ["P1"]
    assert "previous_attempt_rejected_because" not in primeira
    # O modelo recebe só o motivo curto, não a resposta anterior inteira.
    assert segunda["previous_attempt_rejected_because"] == "cada participante deve aparecer uma única vez na rodada"


def test_roteiro_desiste_apos_uma_tentativa_de_reparo(catalog):
    songs, versions = catalog
    fake = SequenceClient(REPEATED_PARTICIPANT, REPEATED_PARTICIPANT, ONE_SONG)
    with pytest.raises(LLMServiceError, match="cada participante deve aparecer uma única vez") as error:
        compor_roteiro_solo("forro", "", {"P1": ProfileConfirmed()}, songs, versions, client=fake)
    assert len(fake.requests) == 2
    # A mensagem não despeja a resposta do modelo (input_value) na tela.
    assert "input_value" not in str(error.value)


class ApiErrorClient:
    def __init__(self, status_code):
        self.status_code = status_code
        self.calls = 0
        self.responses = SimpleNamespace(parse=self.parse)

    def parse(self, **kwargs):
        self.calls += 1
        exc = RuntimeError("erro do provedor")
        exc.status_code = self.status_code
        raise exc


@pytest.mark.parametrize("status, trecho", [(401, "não reconheceu a chave"), (402, "falta de créditos"), (429, "Limite de uso")])
def test_roteiro_nao_repete_chamada_em_erro_de_api(catalog, status, trecho):
    songs, versions = catalog
    fake = ApiErrorClient(status)
    with pytest.raises(LLMServiceError, match=trecho):
        compor_roteiro_solo("forro", "", {"P1": ProfileConfirmed()}, songs, versions, client=fake)
    assert fake.calls == 1



def test_roteiro_misto_tambem_tem_tentativa_de_reparo(catalog):
    songs, versions = catalog
    ps = {"A": ProfileConfirmed(duet_allowed=True), "B": ProfileConfirmed(duet_allowed=True)}
    repeated = {"title": "Dupla", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["A", "B"], "justification": "Dueto."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["A"], "justification": "De novo."},
    ]}
    fixed = {"title": "Dupla", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["A", "B"], "justification": "Dueto."},
    ]}
    fake = SequenceClient(repeated, fixed)
    proposal = compor_roteiro_misto("forro", "", ps, songs, versions,
                                    previous_video_ids=["KAR-FOR-005"], client=fake)
    assert [item.participant_ids for item in proposal.items] == [["A", "B"]]
    assert len(fake.requests) == 2
    first = json.loads(fake.requests[0]["input"])
    assert [slot["participant_ids"] for slot in first["slots"]] == [["A", "B"]]
    assert first["previous_script_karaoke_version_ids"] == ["KAR-FOR-005"]
    assert "previous_attempt_rejected_because" in json.loads(fake.requests[1]["input"])



def test_roteiro_misto_recusa_dueto_mais_solo_da_mesma_pessoa(catalog):
    """O erro real: o modelo dava o dueto E solos para quem já estava na dupla."""
    songs, versions = catalog
    songs = [song.model_copy(update={"duet_possible": song.id == "FOR-002"}) for song in songs]
    ps = {"K": ProfileConfirmed(duet_allowed=True), "O": ProfileConfirmed(duet_allowed=True),
          "P": ProfileConfirmed(duet_allowed=False)}
    duet_and_solos = {"title": "Noite", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["K", "O"], "justification": "Dupla."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["K"], "justification": "Solo."},
        {"position": 3, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["P"], "justification": "Solo."},
    ]}
    fixed = {"title": "Noite", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["K", "O"], "justification": "Dupla."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["P"], "justification": "Solo."},
    ]}
    fake = SequenceClient(duet_and_solos, fixed)
    proposal = compor_roteiro_misto("forro", "", ps, songs, versions, client=fake)
    assert [item.participant_ids for item in proposal.items] == [["K", "O"], ["P"]]
    data = json.loads(fake.requests[0]["input"])
    duet_slot = data["slots"][0]
    assert duet_slot["participant_ids"] == ["K", "O"]
    assert duet_slot["allowed_karaoke_version_ids"] == ["KAR-FOR-002"]  # só música de dueto
    assert data["slots"][1]["participant_ids"] == ["P"]


def test_roteiro_misto_recusa_separar_a_dupla_planejada(catalog):
    songs, versions = catalog
    songs = [song.model_copy(update={"duet_possible": True}) for song in songs]
    ps = {"A": ProfileConfirmed(duet_allowed=True), "B": ProfileConfirmed(duet_allowed=True)}
    only_solos = {"title": "Solos", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["A"], "justification": "Solo."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["B"], "justification": "Solo."},
    ]}
    with pytest.raises(LLMServiceError, match="slots"):
        compor_roteiro_misto("forro", "", ps, songs, versions, client=SequenceClient(only_solos, only_solos))


def test_saldo_esgotado_da_openai_tem_mensagem_propria_e_nao_conta_uso():
    from app.llm import _parse

    class NoQuota(Exception):
        status_code, code = 429, "insufficient_quota"

    class Client:
        responses = SimpleNamespace(parse=lambda **kw: (_ for _ in ()).throw(NoQuota()))

    with pytest.raises(LLMServiceError, match="falta de créditos") as error:
        _parse(Client(), "p", {}, _ScriptOut, "m")
    assert error.value.charged is False


def test_perfil_com_evidencia_longa_demais_vira_erro_de_ia(catalog):
    songs, _ = catalog
    text = "Gosto de forró. " + "a" * 600
    fake = FakeClient({"likes": [{"category": "genre", "value": "forro", "evidence": text}],
                       "vetoes": [], "preferred_format": "indiferente", "duet_allowed": None, "questions": []})
    with pytest.raises(LLMServiceError, match="fora do formato"):
        interpretar_perfil(text, songs, client=fake)


def test_roteiro_misto_volta_para_solos_quando_as_duplas_nao_fecham(catalog):
    """A dupla e a pessoa solo só têm a MESMA música: o plano com dueto é impossível."""
    songs, versions = catalog
    versions = [v for v in versions if v.id in {"KAR-FOR-001", "KAR-FOR-002", "KAR-FOR-004"}]
    veto = lambda title: {"category": "song", "value": title, "evidence": title}
    ps = {
        "A": ProfileConfirmed(duet_allowed=True),
        "B": ProfileConfirmed(duet_allowed=True),
        # C só pode cantar "Eu Só Quero um Xodó" (KAR-FOR-002), a única música de dueto.
        "C": ProfileConfirmed(vetoes=[veto("Asa Branca"), veto("O Xote das Meninas")]),
    }
    fake = FakeClient({"title": "Só solos", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["A"], "justification": "Solo."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["B"], "justification": "Solo."},
        {"position": 3, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["C"], "justification": "Solo."},
    ]})
    proposal = compor_roteiro_misto("forro", "", ps, songs, versions, client=fake)
    assert all(len(item.participant_ids) == 1 for item in proposal.items)
    data = json.loads(fake.requests[0]["input"])
    # Sem dueto viável, usa o fluxo solo (com suas regras de afinidade).
    assert "slots" not in data and data["required_participant_ids"] == ["A", "B", "C"]
    assert len(fake.requests) == 1  # nenhuma chamada gasta num plano impossível


def test_roteiro_misto_desfaz_so_a_dupla_que_nao_cabe(catalog):
    """Duas duplas disputam a única música de dueto: fica uma dupla e dois solos."""
    songs, versions = catalog
    songs = [song.model_copy(update={"duet_possible": song.id == "FOR-002"}) for song in songs]
    ps = {pid: ProfileConfirmed(duet_allowed=True) for pid in ("A", "B", "C", "D")}
    fake = FakeClient({"title": "Misto", "items": [
        {"position": 1, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["A", "B"], "justification": "Dueto."},
        {"position": 2, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["C"], "justification": "Solo."},
        {"position": 3, "karaoke_version_id": "KAR-FOR-004", "participant_ids": ["D"], "justification": "Solo."},
    ]})
    compor_roteiro_misto("forro", "", ps, songs, versions, client=fake)
    data = json.loads(fake.requests[0]["input"])
    assert [slot["participant_ids"] for slot in data["slots"]] == [["A", "B"], ["C"], ["D"]]


def test_planejamento_forma_par_por_afinidade_e_deixa_quem_sobra_solo(catalog):
    from app.llm import _plan_mixed_slots
    songs, _ = catalog
    like = lambda v: {"category": "song", "value": v, "evidence": v}
    ps = {
        "A": ProfileConfirmed(duet_allowed=True, likes=[like("Asa Branca")]),
        "B": ProfileConfirmed(duet_allowed=True),
        "C": ProfileConfirmed(duet_allowed=True, likes=[like("Asa Branca")]),
    }
    songs = [song.model_copy(update={"duet_possible": True}) for song in songs]
    options = {frozenset(p): ["X"] for p in (("A", "B"), ("A", "C"), ("B", "C"))}
    assert _plan_mixed_slots(ps, options, songs) == [["A", "C"], ["B"]]
