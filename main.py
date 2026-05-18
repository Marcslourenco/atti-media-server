import os
import logging
from pathlib import Path
from typing import Optional
from enum import Enum
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("humanos-digitais-tts-rag-llm")

BACKEND_VERSION = "7.0.0"

class EventType(str, Enum):
    INTRO = "intro"
    USER_QUERY = "query"

class SpeakRequest(BaseModel):
    avatar_id: str = Field(..., description="ID do avatar")
    text: str = Field(default="", description="Texto para sintetizar")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto (pt-BR, en, es)")
    event_type: EventType = Field(EventType.USER_QUERY, description="Tipo de evento (intro ou query)")
    session_id: Optional[str] = Field(None, description="ID da sessão")

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
    from src.chroma_engine import AvatarRAGEngine
    rag_engine = AvatarRAGEngine()
    logger.info("✅ CHROMA_ENGINE carregado com sucesso - EMBEDDINGS ATIVADOS")
    logger.info(f"✅ ChromaDB inicializado com persistência")
except Exception as e:
    logger.error(f"❌ Erro ao importar CHROMA_ENGINE: {e}", exc_info=True)
    logger.warning("⚠️ Fallback para rag_engine simples")
    try:
        from src.rag_engine import rag_engine
        logger.info("⚠️ RAG engine simples carregado (sem embeddings)")
    except Exception as e2:
        logger.error(f"❌ Erro ao importar RAG engine fallback: {e2}", exc_info=True)
        rag_engine = None

try:
    from src.validation_endpoint import setup_validation_endpoint
    validation_available = True
except Exception as e:
    logger.warning(f"Validação endpoint não disponível: {e}")
    validation_available = False

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

# Setup validation endpoint
if validation_available and rag_engine:
    setup_validation_endpoint(app, rag_engine)
    logger.info("✅ Endpoint /api/validate-rag disponível")

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

@app.get("/api/health")
async def health():
    """Health check com status do RAG"""
    return {
        "status": "online",
        "version": BACKEND_VERSION,
        "rag_available": rag_engine is not None,
        "validation_available": validation_available
    }

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

import uuid
import time
import json
from enum import Enum

class EventType(str, Enum):
    INTRO = "intro"
    USER_QUERY = "query"

class SpeakRequestV2(BaseModel):
    avatar_id: str = Field(..., description="ID do avatar")
    text: str = Field(default="", description="Texto para sintetizar")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto")
    event_type: EventType = Field(EventType.USER_QUERY, description="Tipo de evento")
    session_id: Optional[str] = Field(None, description="ID da sessão")

@app.post("/api/avatar/speak")
async def avatar_speak(request: SpeakRequest):
    """Endpoint principal para fala do avatar com suporte a event_type."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    avatar_id = request.avatar_id
    text = request.text.strip() if request.text else ""
    language = request.language or "pt-BR"
    event_type = request.event_type
    session_id = request.session_id
    
    logger.info(f"[{request_id}] Avatar speak: avatar={avatar_id}, event_type={event_type}, language={language}")
    
    # CORREÇÃO A: Se event_type=intro, retornar saudação automática
    if event_type == EventType.INTRO:
        intro_text = f"Olá! Sou {avatar_id.capitalize()}. Como posso ajudar?"
        logger.info(f"[{request_id}] [INTRO] {avatar_id}: {intro_text}")
        
        # Gerar áudio se disponível
        audio_data = None
        visemes = []
        if viseme_sync:
            try:
                result = await viseme_sync.synthesize_with_visemes(intro_text, avatar_id, language)
                if result:
                    audio_data = result.get("audio")
                    visemes = result.get("visemes", [])
            except Exception as e:
                logger.error(f"Erro ao gerar áudio para intro: {e}")
        
        return {
            "success": True,
            "text_response": intro_text,
            "audio_data": audio_data,
            "visemes": visemes,
            "source": "intro",
            "avatar_id": avatar_id,
            "language": language,
            "request_id": request_id
        }
    
    # Se event_type=query, usar pipeline LLM com RAG
    if not text:
        raise HTTPException(status_code=400, detail="Campo 'text' é obrigatório para queries")
    
    if language not in app.state.supported_languages:
        language = "pt-BR"
    
    logger.info(f"[{request_id}] Avatar speak: avatar={avatar_id}, language={language}, text='{text[:100]}'")
    
    # PIPELINE LLM: RAG + LLMOrchestrator
    response_text = text
    llm_source = "fallback"
    rag_used = False
    docs_found = 0
    avg_score = 0.0
    fallback_reason = "NONE"
    
    # Importar SessionMemory no topo
    from src.session_memory import SessionMemory
    
    try:
        # 1. Buscar contexto do RAG
        context_docs = ""
        if rag_engine:
            try:
                result = rag_engine.generate_response(text, avatar_id, language)
                if result and isinstance(result, str) and len(result) > 0:
                    context_docs = result
                    rag_used = True
                    docs_found = 1
                    avg_score = 0.25
                    logger.info(f"[{request_id}] ✅ RAG: {len(context_docs)} chars de contexto")
            except Exception as e:
                logger.warning(f"[{request_id}] ⚠️ RAG erro: {e}")
        
        # 2. Buscar histórico da sessão
        history = []
        if session_id:
            try:
                mem = SessionMemory(session_id)
                history = mem.get_history()
                logger.info(f"[{request_id}] ✅ Histórico: {len(history)} mensagens")
            except Exception as e:
                logger.warning(f"[{request_id}] ⚠️ Histórico erro: {e}")
        
        # 3. Buscar system prompt do avatar
        system_prompt = ""
        try:
            from src.brain_manager import BrainManager
            brain_manager = BrainManager()
            system_prompt = brain_manager.get_system_prompt(avatar_id)
            if not system_prompt:
                system_prompt = f"Você é {avatar_id.capitalize()}, assistente virtual. Responda em português."
            logger.info(f"[{request_id}] ✅ System prompt: {len(system_prompt)} chars")
        except Exception as e:
            logger.warning(f"[{request_id}] ⚠️ System prompt erro: {e}")
            system_prompt = f"Você é {avatar_id.capitalize()}, assistente virtual. Responda em português."
        
        # 4. Gerar resposta com LLM real (OpenRouter)
        try:
            from src.llm_orchestrator import generate_llm_response
            
            llm_result = await generate_llm_response(
                system_prompt=system_prompt,
                context=context_docs,
                history=history,
                query=text
            )
            
            response_text = llm_result['response']
            llm_source = llm_result['source']
            logger.info(f"[{request_id}] ✅ LLM ({llm_source}): {len(response_text)} chars")
            
        except Exception as e:
            logger.error(f"[{request_id}] ❌ LLM erro: {e}", exc_info=True)
            fallback_reason = "LLM_ERROR"
            # Fallback para RAG se LLM falhar
            if context_docs:
                response_text = context_docs
                llm_source = "rag_fallback"
            else:
                response_text = text
                llm_source = "fallback"
        
        # 5. Salvar na memória da sessão
        if session_id:
            try:
                mem = SessionMemory(session_id)
                mem.add_turn(text, response_text)
                logger.info(f"[{request_id}] ✅ Sessão salva")
            except Exception as e:
                logger.warning(f"[{request_id}] ⚠️ Sessão erro: {e}")
    
    except Exception as e:
        logger.error(f"[{request_id}] ❌ Pipeline erro: {e}", exc_info=True)
        fallback_reason = "PIPELINE_ERROR"
        response_text = text
    
    # 2️⃣ Gerar áudio e visemes com a resposta inteligente
    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            logger.info(f"Gerando áudio com resposta: {response_text[:100]}")
            result = await viseme_sync.synthesize_with_visemes(response_text, avatar_id, language)
            if result:
                audio_data = result.get("audio")
                visemes = result.get("visemes", [])
                logger.info(f"Áudio gerado: {len(audio_data) if audio_data else 0} bytes, {len(visemes)} visemes")
        except Exception as e:
            logger.error(f"Erro ao gerar áudio: {e}")
    
    # Log estruturado para observabilidade
    latency_ms = int((time.time() - start_time) * 1000)
    structured_log = {
        "request_id": request_id,
        "avatar_id": avatar_id,
        "rag_used": rag_used,
        "docs_found": docs_found,
        "avg_score": avg_score,
        "fallback_reason": fallback_reason,
        "latency_ms": latency_ms,
        "audio_generated": bool(audio_data),
        "visemes_count": len(visemes)
    }
    logger.info(f"[{request_id}] 📊 METRICS: {json.dumps(structured_log)}")
    logger.info(f"🔍 DIAGNÓSTICO - Retornando: audio={bool(audio_data)}, visemes={len(visemes)}, response='{response_text[:50]}'")
    
    return {
        "success": True,
        "text_response": response_text,
        "audio_data": audio_data,
        "visemes": visemes,
        "language": language,
        "avatar_id": avatar_id,
        "supported_languages": app.state.supported_languages,
        "request_id": request_id,
        "source": llm_source,
        "metrics": structured_log
    }

@app.post("/api/avatar/speak-v2")
async def avatar_speak_v2(request: SpeakRequestV2):
    """Endpoint v2 com suporte a event_type (intro/query)"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    avatar_id = request.avatar_id
    text = request.text.strip() if request.text else ""
    language = request.language or "pt-BR"
    event_type = request.event_type
    
    logger.info(f"[{request_id}] Avatar speak v2: avatar={avatar_id}, event_type={event_type}, language={language}")
    
    # AÇÃO 1: Se event_type=intro, retornar saudação automática
    if event_type == EventType.INTRO:
        intro_text = f"Olá! Sou {avatar_id.capitalize()}. Como posso ajudar?"
        logger.info(f"[{request_id}] [INTRO] {avatar_id}: {intro_text}")
        return {
            "success": True,
            "text_response": intro_text,
            "source": "intro",
            "avatar_id": avatar_id,
            "language": language,
            "request_id": request_id
        }
    
    # Se event_type=query, usar pipeline normal (RAG + LLM)
    if not text:
        raise HTTPException(status_code=400, detail="text não pode estar vazio para queries")
    
    # Resto do pipeline normal...
    response_text = text
    rag_used = False
    docs_found = 0
    avg_score = 0.0
    fallback_reason = "NONE"
    
    if rag_engine:
        try:
            logger.info(f"[{request_id}] Chamando rag_engine.generate_response...")
            result = rag_engine.generate_response(text, avatar_id, language)
            if result and isinstance(result, str) and len(result) > 0:
                response_text = result
                rag_used = True
                docs_found = 1
                avg_score = 0.25
                logger.info(f"[{request_id}] ✅ RAG com resultados")
            else:
                fallback_reason = "NO_DOCS"
                logger.info(f"[{request_id}] ⚠️ RAG retornou vazio")
        except Exception as e:
            fallback_reason = "RAG_ERROR"
            logger.error(f"[{request_id}] ERRO no RAG: {e}", exc_info=True)
    
    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            result = await viseme_sync.synthesize_with_visemes(response_text, avatar_id, language)
            if result:
                audio_data = result.get("audio")
                visemes = result.get("visemes", [])
        except Exception as e:
            logger.error(f"Erro ao gerar áudio: {e}")
    
    latency_ms = int((time.time() - start_time) * 1000)
    structured_log = {
        "request_id": request_id,
        "avatar_id": avatar_id,
        "rag_used": rag_used,
        "docs_found": docs_found,
        "avg_score": avg_score,
        "fallback_reason": fallback_reason,
        "latency_ms": latency_ms,
        "audio_generated": bool(audio_data),
        "visemes_count": len(visemes)
    }
    
    return {
        "success": True,
        "text_response": response_text,
        "audio_data": audio_data,
        "visemes": visemes,
        "language": language,
        "avatar_id": avatar_id,
        "source": "rag" if rag_used else "fallback",
        "request_id": request_id,
        "metrics": structured_log
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
