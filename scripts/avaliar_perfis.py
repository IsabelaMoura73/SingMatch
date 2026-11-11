"""Avaliação reproduzível da interpretação de perfis do SingMatch.

Na raiz do projeto:
    PYTHONPATH=.:backend python3 scripts/avaliar_perfis.py --modo contrato
    PYTHONPATH=.:backend python3 scripts/avaliar_perfis.py --modo real --cenario simples --limite 3
    PYTHONPATH=.:backend python3 scripts/avaliar_perfis.py --modo real --cenario todos

Os textos são inteiramente fictícios. O modo contrato não acessa a API.
O modo real chama a mesma interpretar_perfil() do produto e pode consumir créditos.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.llm import LLMServiceError, interpretar_perfil
from app.matching import norm
from app.schemas import Song

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "resultados"


def caso(
    identificador: str,
    grupo: str,
    texto: str,
    *,
    likes: list[tuple[str, str]] | None = None,
    vetoes: list[tuple[str, str]] | None = None,
    formatos: tuple[str, ...] | None = ("indiferente",),
    dueto: bool | None | str = None,
    perguntas: bool | None = False,
) -> dict:
    """None para likes/vetoes/formato/perguntas = não avaliar o campo.

    Em `dueto`, a string 'ignorar' desativa a avaliação; None exige
    duet_allowed=null (diferente de omitir essa verificação).
    """
    esperado: dict = {"likes": likes, "vetoes": vetoes}
    if formatos is not None:
        esperado["preferred_format"] = list(formatos)
    if dueto != "ignorar":
        esperado["duet_allowed"] = dueto
    if perguntas is not None:
        esperado["questions_required"] = perguntas
    return {"id": identificador, "cenario": grupo, "texto": texto, "esperado": esperado}


CASOS = [
    # Gostos e vetos diretos: pouca margem para interpretação.
    caso("S01", "simples", "Gosto de músicas animadas.", likes=[("tag", "animada")], vetoes=[]),
    caso("S02", "simples", "Não gosto de músicas românticas.", likes=[], vetoes=[("tag", "romantica")]),
    caso("S03", "simples", "Amo as músicas de Luiz Gonzaga.", likes=[("artist", "Luiz Gonzaga")], vetoes=[]),
    caso("S04", "simples", "Quero cantar Asa Branca.", likes=[("song", "Asa Branca")], vetoes=[]),
    caso("S05", "simples", "Prefiro músicas com energia baixa.", likes=[("tag", "energia_baixa")], vetoes=[]),

    # Extração de múltiplas informações da mesma frase.
    caso("C01", "combinadas", "Gosto de forró animado, mas não gosto de músicas românticas.",
         likes=[("genre", "forro"), ("tag", "animada")], vetoes=[("tag", "romantica")]),
    caso("C02", "combinadas", "Adoro Dominguinhos, mas não quero cantar Asa Branca.",
         likes=[("artist", "Dominguinhos")], vetoes=[("song", "Asa Branca")]),
    caso("C03", "combinadas", "Gosto de músicas tranquilas, mas detesto músicas com energia alta.",
         likes=[("tag", "tranquila")], vetoes=[("tag", "energia_alta")]),
    caso("C04", "combinadas", "Prefiro músicas festivas e não gosto das sofridas.",
         likes=[("tag", "festiva")], vetoes=[("tag", "sofrida")]),
    caso("C05", "combinadas", "Gosto de Luiz Gonzaga, mas não gosto de músicas românticas.",
         likes=[("artist", "Luiz Gonzaga")], vetoes=[("tag", "romantica")]),
    caso("C06", "combinadas", "Não gosto de rock; quero forró.",
         likes=[("genre", "forro")], vetoes=[("genre", "rock")]),

    # Formato da apresentação não é uma propriedade musical (tag).
    caso("F01", "formato", "Prefiro cantar sozinho.", likes=[], vetoes=[], formatos=("solo",), dueto=None),
    caso("F02", "formato", "Não quero cantar em dueto.", likes=[], vetoes=[],
         formatos=("solo", "indiferente"), dueto=False),
    caso("F03", "formato", "Quero cantar em dueto.", likes=[], vetoes=[], formatos=("dueto",), dueto=True),
    caso("F04", "formato", "Prefiro cantar sozinho, mas aceito duetos.", likes=[], vetoes=[],
         formatos=("solo",), dueto=True),
    caso("F05", "formato", "Não gosto de músicas românticas e não quero cantar em dueto.",
         likes=[], vetoes=[("tag", "romantica")], formatos=("solo", "indiferente"), dueto=False),

    # Não impor gold labels controversas; medir apenas perguntas de esclarecimento.
    caso("A01", "ambiguidades", "Adoro músicas românticas, mas não quero nenhuma romântica.",
         likes=None, vetoes=None, formatos=None, dueto="ignorar", perguntas=True),
    caso("A02", "ambiguidades", "Quero cantar em dueto e, ao mesmo tempo, não quero duetos.",
         likes=None, vetoes=None, formatos=None, dueto="ignorar", perguntas=True),
    caso("A03", "ambiguidades", "Gosto de várias músicas, mas não sei dizer quais.",
         likes=None, vetoes=None, formatos=None, dueto="ignorar", perguntas=True),
    caso("A04", "ambiguidades", "Quero músicas animadas, ou talvez só tranquilas; ainda não decidi.",
         likes=None, vetoes=None, formatos=None, dueto="ignorar", perguntas=True),
]


def carregar_catalogo() -> tuple[list[Song], int]:
    songs: dict[str, Song] = {}
    karaoke: dict[str, dict] = {}
    for nome in ("catalogo_piloto.json", "catalogo_forro.json"):
        path = DATA / nome
        if not path.exists():
            raise FileNotFoundError(f"Catálogo não encontrado: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        for row in raw["songs"]:
            songs[row["id"]] = Song.model_validate(row)
        for row in raw["karaoke_versions"]:
            if row.get("approved") and row.get("kind", "karaoke") == "karaoke":
                karaoke[row["id"]] = row
    return list(songs.values()), len(karaoke)


def validar_casos(casos: list[dict], songs: list[Song]) -> None:
    artistas = {norm(a) for song in songs for a in song.artists}
    titulos = {norm(song.title) for song in songs}
    tags = {norm(song.mood) for song in songs if song.mood}
    tags.update({"energia baixa", "energia media", "energia alta"})
    ids = set()
    for item in casos:
        if item["id"] in ids:
            raise ValueError(f"ID de caso duplicado: {item['id']}")
        ids.add(item["id"])
        esperado = item["esperado"]
        for campo in ("likes", "vetoes"):
            pares = esperado[campo]
            if pares is None:
                continue
            if len(pares) != len(set(pares)):
                raise ValueError(f"Rótulo duplicado em {item['id']}/{campo}")
            for categoria, valor in pares:
                v = norm(valor)
                if categoria == "artist" and v not in artistas:
                    raise ValueError(f"Artista esperado não encontrado no catálogo: {valor}")
                if categoria == "song" and v not in titulos:
                    raise ValueError(f"Música esperada não encontrada no catálogo: {valor}")
                if categoria == "tag" and v not in tags:
                    raise ValueError(f"Tag esperada não encontrada no catálogo: {valor}")
                if categoria not in {"artist", "song", "tag", "genre"}:
                    raise ValueError(f"Categoria inesperada em {item['id']}: {categoria}")


def pares_normalizados(labels: list | None) -> set[tuple[str, str]]:
    return {(str(cat), norm(str(value))) for cat, value in (labels or [])}


def mostrar_pares(pares: set[tuple[str, str]]) -> str:
    return ", ".join(f"{cat}:{value}" for cat, value in sorted(pares)) or "—"


def avaliar(item: dict, perfil) -> dict:
    esperado = item["esperado"]
    reais = {
        "likes": [(x.category, x.value) for x in perfil.likes],
        "vetoes": [(x.category, x.value) for x in perfil.vetoes],
    }
    aval = {"labels": {}, "campos": {}, "aprovado": True}
    for campo in ("likes", "vetoes"):
        if esperado[campo] is None:
            continue
        e, a = pares_normalizados(esperado[campo]), pares_normalizados(reais[campo])
        dados = {
            "esperadas": sorted(list(e)), "observadas": sorted(list(a)),
            "corretas": sorted(list(e & a)),
            "extras": sorted(list(a - e)), "ausentes": sorted(list(e - a)),
            "exato": e == a,
        }
        aval["labels"][campo] = dados
        if not dados["exato"]:
            aval["aprovado"] = False
    if "preferred_format" in esperado:
        ok = perfil.preferred_format in esperado["preferred_format"]
        aval["campos"]["preferred_format"] = {
            "esperado": esperado["preferred_format"], "observado": perfil.preferred_format, "ok": ok
        }
        aval["aprovado"] &= ok
    if "duet_allowed" in esperado:
        ok = perfil.duet_allowed is esperado["duet_allowed"]
        aval["campos"]["duet_allowed"] = {
            "esperado": esperado["duet_allowed"], "observado": perfil.duet_allowed, "ok": ok
        }
        aval["aprovado"] &= ok
    if "questions_required" in esperado:
        tem_pergunta = bool(perfil.questions)
        ok = tem_pergunta is esperado["questions_required"]
        aval["campos"]["questions_required"] = {
            "esperado": esperado["questions_required"], "observado": tem_pergunta, "ok": ok
        }
        aval["aprovado"] &= ok
    return aval


def resumo(resultados: list[dict]) -> dict:
    validos = [r for r in resultados if r.get("avaliacao")]
    contagem = Counter()
    campos = Counter()
    for r in validos:
        a = r["avaliacao"]
        contagem["casos_aprovados"] += int(a["aprovado"])
        for d in a["labels"].values():
            contagem["tp"] += len(d["corretas"])
            contagem["fp"] += len(d["extras"])
            contagem["fn"] += len(d["ausentes"])
            contagem["conjuntos_exatos"] += int(d["exato"])
            contagem["conjuntos_avaliados"] += 1
        for nome, val in a["campos"].items():
            campos[nome + "_avaliados"] += 1
            campos[nome + "_corretos"] += int(val["ok"])
    tp, fp, fn = (contagem[x] for x in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        "casos_totais": len(resultados), "casos_respondidos": len(validos),
        "erros": len(resultados) - len(validos),
        "casos_integralmente_corretos": contagem["casos_aprovados"],
        "labels_micro": {"tp": tp, "fp": fp, "fn": fn,
                         "precisao": precision, "revocacao": recall, "f1": f1,
                         "conjuntos_exatos": contagem["conjuntos_exatos"],
                         "conjuntos_avaliados": contagem["conjuntos_avaliados"]},
        "campos": dict(campos),
    }


def detalhes_de_erro(exc: Exception) -> dict:
    # Não exibir input, mensagem original da API, token ou resposta completa.
    causa = exc.__cause__
    dado = {"mensagem": str(exc), "causa": type(causa).__name__ if causa else None}
    if causa and hasattr(causa, "errors"):
        try:
            erros = causa.errors(include_input=False, include_context=False, include_url=False)
            dado["validacoes"] = [
                {"campo": ".".join(map(str, e.get("loc", []))) or "raiz", "tipo": e.get("type")}
                for e in erros[:3]
            ]
        except (TypeError, ValueError):
            pass
    return dado


def executar():
    parser = argparse.ArgumentParser(description="Avaliar interpretação de perfis do SingMatch.")
    parser.add_argument("--modo", choices=("contrato", "real"), required=True)
    parser.add_argument("--cenario", choices=("simples", "combinadas", "formato", "ambiguidades", "todos"), default="todos")
    parser.add_argument("--limite", type=int, default=0, help="0 = todos os casos do cenário; use 3 no teste inicial")
    parser.add_argument("--repeticoes", type=int, default=1, help="Execuções independentes por frase (pode consumir créditos)")
    parser.add_argument("--modelo", default=None, help="Modelo OpenAI, opcional; por padrão respeita OPENAI_MODEL")
    args = parser.parse_args()
    if args.limite < 0 or args.repeticoes < 1:
        parser.error("--limite deve ser >= 0 e --repeticoes >= 1")

    songs, karaokes = carregar_catalogo()
    selecionados = [item for item in CASOS if args.cenario == "todos" or item["cenario"] == args.cenario]
    if args.limite:
        selecionados = selecionados[:args.limite]
    validar_casos(CASOS, songs)
    print(f"Catálogo local: {len(songs)} músicas, {karaokes} karaokês aprovados")
    print(f"Casos selecionados: {len(selecionados)} de {len(CASOS)} (cenário: {args.cenario})")
    por_grupo = Counter(item["cenario"] for item in selecionados)
    print("Distribuição:", dict(por_grupo))

    if args.modo == "contrato":
        print("MODO CONTRATO: frases, labels esperadas e catálogo conferidos. Nenhuma chamada ao GPT.")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("Configure OPENAI_API_KEY no ambiente ou no .env antes do modo real")

    resultados = []
    total = len(selecionados) * args.repeticoes
    atual = 0
    for item in selecionados:
        for repeticao in range(1, args.repeticoes + 1):
            atual += 1
            print(f"\n[{atual}/{total}] {item['id']} ({item['cenario']}) | repetição {repeticao}/{args.repeticoes}", flush=True)
            registro = {"caso_id": item["id"], "cenario": item["cenario"],
                        "texto_ficticio": item["texto"], "repeticao": repeticao,
                        "esperado": item["esperado"]}
            try:
                perfil = interpretar_perfil(item["texto"], songs, model=args.modelo)
                registro["observado"] = perfil.model_dump(mode="json")
                aval = avaliar(item, perfil)
                registro["avaliacao"] = aval
                print("  Resultado:", "PASSOU" if aval["aprovado"] else "DIVERGIU")
                for campo, resultado in aval["labels"].items():
                    print(f"  {campo}: esperado [{mostrar_pares(set(map(tuple, resultado['esperadas'])))}] | "
                          f"observado [{mostrar_pares(set(map(tuple, resultado['observadas'])))}]")
                    if resultado["extras"] or resultado["ausentes"]:
                        print(f"    extras={resultado['extras']} ausentes={resultado['ausentes']}")
                for campo, resultado in aval["campos"].items():
                    if not resultado["ok"]:
                        print(f"  {campo}: esperado {resultado['esperado']} | observado {resultado['observado']}")
                if item["cenario"] == "ambiguidades":
                    print(f"  Perguntas: {perfil.questions}")
            except (LLMServiceError, ValueError) as exc:
                registro["erro"] = detalhes_de_erro(exc)
                print("  ERRO:", registro["erro"])
            resultados.append(registro)

    indicadores = resumo(resultados)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    saida = OUTPUT / f"avaliacao_perfis_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    documento = {"executado_em": datetime.now().astimezone().isoformat(),
                 "modo": args.modo, "cenario": args.cenario, "repeticoes": args.repeticoes,
                 "modelo_solicitado": args.modelo or os.getenv("OPENAI_MODEL") or "padrao_do_backend",
                 "metricas": indicadores, "resultados": resultados,
                 "nota": "Métricas de labels usam correspondência exata normalizada; casos ambíguos avaliam perguntas, não labels. Textos são fictícios."}
    saida.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRelatório salvo em: {saida}")
    print(f"Respostas: {indicadores['casos_respondidos']}/{indicadores['casos_totais']}; "
          f"casos integralmente corretos: {indicadores['casos_integralmente_corretos']}; "
          f"erros: {indicadores['erros']}")
    labels = indicadores["labels_micro"]
    def percentual(x):
        return f"{x * 100:.1f}%" if x is not None else "não aplicável"
    print(f"Labels: precisão={percentual(labels['precisao'])}; "
          f"revocação={percentual(labels['revocacao'])}; F1={percentual(labels['f1'])}")
    for nome in ("preferred_format", "duet_allowed", "questions_required"):
        n, ok = indicadores["campos"].get(nome + "_avaliados", 0), indicadores["campos"].get(nome + "_corretos", 0)
        if n:
            print(f"{nome}: {ok}/{n} ({ok/n:.1%})")
    print("Medição experimental: casos pequenos e textos fictícios; não representa todos os usuários.")


if __name__ == "__main__":
    try:
        executar()
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERRO DE CONFIGURAÇÃO: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
