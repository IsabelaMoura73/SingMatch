#!/usr/bin/env python3
"""Gera o catálogo ampliado de forró com vídeos de letra sincronizada.

Só usa biblioteca padrão. Roda uma vez na máquina de quem cuida dos dados; o
resultado (JSON + arquivos .lrc) é versionado e o deploy NÃO acessa a rede.

Fontes de MÚSICAS (identidade da obra):
  * BYRM (Zenodo 16617888): título, canal e ID do YouTube da gravação original.
  * UFMG (Zenodo 12733931): título, artista e emoções da letra. O rótulo
    "forró" dessa base é ruidoso (Xuxa, Anitta, Lulu Santos...), por isso só
    entram artistas listados em UFMG_FORRO_ARTISTS.

Para cada música:
  1. Busca a letra sincronizada (LRC) no LRCLIB.
  2. Usa o vídeo do dataset se a duração bater com a letra (±3 s); senão,
     procura no YouTube um upload oficial com a mesma duração da letra.
  3. Confere no YouTube se o vídeo existe e permite incorporação.
  4. Aplica a curadoria de clima/energia (`data/curadoria_forro.json`).

Uso:
    python3 scripts/build_catalog.py               # rede + cache em data/.cache
    python3 scripts/build_catalog.py --offline     # só cache
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
USER_AGENT = "Mozilla/5.0 (SingMatch academic prototype; github.com/IsabelaMoura73/SingMatch)"
BYRM_SOURCE = "byrm_zenodo_16617888"
UFMG_SOURCE = "ufmg_zenodo_12733931"
PESQUISA_SOURCE = "pesquisa_lrclib_2026-11"
LRCLIB_SOURCE = "lrclib.net"
DURATION_TOLERANCE_S = 3.0
UFMG_FORRO_ARTISTS = {"/avioes-do-forro/": "Aviões do Forró"}

NOISE = [
    r"\(\s*[áa]udio oficial\s*\)", r"\(\s*clipe oficial\s*\)", r"\(\s*v[íi]deo oficial\s*\)",
    r"\(\s*official (?:audio|video)\s*\)", r"-\s*oficial\s*$", r"-\s*10 anos de carreira vol\.?\s*\d+",
    r"\(\s*cantam luiz gonzaga[^)]*\)", r"-\s*ao vivv?o\s*$", r"\(\s*ao vivo\s*\)", r"\(\s*live\s*\)",
]
FEAT = re.compile(r"\(\s*(?:feat\.?|part\.?|participa[çc][ãa]o(?: especial)?(?: de)?)\s*([^)]*)\)", re.I)
FEAT_INLINE = re.compile(r"\s+(?:part\.|feat\.)\s+(.+)$", re.I)
# Upload que NÃO é a gravação original (a letra sairia dessincronizada ou é outra versão).
BAD_UPLOAD = re.compile(
    r"karaok|cover|remix|piseiro|vers[aã]o|playback|instrumental|dancinha|coreografia|react|rea[cç][aã]o|"
    r"aula|tutorial|cifra|slowed|speed ?up|\b8d\b|acapella|ac[uú]stico|medley|pot.?pourri|\bdj\b|letra|\bgrave\b|pared[aã]o",
    re.I)


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().strip())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return " ".join(value.split())


def base_title(title: str) -> str:
    title = re.sub(r"\(.*?\)|\[.*?\]", "", title)
    title = re.sub(r"\s+-\s+(?:ao vivo|live|remaster\w*|.*vers[aã]o.*)\s*$", "", title, flags=re.I)
    return norm(title)


# Palavras que podem aparecer no título de um upload oficial sem mudar a música.
UPLOAD_WORDS = {"ao", "vivo", "dvd", "vol", "oficial", "official", "clipe", "clip", "video", "audio",
                "part", "feat", "ft", "participacao", "especial", "topic", "album", "hd", "remastered",
                "remaster", "anos", "de", "do", "da", "e", "em", "no", "na", "com"}
ARTIST_ALIASES = {"avioes do forro": ["xand aviao", "solange almeida", "avioes", "aviao"]}


def video_matches(title: str, artists: list[str], video_title: str, channel: str, exact: bool = False) -> bool:
    """O upload precisa ser a música (não outra que contenha o título) do artista principal."""
    if "/" in video_title and "/" not in title:
        return False  # pot-pourri
    primary = norm(artists[0])
    if primary not in norm(video_title) and primary not in norm(channel):
        return False
    text = " " + norm(re.sub(r"\(.*?\)|\[.*?\]", " ", video_title)) + " "
    names = [norm(a) for a in artists] + [norm(channel.removesuffix(" - Topic"))]
    names += [alias for a in artists for alias in ARTIST_ALIASES.get(norm(a), [])]
    for name in sorted(filter(None, names), key=len, reverse=True):
        text = text.replace(f" {name} ", " ")
    words = Counter(w for w in text.split() if not w.isdigit() and w not in UPLOAD_WORDS)
    wanted = Counter(w for w in base_title(title).split() if w not in UPLOAD_WORDS)

    def same(a: str, b: str) -> bool:  # "costa" ~ "costas", "acaua" ~ "acaua"
        return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 2)

    missing = sum(max(0, n - sum(c for w, c in words.items() if same(w, word))) for word, n in wanted.items())
    extra = sum(c for w, c in words.items() if not any(same(w, x) for x in wanted))
    # Título curto ("Me Acha", "Dói Dói") não pode perder palavra nenhuma: "Me Perdoa" não é "Me Acha".
    allowed_missing = 1 if sum(wanted.values()) >= 3 and not exact else 0
    return missing <= allowed_missing and extra <= 2


# ---------------------------------------------------------------- HTTP + cache

class Http:
    def __init__(self, cache_dir: Path, offline: bool, delay: float = 0.2):
        self.cache_dir, self.offline, self.delay = cache_dir, offline, delay
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> tuple[int, str]:
        path = self.cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.json"
        if path.is_file():
            cached = json.loads(path.read_text(encoding="utf-8"))
            return cached["status"], cached["body"]
        if self.offline:
            return 0, ""
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept-Language": "pt-BR,pt;q=0.9"})
        status, body = 0, ""
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=25) as resp:
                    status, body = resp.status, resp.read().decode("utf-8", "replace")
                break
            except urllib.error.HTTPError as exc:
                status, body = exc.code, ""
                if exc.code < 500 and exc.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError):
                status, body = 0, ""
            time.sleep(2.0 * (attempt + 1))
        time.sleep(self.delay)
        if status in (200, 400, 401, 403, 404):  # falha temporária não vai para o cache
            path.write_text(json.dumps({"url": url, "status": status, "body": body}), encoding="utf-8")
        return status, body


# ------------------------------------------------------- título/artista do BYRM

def strip_noise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for pattern in NOISE:
        text = re.sub(pattern, "", text, flags=re.I)
    return " ".join(text.replace("\"", "").split()).strip(" -")


def split_feats(title: str) -> tuple[str, list[str]]:
    feats: list[str] = []
    for match in FEAT.finditer(title):
        feats += [p.strip() for p in re.split(r",|&| e ", match.group(1)) if p.strip()]
    title = FEAT.sub("", title)
    inline = FEAT_INLINE.search(title)
    if inline:
        feats += [p.strip() for p in re.split(r",|&| e ", inline.group(1)) if p.strip()]
        title = title[: inline.start()]
    return " ".join(title.split()).strip(" -"), feats


def parse_byrm(rows: list[dict]) -> list[dict]:
    """Separa título/artista; casos ambíguos são corrigidos em ajustes_byrm.json."""
    lefts: dict[str, int] = {}
    rights: dict[str, int] = {}
    for row in rows:
        parts = [p.strip() for p in strip_noise(row["video_title"]).split(" - ")]
        if len(parts) >= 2:
            lefts[norm(parts[0])] = lefts.get(norm(parts[0]), 0) + 1
            rights[norm(parts[-1])] = rights.get(norm(parts[-1]), 0) + 1
    known = {norm(r["channel"].removesuffix(" - Topic")) for r in rows if r["channel"].endswith(" - Topic")}
    known |= {k for k, n in lefts.items() if n >= 2} | {k for k, n in rights.items() if n >= 2}
    parsed = []
    for row in rows:
        name = strip_noise(row["video_title"])
        if row["channel"].endswith(" - Topic"):
            artist, title = row["channel"].removesuffix(" - Topic"), name
        else:
            parts = [p.strip() for p in name.split(" - ") if p.strip()]
            if len(parts) >= 2 and norm(parts[-1]) in known and norm(parts[0]) not in known:
                title, artist = " - ".join(parts[:-1]), parts[-1]
            elif len(parts) >= 2:
                artist, title = parts[0], " - ".join(parts[1:])
            else:
                artist, title = row["channel"], name
        title, feats = split_feats(title)
        artists = [a.strip() for a in re.split(r"\s+&\s+", artist) if a.strip()] + feats
        parsed.append({**row, "title": title, "artists": artists})
    return parsed


# ---------------------------------------------------------- YouTube e LRCLIB

def youtube_info(http: Http, video_id: str) -> dict:
    """Duração e incorporação: oEmbed 401/403 ou playableInEmbed=false bloqueiam."""
    status, _ = http.get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        f"https://www.youtube.com/watch?v={video_id}"))
    info = {"oembed_status": status, "embeddable": status == 200, "duration_seconds": None,
            "playability": None}
    status, html = http.get(f"https://www.youtube.com/watch?v={video_id}&hl=pt-BR&gl=BR")
    if status == 200:
        length = re.search(r'"lengthSeconds":"(\d+)"', html)
        info["duration_seconds"] = int(length.group(1)) if length else None
        playability = re.search(r'"playabilityStatus":\{"status":"([A-Z_]+)"', html)
        info["playability"] = playability.group(1) if playability else None
        if '"playableInEmbed":false' in html or info["playability"] not in (None, "OK"):
            info["embeddable"] = False
    return info


def _duration(text: str | None) -> int | None:
    if not text:
        return None
    seconds = 0
    for part in text.split(":"):
        if not part.isdigit():
            return None
        seconds = seconds * 60 + int(part)
    return seconds


def youtube_search(http: Http, query: str) -> list[dict]:
    status, html = http.get("https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": query, "hl": "pt-BR", "gl": "BR"}))
    match = re.search(r"var ytInitialData = (\{.*?\});</script>", html or "", re.S)
    if status != 200 or not match:
        return []
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if "videoRenderer" in node:
                v = node["videoRenderer"]
                views = re.sub(r"\D", "", v.get("viewCountText", {}).get("simpleText", "") or "")
                found.append({
                    "video_id": v.get("videoId"),
                    "title": "".join(r.get("text", "") for r in v.get("title", {}).get("runs", [])),
                    "channel": "".join(r.get("text", "") for r in v.get("ownerText", {}).get("runs", [])),
                    "duration": _duration(v.get("lengthText", {}).get("simpleText")),
                    "views": int(views) if views else 0,
                })
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(json.loads(match.group(1)))
    return [f for f in found if f["video_id"] and f["duration"]]


def lrclib_candidates(http: Http, title: str, artists: list[str]) -> list[dict]:
    seen, found = set(), []
    for params in ({"track_name": title, "artist_name": artists[0]}, {"q": f"{title} {artists[0]}"}):
        status, body = http.get("https://lrclib.net/api/search?" + urllib.parse.urlencode(params))
        if status != 200:
            continue
        for item in json.loads(body or "[]"):
            if item.get("id") in seen or not item.get("syncedLyrics") or item.get("instrumental"):
                continue
            seen.add(item["id"])
            found.append(item)
        if found:
            break
    wanted, primary = base_title(title), norm(artists[0])
    return [c for c in found
            if wanted == base_title(c.get("trackName") or "")
            and (primary in norm(c.get("artistName") or "") or norm(c.get("artistName") or "") in primary)]


def choose_lyrics(candidates: list[dict], duration: int | None) -> dict | None:
    if not duration:
        return None
    good = [c for c in candidates if abs(float(c.get("duration") or 0) - duration) <= DURATION_TOLERANCE_S
            and clean_lrc(c["syncedLyrics"]).count("\n") >= 8]  # letra incompleta não serve
    good.sort(key=lambda c: (abs(float(c["duration"]) - duration), -len(c["syncedLyrics"])))
    return good[0] if good else None


MAX_VIDEO_OPTIONS = 4


def video_options(http: Http, title: str, artists: list[str], lyrics: list[dict],
                  dataset_video: str | None, ok: set[str], blocked: set[str]) -> list[dict]:
    """Uploads com a MESMA duração de alguma letra, em ordem de preferência.

    Para no primeiro vídeo já aprovado no navegador (videos_verificados.json) e
    ignora os bloqueados. O YouTube só revela o bloqueio de incorporação (erro
    150) quando o player tenta tocar, por isso a verificação final é no navegador.
    """
    options: list[dict] = []
    seen: set[str] = set()

    def add(video_id: str, origin: str, views: int | None) -> bool:
        if video_id in seen or video_id in blocked or len(options) >= MAX_VIDEO_OPTIONS:
            return False
        seen.add(video_id)
        info = youtube_info(http, video_id)
        chosen = choose_lyrics(lyrics, info["duration_seconds"])
        if info["embeddable"] and chosen:
            options.append({"video_id": video_id, "info": info, "lyrics": chosen,
                            "video_origin": origin, "views": views})
            return video_id in ok
        return False

    if dataset_video and add(dataset_video, "dataset", None):
        return options
    results = youtube_search(http, f"{artists[0]} {title}")
    allowed_live = "ao vivo" in " ".join(norm(c.get("trackName", "")) for c in lyrics)
    ranked = []
    for r in results:
        if BAD_UPLOAD.search(r["title"]) or ("ao vivo" in norm(r["title"]) and not allowed_live):
            continue
        if not video_matches(title, artists, r["title"], r["channel"]):
            continue
        if choose_lyrics(lyrics, r["duration"]) is None:
            continue
        official = r["channel"].endswith(" - Topic") or any(norm(a) == norm(r["channel"]) for a in artists)
        ranked.append((r["video_id"] not in ok, not official, -r["views"], r))
    for *_, r in sorted(ranked, key=lambda x: x[:3]):
        if add(r["video_id"], "busca_youtube", r["views"]):
            break
    return options


KARAOKE_MARK = re.compile(r"karaok|karaoqu|videok[eê]|v[íi]deok[eê]", re.I)
# Karaokê "com voz guia" ou cover não serve: a ideia é a pessoa cantar sozinha.
KARAOKE_BAD = re.compile(r"voz ?guia|com voz|backing|cover|remix|piseiro|ao vivo|tutorial|aula|reac", re.I)
KARAOKE_NOISE = re.compile(r"karaok[eê]s?|karaoque|v[íi]deok[eê]|vers[aã]o|playback|instrumental|cante|cantar|"
                           r"com letra|legendado|viol[aã]o|base|\bhd\b|\b4k\b", re.I)


def karaoke_options(http: Http, title: str, artists: list[str], duration: int | None,
                    blocked: set[str]) -> list[dict]:
    """Até 3 vídeos de karaokê da música (título e artista no nome, duração parecida)."""
    found = []
    for r in youtube_search(http, f"{title} {artists[0]} karaokê"):
        if not KARAOKE_MARK.search(r["title"]) or KARAOKE_BAD.search(r["title"]):
            continue
        if r["video_id"] in blocked or (duration and abs(r["duration"] - duration) > 45):
            continue
        if not video_matches(title, artists, KARAOKE_NOISE.sub(" ", r["title"]), "", exact=True):
            continue
        found.append(r)
        if len(found) == 3:
            break
    return found


def clean_lrc(lrc: str) -> str:
    lines = []
    for raw in lrc.splitlines():
        match = re.match(r"^\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\](.*)$", raw.strip())
        if match:
            centis = (match.group(3) or "0").ljust(2, "0")[:2]
            lines.append(f"[{match.group(1).zfill(2)}:{match.group(2)}.{centis}]{match.group(4).strip()}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- UFMG

def load_ufmg(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ufmg_emotion_tag(row: dict) -> dict:
    scores = {k: float(row[k]) for k in ("raiva", "medo", "alegria", "tristeza", "surpresa")}
    top = max(scores, key=scores.get)
    return {"attribute": "emocao_letra", "value": top, "source": f"{UFMG_SOURCE}#linha={row['linha']}"}


# --------------------------------------------------------------------- main

def resolve(http: Http, title: str, artists: list[str], dataset_video: str | None,
            ok: set[str], blocked: set[str]) -> tuple[dict | None, list[str], str]:
    """Retorna (versão aprovada, vídeos a verificar no navegador, situação)."""
    lyrics = lrclib_candidates(http, title, artists)
    if not lyrics:
        return None, [], "sem letra sincronizada no LRCLIB"
    options = video_options(http, title, artists, lyrics, dataset_video, ok, blocked)
    approved = [o for o in options if o["video_id"] in ok]
    if approved:
        return approved[0], [], "ok"
    if options:
        return None, [o["video_id"] for o in options], f"aguardando verificação no navegador ({len(options)} vídeos)"
    durations = sorted({round(float(c["duration"])) for c in lyrics})[:6]
    return None, [], f"letra existe (durações {durations}s) mas nenhum vídeo liberado com a mesma duração"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--byrm", type=Path, default=DATA / "fontes" / "byrm_forro.csv")
    parser.add_argument("--ufmg", type=Path, default=DATA / "fontes" / "ufmg_forro.csv")
    parser.add_argument("--ufmg-max", type=int, default=30, help="máximo de músicas da UFMG (mais vistas)")
    parser.add_argument("--pesquisa", type=Path, default=DATA / "fontes" / "pesquisa_forro.csv",
                        help="lista titulo,artista montada por pesquisa e conferida no LRCLIB")
    parser.add_argument("--verificados", type=Path, default=DATA / "fontes" / "videos_verificados.json",
                        help="resultado de /verificar.html (ok/bloqueados)")
    parser.add_argument("--ajustes", type=Path, default=DATA / "fontes" / "ajustes_byrm.json")
    parser.add_argument("--curadoria", type=Path, default=DATA / "curadoria_forro.json")
    parser.add_argument("--saida", type=Path, default=DATA / "catalogo_forro.json")
    parser.add_argument("--cache", type=Path, default=DATA / ".cache")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int, default=6, help="requisições em paralelo na pré-busca")
    parser.add_argument("--sem-karaoke", action="store_true", help="não procurar vídeos de karaokê")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    letras_dir = args.saida.parent / "letras"

    http = Http(args.cache, args.offline)
    with args.byrm.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader)
        byrm_rows = [{"video_title": r[0], "video_id": r[1], "channel": r[2]} for r in reader if len(r) >= 3]
    ajustes = json.loads(args.ajustes.read_text(encoding="utf-8")) if args.ajustes.is_file() else {}
    curadoria = json.loads(args.curadoria.read_text(encoding="utf-8")) if args.curadoria.is_file() else {}
    pilot = json.loads((DATA / "catalogo_piloto.json").read_text(encoding="utf-8"))
    ufmg_rows = load_ufmg(args.ufmg)
    ufmg_index = {(base_title(r["titulo"]), r["artista_slug"]): r for r in ufmg_rows}
    checked = json.loads(args.verificados.read_text(encoding="utf-8")) if args.verificados.is_file() else {}
    ok_videos, blocked_videos = set(checked.get("ok", [])), set(checked.get("bloqueados", []))

    candidates = []  # (fonte, source_id, título, artistas, vídeo do dataset, linha UFMG)
    for item in parse_byrm(byrm_rows):
        fix = ajustes.get(item["video_id"], {})
        candidates.append({"source": BYRM_SOURCE, "source_id": item["video_id"],
                           "title": fix.get("title", item["title"]),
                           "artists": fix.get("artists", item["artists"]),
                           "dataset_video": item["video_id"], "excluir": fix.get("excluir")})
    for row in ufmg_rows:
        if row["artista_slug"] in UFMG_FORRO_ARTISTS:
            title, feats = split_feats(row["titulo"])
            candidates.append({"source": UFMG_SOURCE, "source_id": row["linha"], "title": title,
                               "artists": [UFMG_FORRO_ARTISTS[row["artista_slug"]]] + feats,
                               "dataset_video": None, "excluir": None, "ufmg": row})
    if args.pesquisa.is_file():
        with args.pesquisa.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                slug = re.sub(r"[^a-z0-9]+", "-", norm(f"{row['artista']} {row['titulo']}")).strip("-")[:58]
                candidates.append({"source": PESQUISA_SOURCE, "source_id": slug, "title": row["titulo"].strip(),
                                   "artists": [row["artista"].strip()], "dataset_video": None, "excluir": None})

    if not args.offline and args.workers > 1:
        # Pré-busca em paralelo só aquece o cache; a seleção abaixo continua sequencial.
        from concurrent.futures import ThreadPoolExecutor

        def warm(cand: dict) -> None:
            try:
                resolve(http, cand["title"], cand["artists"], cand["dataset_video"], ok_videos, blocked_videos)
            except Exception as exc:  # noqa: BLE001 - a passada sequencial repete e reporta
                print(f"pré-busca falhou em {cand['title']!r}: {type(exc).__name__}")

        with ThreadPoolExecutor(args.workers) as pool:
            list(pool.map(warm, [c for c in candidates if not c["excluir"]]))

    seen_titles = {base_title(s["title"]) for s in pilot["songs"]}
    used_videos = {v["youtube_video_id"] for v in pilot["karaoke_versions"]}
    accepted, report, to_verify = [], [], []
    for cand in candidates:
        line = {"source": cand["source"], "source_id": cand["source_id"], "title": cand["title"],
                "artists": cand["artists"], "status": ""}
        report.append(line)
        if cand["excluir"]:
            line["status"] = f"excluída: {cand['excluir']}"
            continue
        if base_title(cand["title"]) in seen_titles:
            line["status"] = "título já presente no catálogo"
            continue
        resolved, pending, why = resolve(http, cand["title"], cand["artists"], cand["dataset_video"],
                                         ok_videos, blocked_videos)
        to_verify += [v for v in pending if v not in to_verify]
        if pending:
            seen_titles.add(base_title(cand["title"]))
        if resolved is None or resolved["video_id"] in used_videos:
            line["status"] = why if resolved is None else "vídeo já usado"
            continue
        seen_titles.add(base_title(cand["title"]))
        used_videos.add(resolved["video_id"])
        accepted.append((cand, resolved))
        line["status"] = (f"OK · vídeo {resolved['video_id']} ({resolved['video_origin']}) · "
                          f"LRCLIB {resolved['lyrics']['id']}")

    # UFMG: manter só as mais vistas para o catálogo não virar só um artista.
    ufmg_ok = sorted([a for a in accepted if a[0]["source"] == UFMG_SOURCE], key=lambda a: -(a[1]["views"] or 0))
    dropped = {id(a[0]) for a in ufmg_ok[args.ufmg_max:]}
    for line, cand in zip(report, candidates):
        if id(cand) in dropped:
            line["status"] = "fora do limite --ufmg-max (menos visualizações)"
    accepted = [a for a in accepted if id(a[0]) not in dropped]

    letras_dir.mkdir(parents=True, exist_ok=True)
    for old in letras_dir.glob("LET-*.lrc"):
        old.unlink()
    today = date.today().isoformat()
    cur_source = curadoria.get("source", "curadoria")
    songs, versions = [], []
    for cand, res in accepted:
        prefix = {BYRM_SOURCE: "BYRM", UFMG_SOURCE: "UFMG", PESQUISA_SOURCE: "PESQ"}[cand["source"]]
        song_id, version_id = f"{prefix}-{cand['source_id']}", f"LET-{res['video_id']}"
        cur = curadoria.get("songs", {}).get(song_id, {})
        tags = []
        if cur.get("mood"):
            tags.append({"attribute": "clima", "value": cur["mood"], "source": cur_source})
        if cur.get("energy"):
            tags.append({"attribute": "energia", "value": str(cur["energy"]), "source": cur_source})
        ufmg_row = cand.get("ufmg") or ufmg_index.get((base_title(cand["title"]), "/avioes-do-forro/"))
        if ufmg_row and any(norm(a) == norm(UFMG_FORRO_ARTISTS.get(ufmg_row["artista_slug"], "")) for a in cand["artists"]):
            tags.append(ufmg_emotion_tag(ufmg_row))
        songs.append({
            "id": song_id, "title": cand["title"], "artists": cand["artists"], "genre": "forro",
            "energy": cur.get("energy"), "mood": cur.get("mood"),
            "duet_possible": bool(cur.get("duet_possible", False)), "tags": tags,
            "duration_ms": int(float(res["lyrics"]["duration"]) * 1000),
            "source": cand["source"], "source_id": cand["source_id"],
        })
        (letras_dir / f"{version_id}.lrc").write_text(clean_lrc(res["lyrics"]["syncedLyrics"]), encoding="utf-8")
        versions.append({
            "id": version_id, "song_id": song_id, "youtube_video_id": res["video_id"],
            "kind": "letra_sincronizada", "duration_seconds": res["info"]["duration_seconds"],
            "approved": True, "verified_at": today, "rights_reviewed": False,
            "lyrics_file": f"letras/{version_id}.lrc",
            "lyrics_source": f"{LRCLIB_SOURCE}#id={res['lyrics']['id']}",
            "video_origin": res["video_origin"],
        })

    # Karaokê de verdade (instrumental com letra no vídeo), quando existir e tocar.
    # Fica com id KAR-*, que o matching escolhe antes da versão LET-* (cante junto).
    if not args.sem_karaoke:
        by_id = {s["id"]: s for s in songs}
        targets = [(s, next(v for v in versions if v["song_id"] == s["id"])) for s in songs]
        if not args.offline and args.workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(args.workers) as pool:
                list(pool.map(lambda t: karaoke_options(http, t[0]["title"], t[0]["artists"], t[1]["duration_seconds"],
                                                        blocked_videos), targets))
        karaoke_count = 0
        for song, letra in targets:
            options = [o for o in karaoke_options(http, song["title"], song["artists"], letra["duration_seconds"],
                                                  blocked_videos) if o["video_id"] not in used_videos]
            chosen = next((o for o in options if o["video_id"] in ok_videos), None)
            if chosen is None:
                to_verify += [o["video_id"] for o in options if o["video_id"] not in to_verify]
                continue
            used_videos.add(chosen["video_id"])
            karaoke_count += 1
            versions.append({
                "id": f"KAR-{chosen['video_id']}", "song_id": by_id[song["id"]]["id"],
                "youtube_video_id": chosen["video_id"], "kind": "karaoke",
                "duration_seconds": chosen["duration"], "approved": True, "verified_at": today,
                "rights_reviewed": False, "video_origin": "busca_youtube_karaoke",
            })
        print(f"{karaoke_count} músicas novas também têm karaokê de verdade (versão principal).")

    catalog = {
        "metadata": {
            "origin": "scripts/build_catalog.py",
            "generated_at": today,
            "sources": {
                BYRM_SOURCE: "BYRM: Brazilian YouTube Regional Music Dataset — Guimarães & de Freitas (UFAM), CC BY 4.0",
                UFMG_SOURCE: "Conjunto de Dados de Séries Temporais de Músicas Brasileiras — Viana & Moro (UFMG), CC BY 4.0",
                PESQUISA_SOURCE: "Lista de forrós montada por pesquisa assistida por IA, conferida no LRCLIB",
                LRCLIB_SOURCE: "Letras sincronizadas (LRC) da comunidade LRCLIB",
            },
            "note": ("approved=true = o vídeo tocou no player incorporado (/verificar.html) e a letra tem a "
                     "mesma duração da gravação (±3 s). Repetir /verificar.html no domínio publicado. "
                     "Clima/energia vêm da fonte indicada em tags[].source."),
        },
        "songs": songs,
        "karaoke_versions": versions,
    }
    args.saida.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "relatorio_catalogo.md").write_text(render_report(report, songs), encoding="utf-8")
    by_source = {s: sum(1 for x in songs if x["source"] == s) for s in (BYRM_SOURCE, UFMG_SOURCE, PESQUISA_SOURCE)}
    print(f"{len(songs)} músicas novas com letra sincronizada: {by_source}")
    pending_file = DATA / "fontes" / "videos_a_verificar.txt"
    pending_file.write_text(",".join(to_verify) + "\n", encoding="utf-8")
    if to_verify:
        print(f"{len(to_verify)} vídeos aguardam verificação: abra /verificar.html?ids=<conteúdo de "
              f"{pending_file.relative_to(ROOT)}> e salve o JSON em {args.verificados.relative_to(ROOT)}")
    missing = [s["id"] for s in songs if not s["mood"] or not s["energy"]]
    if missing:
        print(f"Atenção: {len(missing)} sem clima/energia em {args.curadoria.name} (vetos de clima as bloqueiam).")


def render_report(report: list[dict], songs: list[dict]) -> str:
    out = ["# Relatório do catálogo ampliado", "",
           f"Gerado por `scripts/build_catalog.py` em {date.today().isoformat()}. "
           f"**{len(songs)}** músicas novas entraram no catálogo.", "",
           "| Fonte | ID na fonte | Título | Artistas | Situação |", "|---|---|---|---|---|"]
    for line in report:
        src = {BYRM_SOURCE: "BYRM", UFMG_SOURCE: "UFMG", PESQUISA_SOURCE: "Pesquisa"}[line["source"]]
        out.append(f"| {src} | `{line['source_id']}` | {line['title']} | {', '.join(line['artists'])} | {line['status']} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
