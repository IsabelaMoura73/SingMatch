"""Regressão: veto de formato dueto NÃO elimina músicas em rodada solo."""
import json
from pathlib import Path

import pytest

from app.matching import MatchingError, eligible_candidates
from app.schemas import KaraokeVersion, ProfileConfirmed, Song

DATA = Path(__file__).resolve().parents[2] / "data" / "catalogo_piloto.json"


def catalog():
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return (
        [Song.model_validate(x) for x in raw["songs"]],
        [KaraokeVersion.model_validate(x) for x in raw["karaoke_versions"]],
    )


@pytest.mark.parametrize("format_veto", ["dueto", "duetos", "em dueto", "dupla", "cantar em dupla"])
def test_format_rejection_does_not_filter_any_song_in_solo(format_veto):
    songs, versions = catalog()
    profile = ProfileConfirmed(
        vetoes=[{"category": "tag", "value": format_veto, "evidence": "não quero duetos"}],
        duet_allowed=False,
        preferred_format="solo",
    )
    eligible = eligible_candidates("forro", {"zezinho": profile}, songs, versions)
    assert len(eligible["zezinho"]) == 5


def test_format_veto_is_not_allowed_to_override_real_song_veto():
    songs, versions = catalog()
    profile = ProfileConfirmed(
        vetoes=[
            {"category": "tag", "value": "dueto", "evidence": "não quero dueto"},
            {"category": "tag", "value": "romantica", "evidence": "não gosto de românticas"},
        ],
        duet_allowed=False,
    )
    eligible = eligible_candidates("forro", {"zezinho": profile}, songs, versions)
    assert len(eligible["zezinho"]) == 4
    assert "KAR-FOR-003" not in eligible["zezinho"]


def test_unknown_musical_tag_still_blocks_when_unverifiable():
    songs, versions = catalog()
    profile = ProfileConfirmed(vetoes=[
        {"category": "tag", "value": "muito triste", "evidence": "não gosto de música muito triste"},
    ])
    with pytest.raises(MatchingError, match="nenhuma música elegível"):
        eligible_candidates("forro", {"zezinho": profile}, songs, versions)
