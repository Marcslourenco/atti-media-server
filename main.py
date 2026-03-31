import os
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("humanos-digitais-tts-rag-llm")

BACKEND_VERSION = "7.0.0"

class SpeakRequest(BaseModel):
    text: str = Field(..., description="Texto para sintetizar e gerar visemes")
    avatar_id: Optional[str] = Field("default", description="ID do avatar para visemes")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto (pt-BR, en, es)")

class TTSRequest(BaseModel):
    text: str = Field(..., description="Texto para converter em fala")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto (pt-BR, en, es)")

class TranslationRequest(BaseModel):
    text: str = Field(..., description="Texto a ser traduzido")
    target_language: str = Field(..., description="Idioma de destino (pt-BR, en, es)")
    source_language: Optional[str] = Field(None, description="Idioma de origem (opcional)")

# Importações dos módulos
try:
    from i18n_engine import I18nEngine
    i18n_engine = I18nEngine()
    logger.info("i18n_engine carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar i18n_engine: {e}", exc_info=True)
    i18n_engine = None

try:
    from src.avatar.viseme_sync import VisemeSyncEngine
    viseme_sync = VisemeSyncEngine(fps=30)
    logger.info("viseme_sync carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar viseme_sync: {e}", exc_info=True)
    viseme_sync = None

try:
    from src.rag_engine import rag_engine
    logger.info("RAG engine carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar RAG engine: {e}", exc_info=True)
    rag_engine = None
    viseme_sync = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Iniciando humanos-digitais-tts-rag-llm v{BACKEND_VERSION}")
    
    translation_available = i18n_engine is not None
    tts_available = viseme_sync is not None
    
    app.state.translation_available = translation_available
    app.state.tts_available = tts_available
    app.state.supported_languages = ["pt-BR", "en", "es"] if translation_available else ["pt-BR"]
    
    logger.info(f"Tradução disponível: {translation_available}")
    logger.info(f"TTS/Visemes disponível: {tts_available}")
    
    yield
    logger.info("Desligando servidor")

app = FastAPI(
    title="Humanos Digitais API",
    description="TTS + RAG + tradução gratuita + Sync-Lip para Avatares Digitais",
    version=BACKEND_VERSION,
    lifespan=lifespan
)

# ==================== CORS ====================
origins_str = os.getenv("CORS_ALLOW_ORIGINS", "")
origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    return {
        "service": "humanos-digitais-tts-rag-llm",
        "version": BACKEND_VERSION,
        "status": "online",
        "translation": {
            "provider": "deep-translator",
            "available": app.state.translation_available
        },
        "i18n": {
            "default_language": "pt-BR",
            "supported_languages": app.state.supported_languages
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "version": BACKEND_VERSION}

@app.get("/api/avatar/status")
async def avatar_status():
    return {
        "status": "online",
        "version": BACKEND_VERSION,
        "avatars_available": True,
        "tts_available": app.state.tts_available,
        "visemes_available": viseme_sync is not None
    }

@app.post("/api/avatar/speak")
async def avatar_speak(request: SpeakRequest):
    """Endpoint principal para fala do avatar."""
    text = request.text.strip()
    avatar_id = request.avatar_id or "default"
    language = request.language or "pt-BR"
    
    if not text:
        raise HTTPException(status_code=400, detail="Campo 'text' é obrigatório")
    
    if language not in app.state.supported_languages:
        language = "pt-BR"
    
    logger.info(f"Avatar speak: avatar={avatar_id}, language={language}, text='{text[:100]}'")
    
    # Gerar áudio e visemes
    audio_data = None
    visemes = []
    
    if viseme_sync:
        try:
            result = await viseme_sync.synthesize_with_visemes(text, avatar_id, language)
            if result:
                audio_data = result.get("audio")
                visemes = result.get("visemes", [])
                logger.info(f"Visemes gerados: {len(visemes)} frames")
        except Exception as e:
            logger.error(f"Erro ao gerar áudio/visemes: {e}")
    
    # Gerar resposta com RAG
    response_text = text
    if rag_engine:
        try:
            response_text = rag_engine.generate_response(text, avatar_id, language)
            logger.info(f"Resposta RAG gerada: '{response_text[:100]}'")
        except Exception as e:
            logger.warning(f"Erro ao gerar resposta com RAG: {e}, usando eco")
            response_text = text
    
    return {
        "success": True,
        "text_response": response_text,
        "audio_data": audio_data,
        "visemes": visemes,
        "language": language,
        "avatar_id": avatar_id,
        "supported_languages": app.state.supported_languages
    }
@app.post("/api/tts")
async def tts_only(request: TTSRequest):
    """Endpoint apenas para TTS (sem visemes)."""
    text = request.text.strip()
    language = request.language or "pt-BR"
    
    if not text:
        raise HTTPException(status_code=400, detail="Campo 'text' é obrigatório")
    
    if language not in app.state.supported_languages:
        language = "pt-BR"
    
    audio_data = None
    
    if viseme_sync:
        try:
            result = await viseme_sync.synthesize_with_visemes(text, "default", language)
            if result:
                audio_data = result.get("audio")
        except Exception as e:
            logger.error(f"Erro no TTS: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar áudio: {str(e)}")
    
    if not audio_data:
        raise HTTPException(status_code=500, detail="Falha ao gerar áudio")
    
    return {
        "success": True,
        "audio_data": audio_data,
        "language": language
    }

@app.post("/api/translate")
async def translate_text(request: TranslationRequest):
    """Endpoint para tradução de texto."""
    if not app.state.translation_available:
        raise HTTPException(status_code=503, detail="Serviço de tradução não disponível")
    
    try:
        result = i18n_engine.translate_text(
            text=request.text,
            target_lang=request.target_language,
            source_lang=request.source_language
        )
        return {
            "success": True,
            "original_text": request.text,
            "translated_text": result["translated_text"],
            "source_language": result["detected_source"],
            "target_language": request.target_language
        }
    except Exception as e:
        logger.error(f"Erro na tradução: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na tradução: {str(e)}")

# ==================== STARTUP ====================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
