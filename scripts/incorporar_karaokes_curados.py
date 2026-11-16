#!/usr/bin/env python3
"""Incorpora karaokês revisados ao catálogo e à auditoria.

Não acessa o banco de dados nem faz chamadas de rede.
Pode ser executado novamente sem duplicar os registros.
"""
import csv
import json
import re
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CATALOG = DATA / "catalogo_forro.json"
CURATED = DATA / "fontes" / "karaokes_curados.json"
AUDIT = DATA / "fontes" / "auditoria_karaoke.csv"
VERIFIED = DATA / "fontes" / "videos_verificados.json"


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    verified = json.loads(VERIFIED.read_text(encoding="utf-8"))

    ok = set(verified.get("ok", []))
    blocked = set(verified.get("bloqueados", []))

    with AUDIT.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        audit_rows = list(reader)

    if not fields:
        raise ValueError("CSV de auditoria sem cabeçalho.")

    songs = {s["id"]: s for s in catalog["songs"]}
    versions = catalog["karaoke_versions"]

    existing_ids = {v["id"]: v for v in versions}
    existing_audit = {r["version_id"]: r for r in audit_rows}

    used_videos = {
        v["youtube_video_id"]
        for v in versions
    }

    pilot = json.loads(
        (DATA / "catalogo_piloto.json").read_text(encoding="utf-8")
    )
    used_videos.update(
        v["youtube_video_id"] for v in pilot["karaoke_versions"]
    )

    added = 0
    seen = set()

    for entry in curated["aprovados"]:
        song_id = entry["song_id"]
        video_id = entry["youtube_video_id"]
        verified_at = entry["verified_at"]
        version_id = f"KAR-{video_id}"

        # 1. Conferir a identidade da música e do vídeo.
        if song_id not in songs:
            raise ValueError(f"Música inexistente: {song_id}")

        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError(f"ID de YouTube inválido: {video_id}")

        date.fromisoformat(verified_at)

        if version_id in seen:
            raise ValueError(f"Escolha duplicada: {version_id}")
        seen.add(version_id)

        # 2. Exigir reprodução previamente verificada.
        if video_id not in ok or video_id in blocked:
            raise ValueError(f"Vídeo não liberado: {video_id}")

        # 3. Não criar duas versões principais para a mesma música.
        other = [
            v for v in versions
            if v["song_id"] == song_id
            and v.get("kind", "karaoke") == "karaoke"
            and v["id"] != version_id
        ]
        if other:
            raise ValueError(
                f"A música {song_id} já possui outro karaokê."
            )

        # 4. Evitar reutilização ou alteração indevida de IDs.
        existing = existing_ids.get(version_id)

        if existing:
            if (
                existing["song_id"] != song_id
                or existing["youtube_video_id"] != video_id
                or existing.get("kind", "karaoke") != "karaoke"
            ):
                raise ValueError(f"Conflito na versão {version_id}")
        elif video_id in used_videos:
            raise ValueError(f"Vídeo já utilizado: {video_id}")

        # 5. Preparar registro da auditoria.
        audit_row = existing_audit.get(version_id)
        url = f"https://www.youtube.com/watch?v={video_id}"

        if audit_row:
            if (
                audit_row["youtube_url"] != url
                or audit_row["status"] != "aprovado"
                or any(
                    audit_row[field] != "sim"
                    for field in (
                        "instrumental",
                        "letra_correta",
                        "reproducao",
                    )
                )
            ):
                raise ValueError(
                    f"Auditoria existente incompatível: {version_id}"
                )
        else:
            song = songs[song_id]

            row = {
                "version_id": version_id,
                "musica": song["title"],
                "artista": ", ".join(song["artists"]),
                "youtube_url": url,
                "instrumental": "sim",
                "letra_correta": "sim",
                "reproducao": "sim",
                "status": "aprovado",
                "observacoes": (
                    f"Revisão manual de áudio e letra em {verified_at}"
                ),
            }

            audit_rows.append(row)
            existing_audit[version_id] = row

        # 6. Adicionar a versão somente se ainda não existir.
        if not existing:
            version = {
                "id": version_id,
                "song_id": song_id,
                "youtube_video_id": video_id,
                "kind": "karaoke",
                "duration_seconds": None,
                "approved": True,
                "verified_at": verified_at,
                "rights_reviewed": False,
                "video_origin": "auditoria_manual",
            }

            versions.append(version)
            existing_ids[version_id] = version
            used_videos.add(video_id)
            added += 1

    # Somente escrever depois de validar todas as escolhas.
    CATALOG.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with AUDIT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(audit_rows)

    print(f"Novas versões adicionadas: {added}")
    print(f"Total de versões de karaokê auditadas: {len(audit_rows)}")


if __name__ == "__main__":
    main()