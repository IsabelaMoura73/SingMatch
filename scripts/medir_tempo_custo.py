"""Mede tempo, tokens e custo de uma geração do SingMatch por tamanho de sala.

Cada sala = N participantes fictícios: N interpretações de perfil + 1 roteiro solo.
Por padrão mede salas de 1 a 5 pessoas (P1..P5; P1-P3 são os mesmos de
avaliar_fluxo_integrado.py). Cada chamada à IA é cronometrada e os tokens vêm do
campo `usage` que a própria API devolve (não é estimativa). Tentativas de reparo
aparecem como chamadas extras.

Rode na raiz do repositório:
  PYTHONPATH=.:backend python3 scripts/medir_tempo_custo.py --modo simulado
  PYTHONPATH=.:backend python3 scripts/medir_tempo_custo.py --modo real
  PYTHONPATH=.:backend python3 scripts/medir_tempo_custo.py --modo real --pessoas 3 --repeticoes 5

O modo simulado não chama a API (serve só para conferir o script; os números
dele NÃO valem para apresentação). Nada é gravado no banco.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime

from app.llm import DEFAULT_MODEL, LLMServiceError, compor_roteiro_solo, interpretar_perfil
from app.matching import MatchingError
from app.schemas import ProfileConfirmed
from scripts.avaliar_fluxo_integrado import (
    ESPERADO as ESPERADO_BASE, INTENCAO, OUTPUT, ROOT, TEXTOS as TEXTOS_BASE,
    carregar_catalogo, pares, pares_esperados, verificar_roteiro,
)

# P4 e P5 completam a sala de 5 pessoas; referência definida antes das chamadas.
TEXTOS = {
    **TEXTOS_BASE,
    "P4": "Quero cantar Luiz Gonzaga, mas nada sofrido.",
    "P5": "Gosto de Falamansa e de músicas festivas.",
}
ESPERADO = {
    **ESPERADO_BASE,
    "P4": {"likes": [("artist", "Luiz Gonzaga")], "vetoes": [("tag", "sofrida")]},
    "P5": {"likes": [("artist", "Falamansa"), ("tag", "festiva")], "vetoes": []},
}
PARTICIPANTES = list(TEXTOS)

# US$ por 1 milhão de tokens (entrada, saída). Conferir em https://openai.com/api/pricing
PRECOS = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.1-terra": (1.00, 5.00),
}


class ClienteMedido:
    """Repassa as chamadas ao cliente real e registra tempo e tokens de cada uma."""

    def __init__(self, cliente):
        self._cliente = cliente
        self.responses = self
        self.etapa = ""
        self.chamadas: list[dict] = []

    def parse(self, **kwargs):
        registro = {"etapa": self.etapa, "modelo": kwargs.get("model")}
        inicio = time.perf_counter()
        try:
            resposta = self._cliente.responses.parse(**kwargs)
        except Exception as exc:
            registro.update(segundos=time.perf_counter() - inicio, erro=type(exc).__name__)
            self.chamadas.append(registro)
            raise
        registro["segundos"] = time.perf_counter() - inicio
        usage = getattr(resposta, "usage", None)
        detalhes = getattr(usage, "input_tokens_details", None)
        registro.update(
            modelo=getattr(resposta, "model", None) or registro["modelo"],
            tokens_entrada=getattr(usage, "input_tokens", None),
            tokens_saida=getattr(usage, "output_tokens", None),
            tokens_entrada_cache=getattr(detalhes, "cached_tokens", None),
        )
        self.chamadas.append(registro)
        return resposta


class _Resposta:
    def __init__(self, parsed):
        self.status, self.output_parsed, self.usage, self.model = "completed", parsed, None, "simulado"


class ClienteSimulado:
    """Responde sem API: perfis esperados e um roteiro qualquer dentro dos permitidos."""

    def __init__(self):
        self.responses = self

    def parse(self, *, input, text_format, **_):
        data = json.loads(input)
        time.sleep(0.05)
        if "texto" in data:
            pid = next(p for p, t in TEXTOS.items() if t == data["texto"])
            label = lambda c, v: {"category": c, "value": v, "evidence": data["texto"]}
            return _Resposta(text_format.model_validate({
                "likes": [label(c, v) for c, v in ESPERADO[pid]["likes"]],
                "vetoes": [label(c, v) for c, v in ESPERADO[pid]["vetoes"]],
                "preferred_format": "indiferente", "duet_allowed": None, "questions": [],
            }))
        usados, itens = set(), []
        for pos, pid in enumerate(data["required_participant_ids"], start=1):
            vid = next(v for v in data["participants"][pid]["allowed_karaoke_version_ids"] if v not in usados)
            usados.add(vid)
            itens.append({"position": pos, "karaoke_version_id": vid,
                          "participant_ids": [pid], "justification": "Simulado."})
        return _Resposta(text_format.model_validate({"title": "Simulado", "items": itens}))


def perfil_correto(pid: str, draft) -> bool:
    esperado = ESPERADO[pid]
    return (pares(draft.likes) == pares_esperados(esperado["likes"])
            and pares(draft.vetoes) == pares_esperados(esperado["vetoes"])
            and not draft.questions)


def custo(chamada: dict, precos: tuple[float, float] | None) -> float | None:
    if not precos or chamada.get("tokens_entrada") is None:
        return None
    entrada, saida = precos
    return (chamada["tokens_entrada"] * entrada + chamada["tokens_saida"] * saida) / 1_000_000


def soma(valores):
    valores = [v for v in valores if v is not None]
    return sum(valores) if valores else None


def fmt(valor, formato: str) -> str:
    return "—" if valor is None else format(valor, formato)


def media(valores):
    valores = [v for v in valores if v is not None]
    return statistics.mean(valores) if valores else None


def sala(cliente: ClienteMedido, pids: list[str], songs, versions, modelo, precos) -> dict:
    inicio_cliente = len(cliente.chamadas)
    resultado: dict = {"pessoas": len(pids), "participantes": pids, "perfis_corretos": 0, "erro": None}
    try:
        profiles = {}
        for pid in pids:
            cliente.etapa = f"interpretacao {pid}"
            draft = interpretar_perfil(TEXTOS[pid], songs, client=cliente, model=modelo)
            resultado["perfis_corretos"] += perfil_correto(pid, draft)
            profiles[pid] = ProfileConfirmed.model_validate(draft.model_dump())
        cliente.etapa = "roteiro"
        roteiro = compor_roteiro_solo("forro", INTENCAO, profiles, songs, versions, client=cliente, model=modelo)
        analise = verificar_roteiro(roteiro, profiles, songs, versions)
        resultado.update(
            afinidade_labels=analise["afinidade_labels"],
            afinidade_pessoas=analise["afinidade_pessoas"],
            vetos_violados=len(analise["vetos_violados"]),
            energia_nao_decrescente=analise["progressao_energia_nao_decrescente"],
        )
    except (LLMServiceError, MatchingError, ValueError, KeyError) as exc:
        resultado["erro"] = f"{type(exc).__name__}: {exc}"
    chamadas = cliente.chamadas[inicio_cliente:]
    for c in chamadas:
        c["custo_usd"] = custo(c, precos)
    interp = [c for c in chamadas if c["etapa"].startswith("interpretacao")]
    rot = [c for c in chamadas if c["etapa"] == "roteiro"]
    resultado.update(
        chamadas=chamadas,
        segundos_total=sum(c["segundos"] for c in chamadas),
        segundos_interpretacao_media=media(c["segundos"] for c in interp),
        segundos_roteiro=sum(c["segundos"] for c in rot) if rot else None,
        tentativas_roteiro=len(rot),
        tokens_entrada=soma(c.get("tokens_entrada") for c in chamadas),
        tokens_saida=soma(c.get("tokens_saida") for c in chamadas),
        tokens_entrada_roteiro=soma(c.get("tokens_entrada") for c in rot),
        custo_usd=soma(c["custo_usd"] for c in chamadas),
    )
    return resultado


def tamanhos(texto: str) -> list[int]:
    """'1-5' -> [1..5]; '3' -> [3]; '1,3,5' -> [1, 3, 5]."""
    valores: list[int] = []
    for parte in texto.split(","):
        inicio, _, fim = parte.strip().partition("-")
        valores += range(int(inicio), int(fim or inicio) + 1)
    if not valores or any(not 1 <= v <= len(PARTICIPANTES) for v in valores):
        raise ValueError
    return valores


def executar():
    parser = argparse.ArgumentParser(description="Medir tempo, tokens e custo por tamanho de sala.")
    parser.add_argument("--modo", required=True, choices=("simulado", "real"))
    parser.add_argument("--pessoas", default="1-5",
                        help=f"tamanhos de sala, ex.: 1-5, 3 ou 1,3,5 (máx. {len(PARTICIPANTES)})")
    parser.add_argument("--repeticoes", type=int, default=1, help="salas medidas por tamanho (1 a 5)")
    parser.add_argument("--modelo", default=None, help="padrão: OPENAI_MODEL do .env ou " + DEFAULT_MODEL)
    parser.add_argument("--preco-entrada", type=float, help="US$ por 1M tokens de entrada (sobrepõe a tabela)")
    parser.add_argument("--preco-saida", type=float, help="US$ por 1M tokens de saída (sobrepõe a tabela)")
    args = parser.parse_args()
    try:
        lista_tamanhos = tamanhos(args.pessoas)
    except ValueError:
        parser.error(f"--pessoas inválido; use algo como 1-5, 3 ou 1,3,5 (de 1 a {len(PARTICIPANTES)})")
    if not 1 <= args.repeticoes <= 5:
        parser.error("--repeticoes deve ficar entre 1 e 5")
    if (args.preco_entrada is None) != (args.preco_saida is None):
        parser.error("informe --preco-entrada e --preco-saida juntos")

    if args.modo == "real":
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        if not os.getenv("OPENAI_API_KEY"):
            parser.error("Configure OPENAI_API_KEY no terminal ou no .env antes do modo real")
        from openai import OpenAI
        base = OpenAI(timeout=45.0, max_retries=1)
    else:
        base = ClienteSimulado()
    modelo = args.modelo or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
    precos = ((args.preco_entrada, args.preco_saida) if args.preco_entrada is not None
              else PRECOS.get(modelo.removeprefix("openai/")))

    songs, versions = carregar_catalogo()
    cliente = ClienteMedido(base)
    print(f"Modo: {args.modo} · modelo: {modelo} · salas de {args.pessoas} pessoa(s) · "
          f"{args.repeticoes} repetição(ões) por tamanho")
    if os.getenv("OPENAI_BASE_URL"):
        print("Atenção: OPENAI_BASE_URL está definida (ex.: OpenRouter); os números não são da OpenAI direta.")
    if precos:
        print(f"Preço usado: US$ {precos[0]} entrada / US$ {precos[1]} saída por 1M tokens")
    else:
        print("Sem preço para esse modelo: use --preco-entrada e --preco-saida para calcular o custo.")
    if args.modo == "simulado":
        print("MODO SIMULADO: nenhuma chamada à API; NÃO use estes números nos slides.")

    salas = []
    for n in lista_tamanhos:
        pids = PARTICIPANTES[:n]
        for rep in range(1, args.repeticoes + 1):
            print(f"\nSala com {n} pessoa(s) ({', '.join(pids)})"
                  + (f" · repetição {rep}/{args.repeticoes}" if args.repeticoes > 1 else ""))
            r = sala(cliente, pids, songs, versions, modelo, precos)
            salas.append(r)
            for c in r["chamadas"]:
                print(f"  {c['etapa']:<18} {c['segundos']:5.2f} s  "
                      f"entrada {fmt(c.get('tokens_entrada'), 'd'):>6}  saída {fmt(c.get('tokens_saida'), 'd'):>5}  "
                      f"US$ {fmt(c['custo_usd'], '.6f')}" + (f"  ERRO {c['erro']}" if c.get("erro") else ""))
            print(f"  Total: {r['segundos_total']:.2f} s · US$ {fmt(r['custo_usd'], '.6f')} · "
                  f"perfis corretos {r['perfis_corretos']}/{n}")
            if r["erro"]:
                print(f"  ERRO: {r['erro']}")
            else:
                print(f"  Qualidade: afinidade {r['afinidade_labels']:.0%} · vetos violados {r['vetos_violados']} · "
                      f"energia não decrescente: {r['energia_nao_decrescente']} · "
                      f"tentativas do roteiro: {r['tentativas_roteiro']}")

    print("\n=== Resumo por tamanho de sala (média das salas sem erro) ===")
    cabecalho = (f"{'Pessoas':>7} | {'Ok':>5} | {'Tempo total':>11} | {'Interp. (média)':>15} | "
                 f"{'Roteiro':>8} | {'Tokens entr.':>12} | {'Tokens saída':>12} | {'Custo US$':>10} | "
                 f"{'Afinid.':>7} | {'Vetos':>5} | {'Reparos':>7}")
    print(cabecalho)
    print("-" * len(cabecalho))
    for n in lista_tamanhos:
        grupo = [r for r in salas if r["pessoas"] == n]
        ok = [r for r in grupo if not r["erro"]]
        m = lambda chave: media(r.get(chave) for r in ok)
        print(f"{n:>7} | {len(ok):>2}/{len(grupo):<2} | {fmt(m('segundos_total'), '.2f'):>9} s | "
              f"{fmt(m('segundos_interpretacao_media'), '.2f'):>13} s | {fmt(m('segundos_roteiro'), '.2f'):>6} s | "
              f"{fmt(m('tokens_entrada'), '.0f'):>12} | {fmt(m('tokens_saida'), '.0f'):>12} | "
              f"{fmt(m('custo_usd'), '.5f'):>10} | {fmt(m('afinidade_labels'), '.0%'):>7} | "
              f"{fmt(sum(r['vetos_violados'] for r in ok) if ok else None, 'd'):>5} | "
              f"{sum(r['tentativas_roteiro'] > 1 for r in grupo):>3}/{len(grupo):<3}")
    custos = [r["custo_usd"] for r in salas if not r["erro"] and r["custo_usd"] is not None]
    if custos:
        print(f"\nCusto médio por sala (todos os tamanhos): US$ {statistics.mean(custos):.5f} · "
              f"1.000 salas: US$ {statistics.mean(custos) * 1000:.2f}")
    print("Perfis interpretados corretamente:",
          f"{sum(r['perfis_corretos'] for r in salas)}/{sum(r['pessoas'] for r in salas)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"medicao_tempo_custo_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({
        "modo": args.modo, "modelo": modelo, "precos_por_milhao": precos,
        "base_url_alternativa": bool(os.getenv("OPENAI_BASE_URL")),
        "tamanhos": lista_tamanhos, "repeticoes": args.repeticoes,
        "executado_em": datetime.now().astimezone().isoformat(), "salas": salas,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRelatório salvo em: {path}")


if __name__ == "__main__":
    executar()
