"""Validação independente do LLM para o MVP SOLO do SingMatch.

Nenhuma regra de negócio crítica depende do prompt. Uma label sem metadado
correspondente não é considerada automaticamente segura (fail closed).
"""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from app.schemas import KaraokeVersion, PreferenceLabel, ProfileConfirmed, ScriptProposal, Song


class MatchingError(ValueError):
    """Um roteiro ou conjunto de candidatos viola alguma regra do MVP."""


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().strip())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.replace("_", " ").replace("-", " ").split())


def _tag_compatible(song: Song, veto_value: str, known_moods: set[str]) -> bool:
    """Retorna True somente se há evidência suficiente de não violação.

    - clima fechado é comparado com o clima conhecido do catálogo;
    - energia é comparada com faixa numérica, se presente;
    - outro atributo exige metadado explícito no registro da música.
    """
    value = norm(veto_value)
    moods = {norm(m) for m in known_moods}
    if value in moods:
        return song.mood is not None and norm(song.mood) != value
    ranges = {"energia baixa": range(1, 3), "energia media": range(3, 4), "energia alta": range(4, 6)}
    if value in ranges:
        return song.energy is not None and song.energy not in ranges[value]
    # Tags livres não têm cobertura completa no piloto. Na ausência de
    # evidência de que NÃO há a característica vetada, bloquear.
    return False


def respects_veto(song: Song, veto: PreferenceLabel, known_moods: set[str]) -> bool:
    value = norm(veto.value)
    if veto.category == "genre":
        return norm(song.genre) != value
    if veto.category == "song":
        return norm(song.title) != value
    if veto.category == "artist":
        return all(norm(a) != value for a in song.artists)
    if veto.category == "tag":
        return _tag_compatible(song, value, known_moods)
    return False


def matches_like(song: Song, label: PreferenceLabel) -> bool:
    value = norm(label.value)
    if label.category == "genre":
        return norm(song.genre) == value
    if label.category == "song":
        return norm(song.title) == value
    if label.category == "artist":
        return any(norm(a) == value for a in song.artists)
    if label.category == "tag":
        if song.mood and norm(song.mood) == value:
            return True
        if song.energy is not None:
            if value == "energia alta" and song.energy >= 4:
                return True
            if value == "energia media" and song.energy == 3:
                return True
            if value == "energia baixa" and song.energy <= 2:
                return True
        return any(norm(tag.value) == value for tag in song.tags)
    return False


def eligible_candidates(
    genre: str,
    profiles: dict[str, ProfileConfirmed],
    songs: Sequence[Song],
    karaoke_versions: Sequence[KaraokeVersion],
) -> dict[str, list[str]]:
    if not profiles:
        raise MatchingError("É necessário ter pelo menos um participante.")
    songs_by_id = {song.id: song for song in songs}
    known_moods = {s.mood for s in songs if s.mood}
    approved_all = [v for v in karaoke_versions if v.approved and v.song_id in songs_by_id
                    and norm(songs_by_id[v.song_id].genre) == norm(genre)]
    # Uma versão por obra no MVP. Uma segunda versão da MESMA música pode ser
    # fallback técnico, mas não deve contar como escolha distinta do roteiro.
    # Karaokê de verdade (instrumental) vem antes da versão "cante junto" da mesma música.
    approved_all.sort(key=lambda v: (v.kind != "karaoke", v.id))
    approved, seen_songs = [], set()
    for v in approved_all:
        if v.song_id not in seen_songs:
            approved.append(v)
            seen_songs.add(v.song_id)
    if not approved:
        raise MatchingError(f"Não há vídeos aprovados para o gênero {genre!r}.")
    # Restrições sobre o FORMATO de apresentação não são restrições
    # sobre as músicas. Neste MVP, TODAS as apresentações são solo.
    # Assim, "não quero dueto" nunca deve zerar os candidatos musicais.
    # Conservar o veto no perfil para respeitá-lo quando duetos existirem.
    solo_format_vetoes = {
        "dueto", "duetos", "em dueto", "cantar em dueto",
        "cantar duetos", "apresentacao em dueto", "dupla",
        "duplas", "em dupla", "cantar em dupla",
    }
    result = {}
    for participant_id, profile in profiles.items():
        musical_vetoes = [veto for veto in profile.vetoes
                          if not (veto.category == "tag"
                                  and norm(veto.value) in solo_format_vetoes)]
        eligible = [v for v in approved if all(
            respects_veto(songs_by_id[v.song_id], veto, known_moods)
            for veto in musical_vetoes
        )]
        eligible.sort(
            key=lambda v: -sum(matches_like(songs_by_id[v.song_id], like) for like in profile.likes)
        )
        result[participant_id] = [v.id for v in eligible]
        if not result[participant_id]:
            raise MatchingError(f"Participante {participant_id}: nenhuma música elegível; revisar vetos.")
    if not _assignment_possible(result):
        raise MatchingError("Sem solução: não há vídeos distintos suficientes para todos; revisar perfis.")
    return result


def _assignment_possible(candidates: dict[str, list[str]]) -> bool:
    # Algoritmo de caminhos aumentantes, suficiente para o pequeno catálogo do MVP.
    ownership: dict[str, str] = {}
    def assign(person_id: str, visited: set[str]) -> bool:
        for video_id in candidates[person_id]:
            if video_id in visited:
                continue
            visited.add(video_id)
            if video_id not in ownership or assign(ownership[video_id], visited):
                ownership[video_id] = person_id
                return True
        return False
    return all(assign(person_id, set()) for person_id in candidates)


def duet_eligible_pairs(
    profiles: dict[str, ProfileConfirmed],
    songs: Sequence[Song],
    karaoke_versions: Sequence[KaraokeVersion],
) -> dict[str, set[str]]:
    """Mapeia parceiros possíveis; consentimento explícito bilateral é obrigatório."""
    known_moods = {s.mood for s in songs if s.mood}
    approved_song_ids = {v.song_id for v in karaoke_versions if v.approved}
    eligible_songs = [s for s in songs if s.duet_possible and s.id in approved_song_ids]
    format_vetoes = {"dueto", "duetos", "em dueto", "cantar em dueto", "cantar duetos",
                     "apresentacao em dueto", "dupla", "duplas", "em dupla", "cantar em dupla"}
    eligible_by_person = {
        pid: {s.id for s in eligible_songs if all(
            respects_veto(s, veto, known_moods) for veto in profile.vetoes
            if not (veto.category == "tag" and norm(veto.value) in format_vetoes)
        )}
        for pid, profile in profiles.items()
    }
    result = {pid: set() for pid in profiles}
    members = list(profiles)
    for index, first in enumerate(members):
        if profiles[first].duet_allowed is not True:
            continue
        for second in members[index + 1:]:
            if profiles[second].duet_allowed is True and eligible_by_person[first] & eligible_by_person[second]:
                result[first].add(second)
                result[second].add(first)
    return result


def validate_solo_script(
    proposal: ScriptProposal,
    profiles: dict[str, ProfileConfirmed],
    allowed_candidates: dict[str, list[str]],
) -> None:
    """Verifica o roteiro contra os perfis/candidatos reais do backend."""
    if any(len(item.participant_ids) != 1 for item in proposal.items):
        raise MatchingError("Neste estágio somente apresentações SOLO são permitidas.")
    if len(proposal.items) != len(profiles):
        raise MatchingError("Roteiro deve ter exatamente uma apresentação por participante.")
    actual_participants: set[str] = set()
    for item in proposal.items:
        if len(item.participant_ids) != 1:
            raise MatchingError("Neste estágio somente apresentações SOLO são permitidas.")
        person = item.participant_ids[0]
        if person not in profiles or person not in allowed_candidates:
            raise MatchingError(f"Participante desconhecido: {person!r}.")
        if item.karaoke_version_id not in allowed_candidates[person]:
            raise MatchingError(f"Vídeo {item.karaoke_version_id!r} não permitido para {person!r}.")
        actual_participants.add(person)
    if actual_participants != set(profiles):
        raise MatchingError("O roteiro omitiu algum participante da rodada.")


def duet_affinity(first: ProfileConfirmed, second: ProfileConfirmed,
                  songs: Sequence[Song]) -> float:
    """Score 0..1 from shared stated likes over duet-capable works."""
    common = [song for song in songs if song.duet_possible]
    if not common:
        return 0.0
    if not first.likes or not second.likes:
        return 0.0
    matched = sum(
        any(matches_like(song, label) for label in first.likes)
        and any(matches_like(song, label) for label in second.likes)
        for song in common
    )
    return round(matched / len(common), 3)


def validate_mixed_script(
    proposal: ScriptProposal,
    profiles: dict[str, ProfileConfirmed],
    allowed_candidates: dict[str, list[str]],
    songs: Sequence[Song],
    karaoke_versions: Sequence[KaraokeVersion],
) -> None:
    """Valida solos e duetos; cada pessoa aparece uma vez e duetos exigem permissão."""
    if len(proposal.items) > len(profiles):
        raise MatchingError("Roteiro excede o número de participantes.")
    partners = duet_eligible_pairs(profiles, songs, karaoke_versions)
    seen: set[str] = set()
    versions = {v.id: v for v in karaoke_versions}
    songs_by_id = {s.id: s for s in songs}
    for item in proposal.items:
        ids = item.participant_ids
        if len(ids) not in (1, 2) or len(set(ids)) != len(ids):
            raise MatchingError("Cada apresentação deve ser solo ou dueto com duas pessoas distintas.")
        if any(pid not in profiles or pid in seen for pid in ids):
            raise MatchingError("Participante desconhecido ou repetido na rodada.")
        version = versions.get(item.karaoke_version_id)
        if version is None or not version.approved:
            raise MatchingError("Versão de karaokê inexistente ou não aprovada.")
        song = songs_by_id.get(version.song_id)
        if song is None or not song.duet_possible and len(ids) == 2:
            raise MatchingError("Esta música não está habilitada para dueto.")
        if len(ids) == 2 and (ids[1] not in partners.get(ids[0], set())):
            raise MatchingError("Dueto exige consentimento explícito e compatibilidade dos dois participantes.")
        if any(item.karaoke_version_id not in allowed_candidates.get(pid, []) for pid in ids):
            raise MatchingError("Música não permitida para um dos participantes do item.")
        seen.update(ids)
    if seen != set(profiles):
        raise MatchingError("Roteiro deve incluir cada participante exatamente uma vez.")
