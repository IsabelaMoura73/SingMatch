"""Executar a prova de conceito real, sem banco nem frontend.

Na raiz do repositório:
  PYTHONPATH=backend python3 scripts/demo_llm.py --modo contrato
  PYTHONPATH=backend python3 scripts/demo_llm.py --modo real
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.llm import LLMServiceError, compor_roteiro_solo, interpretar_perfil
from app.matching import MatchingError, eligible_candidates
from app.schemas import KaraokeVersion, ProfileConfirmed, Song

ROOT = Path(__file__).resolve().parents[1]


def get_seed():
    seed = json.loads((ROOT / "data" / "catalogo_piloto.json").read_text(encoding="utf-8"))
    return [Song.model_validate(s) for s in seed["songs"]], [
        KaraokeVersion.model_validate(v) for v in seed["karaoke_versions"]
    ]


def sample_profiles() -> dict[str, ProfileConfirmed]:
    return {
        "P1": ProfileConfirmed(vetoes=[{"category": "tag", "value": "romantica", "evidence": "Não gosto de músicas românticas."}], preferred_format="solo"),
        "P2": ProfileConfirmed(likes=[{"category": "tag", "value": "animada", "evidence": "Gosto de músicas animadas."}]),
        "P3": ProfileConfirmed(likes=[{"category": "song", "value": "Asa Branca", "evidence": "Gosto de Asa Branca."}]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modo", choices=["contrato", "real"], required=True)
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    songs, versions = get_seed()
    profiles = sample_profiles()
    allowed = eligible_candidates("forro", profiles, songs, versions)
    print("OK: 5 músicas do catálogo validadas; candidatos elegíveis:")
    for person, candidates in allowed.items():
        print(f"  {person}: {len(candidates)} vídeos permitidos")
    if args.modo == "contrato":
        print("MODO CONTRATO: nenhuma chamada de API; nenhuma saída do GPT foi validada.")
        return
    if not os.getenv("OPENAI_API_KEY"):
        print("ERRO: configure OPENAI_API_KEY antes de executar --modo real.", file=sys.stderr)
        sys.exit(2)
    text = "Gosto de forró animado, mas não gosto de músicas românticas. Prefiro cantar sozinho."
    try:
        draft = interpretar_perfil(text, songs)
        print("\nPERFIL GERADO POR GPT (rascunho, requer confirmação):")
        print(draft.model_dump_json(indent=2))
        # No produto real, só usar perfil após o usuário confirmar/editar.
        # Nesta prova de conceito há confirmação EXPLÍCITA simulada no terminal.
        answer = input("Confirma o perfil gerado para P1? [s/N]: ").strip().casefold()
        if answer != "s":
            print("Perfil não confirmado; roteiro não será gerado.")
            return
        profiles["P1"] = ProfileConfirmed.model_validate(draft.model_dump())
        roteiro = compor_roteiro_solo("forro", "Começar tranquilo e terminar animado", profiles, songs, versions)
        print("\nROTEIRO PROPOSTO POR GPT (não aprovado):")
        print(roteiro.model_dump_json(indent=2))
        outfile = ROOT / "resultados_llm_demo.json"
        outfile.write_text(json.dumps({"profile_draft": draft.model_dump(), "script_proposal": roteiro.model_dump()}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nResultado salvo em {outfile.name} (não envie com dados pessoais reais ao GitHub).")
    except (MatchingError, LLMServiceError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
