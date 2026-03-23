"""
Humanos Digitais — TTS Backend
Ultra-lite: edge-tts only, no heavy deps
Guaranteed to work on Render Free Tier
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import base64
import io
import os

app = FastAPI(title="Humanos Digitais TTS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Voice mapping: avatar_id → (edge-tts voice, rate, pitch)
VOICES = {
    "sofia":    ("pt-BR-FranciscaNeural", "+0%",  "+5%"),
    "rafael":   ("pt-BR-AntonioNeural",   "-5%",  "-5%"),
    "clara":    ("pt-BR-FranciscaNeural", "+0%",  "+0%"),
    "lucas":    ("pt-BR-AntonioNeural",   "+5%",  "+5%"),
    "amanda":   ("pt-BR-FranciscaNeural", "+0%",  "+5%"),
    "fernanda": ("pt-BR-FranciscaNeural", "-5%",  "+0%"),
    "marina":   ("pt-BR-FranciscaNeural", "+5%",  "+5%"),
    "roberto":  ("pt-BR-AntonioNeural",   "+0%",  "-5%"),
    "luisa":    ("pt-BR-FranciscaNeural", "-10%", "-5%"),
    "lais":     ("pt-BR-FranciscaNeural", "-5%",  "+0%"),
    "paula":    ("pt-BR-FranciscaNeural", "+0%",  "+5%"),
    "bruno":    ("pt-BR-AntonioNeural",   "+20%", "+10%"),
    "giovana":  ("pt-BR-FranciscaNeural", "+15%", "+10%"),
    "marcos":   ("pt-BR-AntonioNeural",   "+10%", "+5%"),
    "carol":    ("pt-BR-FranciscaNeural", "+15%", "+10%"),
}

class SpeakRequest(BaseModel):
    avatar_id: str = "sofia"
    text: str
    emotion: str = "friendly"
    speed: float = 1.0
    voice_profile: str = ""


@app.get("/")
def root():
    return {"service": "Humanos Digitais TTS", "status": "ok"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "humanos-digitais-tts",
        "engine": "edge-tts",
        "voices": len(VOICES),
        "version": "2.0"
    }


@app.get("/api/voices")
def list_voices():
    return {
        "voices": [
            {"id": k, "voice": v[0], "rate": v[1], "pitch": v[2]}
            for k, v in VOICES.items()
        ]
    }


@app.post("/api/avatar/speak")
async def speak(req: SpeakRequest):
    try:
        import edge_tts

        avatar_id = req.avatar_id.lower().strip()
        cfg = VOICES.get(avatar_id, VOICES["sofia"])
        voice, rate

        # Clean text (remove emojis that cause TTS issues)
        import re
        text_clean = re.sub(
            r'[^\w\s\.,!?\-áéíóúàèìòùâêîôûãõçÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ]',
            '', req.text
        ).strip()

        if not text_clean:
            text_clean = "Olá! Como posso ajudar?"

        # Generate audio
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(
            text_clean, voice, rate=rate
        )

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])

        audio_bytes = buf.getvalue()
        if not audio_bytes:
            raise ValueError("No audio generated")

        audio_b64 = base64.b64encode(audio_bytes).decode()

        return {
            "status": "success",
            "avatar_id": avatar_id,
            "voice_used": voice,
            "audio_base64": audio_b64,
            "audio_format": "mp3",
            "text": text_clean,
            "chars": len(audio_b64)
        }

    except ImportError:
        return {
            "status": "error",
            "message": "edge-tts not installed",
            "audio_base64": ""
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "audio_base64": ""
        }


@app.get("/api/avatar/{avatar_id}/greet")
async def greet(avatar_id: str):
    greetings = {
        "sofia":    "Oi! Sou a Sofia, vamos conversar?",
        "rafael":   "Oi! Sou o Rafael, especialista tributario.",
        "clara":    "Ola! Sou a Clara, consultora hospitalar.",
        "lucas":    "E ai! Sou o Lucas, consultor automotivo!",
        "amanda":   "Ola! Sou a Amanda, recepcionista de hotel.",
        "fernanda": "Ola! Sou a Fernanda, atendente municipal.",
        "marina":   "Oi! Sou a Marina, guia do shopping.",
        "roberto":  "Oi! Sou o Roberto, consultor de energia solar.",
        "luisa":    "Ola! Sou a Luisa, mentora educacional.",
        "lais":     "Oi! Sou a Lais, orientadora de medicina.",
        "paula":    "Ola! Sou a Paula, atendente odontologica.",
        "bruno":    "E ai Tricolor! Bora falar de futebol?!",
        "giovana":  "Oi! Sou a Giovana, Tricolinda!",
        "marcos":   "Salve Fiel! Sou o Marcos, corinthiano da ZL!",
        "carol":    "Oi! Sou a Carol, Bandona e Fiel ate o fim!",
    }
    text = greetings.get(avatar_id.lower(), "Oi! Como posso ajudar?")
    req = SpeakRequest(avatar_id=avatar_id, text=text)
    return await speak(req)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
