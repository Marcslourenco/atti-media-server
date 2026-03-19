"""redis/cache_config.py

Cache Redis para síntese de voz (TTS) e utilitários.

Objetivo MVP:
- Evitar recomputar TTS para textos repetidos.
- TTL padrão: 24h.
- Chave por hash do conteúdo (texto + voice_id + parâmetros relevantes).

Observações:
- Cachear áudio em Redis é simples e rápido, mas pode consumir memória.
  Por isso incluímos um limite de tamanho (default 15MB). Para áudios maiores,
  recomendamos (futuro) salvar em storage (S3/minio) e cachear apenas a URL.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import redis


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class RedisClients:
    """Clientes Redis separados (recomendado) para:

    - broker: fila Celery (db 0 por padrão)
    - cache: resultados (db 1 por padrão)

    Se você quiser, pode usar 1 URL só e alterar o DB.
    """

    cache: redis.Redis


def create_redis_clients() -> RedisClients:
    # Por padrão, usamos REDIS_URL apontando para db 0.
    # Para cache, preferimos db 2, mas aqui mantemos simples:
    # - se REDIS_URL já vier com /X, usamos esse DB.
    # - para separar, use ATTI_REDIS_CACHE_URL (opcional).
    cache_url = _env("ATTI_REDIS_CACHE_URL", _env("REDIS_URL", "redis://localhost:6379/0"))
    cache = redis.Redis.from_url(cache_url, decode_responses=False)
    return RedisClients(cache=cache)


def tts_cache_key(text: str, voice_id: str, params: Optional[dict[str, Any]] = None) -> str:
    """Gera uma chave determinística para cache de TTS."""

    payload = {
        "text": text,
        "voice_id": voice_id,
        "params": params or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return f"tts:v1:{digest}"


def cache_get_audio(r: redis.Redis, key: str) -> Optional[bytes]:
    """Retorna bytes de áudio se existir no cache."""

    data = r.get(key)
    if not data:
        return None

    # Armazenamos como base64 para evitar problemas com binário (opcional).
    # Como Redis já suporta bytes, isso é redundante, mas ajuda na portabilidade.
    try:
        decoded = base64.b64decode(data)
        return decoded
    except Exception:
        # Caso alguém tenha colocado bytes "puros"
        return data


def cache_set_audio(
    r: redis.Redis,
    key: str,
    audio_bytes: bytes,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """Salva áudio no cache com TTL. Retorna True se cacheou, False se pulou."""

    ttl = ttl_seconds or _env_int("ATTI_TTS_CACHE_TTL_SECONDS", 86400)
    max_bytes = _env_int("ATTI_TTS_CACHE_MAX_BYTES", 15 * 1024 * 1024)

    if len(audio_bytes) > max_bytes:
        # MVP: não cacheia arquivos muito grandes
        return False

    b64 = base64.b64encode(audio_bytes)
    r.setex(key, ttl, b64)
    return True
