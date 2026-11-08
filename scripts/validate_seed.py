"""Valida os catálogos locais, sem fazer chamadas ao YouTube nem ao banco."""
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parents[1] / "data"
LRC_LINE = re.compile(r"^\[\d{2}:\d{2}\.\d{2}\].*$")

# --- Piloto: 5 músicas com vídeo de karaokê curado pela equipe ---
data = json.loads((DATA / "catalogo_piloto.json").read_text(encoding="utf-8"))
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

# --- Catálogo ampliado: gerado por scripts/build_catalog.py ---
expanded_path = DATA / "catalogo_forro.json"
if expanded_path.is_file():
    exp = json.loads(expanded_path.read_text(encoding="utf-8"))
    exp_ids = [m["id"] for m in exp["songs"]]
    assert len(exp_ids) == len(set(exp_ids)), "IDs duplicados no catálogo ampliado"
    assert not set(exp_ids) & set(ids), "ID do catálogo ampliado colide com o piloto"
    all_videos = video_ids + [v["youtube_video_id"] for v in exp["karaoke_versions"]]
    assert len(all_videos) == len(set(all_videos)), "Vídeo repetido entre catálogos"
    for m in exp["songs"]:
        assert m["genre"] == "forro" and m["title"] and m["artists"], m["id"]
        assert m["mood"] and m["energy"] and 1 <= m["energy"] <= 5, f"{m['id']} sem clima/energia"
    for v in exp["karaoke_versions"]:
        assert v["song_id"] in exp_ids, v["id"]
        assert v["kind"] in ("letra_sincronizada", "karaoke"), v["id"]
        if v["kind"] == "karaoke":
            continue  # vídeo de karaokê já traz a letra
        lines = (DATA / v["lyrics_file"]).read_text(encoding="utf-8").splitlines()
        assert lines and all(LRC_LINE.match(x) for x in lines), f"LRC inválido em {v['lyrics_file']}"
    kar = sum(1 for v in exp["karaoke_versions"] if v["kind"] == "karaoke")
    print(f"OK: {len(exp_ids)} músicas novas, todas com letra sincronizada; {kar} também com karaokê.")
print("Atenção: isso NÃO verifica incorporação atual nem direitos de uso.")
