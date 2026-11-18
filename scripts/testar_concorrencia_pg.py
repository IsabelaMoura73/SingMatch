"""Teste isolado da concorrência do SingMatch com PostgreSQL real e IA simulada.

Execute na raiz do SingMatch:
  PYTHONPATH=.:backend python scripts/testar_concorrencia_pg.py

Cria e remove um banco de testes TEMPORÁRIO em PostgreSQL LOCAL.
Não faz chamadas à OpenAI e não modifica o banco habitual do projeto.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app import routes  # noqa: E402
from app.database import get_db, normalize_database_url  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.schemas import ProfileDraft  # noqa: E402
from scripts.import_catalog import seed_catalog  # noqa: E402


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def expect(res, expected: int, action: str):
    if res.status_code != expected:
        raise AssertionError(f"{action}: HTTP {res.status_code} (esperado {expected}): {res.text[:700]}")
    return res.json()


def fake_profile(text, songs):
    time.sleep(0.15)  # Imita uma chamada à IA liberando a execução concorrente.
    return ProfileDraft(likes=[{
        "category": "genre", "value": "forro", "evidence": "Gosto de forró"
    }])


def run_test(engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with factory() as db:
            yield db

    prior_override = app.dependency_overrides.get(get_db)
    old_interpreter = routes.interpretar_perfil
    app.dependency_overrides[get_db] = override_get_db
    routes.interpretar_perfil = fake_profile
    try:
        with TestClient(app) as api:
            def room():
                res = expect(api.post("/api/sessions", json={
                    "genre": "forró", "intention": "Festa com amigos"
                }), 201, "Criar sala")
                return res["session"], res["host_token"]

            def join(s, name):
                return api.post("/api/join", json={"code": s["code"], "name": name})

            def interpret(p):
                return api.post(
                    f"/api/participants/{p['participant_id']}/interpret",
                    json={"text": "Gosto de forró animado"},
                    headers=auth(p["participant_token"]),
                )

            def confirm(p):
                return api.put(
                    f"/api/participants/{p['participant_id']}/profile",
                    json={"profile": {
                        "likes": [], "vetoes": [], "preferred_format": "solo",
                        "duet_allowed": False, "questions": [],
                    }},
                    headers=auth(p["participant_token"]),
                )

            print("Cenário A: 12 entradas simultâneas...")
            s, host = room()
            with ThreadPoolExecutor(max_workers=12) as pool:
                entries = list(pool.map(lambda i: join(s, f"Pessoa {i:02d}"), range(1, 13)))
            people = [expect(res, 201, f"Entrada {i}") for i, res in enumerate(entries, 1)]
            assert len({p["participant_id"] for p in people}) == 12
            print("  OK: 12/12 participantes entraram")

            print("Cenário B: 12 interpretações simultâneas...")
            with ThreadPoolExecutor(max_workers=12) as pool:
                parsed = list(pool.map(interpret, people))
            for i, res in enumerate(parsed, 1):
                expect(res, 200, f"Interpretação {i}")
            print("  OK: 12/12 interpretações concluídas")

            print("Cenário C: 12 confirmações simultâneas...")
            with ThreadPoolExecutor(max_workers=12) as pool:
                confirmed = list(pool.map(confirm, people))
            for i, res in enumerate(confirmed, 1):
                expect(res, 200, f"Confirmação {i}")
            state = expect(api.get(f"/api/sessions/{s['id']}", headers=auth(host)), 200, "Consultar sala")
            assert len(state["participants"]) == 12, state
            assert all(p["profile_confirmed"] for p in state["participants"]), state
            assert state["session"]["revision"] == 36, state["session"]
            print("  OK: 12/12 confirmados, revisão da sala = 36")

            print("Cenário D: outra pessoa entra enquanto a IA interpreta...")
            s2, _ = room()
            a = expect(join(s2, "Ana"), 201, "Entrada Ana")
            started = Event()
            release = Event()

            def slow_profile(text, songs):
                started.set()
                if not release.wait(timeout=15):
                    raise RuntimeError("Tempo esgotado na simulação da IA")
                return fake_profile(text, songs)

            routes.interpretar_perfil = slow_profile
            with ThreadPoolExecutor(max_workers=2) as pool:
                future = pool.submit(interpret, a)
                try:
                    assert started.wait(timeout=10), "A interpretação não iniciou"
                    expect(join(s2, "Beto"), 201, "Entrada de Beto durante interpretação")
                finally:
                    release.set()
                expect(future.result(timeout=15), 200, "Interpretação de Ana após entrada de Beto")
            print("  OK: entrada de Beto não invalidou a interpretação de Ana")

            print("\nSUCESSO: cenários de concorrência passaram com PostgreSQL real.")
    finally:
        routes.interpretar_perfil = old_interpreter
        if prior_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior_override


def main():
    source = dotenv_values(ROOT / ".env").get("DATABASE_URL")
    if not source:
        raise SystemExit("DATABASE_URL ausente do .env local.")
    base = make_url(normalize_database_url(source))
    if base.get_backend_name() != "postgresql" or base.host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("SEGURANÇA: o banco do .env precisa ser PostgreSQL LOCAL, não o Render.")
    if base.database in {None, "postgres", "template1"}:
        raise SystemExit("SEGURANÇA: configure no .env um banco de aplicação, não um banco administrativo.")

    # Nome exclusivamente alfanumérico: SQL de CREATE DATABASE não admite bind de identificador.
    name = "singmatch_test_" + uuid4().hex[:10]
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        engine = create_engine(base.set(database=name), pool_pre_ping=True)
        print("Banco temporário local:", name)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            seed_catalog(db)
            db.commit()
        run_test(engine)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE "{name}"'))
            print("Banco temporário removido.")
        admin.dispose()


if __name__ == "__main__":
    main()
