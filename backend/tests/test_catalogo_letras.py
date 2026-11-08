"""Catálogo ampliado (BYRM/UFMG + LRCLIB) e endpoint de letra; offline, SQLite."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.matching import eligible_candidates
from app.models import Base
from app.schemas import KaraokeVersion, PreferenceLabel, ProfileConfirmed, Song
from app.models import KaraokeVersionRow
from scripts.import_catalog import FILE_ONLY_FIELDS, PILOT as PILOT_PATH, revoke_blocked, seed_all, seed_catalog

ROOT = Path(__file__).resolve().parents[2]
PILOT = json.loads((ROOT / "data" / "catalogo_piloto.json").read_text(encoding="utf-8"))
EXPANDED = json.loads((ROOT / "data" / "catalogo_forro.json").read_text(encoding="utf-8"))
LRC_LINE = re.compile(r"^\[\d{2}:\d{2}\.\d{2}\].*$")


def _all_contracts():
    raw = PILOT["songs"] + EXPANDED["songs"], PILOT["karaoke_versions"] + EXPANDED["karaoke_versions"]
    songs = [Song.model_validate(s) for s in raw[0]]
    versions = [KaraokeVersion.model_validate({k: v for k, v in x.items() if k not in FILE_ONLY_FIELDS})
                for x in raw[1]]
    return songs, versions


def test_expanded_catalog_matches_contracts_and_has_no_duplicates():
    songs, versions = _all_contracts()
    assert len(EXPANDED["songs"]) >= 20
    assert len({s.id for s in songs}) == len(songs)
    assert len({(s.source, s.source_id) for s in songs}) == len(songs)
    assert len({v.id for v in versions}) == len(versions)
    assert len({v.youtube_video_id for v in versions}) == len(versions)
    titles = [re.sub(r"\W+", " ", s.title.casefold()).strip() for s in songs]
    assert len(set(titles)) == len(titles), "mesma obra duas vezes no catálogo"
    assert all(s.genre == "forro" for s in songs)


def test_every_synced_version_has_valid_lrc_file():
    synced = [raw for raw in EXPANDED["karaoke_versions"] if raw["kind"] == "letra_sincronizada"]
    # Toda música nova tem a versão "cante junto"; o karaokê é extra quando existe.
    assert {raw["song_id"] for raw in synced} == {s["id"] for s in EXPANDED["songs"]}
    for raw in synced:
        lines = (ROOT / "data" / raw["lyrics_file"]).read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 8, raw["id"]
        assert all(LRC_LINE.match(line) for line in lines), raw["id"]


def test_expanded_songs_have_mood_and_energy_for_veto_matching():
    # Sem clima/energia o matching bloqueia a música em qualquer veto de clima (fail closed).
    missing = [s["id"] for s in EXPANDED["songs"] if not s["mood"] or not s["energy"]]
    assert missing == []


def test_mood_veto_works_on_full_catalog():
    songs, versions = _all_contracts()
    veto = PreferenceLabel(category="tag", value="romantica", evidence="nada romântico")
    profile = ProfileConfirmed(vetoes=[veto])
    allowed = eligible_candidates("forro", {"p1": profile}, songs, versions)["p1"]
    by_version = {v.id: v.song_id for v in versions}
    by_song = {s.id: s for s in songs}
    assert allowed
    assert all(by_song[by_version[v]].mood != "romantica" for v in allowed)
    assert any(by_song[by_version[v]].source != "singmatch_piloto" for v in allowed)


@pytest.fixture
def api():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = seed_all(db)
        assert first["catalogo_piloto.json"] == (5, 5)
        assert first["catalogo_forro.json"] == (len(EXPANDED["songs"]), len(EXPANDED["karaoke_versions"]))
        assert all(v == (0, 0) for v in seed_all(db).values())  # idempotente
        db.commit()

    def override():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def test_catalog_endpoint_exposes_kind_but_not_lyrics(api):
    cat = api.get("/api/catalog").json()
    assert len(cat["songs"]) == 5 + len(EXPANDED["songs"])
    kinds = {v["id"]: v["kind"] for v in cat["karaoke_versions"]}
    assert kinds["KAR-FOR-001"] == "karaoke"
    assert all(kinds[v["id"]] == v["kind"] for v in EXPANDED["karaoke_versions"])
    assert all(v["kind"] == "karaoke" for v in EXPANDED["karaoke_versions"] if v["id"].startswith("KAR-"))
    assert all("lyrics_lrc" not in v and "lrc" not in v for v in cat["karaoke_versions"])


def test_lyrics_endpoint(api):
    version = next(v for v in EXPANDED["karaoke_versions"] if v["kind"] == "letra_sincronizada")
    resp = api.get(f"/api/karaoke_versions/{version['id']}/lyrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["karaoke_version_id"] == version["id"]
    assert body["lrc"].startswith("[")
    assert body["source"].startswith("lrclib.net")
    assert api.get("/api/karaoke_versions/KAR-FOR-001/lyrics").status_code == 404
    assert api.get("/api/karaoke_versions/NAO-EXISTE/lyrics").status_code == 404


def test_blocked_video_is_replaced_on_old_db_or_approval_revoked():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_catalog(db, PILOT_PATH)
        old = db.get(KaraokeVersionRow, "KAR-FOR-004")
        new_video = old.youtube_video_id
        old.youtube_video_id = "ZFGBYMnc-MU"  # banco publicado antes da troca
        db.flush()
        blocked = {"ZFGBYMnc-MU", "tvAtWam6V0E"}
        seed_catalog(db, PILOT_PATH, blocked)
        assert db.get(KaraokeVersionRow, "KAR-FOR-004").youtube_video_id == new_video
        # KAR-FOR-001 não tem substituto no JSON: perde a aprovação, não some do banco.
        assert revoke_blocked(db, blocked) == ["KAR-FOR-001"]
        assert db.get(KaraokeVersionRow, "KAR-FOR-001").approved is False
        assert db.get(KaraokeVersionRow, "KAR-FOR-004").approved is True
    engine.dispose()


def test_real_karaoke_is_preferred_over_sing_along():
    songs, versions = _all_contracts()
    with_karaoke = {v.song_id for v in versions if v.kind == "karaoke" and v.id.startswith("KAR-") and v.song_id.startswith(("BYRM", "UFMG", "PESQ"))}
    assert with_karaoke, "nenhuma música nova com karaokê"
    allowed = eligible_candidates("forro", {"p1": ProfileConfirmed()}, songs, versions)["p1"]
    kind = {v.id: v.kind for v in versions}
    song_of = {v.id: v.song_id for v in versions}
    chosen = {song_of[v]: kind[v] for v in allowed}
    assert all(chosen[s] == "karaoke" for s in with_karaoke)
