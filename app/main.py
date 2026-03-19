"""app/main.py

FastAPI — Ponto de entrada principal do ATTI Media Server.

Endpoints incluídos:
  GET  /health                → healthcheck
  GET  /api/voices            → lista vozes disponíveis
  GET  /api/stream-audio      → gera e retorna áudio WAV (TTS direto)
  POST /api/avatar/speak      → enfileira geração de vídeo completo (Celery)
  GET  /api/task/{task_id}    → consulta status de task Celery
  GET  /outputs/{filename}    → serve artefatos de vídeo
  GET  /stream/{filename}     → serve streams de áudio

Autenticação (endpoints de geração):
  Header: X-API-Key (ver auth/api_key.py)

Rate limiting:
  - /api/stream-audio: ATTI_RATE_LIMIT_PUBLIC (default 100/hour)
  - /api/avatar/speak: ATTI_RATE_LIMIT_GENERATE (default 30/hour)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from logging_atti.logger import RequestIdMiddleware, init_logging
from auth.api_key import require_api_key
from auth.rate_limit import init_rate_limiter
from atti_celery.worker import create_task_status_router
from atti_celery.tasks import generate_full_video as celery_generate_video
from atti_celery.tasks import synthesize_long_tts as celery_tts
from src.streaming.audio_stream import AudioStream

# ---------------------------------------------------------------------------
# Logging e App
# ---------------------------------------------------------------------------
init_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ATTI Media Server",
    description="Pipeline de avatares: TTS + Lip Sync + Animação Facial",
    version="1.0.0",
)
app.add_middleware(RequestIdMiddleware)
limiter = init_rate_limiter(app)

# Inclui router de status de tasks Celery
app.include_router(create_task_status_router(prefix="/api"))

# Serve artefatos de vídeo
_OUTPUT_DIR = os.getenv("ATTI_OUTPUT_DIR", "/tmp/atti_outputs")
_STREAM_DIR = os.getenv("ATTI_STREAM_DIR", "/tmp/atti_streams")
os.makedirs(_OUTPUT_DIR, exist_ok=True)
os.makedirs(_STREAM_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class SpeakRequest(BaseModel):
    text: str
    voice_id: str = "pt_br_01"
    avatar_id: str = "default"
    voice_profile: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    output: Optional[Dict[str, str]] = None


class VoiceInfo(BaseModel):
    id: str
    name: str
    language: str
    has_reference: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["infra"])
async def health() -> Dict[str, Any]:
    """Healthcheck do servidor."""
    return {"status": "ok", "service": "atti-media-server"}


@app.get("/api/voices", response_model=List[VoiceInfo], tags=["voices"])
async def list_voices() -> List[VoiceInfo]:
    """Lista vozes disponíveis no servidor.

    Vozes configuradas via XTTS_VOICE_<ID>=<path> ou /models/voices/*.wav
    """
    models_dir = os.getenv("ATTI_MODELS_DIR", "/models")
    voices_dir = os.path.join(models_dir, "voices")

    # Vozes built-in
    builtin: List[VoiceInfo] = [
        VoiceInfo(id="pt_br_01", name="Ana (PT-BR)", language="pt", has_reference=False),
        VoiceInfo(id="pt_br_02", name="Carlos (PT-BR)", language="pt", has_reference=False),
        VoiceInfo(id="en_us_01", name="Emma (EN-US)", language="en", has_reference=False),
        VoiceInfo(id="default",  name="Default (PT-BR)", language="pt", has_reference=False),
    ]

    # Verifica disponibilidade dos arquivos de referência
    for v in builtin:
        ref_path = os.path.join(voices_dir, f"{v.id}.wav")
        env_key = f"XTTS_VOICE_{v.id.upper().replace('-', '_')}"
        env_path = os.getenv(env_key, "")
        v.has_reference = (
            os.path.isfile(ref_path) or
            (bool(env_path) and os.path.isfile(env_path))
        )

    # Adiciona vozes extras encontradas em /models/voices/
    if os.path.isdir(voices_dir):
        known_ids = {v.id for v in builtin}
        for fname in sorted(os.listdir(voices_dir)):
            if fname.endswith(".wav"):
                vid = fname[:-4]
                if vid not in known_ids:
                    builtin.append(VoiceInfo(
                        id=vid, name=vid, language="unknown", has_reference=True
                    ))

    return builtin


@app.get("/api/stream-audio", tags=["audio"])
@limiter.limit(os.getenv("ATTI_RATE_LIMIT_PUBLIC", "100/hour"))
async def stream_audio(
    request: Request,
    texto: str = Query(..., description="Texto a ser sintetizado"),
    voice_id: str = Query("default", description="ID da voz"),
    language: str = Query("pt", description="Idioma (pt, en, es...)"),
    speed: float = Query(1.0, description="Velocidade da fala (0.5–2.0)", ge=0.5, le=2.0),
):
    """Gera áudio via TTS e retorna como arquivo WAV para download/stream.

    Endpoint síncrono (para textos curtos).
    Para textos longos, use POST /api/avatar/speak (assíncrono via Celery).
    """
    import tempfile

    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    logger.info(
        f"stream-audio | chars={len(texto)} | voice={voice_id}",
        extra={"extra": {"request_id": req_id}},
    )

    # Tenta TTS real (XTTS ou fallback gTTS)
    try:
        from src.media.pipeline_real import _synthesize_audio
        audio_bytes = _synthesize_audio(
            text=texto,
            voice_profile=voice_id,
            speed=speed,
            language=language,
        )
    except Exception as exc:
        logger.error(f"TTS falhou: {exc}", extra={"extra": {"request_id": req_id}})
        raise HTTPException(status_code=500, detail=f"Erro na síntese de voz: {exc}")

    # Salva temporariamente e retorna como stream
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    stream = AudioStream(tmp_path, file_id=req_id)
    return stream.get_streaming_response()


@app.post("/api/avatar/speak", tags=["avatar"])
@limiter.limit(os.getenv("ATTI_RATE_LIMIT_GENERATE", "30/hour"))
async def avatar_speak(
    request: Request,
    body: SpeakRequest,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    """Enfileira geração de vídeo completo do avatar (assíncrono).

    Requer header: X-API-Key

    Retorna task_id para consultar status em GET /api/task/{task_id}.
    """
    req_id = body.request_id or request.headers.get("X-Request-ID", str(uuid.uuid4()))
    logger.info(
        f"avatar/speak enfileirado | avatar={body.avatar_id} | chars={len(body.text)}",
        extra={"extra": {"request_id": req_id}},
    )

    payload = {
        "text": body.text,
        "voice_id": body.voice_id,
        "avatar_id": body.avatar_id,
        "voice_profile": body.voice_profile or body.voice_id,
        "params": body.params or {},
        "request_id": req_id,
        "output": body.output or {"format": "mp4"},
    }

    task = celery_generate_video.delay(payload)
    return {
        "task_id": task.id,
        "status": "queued",
        "request_id": req_id,
        "status_url": f"/api/task/{task.id}",
    }


@app.post("/api/tts/async", tags=["audio"])
async def tts_async(
    request: Request,
    body: Dict[str, Any],
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    """Enfileira síntese de voz longa via Celery.

    Body:
      {
        "text": "...",
        "voice_id": "pt_br_01",
        "params": {"speed": 1.0, "language": "pt"}
      }
    """
    req_id = body.get("request_id") or str(uuid.uuid4())
    body["request_id"] = req_id

    task = celery_tts.delay(body)
    return {
        "task_id": task.id,
        "status": "queued",
        "request_id": req_id,
        "status_url": f"/api/task/{task.id}",
    }


# ── Serve artefatos e streams ──────────────────────────────────────────────

@app.get("/outputs/{filename}", tags=["static"])
async def serve_output(filename: str):
    """Serve artefatos de vídeo gerados."""
    path = os.path.join(_OUTPUT_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Artefato não encontrado.")
    return FileResponse(path)


@app.get("/stream/{filename}", tags=["static"])
async def serve_stream(filename: str):
    """Serve streams de áudio."""
    path = os.path.join(_STREAM_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Stream não encontrado.")
    ext = os.path.splitext(filename)[1].lower()
    media_type = "audio/mpeg" if ext == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})
