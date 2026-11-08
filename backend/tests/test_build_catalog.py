"""Regras de escolha de vídeo/letra do scripts/build_catalog.py (sem rede)."""
from __future__ import annotations

import pytest

from scripts.build_catalog import BAD_UPLOAD, base_title, choose_lyrics, clean_lrc, video_matches

AVIOES = ["Aviões do Forró"]


@pytest.mark.parametrize("title,artists,video_title,channel,expected", [
    # Casos reais que o script escolheu errado antes de a regra ficar rígida.
    ("Me Acha", AVIOES, "Aviões do Forró - Me perdoa (Antigas)", "Lima'z", False),
    ("Pense Aí", AVIOES, "Pense em mim - Aviões do Forró 2010", "Millopirata", False),
    ("Dói Dói", AVIOES, "Aviões do Forró - Dói Né - Aviões 12 Anos", "Victor Valente", False),
    ("Não Vou", AVIOES, "Xand Avião - Aviões do Forró Eu Não Vou Mais Chorar VOL 3", "Xand Avião", False),
    ("Amor de Motel", AVIOES, "Amor de Motel / Brinquedo em Suas Mãos (Ao Vivo)", "Aviões do Forró - Topic", False),
    ("Sintonia e Desejo", AVIOES + ["Ivete Sangalo"], "Sintonia E Desejo", "Ivete Sangalo - Topic", False),
    # Uploads legítimos com ruído de título.
    ("Dói Dói", AVIOES, "Doi Doi", "Aviões do Forró - Topic", True),
    ("Acabou na Lama", AVIOES, "Xand Avião - Aviões do Forró - DVD 10 anos - Acabou Na Lama", "Xand Avião", True),
    ("Chá de Costa", AVIOES, "Aviões do forró  - Chá de costas", "Aviaozeiros Tma", True),
    ("Cortando Pano", ["Luiz Gonzaga"], "Cortando O Pano", "Luiz Gonzaga - Topic", True),
    ("Amor covarde", ["Dorgival Dantas"],
     "Dorgival Dantas - Amor Covarde - Part. Chambinho [DVD Simplesmente Dorgival Dantas]", "Dorgival Dantas", True),
])
def test_video_matches(title, artists, video_title, channel, expected):
    assert video_matches(title, artists, video_title, channel) is expected


def test_bad_uploads_are_filtered():
    for title in ["LUIZ GONZAGA - FORRÓ NO ESCURO (COM GRAVE)", "Asa Branca - Karaokê",
                  "Vem Morena (Versão Piseiro) Remix", "Xote da Alegria cover"]:
        assert BAD_UPLOAD.search(title), title
    assert not BAD_UPLOAD.search("Luiz Gonzaga - Vem Morena (Áudio Oficial)")


def test_base_title_ignores_live_and_parentheses():
    assert base_title("Amor Covarde - Ao Vivo") == base_title("Amor covarde")
    assert base_title("Destá (Ao Vivo)") == "desta"


def test_lyrics_must_match_video_duration():
    full = "".join(f"[00:{10 + i}.00]linha {i}\n" for i in range(10))
    lyrics = [{"id": 1, "duration": 200.0, "syncedLyrics": full},
              {"id": 2, "duration": 231.5, "syncedLyrics": full},
              {"id": 3, "duration": 230.0, "syncedLyrics": "[00:01.00]só um trecho\n"}]
    assert choose_lyrics(lyrics, 230)["id"] == 2  # o id 3 tem a duração exata, mas está incompleto
    assert choose_lyrics(lyrics, 215) is None
    assert choose_lyrics(lyrics, None) is None


def test_clean_lrc_keeps_only_timed_lines():
    assert clean_lrc("[ar:Fulano]\n[00:05.1]Linha\n\n[1:02.345]Outra\n") == "[00:05.10]Linha\n[01:02.34]Outra\n"
