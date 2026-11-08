#!/usr/bin/env python3
"""Mescla o JSON copiado de /verificar.html em data/fontes/videos_verificados.json.

Uso:
    python3 scripts/registrar_verificacao.py resultado.json
    (ou cole o JSON na entrada padrão)

O resultado mais recente de cada vídeo prevalece. Depois rode
`python3 scripts/build_catalog.py` para o catálogo usar só vídeos aprovados.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "data" / "fontes" / "videos_verificados.json"


def merge(current: dict, new: dict) -> dict:
    status = {v: "ok" for v in current.get("ok", [])}
    status.update({v: "bloqueados" for v in current.get("bloqueados", [])})
    status.update({v: "ok" for v in new.get("ok", [])})
    status.update({v: "bloqueados" for v in new.get("bloqueados", [])})
    runs = current.get("rodadas", []) + [{k: new.get(k) for k in ("origem", "verificado_em")} |
                                         {"ok": len(new.get("ok", [])), "bloqueados": len(new.get("bloqueados", [])),
                                          "sem_resposta": len(new.get("timeout", []))}]
    return {
        "nota": "Gerado por scripts/registrar_verificacao.py a partir de /verificar.html (player incorporado real).",
        "rodadas": runs,
        "ok": sorted(v for v, s in status.items() if s == "ok"),
        "bloqueados": sorted(v for v, s in status.items() if s == "bloqueados"),
    }


def main() -> None:
    raw = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read()
    new = json.loads(raw)
    current = json.loads(TARGET.read_text(encoding="utf-8")) if TARGET.is_file() else {}
    merged = merge(current, new)
    TARGET.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{TARGET.name}: {len(merged['ok'])} ok, {len(merged['bloqueados'])} bloqueados.")


if __name__ == "__main__":
    main()
