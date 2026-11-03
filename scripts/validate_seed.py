"""Valida o piloto local, sem fazer chamadas ao YouTube nem ao banco."""
import json
from pathlib import Path
import re

file = Path(__file__).resolve().parents[1] / "data" / "catalogo_piloto.json"
data = json.loads(file.read_text(encoding="utf-8"))
songs = data["songs"]
versions = data["karaoke_versions"]
ids = [m["id"] for m in songs]
assert len(ids) == len(set(ids)), "IDs de músicas duplicados"
assert len(ids) == 5, "Piloto deveria conter cinco músicas"
assert all(m["genre"] == "forro" for m in songs)
assert all(1 <= m["energy"] <= 5 for m in songs)
assert all(m["title"] and m["artists"] for m in songs)
video_ids = [v["youtube_video_id"] for v in versions]
assert len(video_ids) == len(set(video_ids)), "Vídeos duplicados no piloto"
assert all(v["song_id"] in ids for v in versions)
assert all(re.fullmatch(r"[A-Za-z0-9_-]{11}", v["youtube_video_id"]) for v in versions)
assert len(versions) == len(songs)
print(f"OK: {len(songs)} músicas e {len(versions)} versões de karaokê no piloto.")
print("Atenção: isso NÃO verifica incorporação atual nem direitos de uso.")
