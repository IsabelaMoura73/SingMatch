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

    def fake_script(genre, intention, profiles, songs, versions):
        ids = list(profiles)
        return ScriptProposal(title="Forró progressivo", items=[
            ScriptItem(position=i+1, karaoke_version_id=vid, participant_ids=[pid],
                       justification="Escolha de teste", origin="ia")
            for i, (pid, vid) in enumerate(zip(ids, ["KAR-FOR-001", "KAR-FOR-002", "KAR-FOR-004"]))
        ])

    monkeypatch.setattr(routes, "interpretar_perfil", fake_profile)
    monkeypatch.setattr(routes, "compor_roteiro_solo", fake_script)
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


def confirm(api, participant_id, token, veto=False):
    response = api.post(f"/api/participants/{participant_id}/interpret",
                        json={"text": "Gosto de forró e prefiro músicas animadas"}, headers=auth(token))
    assert response.status_code == 200, response.text
    labels = [{"category": "tag", "value": "romantica", "evidence": "não gosto de românticas"}]
    response = api.put(f"/api/participants/{participant_id}/profile",
                       json={"profile": {"likes": [], "vetoes": labels if veto else [],
                                         "preferred_format": "solo", "duet_allowed": False,
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
