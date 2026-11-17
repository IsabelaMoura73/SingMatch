"""Limites de uso da IA para o site publicado (protege a cota da chave da OpenAI).

Contagem em memória numa janela deslizante de 1 hora. Basta para o piloto, que
roda uma única instância (ver Dockerfile); ao reiniciar o servidor a contagem zera.
Valores ajustáveis por variável de ambiente.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

WINDOW_SECONDS = 3600

# Tamanho máximo do perfil confirmado (vai inteiro para o prompt do roteiro).
MAX_LIKES = 20
MAX_VETOES = 20
MAX_QUESTIONS = 10


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError:
        return default
    return max(value, 1)


class HourlyLimit:
    """Até `limit` usos por chave (participante, sala...) na última hora."""

    def __init__(self, env_name: str, default: int, message: str):
        self.env_name, self.default, self.message = env_name, default, message
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return _env_int(self.env_name, self.default)

    def hit(self, key: str, now: float | None = None) -> None:
        """Registra um uso ou levanta 429 se o limite da última hora já foi atingido."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(now)
            hits = self._hits[key]
            if len(hits) >= self.limit:
                remaining = WINDOW_SECONDS - (now - hits[0])
                minutes = max(1, math.ceil(remaining / 60))
                raise HTTPException(status_code=429, detail=f"{self.message} Tente de novo em {minutes} min.")
            hits.append(now)

    def refund(self, key: str) -> None:
        """Desfaz o último uso da chave (ex.: o serviço de IA falhou e nada foi gerado)."""
        with self._lock:
            hits = self._hits.get(key)
            if hits:
                hits.pop()
                if not hits:
                    del self._hits[key]

    def _prune(self, now: float) -> None:
        """Descarta usos fora da janela e chaves vazias (salas antigas não ficam na memória)."""
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if not hits:
                del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


interpret_limit = HourlyLimit(
    "SINGMATCH_MAX_INTERPRETACOES_HORA", 10,
    "Limite de interpretações por participante atingido (uso da IA).",
)
script_limit = HourlyLimit(
    "SINGMATCH_MAX_ROTEIROS_HORA", 15,
    "Limite de roteiros gerados nesta sala atingido (uso da IA).",
)
