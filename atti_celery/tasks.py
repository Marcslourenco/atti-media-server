"""atti_celery/tasks.py

Tasks Celery para processamento assíncrono — INTEGRAÇÃO REAL com pipeline de avatares.

Tasks disponíveis:
  - synthesize_long_tts  →  TTS via XTTSEngineReal (fallback para gTTS)
  - generate_full_video  →  pipeline completo: TTS + visemas + animação facial + vídeo

Estratégia de fallback:
  - XTTS disponível   → usa XTTSEngineReal
  - XTTS indisponível → usa gTTS (fallback leve, sem dependência de GPU)

Cache TTS (Redis, TTL 24h padrão):
  - chave determinística por (text, voice_id, params)
  - limita áudios > 15 MB (configurável via ATTI_TTS_CACHE_MAX_BYTES)
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional

from celery.utils.log import get_task_logger

from .worker import celery_app
from redis.cache_config import (
    cache_get_audio,
    cache_set_audio,
    create_redis_clients,
    tts_cache_key,
)

logger = get_task_logger(__name__)
py_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# Cliente Redis para cache de TTS (inicializado uma vez por worker)
_redis_clients = create_redis_clients()


# ---------------------------------------------------------------------------
# Carregamento lazy dos motores (evita import pesado no startup do worker)
# ---------------------------------------------------------------------------

_xtts_engine = None
_viseme_engine = None
_avatar_engine = None


def _get_xtts_engine():
    """Carrega XTTSEngineReal de forma lazy. Retorna None se não disponível."""
    global _xtts_engine
    if _xtts_engine is not None:
        return _xtts_engine
    try:
        from src.tts.xtts_engine_real import XTTSEngineReal
        _xtts_engine = XTTSEngineReal()
        py_logger.info("XTTSEngineReal carregado com sucesso.")
    except Exception as exc:
        py_logger.warning(
            f"XTTSEngineReal não disponível ({exc}). Usando fallback gTTS.",
            exc_info=False,
        )
        _xtts_engine = None
    return _xtts_engine


def _get_viseme_engine(fps: int = 30):
    """Carrega VisemeSyncEngine de forma lazy."""
    global _viseme_engine
    if _viseme_engine is not None:
        return _viseme_engine
    try:
        from src.avatar.viseme_sync import VisemeSyncEngine
        _viseme_engine = VisemeSyncEngine(fps=fps)
        py_logger.info("VisemeSyncEngine carregado com sucesso.")
    except Exception as exc:
        py_logger.warning(f"VisemeSyncEngine não disponível ({exc}).", exc_info=False)
        _viseme_engine = None
    return _viseme_engine


def _get_avatar_engine():
    """Carrega LivePortraitEngineReal de forma lazy."""
    global _avatar_engine
    if _avatar_engine is not None:
        return _avatar_engine
    try:
        from src.avatar.liveportrait_engine_real import LivePortraitEngineReal
        _avatar_engine = LivePortraitEngineReal()
        py_logger.info("LivePortraitEngineReal carregado com sucesso.")
    except Exception as exc:
        py_logger.warning(f"LivePortraitEngineReal não disponível ({exc}).", exc_info=False)
        _avatar_engine = None
    return _avatar_engine


# ---------------------------------------------------------------------------
# Pipelines reais
# ---------------------------------------------------------------------------

def _run_tts_pipeline(
    text: str,
    voice_id: str,
    params: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Executa TTS e retorna bytes WAV do áudio.

    Prioridade:
      1. XTTSEngineReal  (alta qualidade, requer GPU/modelos)
      2. gTTS            (fallback leve, sem GPU)
    """
    params = params or {}
    speed: float = float(params.get("speed", 1.0))
    language: str = params.get("language", "pt")

    xtts = _get_xtts_engine()

    if xtts is not None:
        # ── Caminho principal: XTTS ──────────────────────────────────────
        py_logger.info(f"TTS via XTTSEngineReal | voice={voice_id} | chars={len(text)}")
        audio_np, sr = xtts.synthesize(
            text=text,
            voice_id=voice_id,
            speed=speed,
            language=language,
        )
        # Converte numpy array → bytes WAV
        import io
        import numpy as np
        import scipy.io.wavfile as wav_io

        buf = io.BytesIO()
        wav_io.write(buf, sr, audio_np.astype(np.float32))
        return buf.getvalue()

    else:
        # ── Fallback: gTTS ───────────────────────────────────────────────
        py_logger.info(f"TTS via gTTS (fallback) | chars={len(text)}")
        try:
            from gtts import gTTS
            import io

            tts_obj = gTTS(text=text, lang=language, slow=(speed < 0.85))
            buf = io.BytesIO()
            tts_obj.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except Exception as exc:
            py_logger.error(f"Fallback gTTS falhou: {exc}", exc_info=True)
            raise RuntimeError(f"Síntese de voz falhou (XTTS e gTTS indisponíveis): {exc}") from exc


def _run_full_video_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executa o pipeline completo de vídeo usando módulos reais.

    Fluxo:
      1. TTS  →  bytes WAV (com cache Redis)
      2. Visemas  →  blend_shapes
      3. Animação facial  →  frames
      4. Pipeline final  →  URL do vídeo

    payload esperado:
    {
      "text":          "Olá, este é um teste.",
      "voice_id":      "pt_br_01",
      "avatar_id":     "avatar_a",
      "voice_profile": "default",
      "params":        {"speed": 1.0, "language": "pt"},
      "request_id":    "...",
      "output":        {"format": "mp4"},
      "tts_audio_bytes": <bytes opcionais pré-cacheados>
    }
    """
    req_id = payload.get("request_id", "-")
    text = payload.get("text", "")
    voice_id = payload.get("voice_id", "default")
    avatar_id = payload.get("avatar_id", "default")
    voice_profile = payload.get("voice_profile", voice_id)
    params = payload.get("params") or {}

    # ── 1. TTS (reutiliza bytes pré-cacheados se disponíveis) ────────────
    audio_bytes: bytes = payload.get("tts_audio_bytes") or b""
    if not audio_bytes:
        py_logger.info("TTS: sintetizando...", extra={"extra": {"request_id": req_id}})
        audio_bytes = _run_tts_pipeline(text=text, voice_id=voice_id, params=params)

    # Salva áudio em arquivo temporário para passar aos motores seguintes
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
        tmp_audio.write(audio_bytes)
        audio_path = tmp_audio.name

    try:
        # ── 2. Pipeline completo via pipeline_real ───────────────────────
        # Tenta usar o pipeline_real integrado (preferencial)
        try:
            from src.media.pipeline_real import generate_full_video as _pipeline_generate

            py_logger.info(
                "Usando pipeline_real.generate_full_video",
                extra={"extra": {"request_id": req_id}},
            )
            video_url = _pipeline_generate(
                avatar_id=avatar_id,
                voice_profile=voice_profile,
                text=text,
                speed=float(params.get("speed", 1.0)),
            )
            return {
                "status": "ok",
                "artifact": {
                    "type": "video",
                    "format": payload.get("output", {}).get("format", "mp4"),
                    "video_url": video_url,
                },
            }

        except ImportError:
            py_logger.warning(
                "pipeline_real não encontrado — usando pipeline modular (TTS + visemas + avatar).",
                extra={"extra": {"request_id": req_id}},
            )

        # ── 2-B. Pipeline modular (fallback quando pipeline_real ausente) ─
        # 2-B.1  Visemas
        viseme_eng = _get_viseme_engine(fps=int(params.get("fps", 30)))
        blend_shapes = None
        if viseme_eng is not None:
            py_logger.info("Extraindo visemas...", extra={"extra": {"request_id": req_id}})
            visemes = viseme_eng.extract_visemes(audio_path)
            # duração estimada = tamanho do WAV / (sample_rate * bytes_por_amostra)
            fps = int(params.get("fps", 30))
            total_frames = max(fps * 5, fps * len(visemes) // 100)
            lip_curve = viseme_eng.generate_lip_curve(visemes, total_frames)
            blend_shapes = viseme_eng.to_blend_shapes(lip_curve)
            py_logger.info(
                f"Visemas extraídos: {len(visemes)} itens.",
                extra={"extra": {"request_id": req_id}},
            )

        # 2-B.2  Animação facial
        avatar_eng = _get_avatar_engine()
        frames = None
        avatar_image_path = os.path.join(
            os.getenv("ATTI_MODELS_DIR", "/models"),
            "avatars",
            f"{avatar_id}.png",
        )
        if avatar_eng is not None and os.path.isfile(avatar_image_path):
            py_logger.info(
                "Gerando animação facial...",
                extra={"extra": {"request_id": req_id}},
            )
            frames = avatar_eng.generate_animation(avatar_image_path, audio_path)
            py_logger.info(
                f"Animação gerada: {len(frames) if frames else 0} frames.",
                extra={"extra": {"request_id": req_id}},
            )
        elif avatar_eng is None:
            py_logger.warning(
                "LivePortraitEngineReal indisponível — vídeo sem animação facial.",
                extra={"extra": {"request_id": req_id}},
            )
        else:
            py_logger.warning(
                f"Imagem do avatar não encontrada: {avatar_image_path}",
                extra={"extra": {"request_id": req_id}},
            )

        # 2-B.3  Streaming de áudio (opcional)
        try:
            from src.streaming.audio_stream import AudioStream
            stream = AudioStream(audio_path)
            stream_url = stream.get_stream_url()
            py_logger.info(
                f"Stream de áudio disponível em: {stream_url}",
                extra={"extra": {"request_id": req_id}},
            )
        except Exception:
            stream_url = None

        return {
            "status": "ok",
            "artifact": {
                "type": "video",
                "format": payload.get("output", {}).get("format", "mp4"),
                "audio_path": audio_path,
                "stream_url": stream_url,
                "has_blend_shapes": blend_shapes is not None,
                "has_frames": frames is not None,
                "note": (
                    "Pipeline modular executado. "
                    "Para vídeo final (.mp4), integre src/media/pipeline_real.py "
                    "com os frames e blend_shapes retornados."
                ),
            },
        }

    finally:
        # Limpeza do arquivo temporário de áudio
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tasks Celery
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="atti_celery.tasks.synthesize_long_tts",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def synthesize_long_tts(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Task: TTS para textos longos (> 30s de fala estimados).

    payload esperado:
      {
        "text":       "...",
        "voice_id":   "pt_br_01",
        "params":     {"speed": 1.0, "language": "pt"},
        "request_id": "<uuid>"
      }

    Retorno:
      {
        "status":    "ok" | "cached",
        "cached":    true | false,
        "audio_b64": "<base64 do WAV>"
      }

    Nota MVP: retornamos base64 para transporte JSON simples.
    Futuro: salvar em storage (S3/MinIO) e retornar URL.
    """
    req_id = payload.get("request_id", "-")
    py_logger.info(
        "Iniciando synthesize_long_tts",
        extra={"extra": {"request_id": req_id}},
    )

    text = payload["text"]
    voice_id = payload["voice_id"]
    params = payload.get("params")

    # ── Cache ─────────────────────────────────────────────────────────────
    key = tts_cache_key(text=text, voice_id=voice_id, params=params)
    cached = cache_get_audio(_redis_clients.cache, key)
    if cached:
        py_logger.info("TTS cache HIT", extra={"extra": {"request_id": req_id}})
        return {
            "status": "cached",
            "cached": True,
            "audio_b64": base64.b64encode(cached).decode("utf-8"),
        }

    py_logger.info("TTS cache MISS — sintetizando", extra={"extra": {"request_id": req_id}})

    audio_bytes = _run_tts_pipeline(text=text, voice_id=voice_id, params=params)

    ttl = _env_int("ATTI_TTS_CACHE_TTL_SECONDS", 86400)
    cached_ok = cache_set_audio(_redis_clients.cache, key, audio_bytes, ttl_seconds=ttl)
    py_logger.info(
        f"TTS concluído — cacheado={cached_ok} | bytes={len(audio_bytes)}",
        extra={"extra": {"request_id": req_id}},
    )

    return {
        "status": "ok",
        "cached": cached_ok,
        "audio_b64": base64.b64encode(audio_bytes).decode("utf-8"),
    }


@celery_app.task(
    bind=True,
    name="atti_celery.tasks.generate_full_video",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def generate_full_video(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Task: pipeline completo de vídeo (TTS → visemas → animação → vídeo final).

    payload esperado:
      {
        "text":          "Olá, este é um teste.",
        "voice_id":      "pt_br_01",
        "avatar_id":     "avatar_a",
        "voice_profile": "default",
        "params":        {"speed": 1.0, "language": "pt", "fps": 30},
        "request_id":    "<uuid>",
        "output":        {"format": "mp4"}
      }

    Retorno:
      {
        "status":   "ok",
        "artifact": {
          "type":      "video",
          "format":    "mp4",
          "video_url": "http://..." | null
        }
      }
    """
    req_id = payload.get("request_id", "-")
    py_logger.info(
        "Iniciando generate_full_video",
        extra={"extra": {"request_id": req_id}},
    )

    text = payload.get("text", "")
    voice_id = payload.get("voice_id", "default")
    params = payload.get("params") or {}

    # ── Pré-TTS com cache ────────────────────────────────────────────────
    if text and voice_id:
        key = tts_cache_key(text=text, voice_id=voice_id, params=params)
        cached_audio = cache_get_audio(_redis_clients.cache, key)
        if cached_audio:
            py_logger.info(
                "TTS reaproveitado do cache",
                extra={"extra": {"request_id": req_id}},
            )
            payload["tts_audio_bytes"] = cached_audio
        else:
            py_logger.info(
                "TTS cache MISS — sintetizando antes do vídeo",
                extra={"extra": {"request_id": req_id}},
            )
            audio_bytes = _run_tts_pipeline(text=text, voice_id=voice_id, params=params)
            payload["tts_audio_bytes"] = audio_bytes
            ttl = _env_int("ATTI_TTS_CACHE_TTL_SECONDS", 86400)
            cache_set_audio(_redis_clients.cache, key, audio_bytes, ttl_seconds=ttl)

    result = _run_full_video_pipeline(payload)
    py_logger.info(
        f"generate_full_video concluído — status={result.get('status')}",
        extra={"extra": {"request_id": req_id}},
    )
    return result
