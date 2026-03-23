from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import edge_tts
import asyncio
import base64
import os

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vozes Edge-TTS PT-BR
VOICES = {
    "sofia": "pt-BR-FranciscaNeural",
    "rafael": "pt-BR-AntonioNeural",
    "bruno": "pt-BR-BrendaNeural",
    "giovana": "pt-BR-GiovannaNeural",
    "marcos": "pt-BR-HumbertoNeural",
    "carol": "pt-BR-BrendaNeural",
}

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "humanos-digitais-tts",
        "engine": "edge-tts",
        "voices": len(VOICES),
        "version": "2.0"
    }

@app.get("/api/voices")
async def list_voices():
    return {
        "voices": [
            {"id": k, "voice": v}
            for k, v in VOICES.items()
        ]
    }

@app.post("/api/avatar/speak")
async def avatar_speak(data: dict):
    avatar_id = data.get("avatar_id", "sofia")
    text = data.get("text", "")
    
    if not text:
        raise HTTPException(status_code=400, detail="Text required")
    
    voice = VOICES.get(avatar_id, VOICES["sofia"])
    
    try:
        # Gerar áudio com Edge-TTS
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        # Converter para base64
        audio_b64 = base64.b64encode(audio_data).decode()
        
        return {
            "status": "success",
            "avatar_id": avatar_id,
            "voice_used": voice,
            "audio_base64": audio_b64,
            "text": text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "audio_base64": ""
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
