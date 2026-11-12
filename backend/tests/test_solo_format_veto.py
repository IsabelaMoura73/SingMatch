"""Regressão: veto de formato dueto NÃO elimina músicas em rodada solo."""
import json
from pathlib import Path

import pytest

from app.matching import MatchingError, eligible_candidates
from app.schemas import KaraokeVersion, ProfileConfirmed, ScriptProposal, Song

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


def test_duet_is_possible_only_with_explicit_consent_from_both_and_duet_song():
    songs, versions = catalog()
    duet_song = songs[0].model_copy(update={"duet_possible": True})
    profiles = {
        "a": ProfileConfirmed(duet_allowed=True),
        "b": ProfileConfirmed(duet_allowed=True),
        "c": ProfileConfirmed(duet_allowed=None),
    }
    from app.matching import duet_eligible_pairs
    songs = [duet_song, *(song.model_copy(update={"duet_possible": False}) for song in songs[1:])]
    pairs = duet_eligible_pairs(profiles, songs, versions)
    assert pairs["a"] == {"b"}
    assert pairs["b"] == {"a"}
    assert pairs["c"] == set()


def test_duet_pair_requires_both_people_to_be_musically_eligible():
    songs, versions = catalog()
    duet_song = songs[0].model_copy(update={"duet_possible": True})
    profiles = {
        "a": ProfileConfirmed(duet_allowed=True),
        "b": ProfileConfirmed(duet_allowed=True, vetoes=[{
            "category": "song", "value": duet_song.title, "evidence": "não quero essa música"
        }]),
    }
    from app.matching import duet_eligible_pairs
    songs = [duet_song, *(song.model_copy(update={"duet_possible": False}) for song in songs[1:])]
    assert duet_eligible_pairs(profiles, songs, versions) == {"a": set(), "b": set()}


def test_mixed_validator_accepts_consenting_duet_and_one_solo_each():
    from app.matching import validate_mixed_script
    songs, versions = catalog()
    songs = [song.model_copy(update={"duet_possible": song.id == "FOR-001"}) for song in songs]
    profiles = {"a": ProfileConfirmed(duet_allowed=True), "b": ProfileConfirmed(duet_allowed=True),
                "c": ProfileConfirmed(duet_allowed=None)}
    allowed = eligible_candidates("forro", profiles, songs, versions)
    proposal = ScriptProposal(title="Misto", items=[
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["a", "b"]},
        {"position": 2, "karaoke_version_id": "KAR-FOR-002", "participant_ids": ["c"]},
    ])
    validate_mixed_script(proposal, profiles, allowed, songs, versions)


def test_mixed_validator_rejects_unconsented_duet():
    from app.matching import validate_mixed_script
    songs, versions = catalog()
    songs = [song.model_copy(update={"duet_possible": True}) for song in songs]
    profiles = {"a": ProfileConfirmed(duet_allowed=True), "b": ProfileConfirmed(duet_allowed=None)}
    allowed = eligible_candidates("forro", profiles, songs, versions)
    proposal = ScriptProposal(title="Misto", items=[
        {"position": 1, "karaoke_version_id": "KAR-FOR-001", "participant_ids": ["a", "b"]},
    ])
    with pytest.raises(MatchingError, match="consentimento explícito"):
        validate_mixed_script(proposal, profiles, allowed, songs, versions)


def test_duet_affinity_rewards_shared_explicit_music_likes():
    from app.matching import duet_affinity
    songs, _ = catalog()
    songs = [song.model_copy(update={"duet_possible": True}) for song in songs]
    shared = ProfileConfirmed(likes=[{"category": "song", "value": "Asa Branca", "evidence": "gosto Asa Branca"}])
    none = ProfileConfirmed()
    assert duet_affinity(shared, shared, songs) > duet_affinity(shared, none, songs)
