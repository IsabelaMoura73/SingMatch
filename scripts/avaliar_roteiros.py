"""Avaliação local dos roteiros do SingMatch, sem banco nem frontend.

Na raiz do projeto:
  PYTHONPATH=backend python3 scripts/avaliar_roteiros.py --modo contrato
  PYTHONPATH=backend python3 scripts/avaliar_roteiros.py --modo real --cenario iguais --repeticoes 2
  PYTHONPATH=backend python3 scripts/avaliar_roteiros.py --modo real --cenario todos --repeticoes 3
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from app.llm import LLMServiceError, compor_roteiro_solo
from app.matching import MatchingError, eligible_candidates, matches_like, respects_veto
from app.schemas import KaraokeVersion, ProfileConfirmed, Song

ROOT = Path(__file__).resolve().parents[1]


def load_catalog():
    songs_by_id = {}
    versions_by_id = {}
    for filename in ("catalogo_piloto.json", "catalogo_forro.json"):
        data = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))
        for record in data["songs"]:
            song = Song.model_validate({k: record[k] for k in Song.model_fields if k in record})
            songs_by_id[song.id] = song
        for record in data["karaoke_versions"]:
            if not record.get("approved") or record.get("kind", "karaoke") != "karaoke":
                continue
            version = KaraokeVersion.model_validate(
                {k: record[k] for k in KaraokeVersion.model_fields if k in record}
            )
            versions_by_id[version.id] = version
    return songs_by_id, versions_by_id


def profile(likes=(), vetoes=()):
    def labels(values):
        return [
            {"category": category, "value": value, "evidence": "cenário fictício"}
            for category, value in values
        ]
    return ProfileConfirmed(likes=labels(likes), vetoes=labels(vetoes))


def scenarios():
    return {
        "iguais": (
            "Organizar um forró animado com três participantes.",
            {p: profile(likes=[("tag", "animada")]) for p in ("P1", "P2", "P3")},
        ),
        "diferentes": (
            "Variar os estilos e valorizar os gostos individuais.",
            {
                "P1": profile(likes=[("artist", "Luiz Gonzaga")]),
                "P2": profile(likes=[("artist", "Dominguinhos")]),
                "P3": profile(likes=[("tag", "energia_alta")]),
            },
        ),
        "vetos": (
            "Criar uma sequência variada respeitando as restrições.",
            {
                "P1": profile(vetoes=[("tag", "romantica")]),
                "P2": profile(vetoes=[("tag", "animada")]),
                "P3": profile(vetoes=[("tag", "saudosa")]),
            },
        ),
        "progressao": (
            "Começar calmo, crescer gradualmente em energia e terminar animado.",
            {p: profile() for p in ("P1", "P2", "P3")},
        ),
    }


def evaluate_script(script, profiles, songs, versions, previous_ids, scenario_name):
    known_moods = {s.mood for s in songs.values() if s.mood}
    ids = {item.karaoke_version_id for item in script.items}
    total_likes = 0
    matched_likes = 0
    violations = 0
    energies = []
    details = []

    for item in sorted(script.items, key=lambda it: it.position):
        person_id = item.participant_ids[0]
        person = profiles[person_id]
        song = songs[versions[item.karaoke_version_id].song_id]
        matched_likes += sum(matches_like(song, like) for like in person.likes)
        total_likes += len(person.likes)
        violations += sum(
            not respects_veto(song, veto, known_moods) for veto in person.vetoes
        )
        energies.append(song.energy)
        details.append({
            "posicao": item.position,
            "participante": person_id,
            "musica": song.title,
            "artista": ", ".join(song.artists),
            "video_id": item.karaoke_version_id,
            "energia": song.energy,
        })

    progressive = None
    if scenario_name == "progressao" and all(e is not None for e in energies):
        progressive = all(a <= b for a, b in zip(energies, energies[1:]))

    return {
        "repeticao_pct": round(100 * len(ids & set(previous_ids)) / len(ids), 1)
        if previous_ids else None,
        "afinidade_pct": round(100 * matched_likes / total_likes, 1)
        if total_likes else None,
        "violacoes_veto": violations,
        "energia_crescente": progressive,
        "itens": details,
    }


def average(records, key):
    values = [row[key] for row in records if row.get(key) is not None]
    return round(mean(values), 1) if values else None


def mostrar_erro(exc):
    """Mostra a estrutura do erro sem imprimir respostas da IA ou dados pessoais."""
    print(f"    ERRO: {exc}")
    causa = exc.__cause__
    if causa is None:
        return
    print(f"    Causa interna: {type(causa).__name__}")
    if hasattr(causa, "errors"):
        try:
            detalhes = causa.errors(
                include_input=False, include_context=True, include_url=False
            )
        except TypeError:
            detalhes = []
        for detalhe in detalhes[:8]:
            campo = ".".join(str(v) for v in detalhe.get("loc", ())) or "(raiz)"
            print(f"      Campo: {campo}; tipo: {detalhe.get('type', 'desconhecido')}")
            if detalhe.get("type") == "json_invalid":
                motivo = detalhe.get("ctx", {}).get("error")
                if motivo:
                    print(f"      Motivo do JSON: {str(motivo)[:180]}")


def resumo(registros, repeticoes):
    completo = (len(registros) == repeticoes and
                all("erro" not in registro for registro in registros))
    return {
        "completo": completo,
        "geracoes_validas": sum("erro" not in registro for registro in registros),
        "media_repeticao_pct": average(registros, "repeticao_pct") if completo else None,
        "media_afinidade_pct": average(registros, "afinidade_pct") if completo else None,
        "total_violacoes_veto": sum(r.get("violacoes_veto", 0) for r in registros),
        "registros": registros,
    }


def main():
    parser = argparse.ArgumentParser(description="Avaliar diversidade dos roteiros SingMatch")
    parser.add_argument("--modo", choices=("contrato", "real"), default="contrato")
    parser.add_argument(
        "--cenario", choices=(*scenarios(), "todos"), default="iguais"
    )
    parser.add_argument("--repeticoes", type=int, default=2)
    args = parser.parse_args()
    if args.repeticoes < 2:
        parser.error("--repeticoes deve ser pelo menos 2")

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    songs, versions = load_catalog()
    print(f"Catálogo local: {len(songs)} músicas, {len(versions)} karaokês aprovados")

    if args.modo == "real" and not os.getenv("OPENAI_API_KEY"):
        parser.error("Configure OPENAI_API_KEY no ambiente ou no .env antes do modo real")

    selected = scenarios()
    if args.cenario != "todos":
        selected = {args.cenario: selected[args.cenario]}

    report = {
        "modo": args.modo,
        "repeticoes": args.repeticoes,
        "comparacao": "primeira_geracao_compartilhada",
        "catalogo": {"musicas": len(songs), "karaokes": len(versions)},
        "cenarios": {},
    }
    songs_list = list(songs.values())
    versions_list = list(versions.values())
    for name, (intention, profiles) in selected.items():
        print(f"\nCenário: {name}")
        allowed = eligible_candidates("forro", profiles, songs_list, versions_list)
        print("Candidatos por participante:", {p: len(c) for p, c in allowed.items()})
        if args.modo == "contrato":
            continue

        by_method = {"sem_historico": [], "com_historico": []}
        previous = {"sem_historico": [], "com_historico": []}
        active = {"sem_historico": True, "com_historico": True}

        # Ambos os métodos começam EXATAMENTE do mesmo roteiro inicial.
        print(f"  Geração inicial compartilhada (1/{args.repeticoes})", flush=True)
        try:
            initial_script = compor_roteiro_solo(
                "forro", intention, profiles, songs_list, versions_list
            )
        except (LLMServiceError, MatchingError) as exc:
            mostrar_erro(exc)
            for method in by_method:
                by_method[method].append({"geracao": 1, "erro": str(exc)})
                active[method] = False
        else:
            initial_result = evaluate_script(
                initial_script, profiles, songs, versions, [], name
            )
            initial_result["geracao"] = 1
            print("  Músicas iniciais:", "; ".join(
                i["musica"] for i in initial_result["itens"]
            ))
            initial_ids = [i.karaoke_version_id for i in initial_script.items]
            for method in by_method:
                by_method[method].append(dict(initial_result))
                previous[method] = list(initial_ids)

        for number in range(2, args.repeticoes + 1):
            for method in by_method:
                if not active[method]:
                    continue
                print(f"  Método: {method}; geração {number}/{args.repeticoes}", flush=True)
                try:
                    script = compor_roteiro_solo(
                        "forro", intention, profiles, songs_list, versions_list,
                        previous_video_ids=(previous[method]
                                            if method == "com_historico" else ()),
                    )
                except (LLMServiceError, MatchingError) as exc:
                    mostrar_erro(exc)
                    by_method[method].append({"geracao": number, "erro": str(exc)})
                    active[method] = False
                    continue
                result = evaluate_script(
                    script, profiles, songs, versions, previous[method], name
                )
                result["geracao"] = number
                by_method[method].append(result)
                previous[method] = [i.karaoke_version_id for i in script.items]
                print("    Músicas:", "; ".join(i["musica"] for i in result["itens"]))
                print(f"    Repetição: {result['repeticao_pct']}%")

        report["cenarios"][name] = {
            method: resumo(records, args.repeticoes)
            for method, records in by_method.items()
        }

    if args.modo == "contrato":
        print("\nMODO CONTRATO: elegibilidade verificada sem consultar o GPT.")
        return

    out = ROOT / "resultados"
    out.mkdir(exist_ok=True)
    filepath = out / f"avaliacao_roteiros_{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
    filepath.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nRelatório salvo em:", filepath)
    for name, modes in report["cenarios"].items():
        print(f"\nResumo — {name}:")
        for method, summary in modes.items():
            records = summary["registros"]
            progress = [r["energia_crescente"] for r in records
                        if r.get("energia_crescente") is not None]
            errors = sum("erro" in r for r in records)
            if not summary["completo"]:
                print(f"  {method}: INCOMPLETO; gerações válidas="
                      f"{summary['geracoes_validas']}/{args.repeticoes}; erros={errors}.")
                continue
            print(
                f"  {method}: repetição={summary['media_repeticao_pct']}%; "
                f"afinidade={summary['media_afinidade_pct']}%; "
                f"vetos violados={summary['total_violacoes_veto']}; "
                f"progressão crescente={sum(progress)}/{len(progress)} "
                f"(se aplicável); erros={errors}"
            )
    print("Amostras pequenas mostram tendências, não garantem superioridade estatística.")


if __name__ == "__main__":
    main()
