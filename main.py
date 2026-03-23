"""
main.py — Humanos Digitais TTS API
FastAPI + Edge-TTS — 15 Avatares PT-BR — Custo ZERO
Backend: https://humanosdigitais.com.br
GitHub: https://github.com/Marcslourenco/atti-media-server
Versão: 2.0.0
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("humanos-digitais-tts")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Humanos Digitais TTS API",
    description=(
        "API de Text-to-Speech para 15 avatares digitais PT-BR. "
        "Engine: Microsoft Edge-TTS (custo zero, sem API key). "
        "Site: humanosdigitais.com.br"
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mapeamento de Vozes — 15 Avatares
# ---------------------------------------------------------------------------
VOICE_MAP: Dict[str, Dict[str, str]] = {
    # ── Avatares Profissionais ──────────────────────────────────────────────
    "sofia": {
        "voice": "pt-BR-FranciscaNeural",
        "rate": "+0%",
        "pitch": "+5Hz",
        "emotion": "friendly",
        "description": "Atendente geral — calorosa e prestativa",
        "gender": "feminino",
        "category": "geral",
    },
    "rafael": {
        "voice": "pt-BR-AntonioNeural",
        "rate": "-5%",
        "pitch": "-5Hz",
        "emotion": "professional",
        "description": "Especialista tributário — formal e preciso",
        "gender": "masculino",
        "category": "financeiro",
    },
    "clara": {
        "voice": "pt-BR-BrendaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "emotion": "empathetic",
        "description": "Consultora hospitalar — empática e tranquilizadora",
        "gender": "feminino",
        "category": "saude",
    },
    "lucas": {
        "voice": "pt-BR-FabioNeural",
        "rate": "+5%",
        "pitch": "+5Hz",
        "emotion": "enthusiastic",
        "description": "Consultor automotivo — animado e entusiasta",
        "gender": "masculino",
        "category": "automotivo",
    },
    "amanda": {
        "voice": "pt-BR-GiovannaNeural",
        "rate": "+0%",
        "pitch": "+5Hz",
        "emotion": "warm",
        "description": "Recepcionista de hotel — calorosa e receptiva",
        "gender": "feminino",
        "category": "hospitalidade",
    },
    "fernanda": {
        "voice": "pt-BR-LeticiaNeural",
        "rate": "-5%",
        "pitch": "+0Hz",
        "emotion": "clear",
        "description": "Atendente municipal — clara e objetiva",
        "gender": "feminino",
        "category": "governo",
    },
    "marina": {
        "voice": "pt-BR-ManuelaNeural",
        "rate": "+5%",
        "pitch": "+5Hz",
        "emotion": "cheerful",
        "description": "Guia do shopping — alegre e dinâmica",
        "gender": "feminino",
        "category": "varejo",
    },
    "roberto": {
        "voice": "pt-BR-DonatoNeural",
        "rate": "+0%",
        "pitch": "-5Hz",
        "emotion": "confident",
        "description": "Consultor de energia solar — confiante e direto",
        "gender": "masculino",
        "category": "energia",
    },
    "luisa": {
        "voice": "pt-BR-ElzaNeural",
        "rate": "-10%",
        "pitch": "-5Hz",
        "emotion": "calm",
        "description": "Mentora educacional — calma e sábia",
        "gender": "feminino",
        "category": "educacao",
    },
    "lais": {
        "voice": "pt-BR-FranciscaNeural",
        "rate": "-5%",
        "pitch": "+0Hz",
        "emotion": "professional",
        "description": "Orientadora de medicina — profissional e confiável",
        "gender": "feminino",
        "category": "saude",
    },
    "paula": {
        "voice": "pt-BR-YaraNeural",
        "rate": "+0%",
        "pitch": "+5Hz",
        "emotion": "friendly",
        "description": "Atendente odontológica — simpática e acolhedora",
        "gender": "feminino",
        "category": "saude",
    },
    # ── Avatares Futebol ───────────────────────────────────────────────────
    "bruno": {
        "voice": "pt-BR-ValerioNeural",
        "rate": "+20%",
        "pitch": "+10Hz",
        "emotion": "excited",
        "description": "Torcedor São Paulo FC (Tricolor) — animado e passional",
        "gender": "masculino",
        "category": "futebol",
    },
    "giovana": {
        "voice": "pt-BR-GiovannaNeural",
        "rate": "+15%",
        "pitch": "+10Hz",
        "emotion": "passionate",
        "description": "Torcedora São Paulo FC (Tricolinda) — apaixonada",
        "gender": "feminino",
        "category": "futebol",
    },
    "marcos": {
        "voice": "pt-BR-HumbertoNeural",
        "rate": "+10%",
        "pitch": "+5Hz",
        "emotion": "intense",
        "description": "Corinthiano da Zona Leste — raiz e intenso",
        "gender": "masculino",
        "category": "futebol",
    },
    "carol": {
        "voice": "pt-BR-BrendaNeural",
        "rate": "+15%",
        "pitch": "+10Hz",
        "emotion": "passionate",
        "description": "Torcedora Corinthians (Fiel) — bandona e apaixonada",
        "gender": "feminino",
        "category": "futebol",
    },
}

# Saudações padrão por avatar
DEFAULT_GREETINGS: Dict[str, str] = {
    "sofia":   "Oi! Sou a Sofia, como posso te ajudar hoje?",
    "rafael":  "Olá! Sou o Rafael, especialista tributário. Pode perguntar!",
    "clara":   "Olá! Sou a Clara, consultora hospitalar. Como posso ajudar?",
    "lucas":   "E aí! Sou o Lucas, consultor automotivo. O que você procura?",
    "amanda":  "Olá! Sou a Amanda, recepcionista do hotel. Seja bem-vindo!",
    "fernanda":"Olá! Sou a Fernanda, atendente municipal. Em que posso ajudar?",
    "marina":  "Oi! Sou a Marina, guia do shopping. Vem comigo!",
    "roberto": "Oi! Sou o Roberto, consultor de energia solar. Economize agora!",
    "luisa":   "Olá! Sou a Luisa, mentora educacional. Vamos aprender juntos?",
    "lais":    "Oi! Sou a Laís, orientadora de medicina. Tire suas dúvidas!",
    "paula":   "Olá! Sou a Paula, atendente odontológica. Sorriso bonito é essencial!",
    "bruno":   "E aí, Tricolor! Sou o Bruno! Bora falar de futebol?!",
    "giovana": "Oi, Tricolindo! Sou a Giovana! Vai São Paulo!",
    "marcos":  "Salve, Fiel! Sou o Marcos, corinthiano da ZL! Timão sempre!",
    "carol":   "Oi! Sou a Carol, Bandona e Fiel até o fim! Vai Corinthians!",
}

# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class SpeakRequest(BaseModel):
    avatar_id: str = Field(default="sofia", description="ID do avatar (ex: sofia, rafael, bruno)")
    text: str = Field(..., description="Texto para sintetizar em voz")
    voice_profile: str = Field(default="", description="Override de voz (opcional)")
    emotion: str = Field(default="", description="Override de emoção (opcional)")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Multiplicador de velocidade")
    use_ssml: bool = Field(default=False, description="Retornar SSML ao invés de áudio")

class SpeakResponse(BaseModel):
    status: str
    avatar_id: str
    audio_base64: str
    audio_format: str
    voice_used: str
    text: str
    duration_ms: int
    engine: str

class VoiceInfo(BaseModel):
    id: str
    voice: str
    emotion: str
    description: str
    gender: str
    category: str
    rate: str
    pitch: str

# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _get_voice_config(avatar_id: str) -> Dict[str, str]:
    """Retorna configuração de voz para o avatar, com fallback para sofia."""
    return VOICE_MAP.get(avatar_id.lower(), VOICE_MAP["sofia"])


async def _synthesize_edge_tts(text: str, voice: str, rate: str, pitch: str) -> bytes:
    """Sintetiza texto com edge-tts e retorna bytes MP3."""
    try:
        import edge_tts  # type: ignore
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="edge-tts não instalado. Execute: pip install edge-tts"
        )

    buf = io.BytesIO()

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
    )

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])

    audio_bytes = buf.getvalue()
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="edge-tts não retornou áudio")

    return audio_bytes


def _build_ssml(text: str, voice: str, rate: str, pitch: str) -> str:
    """Monta SSML completo com prosody."""
    return f"""<speak version='1.0'
  xmlns='http://www.w3.org/2001/10/synthesis'
  xml:lang='pt-BR'>
  <voice name='{voice}'>
    <prosody rate='{rate}' pitch='{pitch}'>
      {text}
    </prosody>
  </voice>
</speak>"""

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["infra"])
async def health() -> Dict[str, Any]:
    """Healthcheck — verifica se o servidor está operacional."""
    return {
        "status": "ok",
        "service": "humanos-digitais-tts",
        "version": "2.0.0",
        "engine": "edge-tts",
        "voices_available": len(VOICE_MAP),
        "language": "pt-BR",
        "cost": "R$ 0,00",
    }


@app.get("/api/voices", response_model=List[VoiceInfo], tags=["voices"])
async def list_voices() -> List[VoiceInfo]:
    """Lista todos os 15 avatares com suas vozes e configurações."""
    return [
        VoiceInfo(
            id=k,
            voice=v["voice"],
            emotion=v["emotion"],
            description=v["description"],
            gender=v["gender"],
            category=v["category"],
            rate=v["rate"],
            pitch=v["pitch"],
        )
        for k, v in VOICE_MAP.items()
    ]


@app.get("/api/voices/{avatar_id}", tags=["voices"])
async def get_voice(avatar_id: str) -> Dict[str, Any]:
    """Retorna configuração detalhada de um avatar específico."""
    cfg = VOICE_MAP.get(avatar_id.lower())
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Avatar '{avatar_id}' não encontrado")
    return {
        "id": avatar_id,
        **cfg,
        "default_greeting": DEFAULT_GREETINGS.get(avatar_id, ""),
    }


@app.post("/api/avatar/speak", response_model=SpeakResponse, tags=["tts"])
async def speak(req: SpeakRequest) -> SpeakResponse:
    """
    Sintetiza texto em voz para um avatar específico.
    
    Retorna áudio MP3 em base64 pronto para reprodução no browser:
    ```js
    const audio = new Audio('data:audio/mp3;base64,' + response.audio_base64);
    audio.play();
    ```
    """
    start = time.time()
    
    cfg = _get_voice_config(req.avatar_id)
    
    # Override de voz se especificado
    voice = req.voice_profile if req.voice_profile else cfg["voice"]
    rate  = cfg["rate"]
    pitch = cfg["pitch"]

    # Ajuste de velocidade via multiplicador
    if req.speed != 1.0:
        base_pct = int(cfg["rate"].replace("%", "").replace("+", ""))
        adjusted = int(base_pct + (req.speed - 1.0) * 20)
        sign = "+" if adjusted >= 0 else ""
        rate = f"{sign}{adjusted}%"

    if req.use_ssml:
        return {
            "status": "ssml",
            "avatar_id": req.avatar_id,
            "ssml": _build_ssml(req.text, voice, rate, pitch),
        }

    audio_bytes = await _synthesize_edge_tts(req.text, voice, rate, pitch)
    
    duration_ms = int((time.time() - start) * 1000)
    audio_b64   = base64.b64encode(audio_bytes).decode("utf-8")

    logger.info(
        f"TTS OK | avatar={req.avatar_id} | voice={voice} | "
        f"chars={len(req.text)} | {duration_ms}ms"
    )

    return SpeakResponse(
        status="success",
        avatar_id=req.avatar_id,
        audio_base64=audio_b64,
        audio_format="mp3",
        voice_used=voice,
        text=req.text,
        duration_ms=duration_ms,
        engine="edge-tts",
    )


@app.get("/api/avatar/{avatar_id}/greet", tags=["tts"])
async def greet_avatar(avatar_id: str) -> Dict[str, Any]:
    """
    Gera saudação padrão de um avatar em áudio MP3 base64.
    Útil para tocar automaticamente ao selecionar um avatar no grid.
    """
    greeting = DEFAULT_GREETINGS.get(avatar_id.lower())
    if not greeting:
        raise HTTPException(status_code=404, detail=f"Avatar '{avatar_id}' não encontrado")
    
    cfg = _get_voice_config(avatar_id)
    audio_bytes = await _synthesize_edge_tts(
        greeting, cfg["voice"], cfg["rate"], cfg["pitch"]
    )
    
    return {
        "status": "success",
        "avatar_id": avatar_id,
        "text": greeting,
        "audio_base64": base64.b64encode(audio_bytes).decode(),
        "audio_format": "mp3",
        "voice_used": cfg["voice"],
    }


@app.post("/api/avatar/speak/stream", tags=["tts"])
async def speak_stream(req: SpeakRequest):
    """
    Versão streaming do endpoint speak.
    Retorna áudio MP3 diretamente como stream (sem base64).
    Útil para reprodução direta via <audio src="..."> ou fetch+ReadableStream.
    """
    try:
        import edge_tts  # type: ignore
    except ImportError:
        raise HTTPException(status_code=500, detail="edge-tts não instalado")

    cfg   = _get_voice_config(req.avatar_id)
    voice = req.voice_profile if req.voice_profile else cfg["voice"]

    async def audio_generator():
        communicate = edge_tts.Communicate(
            text=req.text,
            voice=voice,
            rate=cfg["rate"],
            pitch=cfg["pitch"],
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(
        audio_generator(),
        media_type="audio/mpeg",
        headers={"X-Avatar-ID": req.avatar_id, "X-Voice": voice},
    )


@app.get("/api/avatars", tags=["avatars"])
async def list_avatars() -> Dict[str, Any]:
    """Lista todos os avatares com informações completas incluindo saudações."""
    avatares = []
    for avatar_id, cfg in VOICE_MAP.items():
        avatares.append({
            "id": avatar_id,
            "voice": cfg["voice"],
            "emotion": cfg["emotion"],
            "description": cfg["description"],
            "gender": cfg["gender"],
            "category": cfg["category"],
            "greeting": DEFAULT_GREETINGS.get(avatar_id, ""),
        })
    return {"avatars": avatares, "total": len(avatares)}


# ---------------------------------------------------------------------------
# Entry point local
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, workers=1)
