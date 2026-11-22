
"""Teste manual de geração com 12 perfis e OpenAI real."""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

load_dotenv(ROOT / ".env")

from app.llm import (
    LLMServiceError,
    compor_roteiro_misto,
    compor_roteiro_reserva,
)
from app.matching import (
    eligible_candidates,
    validate_mixed_script,
)
from app.schemas import ProfileConfirmed
from scripts.avaliar_roteiros import load_catalog


def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Configure OPENAI_API_KEY no .env")

    songs_by_id, versions_by_id = load_catalog()
    songs = list(songs_by_id.values())
    versions = list(versions_by_id.values())

    approved = [
        v for v in versions
        if v.approved and v.kind == "karaoke"
    ]

    if len(approved) < 12:
        raise SystemExit("Catálogo insuficiente para o teste.")

    profiles = {}

    for i in range(12):
        # Preferências artificiais baseadas em músicas do catálogo.
        song = songs_by_id[
            approved[(i * 7) % len(approved)].song_id
        ]

        vetoes = []
        if i % 4 == 0:
            excluded_song = songs_by_id[
                approved[(i + 3) % len(approved)].song_id
            ]
            vetoes = [{
                "category": "song",
                "value": excluded_song.title,
                "evidence": "Cenário de teste",
            }]

        profiles[f"P{i + 1:02d}"] = ProfileConfirmed(
            likes=[{
                "category": "artist",
                "value": song.artists[0],
                "evidence": "Cenário de teste",
            }],
            vetoes=vetoes,
            preferred_format="indiferente",
            duet_allowed=i < 8,
        )

    print(f"Participantes: {len(profiles)}")
    print(f"Karaokês aprovados: {len(approved)}")
    print("Modelo:", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    start = time.perf_counter()
    used_fallback = False

    try:
        proposal = compor_roteiro_misto(
            "forro",
            "Começar tranquilo e terminar animado",
            profiles,
            songs,
            versions,
        )
    except LLMServiceError as exc:
        print("Erro da IA:", exc)

        if not exc.recoverable:
            raise SystemExit("Erro não recuperável.")

        used_fallback = True
        proposal = compor_roteiro_reserva(
            "forro", profiles, songs, versions
        )

    elapsed = time.perf_counter() - start

    # Validação completa do roteiro resultante.
    allowed = eligible_candidates(
        "forro", profiles, songs, versions
    )
    validate_mixed_script(
        proposal, profiles, allowed, songs, versions
    )

    print(f"Tempo total: {elapsed:.2f}s")
    print("Usou fallback:", used_fallback)
    print("Apresentações:", len(proposal.items))
    print(
        "Duetos:",
        sum(len(i.participant_ids) == 2
            for i in proposal.items),
    )

    print("\nRoteiro:")
    versions_by_id = {v.id: v for v in versions}

    for item in proposal.items:
        version = versions_by_id[item.karaoke_version_id]
        song = songs_by_id[version.song_id]
        print(
            f"{item.position:02d}. "
            f"{' + '.join(item.participant_ids)}: "
            f"{song.title}"
        )

    print("\nROTEIRO VALIDADO COM SUCESSO")


if __name__ == "__main__":
    main()
