#!/usr/bin/env python3
"""Demonstração de API no servidor REAL. Exige --real: 4 chamadas OpenAI.

Não imprime tokens; perfis são de teste e são confirmados automaticamente
apenas nesta demonstração. No produto, confirmação exige ação do usuário.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import httpx


@dataclass
class Check:
    response: httpx.Response
    label: str

    def data(self) -> dict:
        if self.response.status_code not in {200, 201}:
            # Nosso backend remove segredos de erros. Nunca imprimir headers.
            print(f"ERRO em {self.label}: HTTP {self.response.status_code}: {self.response.text[:500]}")
            raise SystemExit(1)
        return self.response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def demo(base_url: str) -> None:
    with httpx.Client(base_url=base_url, timeout=120) as client:
        Check(client.get("/api/health"), "health").data()
        room = Check(client.post("/api/sessions", json={
            "genre": "forro", "intention": "começar tranquilo, terminar animado",
        }), "criar sala").data()
        session_id, code, host = (room["session"]["id"], room["session"]["code"], room["host_token"])
        print("1/5 Sala criada:", code)
        phrases = [
            ("Teste-Ana", "Gosto de forró animado, não gosto de músicas românticas; prefiro solo."),
            ("Teste-Beto", "Gosto de forró festivo e de Dominguinhos; quero cantar sozinho."),
            ("Teste-Cris", "Gosto de Asa Branca e de um começo tranquilo; prefiro cantar sozinho."),
        ]
        for name, phrase in phrases:
            joined = Check(client.post("/api/join", json={"code": code, "name": name}),
                           "entrar na sala").data()
            pid, member_token = joined["participant_id"], joined["participant_token"]
            draft = Check(client.post(f"/api/participants/{pid}/interpret",
                                      json={"text": phrase}, headers=bearer(member_token)),
                          "interpretar perfil").data()["draft"]
            # Converte rascunho tipado em perfil confirmado só para smoke test.
            Check(client.put(f"/api/participants/{pid}/profile",
                             json={"profile": draft}, headers=bearer(member_token)),
                  "confirmar perfil de teste").data()
            print("2/5 Perfil de teste confirmado:", name)
        result = Check(client.post(f"/api/sessions/{session_id}/script", headers=bearer(host)),
                       "gerar roteiro").data()["script"]
        print("3/5 Roteiro gerado:", result["title"])
        assert len(result["items"]) == 3, "Esperado um solo por participante"
        print("4/5 Apresentações:", ", ".join(i["karaoke_version_id"] for i in result["items"]))
        approved = Check(client.post(f"/api/sessions/{session_id}/script/approve",
                                     headers=bearer(host), json={"expected_version": result["version"]}),
                         "aprovar").data()["script"]
        assert approved["approved"] is True
        print("5/5 Roteiro aprovado. Sessão permanece no banco PostgreSQL.")
        print("OBS: sessão usa dados fictícios; tokens não foram exibidos nem gravados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke test REAL da API SingMatch (faz 4 chamadas OpenAI)")
    parser.add_argument("--real", action="store_true", help="Permite chamadas reais que podem ter custo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not args.real:
        print("Modo seguro: nenhum teste executado. Rode com --real para autorizar 4 chamadas de IA.")
        sys.exit(0)
    demo(args.base_url)
