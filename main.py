import os
import re
import io
import json
import uuid
import base64
import tempfile
import logging
from typing import Dict, List

import os
import edge_tts
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

APP_NAME = "humanos-digitais-tts"
APP_VERSION = "3.0.0"
DEFAULT_ALLOWED_ORIGINS = [
    "https://humanosdigitais-website.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]


def parse_allowed_origins() -> List[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    if not raw.strip():
        return DEFAULT_ALLOWED_ORIGINS
    return [item.strip() for item in raw.split(",") if item.strip()]


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AVATAR_VOICES: Dict[str, Dict[str, str]] = {
    "sofia": {"voice": "pt-BR-FranciscaNeural", "pitch": "+0Hz", "rate": "+0%", "style": "friendly"},
    "rafael": {"voice": "pt-BR-AntonioNeural", "pitch": "-10Hz", "rate": "-4%", "style": "serious"},
    "clara": {"voice": "pt-BR-FranciscaNeural", "pitch": "+8Hz", "rate": "+0%", "style": "caring"},
    "lucas": {"voice": "pt-BR-AntonioNeural", "pitch": "+6Hz", "rate": "+6%", "style": "energetic"},
    "amanda": {"voice": "pt-BR-FranciscaNeural", "pitch": "+2Hz", "rate": "-2%", "style": "hospitality"},
    "fernanda": {"voice": "pt-BR-FranciscaNeural", "pitch": "-2Hz", "rate": "-3%", "style": "institutional"},
    "marina": {"voice": "pt-BR-FranciscaNeural", "pitch": "+10Hz", "rate": "+4%", "style": "retail"},
    "roberto": {"voice": "pt-BR-AntonioNeural", "pitch": "-4Hz", "rate": "+1%", "style": "consultive"},
    "luisa": {"voice": "pt-BR-FranciscaNeural", "pitch": "+5Hz", "rate": "+0%", "style": "educational"},
    "lais": {"voice": "pt-BR-FranciscaNeural", "pitch": "+3Hz", "rate": "-1%", "style": "academic"},
    "paula": {"voice": "pt-BR-FranciscaNeural", "pitch": "+7Hz", "rate": "+3%", "style": "warm"},
    "bruno": {"voice": "pt-BR-AntonioNeural", "pitch": "+12Hz", "rate": "+12%", "style": "sports"},
    "giovana": {"voice": "pt-BR-FranciscaNeural", "pitch": "+11Hz", "rate": "+10%", "style": "sports"},
    "marcos": {"voice": "pt-BR-AntonioNeural", "pitch": "-2Hz", "rate": "+8%", "style": "sports"},
    "carol": {"voice": "pt-BR-FranciscaNeural", "pitch": "+6Hz", "rate": "+7%", "style": "sports"},
}

FALLBACK_AVATAR = "sofia"


class SpeakRequest(BaseModel):
    avatar_id: str = Field(..., min_length=1, max_length=50)
    text: str = Field(..., min_length=1, max_length=1200)
    emotion: str = Field(default="friendly", min_length=1, max_length=50)

    @field_validator("avatar_id")
    @classmethod
    def normalize_avatar_id(cls, value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9_-]", "", value.strip().lower())
        if not cleaned:
            raise ValueError("avatar_id inválido")
        return cleaned

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if not cleaned:
            raise ValueError("text não pode ser vazio")
        return cleaned

    @field_validator("emotion")
    @classmethod
    def normalize_emotion(cls, value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9_-]", "", value.strip().lower())
        return cleaned or "friendly"


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    body_preview = ""
    try:
        if request.method in {"POST", "PUT", "PATCH"}:
            raw_body = await request.body()
            if raw_body:
                body_preview = raw_body.decode("utf-8", errors="ignore")[:500]

            async def receive():
                return {"type": "http.request", "body": raw_body, "more_body": False}

            request._receive = receive  # type: ignore[attr-defined]

        logger.info(
            "[%s] START %s %s origin=%s body=%s",
            request_id,
            request.method,
            request.url.path,
            request.headers.get("origin"),
            body_preview,
        )
        response = await call_next(request)
        logger.info("[%s] END %s status=%s", request_id, request.url.path, response.status_code)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception("[%s] UNHANDLED ERROR %s", request_id, request.url.path)
        raise


def resolve_avatar_config(avatar_id: str) -> Dict[str, str]:
    config = AVATAR_VOICES.get(avatar_id) or AVATAR_VOICES[FALLBACK_AVATAR]
    if avatar_id not in AVATAR_VOICES:
        logger.warning("avatar_id '%s' não encontrado; usando fallback '%s'", avatar_id, FALLBACK_AVATAR)
    return config


async def synthesize_edge_tts(payload: SpeakRequest) -> str:
    avatar_config = resolve_avatar_config(payload.avatar_id)
    logger.info(
        "TTS INIT avatar_id=%s voice=%s pitch=%s rate=%s emotion=%s text_len=%s",
        payload.avatar_id,
        avatar_config["voice"],
        avatar_config["pitch"],
        avatar_config["rate"],
        payload.emotion,
        len(payload.text),
    )

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            temp_path = temp_file.name

        communicate = edge_tts.Communicate(
            text=payload.text,
            voice=avatar_config["voice"],
            rate=avatar_config["rate"],
            pitch=avatar_config["pitch"],
        )
        await communicate.save(temp_path)

        with open(temp_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        if not audio_bytes:
            raise RuntimeError("Áudio vazio gerado pelo Edge-TTS")

        logger.info("TTS OK avatar_id=%s bytes=%s", payload.avatar_id, len(audio_bytes))
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as exc:
        logger.exception("TTS ERROR avatar_id=%s detail=%s", payload.avatar_id, exc)
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.warning("Falha ao remover arquivo temporário: %s", temp_path)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "message": "Use /health, /api/voices e /api/avatar/speak",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "engine": "edge-tts",
        "voices_available": len(AVATAR_VOICES),
        "language": "pt-BR",
        "cost": "R$ 0,00",
    }


@app.get("/api/voices")
async def voices():
    return {
        "status": "ok",
        "engine": "edge-tts",
        "voices_available": len(AVATAR_VOICES),
        "avatars": [
            {
                "avatar_id": avatar_id,
                "voice": config["voice"],
                "pitch": config["pitch"],
                "rate": config["rate"],
                "style": config["style"],
            }
            for avatar_id, config in AVATAR_VOICES.items()
        ],
    }


@app.post("/api/avatar/speak")
async def avatar_speak(payload: SpeakRequest):
    logger.info(
        "SPEAK REQUEST avatar_id=%s emotion=%s text=%s",
        payload.avatar_id,
        payload.emotion,
        payload.text[:160],
    )
    try:
        audio_base64 = await synthesize_edge_tts(payload)
        return {
            "status": "ok",
            "avatar_id": payload.avatar_id,
            "emotion": payload.emotion,
            "engine": "edge-tts",
            "audio_format": "mp3",
            "audio_base64": audio_base64,
            "audio_bytes_estimate": int(len(audio_base64) * 0.75),
        }
    except HTTPException:
        raise
    except Exception as exc:
        detail = f"Falha interna ao gerar áudio: {exc}"
        logger.exception("SPEAK FAILURE avatar_id=%s detail=%s", payload.avatar_id, detail)
        raise HTTPException(status_code=500, detail=detail)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error("HTTPException path=%s status=%s detail=%s", request.url.path, exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception path=%s detail=%s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": f"Erro interno não tratado: {exc}"},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
