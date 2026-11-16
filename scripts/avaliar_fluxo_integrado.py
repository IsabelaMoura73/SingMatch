"""Avaliação integrada do SingMatch: interpretação de texto -> roteiro solo.

Este script só usa perfis fictícios, nunca acessa o banco e não aprova roteiros.
Rode na raiz do repositório:
  PYTHONPATH=.:backend python3 scripts/avaliar_fluxo_integrado.py --modo contrato
  PYTHONPATH=.:backend python3 scripts/avaliar_fluxo_integrado.py --modo real --geracoes 1
  PYTHONPATH=.:backend python3 scripts/avaliar_fluxo_integrado.py --modo real --geracoes 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from app.llm import LLMServiceError, compor_roteiro_solo, interpretar_perfil
from app.matching import MatchingError, eligible_candidates, matches_like, norm, respects_veto
from app.schemas import KaraokeVersion, ProfileConfirmed, Song

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resultados"

TEXTOS = {
    "P1": "Gosto de forró animado, mas não gosto de músicas românticas.",
    "P2": "Adoro Dominguinhos, mas não quero cantar Asa Branca.",
    "P3": "Gosto de músicas tranquilas, mas detesto músicas com energia alta.",
}
# Referência definida pelos avaliadores antes das chamadas ao GPT.
ESPERADO = {
    "P1": {"likes": [("genre", "forro"), ("tag", "animada")], "vetoes": [("tag", "romantica")]},
    "P2": {"likes": [("artist", "Dominguinhos")], "vetoes": [("song", "Asa Branca")]},
    "P3": {"likes": [("tag", "tranquila")], "vetoes": [("tag", "energia_alta")]},
}
INTENCAO = "Começar com músicas tranquilas e aumentar a energia até o final."


def pares(labels):
    return {(x.category, norm(x.value)) for x in labels}


def pares_esperados(items):
    return {(cat, norm(value)) for cat, value in items}


def carregar_catalogo():
    songs_by_id, versions_by_id = {}, {}
    for name in ("catalogo_piloto.json", "catalogo_forro.json"):
        path = ROOT / "data" / name
        raw = json.loads(path.read_text(encoding="utf-8"))
        for item in raw["songs"]:
            song = Song.model_validate(item)
            songs_by_id[song.id] = song
        for item in raw["karaoke_versions"]:
            # Avaliar somente os karaokês aprovados.
            if item.get("approved") and item.get("kind", "karaoke") == "karaoke":

                # Ignorar metadados extras do catálogo,
                # mantendo somente os campos do modelo Pydantic.
                dados_validos = {
                    chave: valor
                    for chave, valor in item.items()
                    if chave in KaraokeVersion.model_fields
                }

                version = KaraokeVersion.model_validate(dados_validos)
                versions_by_id[version.id] = version
    versions = [v for v in versions_by_id.values() if v.song_id in songs_by_id]
    return list(songs_by_id.values()), versions


def avaliar_perfil(pid, draft):
    esperado = ESPERADO[pid]
    resultado = {
        "likes_esperados": sorted(pares_esperados(esperado["likes"])),
        "likes_observados": sorted(pares(draft.likes)),
        "vetoes_esperados": sorted(pares_esperados(esperado["vetoes"])),
        "vetoes_observados": sorted(pares(draft.vetoes)),
        "questions": draft.questions,
    }
    resultado["correto"] = (
        set(map(tuple, resultado["likes_esperados"])) == set(map(tuple, resultado["likes_observados"]))
        and set(map(tuple, resultado["vetoes_esperados"])) == set(map(tuple, resultado["vetoes_observados"]))
        and not draft.questions
    )
    return resultado


def perfil_esperado(pid):
    # Atribuir evidência literal fictícia para contrato Pydantic.
    raw = ESPERADO[pid]
    return ProfileConfirmed(
        likes=[{"category": cat, "value": val, "evidence": TEXTOS[pid]} for cat, val in raw["likes"]],
        vetoes=[{"category": cat, "value": val, "evidence": TEXTOS[pid]} for cat, val in raw["vetoes"]],
    )


def verificar_roteiro(roteiro, profiles, songs, versions):
    songs_by_id = {s.id: s for s in songs}
    versions_by_id = {v.id: v for v in versions}
    moods = {s.mood for s in songs if s.mood}
    labels_atendidas = labels_totais = 0
    pessoas_atendidas = pessoas_com_gostos = 0
    violacoes = []
    energias = []
    linhas = []
    for item in sorted(roteiro.items, key=lambda x: x.position):
        pid = item.participant_ids[0]
        version = versions_by_id[item.karaoke_version_id]
        song = songs_by_id[version.song_id]
        profile = profiles[pid]
        hits = sum(matches_like(song, label) for label in profile.likes)
        labels_atendidas += hits
        labels_totais += len(profile.likes)
        pessoas_com_gostos += bool(profile.likes)
        pessoas_atendidas += bool(hits)
        for veto in profile.vetoes:
            if not respects_veto(song, veto, moods):
                violacoes.append({"participante": pid, "musica": song.title, "veto": veto.value})
        energias.append(song.energy)
        linhas.append({
            "posicao": item.position,
            "participante": pid,
            "musica": song.title,
            "artista": ", ".join(song.artists),
            "energia": song.energy,
            "video_id": version.id,
            "likes_atendidos": hits,
            "likes_totais": len(profile.likes),
            "justificativa": item.justification,
        })
    progressao = (all(a <= b for a, b in zip(energias, energias[1:]))
                  if all(x is not None for x in energias) else None)
    return {
        "musicas": linhas,
        "afinidade_labels": labels_atendidas / labels_totais if labels_totais else None,
        "afinidade_pessoas": pessoas_atendidas / pessoas_com_gostos if pessoas_com_gostos else None,
        "vetos_violados": violacoes,
        "progressao_energia_nao_decrescente": progressao,
    }


def executar():
    parser = argparse.ArgumentParser(description="Avaliar integração perfil -> roteiro do SingMatch.")
    parser.add_argument("--modo", required=True, choices=("contrato", "real"))
    parser.add_argument("--geracoes", type=int, default=1, help="1 para avaliação básica; 2 para testar diversidade")
    parser.add_argument("--modelo", default=None, help="Modelo da OpenAI (opcional)")
    args = parser.parse_args()
    if not 1 <= args.geracoes <= 3:
        parser.error("--geracoes deve ser 1, 2 ou 3")

    songs, versions = carregar_catalogo()
    print(f"Catálogo local: {len(songs)} músicas, {len(versions)} karaokês aprovados")
    print("Cenário integrado: 3 participantes fictícios")
    print("Intenção:", INTENCAO)
    print("Sem acesso ao banco e sem aprovação automática de roteiro.")
    registro = {
        "modo": args.modo,
        "executado_em": datetime.now().astimezone().isoformat(),
        "intencao": INTENCAO,
        "textos_ficticios": TEXTOS,
        "perfis": {}, "roteiros": [], "erro": None,
    }

    if args.modo == "contrato":
        profiles = {pid: perfil_esperado(pid) for pid in TEXTOS}
        allowed = eligible_candidates("forro", profiles, songs, versions)
        for pid, ids in allowed.items():
            print(f"  {pid}: {len(ids)} karaokês elegíveis")
        print("MODO CONTRATO: filtros e possibilidade de atribuição validados. Nenhuma chamada ao GPT.")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("Configure OPENAI_API_KEY no terminal ou no .env antes do modo real")

    try:
        profiles = {}
        for pid, texto in TEXTOS.items():
            print(f"\nInterpretando {pid}...", flush=True)
            draft = interpretar_perfil(texto, songs, model=args.modelo)
            checagem = avaliar_perfil(pid, draft)
            registro["perfis"][pid] = {"rascunho": draft.model_dump(mode="json"), "avaliacao": checagem}
            print("  Labels:", "CORRETAS" if checagem["correto"] else "DIVERGENTES")
            if not checagem["correto"]:
                print("  Esperado:", checagem["likes_esperados"], checagem["vetoes_esperados"])
                print("  Observado:", checagem["likes_observados"], checagem["vetoes_observados"])
                raise ValueError(f"Perfil {pid} divergiu; roteiro não gerado para evitar medir com perfil incorreto.")
            # Simulação controlada: labels já confrontadas com a referência humana.
            # Não substitui a confirmação explícita da pessoa no produto real.
            profiles[pid] = ProfileConfirmed.model_validate(draft.model_dump())

        allowed = eligible_candidates("forro", profiles, songs, versions)
        print("\nElegibilidade com perfis interpretados:", {k: len(v) for k, v in allowed.items()})
        previous = []
        for geracao in range(1, args.geracoes + 1):
            print(f"\nGerando roteiro {geracao}/{args.geracoes}...", flush=True)
            roteiro = compor_roteiro_solo(
                "forro", INTENCAO, profiles, songs, versions,
                previous_video_ids=previous, model=args.modelo,
            )
            analise = verificar_roteiro(roteiro, profiles, songs, versions)
            ids = {item.karaoke_version_id for item in roteiro.items}
            analise["repeticao_anterior"] = (
                len(ids & set(previous)) / len(ids) if previous else None
            )
            registro["roteiros"].append({"geracao": geracao, "roteiro": roteiro.model_dump(mode="json"), "metricas": analise})
            for item in analise["musicas"]:
                print(f"  {item['posicao']}. {item['participante']}: {item['musica']} "
                      f"(energia {item['energia']}, likes {item['likes_atendidos']}/{item['likes_totais']})")
            print(f"  Afinidade das labels: {analise['afinidade_labels']:.1%}")
            print("  Vetos violados:", len(analise["vetos_violados"]))
            print("  Energia não decrescente:", analise["progressao_energia_nao_decrescente"])
            if analise["repeticao_anterior"] is not None:
                print(f"  Repetição frente ao roteiro anterior: {analise['repeticao_anterior']:.1%}")
            previous = [item.karaoke_version_id for item in roteiro.items]
        registro["concluido"] = True
    except (LLMServiceError, MatchingError, ValueError, KeyError) as exc:
        # Não imprimir prompts, segredos ou respostas brutas da API.
        registro["erro"] = {"tipo": type(exc).__name__, "mensagem": str(exc)}
        registro["concluido"] = False
        print(f"\nERRO: {type(exc).__name__}: {exc}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"avaliacao_integrada_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    path.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRelatório salvo em: {path}")
    if not registro["concluido"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        executar()
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERRO DE CONFIGURAÇÃO: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
