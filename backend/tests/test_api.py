"""Integração HTTP offline com SQLite; NENHUMA chamada real à OpenAI."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app import routes
from app.models import Base, ParticipantRow, ScriptRow, SessionRow
from app.schemas import ProfileDraft, ScriptItem, ScriptProposal
from scripts.import_catalog import seed_catalog


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        count = seed_catalog(db)
        assert count == (5, 5)
        assert seed_catalog(db) == (0, 0)  # importação idempotente
        db.commit()

    def override():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = override

    def fake_profile(text, songs):
        return ProfileDraft(likes=[{"category": "genre", "value": "forro",
                                    "evidence": "Gosto de forró"}])

    def fake_script(
        genre,
        intention,
        profiles,
        songs,
        versions,
        *,
        previous_video_ids=(),
    ):
        ids = list(profiles)
        return ScriptProposal(title="Forró progressivo", items=[
            ScriptItem(position=i+1, karaoke_version_id=vid, participant_ids=[pid],
                       justification="Escolha de teste", origin="ia")
            for i, (pid, vid) in enumerate(zip(ids, ["KAR-FOR-001", "KAR-FOR-002", "KAR-FOR-004"]))
        ])

    monkeypatch.setattr(routes, "interpretar_perfil", fake_profile)
    # A rota escolhe solo ou misto conforme haja dupla possível; os dois ficam simulados.
    monkeypatch.setattr(routes, "compor_roteiro_solo", fake_script)
    monkeypatch.setattr(routes, "compor_roteiro_misto", fake_script)
    with TestClient(app) as api:
        yield api, engine
    app.dependency_overrides.clear()
    engine.dispose()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def start_room(api):
    resp = api.post("/api/sessions", json={"genre": "forró",
                                           "intention": "começa tranquilo, termina animado"})
    assert resp.status_code == 201, resp.text
    obj = resp.json()
    return obj["session"], obj["host_token"]


def join(api, code, name):
    r = api.post("/api/join", json={"code": code, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def confirm(api, participant_id, token, veto=False, duet_allowed=False):
    response = api.post(f"/api/participants/{participant_id}/interpret",
                        json={"text": "Gosto de forró e prefiro músicas animadas"}, headers=auth(token))
    assert response.status_code == 200, response.text
    labels = [{"category": "tag", "value": "romantica", "evidence": "não gosto de românticas"}]
    response = api.put(f"/api/participants/{participant_id}/profile",
                       json={"profile": {"likes": [], "vetoes": labels if veto else [],
                                         "preferred_format": "solo", "duet_allowed": duet_allowed,
                                         "questions": []}}, headers=auth(token))
    assert response.status_code == 200, response.text


def ready_room(api):
    s, host = start_room(api)
    members = [join(api, s["code"], n) for n in ("Ana", "Beto", "Cris")]
    for i, member in enumerate(members):
        confirm(api, member["participant_id"], member["participant_token"], veto=(i == 0))
    return s, host, members


def test_health_and_catalog(client):
    api, engine = client
    assert api.get("/api/health").json()["status"] == "ok"
    cat = api.get("/api/catalog").json()
    assert len(cat["songs"]) == len(cat["karaoke_versions"]) == 5
    assert "host_token_hash" not in api.post("/api/sessions", json={"genre": "forro"}).text
    assert api.post("/api/sessions", json={"genre": "samba"}).status_code == 422


def test_room_join_refresh_and_no_private_data(client):
    api, _ = client
    room, host = start_room(api)
    person = join(api, room["code"].lower(), "Ana")
    assert api.post("/api/join", json={"code": room["code"], "name": "ana"}).status_code == 409
    assert api.get(f"/api/sessions/{room['id']}").status_code == 401
    assert api.get(f"/api/sessions/{room['id']}", headers=auth("invalid")).status_code == 403
    state = api.get(f"/api/sessions/{room['id']}", headers=auth(host))
    assert state.status_code == 200
    assert state.json()["session"]["revision"] == 1
    assert state.json()["participants"][0]["profile_confirmed"] is False
    assert "token_hash" not in state.text and "profile_draft" not in state.text
    assert api.get(f"/api/sessions/{room['id']}",
                   headers=auth(person["participant_token"])).status_code == 200


def test_participant_cannot_change_another_person_or_generate(client):
    api, _ = client
    room, host = start_room(api)
    a = join(api, room["code"], "Ana")
    b = join(api, room["code"], "Beto")
    path = f"/api/participants/{b['participant_id']}/interpret"
    assert api.post(path, json={"text": "Gosto de forró"},
                    headers=auth(a["participant_token"])).status_code == 403
    assert api.get(f"/api/participants/{b['participant_id']}/profile",
                   headers=auth(a["participant_token"])).status_code == 403
    assert api.post(f"/api/sessions/{room['id']}/script",
                    headers=auth(a["participant_token"])).status_code == 403
    assert api.post(f"/api/sessions/{room['id']}/script",
                    headers=auth(host)).status_code == 409  # perfis não confirmados


def test_full_solo_flow_edit_and_approve(client):
    api, engine = client
    room, host, people = ready_room(api)
    state = api.get(f"/api/sessions/{room['id']}", headers=auth(host)).json()
    assert state["session"]["revision"] == 9  # 3 joins, 3 interpretações, 3 confirmações
    assert all(p["profile_confirmed"] for p in state["participants"])
    path = f"/api/sessions/{room['id']}/script"
    generated = api.post(path, headers=auth(host))
    assert generated.status_code == 201, generated.text
    first = generated.json()["script"]
    assert first["approved"] is False and first["version"] == 1
    assert len(first["items"]) == 3
    assert api.post(f"{path}/approve", json={"expected_version": 1},
                    headers=auth(people[0]["participant_token"])).status_code == 403
    assert api.put(path, json={"expected_version": 55, "proposal": {
        "title": first["title"], "items": first["items"]}}, headers=auth(host)).status_code == 409
    edited = first["items"].copy()
    edited[0] = dict(edited[0], karaoke_version_id="KAR-FOR-005")
    changed = api.put(path, json={"expected_version": 1,
                                  "proposal": {"title": "Forró editado", "items": edited}},
                      headers=auth(host))
    assert changed.status_code == 200, changed.text
    next_script = changed.json()["script"]
    assert next_script["version"] == 2 and next_script["items"][0]["origin"] == "manual"
    assert next_script["items"][0]["justification"] is None
    assert api.post(f"{path}/approve", json={"expected_version": 1},
                    headers=auth(host)).status_code == 409
    approved = api.post(f"{path}/approve", json={"expected_version": 2}, headers=auth(host))
    assert approved.status_code == 200, approved.text
    assert approved.json()["script"]["approved"] is True
    with Session(engine) as db:
        rows = db.scalars(select(ScriptRow).where(ScriptRow.session_id == room["id"])
                          .order_by(ScriptRow.version)).all()
        assert len(rows) == 2
        assert rows[0].approved is False
        assert rows[1].approved is True


def test_confirmed_profile_changes_invalidate_approval(client):
    api, _ = client
    room, host, members = ready_room(api)
    path = f"/api/sessions/{room['id']}/script"
    assert api.post(path, headers=auth(host)).status_code == 201
    assert api.post(f"{path}/approve", json={"expected_version": 1},
                    headers=auth(host)).status_code == 200
    me = members[0]
    assert api.put(f"/api/participants/{me['participant_id']}/profile",
                   json={"profile": {"likes": [], "vetoes": [], "preferred_format": "solo",
                                     "duet_allowed": False, "questions": []}},
                   headers=auth(me["participant_token"])).status_code == 200
    state = api.get(f"/api/sessions/{room['id']}", headers=auth(host)).json()
    assert state["script"]["approved"] is False
    assert state["script"]["input_revision"] < state["session"]["revision"]
    assert api.post(f"{path}/approve", json={"expected_version": 1},
                    headers=auth(host)).status_code == 409
    assert api.post(path, headers=auth(host)).json()["script"]["version"] == 2


def test_manual_edit_rejects_nonexistent_video_and_duet(client):
    api, _ = client
    room, host, members = ready_room(api)
    path = f"/api/sessions/{room['id']}/script"
    first = api.post(path, headers=auth(host)).json()["script"]
    items = first["items"].copy()
    items[0] = dict(items[0], karaoke_version_id="KAR-INVENTADO")
    r = api.put(path, json={"expected_version": 1,
                            "proposal": {"title": first["title"], "items": items}}, headers=auth(host))
    assert r.status_code == 409
    items = first["items"].copy()
    items[0] = dict(items[0], participant_ids=[members[0]["participant_id"], members[1]["participant_id"]])
    r = api.put(path, json={"expected_version": 1,
                            "proposal": {"title": first["title"], "items": items}}, headers=auth(host))
    assert r.status_code in {409, 422}


def test_host_removes_participant_and_invalidates_script(client):
    api, _ = client
    s, host, (ana, beto, cris) = ready_room(api)
    script = api.post(f"/api/sessions/{s['id']}/script", headers=auth(host)).json()["script"]
    assert api.post(f"/api/sessions/{s['id']}/script/approve", json={"expected_version": script["version"]},
                    headers=auth(host)).status_code == 200
    url = f"/api/sessions/{s['id']}/participants/{beto['participant_id']}"

    # Somente o organizador remove; participante (nem o próprio) não consegue.
    assert api.delete(url).status_code == 401
    assert api.delete(url, headers=auth(ana["participant_token"])).status_code == 403
    assert api.delete(url, headers=auth(beto["participant_token"])).status_code == 403

    removed = api.delete(url, headers=auth(host))
    assert removed.status_code == 200, removed.text
    state = removed.json()
    assert [p["name"] for p in state["participants"]] == ["Ana", "Cris"]
    assert state["script"]["approved"] is False
    assert state["script"]["input_revision"] != state["session"]["revision"]
    assert state["session"]["status"] == "lobby"

    # O token removido perde acesso à sala e ao próprio perfil.
    assert api.get(f"/api/sessions/{s['id']}", headers=auth(beto["participant_token"])).status_code == 403
    assert api.get(f"/api/participants/{beto['participant_id']}/profile",
                   headers=auth(beto["participant_token"])).status_code == 404
    assert api.delete(url, headers=auth(host)).status_code == 404

    # Com quem sobrou, o organizador gera e aprova um novo roteiro.
    new = api.post(f"/api/sessions/{s['id']}/script", headers=auth(host))
    assert new.status_code == 201, new.text
    assert {pid for item in new.json()["script"]["items"] for pid in item["participant_ids"]} == {
        ana["participant_id"], cris["participant_id"]}
    # O nome volta a ficar livre.
    join(api, s["code"], "Beto")


def test_host_cannot_remove_participant_from_another_room(client):
    api, _ = client
    room_a, host_a = start_room(api)
    room_b, _ = start_room(api)
    other = join(api, room_b["code"], "Dani")
    url = f"/api/sessions/{room_a['id']}/participants/{other['participant_id']}"
    assert api.delete(url, headers=auth(host_a)).status_code == 404
    assert api.delete(f"/api/sessions/{room_b['id']}/participants/{other['participant_id']}",
                      headers=auth(host_a)).status_code == 403


# ---------------------------------------------------------------- duetos

def duet_room(api, consent):
    """Sala com Ana, Beto e Cris; consent[i] é o duet_allowed de cada um."""
    s, host = start_room(api)
    members = [join(api, s["code"], n) for n in ("Ana", "Beto", "Cris")]
    for member, allowed in zip(members, consent):
        confirm(api, member["participant_id"], member["participant_token"], duet_allowed=allowed)
    return s, host, members


def fake_mixed_script(genre, intention, profiles, songs, versions, *, previous_video_ids=()):
    # A API ordena os perfis pelo id; a dupla é quem consentiu, o solo é o restante.
    a, b = [pid for pid, p in profiles.items() if p.duet_allowed is True]
    (c,) = [pid for pid in profiles if pid not in (a, b)]
    return ScriptProposal(title="Forró em dupla", items=[
        ScriptItem(position=1, karaoke_version_id="KAR-FOR-002", participant_ids=[a, b],
                   justification="Dueto de teste", origin="ia"),
        ScriptItem(position=2, karaoke_version_id="KAR-FOR-001", participant_ids=[c],
                   justification="Solo de teste", origin="ia"),
    ])


def test_gera_roteiro_misto_quando_ha_dupla_com_consentimento(client, monkeypatch):
    api, _ = client
    monkeypatch.setattr(routes, "compor_roteiro_misto", fake_mixed_script)
    monkeypatch.setattr(routes, "compor_roteiro_solo",
                        lambda *a, **k: pytest.fail("não deveria usar o roteiro só de solos"))
    room, host, members = duet_room(api, (True, True, False))
    path = f"/api/sessions/{room['id']}/script"
    generated = api.post(path, headers=auth(host))
    assert generated.status_code == 201, generated.text
    items = generated.json()["script"]["items"]
    assert [len(item["participant_ids"]) for item in items] == [2, 1]

    # Trocar a música do dueto por outra que admite dueto: aceito.
    edited = [dict(items[0], karaoke_version_id="KAR-FOR-005"), items[1]]
    ok = api.put(path, json={"expected_version": 1, "proposal": {"title": "Editado", "items": edited}},
                 headers=auth(host))
    assert ok.status_code == 200, ok.text
    # Música que não admite dueto: recusada pelo servidor.
    edited = [dict(items[0], karaoke_version_id="KAR-FOR-004"), items[1]]
    bad = api.put(path, json={"expected_version": 2, "proposal": {"title": "Editado", "items": edited}},
                  headers=auth(host))
    assert bad.status_code == 409
    assert "dueto" in bad.json()["detail"]
    assert api.post(f"{path}/approve", json={"expected_version": 2}, headers=auth(host)).status_code == 200


def test_sem_dupla_possivel_continua_so_com_solos(client, monkeypatch):
    api, _ = client
    monkeypatch.setattr(routes, "compor_roteiro_misto",
                        lambda *a, **k: pytest.fail("não deveria usar o roteiro misto"))
    room, host, _ = duet_room(api, (True, False, None))
    generated = api.post(f"/api/sessions/{room['id']}/script", headers=auth(host))
    assert generated.status_code == 201, generated.text
    assert all(len(item["participant_ids"]) == 1 for item in generated.json()["script"]["items"])


def test_edicao_recusa_dueto_sem_consentimento_dos_dois(client):
    api, _ = client
    room, host, members = duet_room(api, (True, False, False))
    path = f"/api/sessions/{room['id']}/script"
    first = api.post(path, headers=auth(host)).json()["script"]
    a, b = members[0]["participant_id"], members[1]["participant_id"]
    c_item = next(i for i in first["items"] if members[2]["participant_id"] in i["participant_ids"])
    # Música de dueto diferente da do solo da Cris (o fake distribui as músicas pela
    # ordem aleatória dos ids); senão o servidor recusaria por vídeo repetido, não por consentimento.
    duet_video = next(v for v in ("KAR-FOR-002", "KAR-FOR-005") if v != c_item["karaoke_version_id"])
    items = [{"position": 1, "karaoke_version_id": duet_video, "participant_ids": [a, b],
              "justification": None, "origin": "manual"}, dict(c_item, position=2)]
    r = api.put(path, json={"expected_version": 1, "proposal": {"title": "Dupla", "items": items}},
                headers=auth(host))
    assert r.status_code == 409
    assert "consentimento" in r.json()["detail"]


def test_nome_ignora_espacos_extras_e_recusa_nome_vazio(client):
    api, _ = client
    room, host = start_room(api)
    join(api, room["code"], "  Ana   Maria ")
    state = api.get(f"/api/sessions/{room['id']}", headers=auth(host)).json()
    assert [p["name"] for p in state["participants"]] == ["Ana Maria"]
    assert api.post("/api/join", json={"code": room["code"], "name": "ana maria"}).status_code == 409
    assert api.post("/api/join", json={"code": room["code"], "name": "   "}).status_code == 422


# ------------------------------------------------- noite em andamento e limites

@pytest.fixture
def limites_zerados():
    from app.limits import interpret_limit, script_limit
    interpret_limit.reset(); script_limit.reset()
    yield
    interpret_limit.reset(); script_limit.reset()


def test_abrir_player_fecha_a_sala_e_reabrir_aceita_entradas(client):
    api, _ = client
    room, host, members = ready_room(api)
    base = f"/api/sessions/{room['id']}"
    assert api.post(f"{base}/start", headers=auth(host)).status_code == 409  # sem roteiro aprovado
    api.post(f"{base}/script", headers=auth(host))
    assert api.post(f"{base}/start", headers=auth(members[0]["participant_token"])).status_code == 403
    assert api.post(f"{base}/script/approve", json={"expected_version": 1}, headers=auth(host)).status_code == 200

    started = api.post(f"{base}/start", headers=auth(host))
    assert started.status_code == 200 and started.json()["session"]["status"] == "playing"
    late = api.post("/api/join", json={"code": room["code"], "name": "Duda"})
    assert late.status_code == 409 and "reabrir" in late.json()["detail"]
    me = members[1]
    assert api.post(f"/api/participants/{me['participant_id']}/interpret", json={"text": "Mudei de ideia"},
                    headers=auth(me["participant_token"])).status_code == 409
    assert api.put(f"/api/participants/{me['participant_id']}/profile",
                   json={"profile": {"likes": [], "vetoes": [], "preferred_format": "solo",
                                     "duet_allowed": False, "questions": []}},
                   headers=auth(me["participant_token"])).status_code == 409
    assert api.delete(f"{base}/participants/{me['participant_id']}", headers=auth(host)).status_code == 409
    state = api.get(base, headers=auth(host)).json()
    assert state["script"]["approved"] is True  # a noite seguiu intacta

    reopened = api.post(f"{base}/reopen", headers=auth(host))
    assert reopened.status_code == 200 and reopened.json()["session"]["status"] == "ready"
    assert api.post("/api/join", json={"code": room["code"], "name": "Duda"}).status_code == 201


def test_roteiro_nao_muda_com_o_player_aberto(client):
    api, _ = client
    room, host, _ = ready_room(api)
    base = f"/api/sessions/{room['id']}"
    script = api.post(f"{base}/script", headers=auth(host)).json()["script"]
    assert api.post(f"{base}/script/approve", json={"expected_version": 1}, headers=auth(host)).status_code == 200
    assert api.post(f"{base}/start", headers=auth(host)).status_code == 200

    assert api.post(f"{base}/script", headers=auth(host)).status_code == 409
    proposal = {"title": script["title"], "items": script["items"]}
    assert api.put(f"{base}/script", json={"expected_version": 1, "proposal": proposal},
                   headers=auth(host)).status_code == 409
    assert api.post(f"{base}/script/approve", json={"expected_version": 1},
                    headers=auth(host)).status_code == 409
    state = api.get(base, headers=auth(host)).json()
    assert state["session"]["status"] == "playing" and state["script"]["approved"] is True


def test_interpretacao_em_andamento_nao_reabre_sala_que_comecou(client, monkeypatch):
    """O organizador abre o player enquanto a IA interpreta o texto de alguém."""
    api, _ = client
    room, host, members = ready_room(api)
    base = f"/api/sessions/{room['id']}"
    api.post(f"{base}/script", headers=auth(host))
    api.post(f"{base}/script/approve", json={"expected_version": 1}, headers=auth(host))

    def profile_while_host_starts(text, songs):
        assert api.post(f"{base}/start", headers=auth(host)).status_code == 200
        return ProfileDraft()

    monkeypatch.setattr(routes, "interpretar_perfil", profile_while_host_starts)
    me = members[1]
    late = api.post(f"/api/participants/{me['participant_id']}/interpret", json={"text": "Mudei de ideia"},
                    headers=auth(me["participant_token"]))
    assert late.status_code == 409
    state = api.get(base, headers=auth(host)).json()
    assert state["session"]["status"] == "playing" and state["script"]["approved"] is True


@pytest.mark.parametrize("charged, segunda_tentativa", [(False, 200), (True, 429)])
def test_limite_so_devolve_uso_quando_a_ia_nao_respondeu(client, monkeypatch, limites_zerados,
                                                        charged, segunda_tentativa):
    """Erro de rede/chave não gasta o limite; resposta do modelo recusada (já cobrada) gasta."""
    from app.llm import LLMServiceError
    api, _ = client
    monkeypatch.setenv("SINGMATCH_MAX_INTERPRETACOES_HORA", "1")
    room, _ = start_room(api)
    me = join(api, room["code"], "Ana")
    url = f"/api/participants/{me['participant_id']}/interpret"

    def broken(text, songs):
        raise LLMServiceError("Falha de teste.", charged=charged)

    with monkeypatch.context() as patch:
        patch.setattr(routes, "interpretar_perfil", broken)
        assert api.post(url, json={"text": "Gosto de forró"}, headers=auth(me["participant_token"])).status_code == 502
    again = api.post(url, json={"text": "Gosto de forró"}, headers=auth(me["participant_token"]))
    assert again.status_code == segunda_tentativa


def test_limite_esquece_chaves_sem_uso_recente():
    from app.limits import HourlyLimit
    limit = HourlyLimit("SINGMATCH_TESTE_INEXISTENTE", 2, "Limite.")
    limit.hit("sala-antiga", now=0)
    limit.hit("sala-nova", now=3600)
    assert set(limit._hits) == {"sala-nova"}
    limit.refund("sala-nova")
    assert limit._hits == {}


def test_limite_informa_minutos_restantes_sem_somar_um_a_mais():
    from fastapi import HTTPException
    from app.limits import HourlyLimit
    limit = HourlyLimit("SINGMATCH_TESTE_INEXISTENTE", 1, "Limite.")
    limit.hit("x", now=0)
    with pytest.raises(HTTPException) as error:
        limit.hit("x", now=3600 - 120)  # faltam exatamente 120 s
    assert "2 min" in error.value.detail


def test_limite_de_interpretacoes_por_hora(client, monkeypatch, limites_zerados):
    api, _ = client
    monkeypatch.setenv("SINGMATCH_MAX_INTERPRETACOES_HORA", "2")
    room, _ = start_room(api)
    me = join(api, room["code"], "Ana")
    url = f"/api/participants/{me['participant_id']}/interpret"
    for _ in range(2):
        assert api.post(url, json={"text": "Gosto de forró"}, headers=auth(me["participant_token"])).status_code == 200
    blocked = api.post(url, json={"text": "Gosto de forró"}, headers=auth(me["participant_token"]))
    assert blocked.status_code == 429 and "Tente de novo em" in blocked.json()["detail"]
    other = join(api, room["code"], "Beto")  # o limite é por participante
    assert api.post(f"/api/participants/{other['participant_id']}/interpret", json={"text": "Gosto de forró"},
                    headers=auth(other["participant_token"])).status_code == 200


def test_limite_de_roteiros_por_hora(client, monkeypatch, limites_zerados):
    api, _ = client
    monkeypatch.setenv("SINGMATCH_MAX_ROTEIROS_HORA", "2")
    room, host, _ = ready_room(api)
    path = f"/api/sessions/{room['id']}/script"
    assert [api.post(path, headers=auth(host)).status_code for _ in range(3)] == [201, 201, 429]


def test_perfil_tem_tamanho_maximo(client):
    api, _ = client
    room, _ = start_room(api)
    me = join(api, room["code"], "Ana")
    headers = auth(me["participant_token"])
    url = f"/api/participants/{me['participant_id']}"
    assert api.post(f"{url}/interpret", json={"text": "Gosto de forró"}, headers=headers).status_code == 200
    label = lambda i: {"category": "artist", "value": f"Artista {i}", "evidence": "teste"}
    too_many = {"likes": [label(i) for i in range(21)], "vetoes": [], "preferred_format": "solo",
                "duet_allowed": None, "questions": []}
    assert api.put(f"{url}/profile", json={"profile": too_many}, headers=headers).status_code == 422
    ok = dict(too_many, likes=[label(i) for i in range(20)], questions=[f"Dúvida {i}" for i in range(15)])
    saved = api.put(f"{url}/profile", json={"profile": ok}, headers=headers)
    assert saved.status_code == 200
    assert len(saved.json()["confirmed"]["questions"]) == 10


def test_janela_do_limite_libera_depois_de_uma_hora():
    from fastapi import HTTPException
    from app.limits import HourlyLimit
    limit = HourlyLimit("SINGMATCH_TESTE_INEXISTENTE", 2, "Limite.")
    limit.hit("x", now=0); limit.hit("x", now=10)
    with pytest.raises(HTTPException) as error:
        limit.hit("x", now=20)
    assert error.value.status_code == 429
    limit.hit("x", now=3600)  # o primeiro uso saiu da janela


def test_interpretacao_nao_falha_quando_outra_pessoa_entra(
    client, monkeypatch
):
    api, _ = client

    room, host = start_room(api)
    ana = join(api, room["code"], "Ana")

    def interpretar_enquanto_outra_pessoa_entra(text, songs):
        # Simula alguém entrando enquanto a OpenAI processa.
        join(api, room["code"], "Bruno")
        return ProfileDraft()

    monkeypatch.setattr(
        routes,
        "interpretar_perfil",
        interpretar_enquanto_outra_pessoa_entra,
    )

    response = api.post(
        f"/api/participants/{ana['participant_id']}/interpret",
        json={"text": "Gosto de forró"},
        headers=auth(ana["participant_token"]),
    )

    assert response.status_code == 200, response.text

    profile = api.get(
        f"/api/participants/{ana['participant_id']}/profile",
        headers=auth(ana["participant_token"]),
    )

    assert profile.status_code == 200
    assert profile.json()["text"] == "Gosto de forró"
    assert profile.json()["draft"] is not None

    state = api.get(
        f"/api/sessions/{room['id']}",
        headers=auth(host),
    )

    assert state.status_code == 200
    assert len(state.json()["participants"]) == 2


def test_roteiro_reserva_quando_ia_falha(client, monkeypatch):
    api, _ = client

    # Sala com três participantes, incluindo pessoas que aceitam dueto.
    room, host, members = duet_room(api, (True, True, False))

    def falha_recuperavel(*args, **kwargs):
        raise routes.LLMServiceError(
            "A IA atingiu o limite de tokens.",
            recoverable=True,
        )

    monkeypatch.setattr(
        routes, "compor_roteiro_solo", falha_recuperavel
    )
    monkeypatch.setattr(
        routes, "compor_roteiro_misto", falha_recuperavel
    )

    response = api.post(
        f"/api/sessions/{room['id']}/script",
        headers=auth(host),
    )

    assert response.status_code == 201, response.text

    script = response.json()["script"]
    items = script["items"]

    assert script["approved"] is False
    assert len(items) == len(members)
    assert all(item["origin"] == "automatico" for item in items)
    assert all(len(item["participant_ids"]) == 1 for item in items)

    # Cada pessoa aparece uma vez.
    actual = [
        pid for item in items
        for pid in item["participant_ids"]
    ]

    expected = [m["participant_id"] for m in members]

    assert set(actual) == set(expected)
    assert len(actual) == len(set(actual))

    # As músicas não se repetem dentro do roteiro.
    videos = [item["karaoke_version_id"] for item in items]
    assert len(videos) == len(set(videos))

    # Mesmo o roteiro automático exige aprovação explícita.
    approved = api.post(
        f"/api/sessions/{room['id']}/script/approve",
        json={"expected_version": script["version"]},
        headers=auth(host),
    )

    assert approved.status_code == 200, approved.text


def test_roteiro_nao_esconde_erro_de_credenciais(
    client, monkeypatch
):
    api, _ = client
    room, host, members = ready_room(api)

    def erro_de_credenciais(*args, **kwargs):
        raise routes.LLMServiceError(
            "Chave da OpenAI inválida.",
            charged=False,
        )

    monkeypatch.setattr(
        routes, "compor_roteiro_solo", erro_de_credenciais
    )

    response = api.post(
        f"/api/sessions/{room['id']}/script",
        headers=auth(host),
    )

    assert response.status_code == 502
    assert "Chave da OpenAI inválida" in response.json()["detail"]


def test_12_participantes_com_roteiro_reserva(client, monkeypatch):
    from scripts.import_catalog import EXPANDED

    api, engine = client

    # O fixture já carrega as 5 músicas do piloto.
    # Adicionar o catálogo ampliado neste teste.
    with Session(engine) as db:
        seed_catalog(db, path=EXPANDED)
        db.commit()

    room, host = start_room(api)

    # Criar e confirmar 12 participantes.
    members = [
        join(api, room["code"], f"Pessoa {i:02d}")
        for i in range(1, 13)
    ]

    for i, member in enumerate(members):
        confirm(
            api,
            member["participant_id"],
            member["participant_token"],
            duet_allowed=(i % 2 == 0),
        )

    # Simular a IA falhando por resposta incompleta.
    def falha_da_ia(*args, **kwargs):
        raise routes.LLMServiceError(
            "A IA atingiu o limite de tokens.",
            recoverable=True,
        )

    monkeypatch.setattr(
        routes, "compor_roteiro_solo", falha_da_ia
    )
    monkeypatch.setattr(
        routes, "compor_roteiro_misto", falha_da_ia
    )

    response = api.post(
        f"/api/sessions/{room['id']}/script",
        headers=auth(host),
    )

    assert response.status_code == 201, response.text

    script = response.json()["script"]
    items = script["items"]

    # O fallback deve atender as 12 pessoas.
    assert len(items) == 12
    assert all(item["origin"] == "automatico" for item in items)
    assert all(len(item["participant_ids"]) == 1 for item in items)

    participant_ids = [
        pid
        for item in items
        for pid in item["participant_ids"]
    ]
    video_ids = [
        item["karaoke_version_id"]
        for item in items
    ]

    assert len(set(participant_ids)) == 12
    assert set(participant_ids) == {
        member["participant_id"] for member in members
    }
    assert len(set(video_ids)) == 12

    # O organizador ainda precisa aprovar o roteiro.
    approved = api.post(
        f"/api/sessions/{room['id']}/script/approve",
        json={"expected_version": script["version"]},
        headers=auth(host),
    )
    assert approved.status_code == 200, approved.text

    # A apresentação pode começar normalmente.
    started = api.post(
        f"/api/sessions/{room['id']}/start",
        headers=auth(host),
    )
    assert started.status_code == 200, started.text
