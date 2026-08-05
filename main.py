import os
import logging
import asyncio
import re
from pathlib import Path
from typing import Optional
from enum import Enum
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("humanos-digitais-tts-rag-llm")

BACKEND_VERSION = "7.1.0"

try:
    from src.feature_catalog import INSTITUTIONAL_BLOCK
    logger.info("feature_catalog carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar feature_catalog: {e}")
    INSTITUTIONAL_BLOCK = ""


def sanitize_for_tts(text: str) -> str:
    """Remove TODOS os símbolos markdown/especiais, preserva apenas texto falável."""
    if not text:
        return ""
    # 1. Remove headers markdown (###, ##, #)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'#{1,6}', '', text)
    # 2. Remove bold/italic markers, PRESERVA conteúdo
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'___([^_]+)___', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # 3. Remove aspas, preserva conteúdo
    text = re.sub(r'[\u201c\u201d\u201e\'\"]([^\u201c\u201d\u201e\'\"\n]+)[\u201c\u201d\u201e\'\"]', r'\1', text)
    # 4. Remove code blocks e inline code
    text = re.sub(r'```[^`]*```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # 5. Remove markdown links [texto](url) → texto
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 6. Remove bullet points e listas
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 7. Remove emojis
    text = re.sub(r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0001F680-\U0001F6FF]', '', text)
    # 8. Remove parênteses curtos (UI states), preserva longos
    text = re.sub(r'\([^)]{0,40}\)', '', text)
    text = re.sub(r'\(([^)]{41,})\)', r'\1', text)
    # 9. Remove símbolos especiais restantes
    text = re.sub(r'[#*_~`|>]', '', text)
    # 10. Normaliza pontuação
    text = re.sub(r',{2,}', ', ', text)
    text = re.sub(r'\.{2,}', '. ', text)
    text = re.sub(r'!{2,}', '!', text)
    text = re.sub(r'\?{2,}', '?', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


class EventType(str, Enum):
    INTRO = "intro"
    USER_QUERY = "query"

class SpeakRequest(BaseModel):
    avatar_id: str = Field(..., description="ID do avatar")
    text: str = Field(default="", description="Texto para sintetizar")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto (pt-BR, en, es)")
    event_type: EventType = Field(EventType.USER_QUERY, description="Tipo de evento")
    session_id: Optional[str] = Field(None, description="ID da sessão")
    context_url: Optional[str] = Field(None, description="URL da página onde o visitante está")

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


# ============================================================================
# RAG READINESS FLAG (P0-REGRESSÃO)
# Bloqueia consultas RAG enquanto ingestão não estiver completa
# ============================================================================
RAG_READY = False

def is_ingestion_ready() -> bool:
    """Gate baseado em colecoes reais, não em flag volátil."""
    if os.path.exists("/tmp/ingestion_complete"):
        return True
    try:
        if rag_engine and hasattr(rag_engine, 'client') and rag_engine.client:
            cols = rag_engine.client.list_collections()
            total = sum(c.count() for c in cols)
            if total > 0:
                logger.info(f"Ingestão pronta via coleções persistidas (sem flag): {len(cols)} coleções, {total} docs")
                return True
    except Exception as e:
        logger.warning(f"check coleções falhou: {e}")
    return False

def rag_ready_check():
    """Retorna True se RAG está pronto para consultas. Senão, retorna False."""
    return RAG_READY or is_ingestion_ready()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Iniciando humanos-digitais-tts-rag-llm v{BACKEND_VERSION}")
    
    translation_available = i18n_engine is not None
    tts_available = viseme_sync is not None
    
    app.state.translation_available = translation_available
    app.state.tts_available = tts_available
    app.state.supported_languages = ["pt-BR", "en", "es"] if translation_available else ["pt-BR"]
    
    logger.info(f"Traducao disponivel: {translation_available}")
    logger.info(f"TTS/Visemes disponivel: {tts_available}")
    
    # Verificar se ingestão já foi concluída
    global RAG_READY
    if is_ingestion_ready():
        RAG_READY = True
        logger.info("✅ Ingestão já concluída (flag encontrada)")
    else:
        logger.info("⏳ Aguardando ingestão em background...")
    
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
# Configurar CORS com domínios do Vercel e desenvolvimento
origins_str = os.getenv("CORS_ALLOW_ORIGINS", "")
origins_list = [origin.strip() for origin in origins_str.split(",") if origin.strip()]

# Se nenhum domínio foi configurado via env, usar defaults
if not origins_list:
    origins_list = [
        "https://humanosdigitais-website-fix.vercel.app",
        "https://humanosdigitais-website.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "*"  # remover em produção final se necessário
    ]

logger.info(f"CORS configurado para: {origins_list}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
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

@app.api_route("/", methods=["GET", "HEAD"])
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
    return {
        "status": "healthy",
        "version": BACKEND_VERSION,
        "rag_ready": RAG_READY or is_ingestion_ready()
    }

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
    context_url: Optional[str] = Field(None, description="URL da página onde o visitante está")

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
    context_url = request.context_url
    
    if context_url:
        logger.info(f"[{request_id}] context_url recebido: {context_url}")
    else:
        logger.info(f"[{request_id}] context_url não recebido")
    logger.info(f"[{request_id}] Avatar speak: avatar={avatar_id}, event_type={event_type}, language={language}")
    
    # CORREÇÃO A: Se event_type=intro, retornar saudação do avatar
    if event_type == EventType.INTRO:
        try:
            from src.brain_manager import BrainManager
            brain_manager = BrainManager()
            intro_text = text if text else brain_manager.get_greeting(avatar_id)
        except Exception as e:
            logger.warning(f"[{request_id}] ⚠️ BrainManager erro na intro: {e}")
            intro_text = text if text else f"Olá! Sou {avatar_id.capitalize()}. Como posso ajudar?"
        logger.info(f"[{request_id}] [INTRO] {avatar_id}: {intro_text}")
        
        # Gerar áudio se disponível
        audio_data = None
        visemes = []
        if viseme_sync:
            try:
                result = await viseme_sync.synthesize_with_visemes(sanitize_for_tts(intro_text), avatar_id, language)
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
    
    # Verificar se ingestao esta completa
    if not is_ingestion_ready():
        logger.warning(f"[{request_id}] RAG ainda nao pronto, gerando TTS do fallback")
        fallback_text = (
            "Ainda estou organizando meu conhecimento. "
            "Por favor, tente novamente em instantes."
        )
        
        # Gerar áudio para o fallback
        audio_data = None
        visemes = []
        if viseme_sync:
            try:
                result = await viseme_sync.synthesize_with_visemes(
                    sanitize_for_tts(fallback_text), avatar_id, language or "pt-BR"
                )
                if result:
                    audio_data = result.get("audio")
                    visemes = result.get("visemes", [])
                    logger.info(f"[{request_id}] TTS fallback: {len(audio_data) if audio_data else 0} bytes")
            except Exception as e:
                logger.warning(f"[{request_id}] TTS fallback erro: {e}")
        
        return {
            "success": True,
            "text_response": fallback_text,
            "audio_data": audio_data,
            "visemes": visemes,
            "source": "rag_loading",
            "avatar_id": avatar_id,
            "language": language or "pt-BR",
            "request_id": request_id
        }
    
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
        if rag_engine and rag_ready_check():
            try:
                # Consulta real para obter metricas
                query_result = rag_engine.query(text, avatar_id, n_results=3)
                if query_result and not query_result.get("error"):
                    docs = query_result.get("documents", [])
                    distances = query_result.get("distances", [])
                    # Achatar docs (pode ser lista de listas)
                    flat_docs = []
                    for d in docs:
                        if isinstance(d, list):
                            flat_docs.extend(d)
                        else:
                            flat_docs.append(d)
                    context_docs = "\n".join(flat_docs)
                    rag_used = True
                    docs_found = len(flat_docs)
                    # Calcular avg_score real: 1 - distancia (quanto menor a distancia, melhor)
                    flat_distances = []
                    for dd in distances:
                        if isinstance(dd, list):
                            flat_distances.extend(dd)
                        else:
                            flat_distances.append(dd)
                    if flat_distances:
                        avg_score = sum(1 - d for d in flat_distances if isinstance(d, (int, float))) / len(flat_distances)
                    logger.info(f"[{request_id}] ✅ RAG: {docs_found} docs, avg_score={avg_score:.3f}")
                else:
                    logger.info(f"[{request_id}] ⚠️ RAG sem resultados para {avatar_id}")
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
        
        # Injetar bloco institucional obrigatório
        if INSTITUTIONAL_BLOCK:
            system_prompt += "\n\n" + INSTITUTIONAL_BLOCK
        
        # Injetar context_url no system prompt
        if context_url:
            system_prompt += f"\n\nO visitante está atualmente na página: {context_url}"
        
        logger.info(f"[{request_id}] System prompt final: {len(system_prompt)} chars (com institutional)")
        
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
            
            # P0-9: Pós-processamento anti-truncamento
            from src.llm_orchestrator import _fix_truncation
            trunc_result = _fix_truncation(response_text)
            if trunc_result['was_truncated']:
                logger.info(f"[{request_id}] ⚠️ TRUNCAMENTO DETECTADO E CORRIGIDO")
                response_text = trunc_result['fixed_text']
            
        except Exception as e:
            logger.error(f"[{request_id}] ❌ LLM erro: {e}", exc_info=True)
            fallback_reason = "LLM_ERROR"
            # Fallback: tenta formular resposta a partir do contexto via cascata
            if context_docs:
                try:
                    from src.llm_orchestrator import generate_llm_response
                    fr = await generate_llm_response(
                        system_prompt + "\nResponda APENAS com base no contexto, em 1-2 frases.",
                        context_docs, [], text
                    )
                    response_text = fr['response']
                    llm_source = fr['source']
                except Exception:
                    from src.llm_orchestrator import _rag_fallback
                    response_text = _rag_fallback(context_docs)
                    llm_source = "rag_fallback"
            else:
                response_text = "Desculpe, não tenho informação sobre isso no momento."
                llm_source = "no_context"
        
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
        response_text = (
            "Desculpe, tive uma dificuldade técnica para processar sua pergunta. "
            "Poderia reformular ou tentar novamente?"
        )
    
    # 2️⃣ Gerar áudio e visemes com a resposta inteligente
    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            logger.info(f"Gerando áudio com resposta: {response_text[:100]}")
            # P0-9: Garantir que o texto não termina truncado antes do TTS
            from src.llm_orchestrator import _fix_truncation
            trunc_result = _fix_truncation(response_text)
            if trunc_result['was_truncated']:
                logger.info(f"[{request_id}] ⚠️ TRUNCAMENTO pré-TTS detectado e corrigido")
                response_text = trunc_result['fixed_text']
            result = await viseme_sync.synthesize_with_visemes(sanitize_for_tts(response_text), avatar_id, language)
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
    
    # P0-11: Identificar source e garantir consistência text_display/text_spoken
    if fallback_reason == "NO_CONTEXT":
        source = "rag_llm_tts"
    elif rag_used:
        source = "rag_llm_tts"
    elif event_type and hasattr(event_type, 'value') and event_type.value == "intro":
        source = "avatar_speak_llm"
    else:
        source = llm_source or "rag_llm_tts"
    
    # text_display e text_spoken são o mesmo texto (texto final do LLM, sanitizado para TTS)
    text_spoken = sanitize_for_tts(response_text)
    text_display = response_text
    
    return {
        "success": True,
        "response_id": request_id,
        "text_response": response_text,
        "text_display": text_display,
        "text_spoken": text_spoken,
        "audio_data": audio_data,
        "visemes": visemes,
        "visemes_count": len(visemes),
        "language": language,
        "avatar_id": avatar_id,
        "supported_languages": app.state.supported_languages,
        "request_id": request_id,
        "source": source,
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

    # AÇÃO 1: Se event_type=intro, retornar saudação do avatar
    if event_type == EventType.INTRO:
        try:
            from src.brain_manager import BrainManager
            brain_manager = BrainManager()
            intro_text = text if text else brain_manager.get_greeting(avatar_id)
        except Exception as e:
            logger.warning(f"[{request_id}] ⚠️ BrainManager erro na intro: {e}")
            intro_text = text if text else f"Olá! Sou {avatar_id.capitalize()}. Como posso ajudar?"
        logger.info(f"[{request_id}] [INTRO] {avatar_id}: {intro_text}")
        return {
            "success": True,
            "text_response": intro_text,
            "source": "intro",
            "avatar_id": avatar_id,
            "language": language,
            "request_id": request_id,
            "visemes": []
        }

    # Se event_type=query, usar pipeline normal (RAG + LLM)
    if not text:
        raise HTTPException(status_code=400, detail="text não pode estar vazio para queries")

    # Pipeline LLM completo com RAG (igual ao v1)
    response_text = text
    llm_source = "fallback"
    rag_used = False
    docs_found = 0
    avg_score = 0.0
    fallback_reason = "NONE"
    context_docs = ""
    context_url = request.context_url

    # P0-13: Log obrigatório de context_url
    if context_url:
        logger.info(f"[{request_id}] context_url recebido: {context_url}")
    else:
        logger.info(f"[{request_id}] context_url não recebido")

    try:
        # 1. Buscar contexto do RAG
        if rag_engine and rag_ready_check():
            try:
                query_result = rag_engine.query(text, avatar_id, n_results=3)
                if query_result and not query_result.get("error"):
                    docs = query_result.get("documents", [])
                    distances = query_result.get("distances", [])
                    flat_docs = []
                    for d in docs:
                        if isinstance(d, list):
                            flat_docs.extend(d)
                        else:
                            flat_docs.append(d)
                    context_docs = "\n".join(flat_docs)
                    rag_used = True
                    docs_found = len(flat_docs)
                    flat_distances = []
                    for dd in distances:
                        if isinstance(dd, list):
                            flat_distances.extend(dd)
                        else:
                            flat_distances.append(dd)
                    if flat_distances:
                        avg_score = sum(1 - d for d in flat_distances if isinstance(d, (int, float))) / len(flat_distances)
                    logger.info(f"[{request_id}] ✅ RAG v2: {docs_found} docs, avg_score={avg_score:.3f}")
                else:
                    fallback_reason = "NO_DOCS"
                    logger.info(f"[{request_id}] ⚠️ RAG sem resultados")
            except Exception as e:
                fallback_reason = "RAG_ERROR"
                logger.error(f"[{request_id}] ERRO no RAG: {e}", exc_info=True)

        # 2. Buscar system prompt do avatar
        system_prompt = ""
        try:
            from src.brain_manager import BrainManager
            brain_manager = BrainManager()
            system_prompt = brain_manager.get_system_prompt(avatar_id)
            if not system_prompt:
                system_prompt = f"Você é {avatar_id.capitalize()}, assistente virtual. Responda em português."
        except Exception as e:
            logger.warning(f"[{request_id}] ⚠️ System prompt erro: {e}")
            system_prompt = f"Você é {avatar_id.capitalize()}, assistente virtual. Responda em português."

        # P0-8: Injetar guardrail institucional
        if INSTITUTIONAL_BLOCK:
            system_prompt += "\n\n" + INSTITUTIONAL_BLOCK

        # Injetar context_url no system prompt
        if context_url:
            system_prompt = system_prompt + "\n\nO visitante está atualmente na página: " + context_url + ". Use essa informação para contextualizar sua resposta quando fizer sentido."

        # 3. Gerar resposta com LLM
        try:
            from src.llm_orchestrator import generate_llm_response
            llm_result = await generate_llm_response(
                system_prompt=system_prompt,
                context=context_docs,
                history=[],
                query=text
            )
            response_text = llm_result['response']
            llm_source = llm_result['source']
            logger.info(f"[{request_id}] ✅ LLM v2 ({llm_source}): {len(response_text)} chars")
        except Exception as e:
            logger.error(f"[{request_id}] ❌ LLM erro: {e}", exc_info=True)
            fallback_reason = "LLM_ERROR"
            if context_docs:
                try:
                    from src.llm_orchestrator import generate_llm_response
                    fr = await generate_llm_response(
                        system_prompt + "\nResponda APENAS com base no contexto, em 1-2 frases.",
                        context_docs, [], text
                    )
                    response_text = fr['response']
                    llm_source = fr['source']
                except Exception:
                    from src.llm_orchestrator import _rag_fallback
                    response_text = _rag_fallback(context_docs)
                    llm_source = "rag_fallback"
            else:
                response_text = "Desculpe, não tenho informação sobre isso no momento."
                llm_source = "no_context"
    except Exception as e:
        logger.error(f"[{request_id}] ❌ Pipeline v2 erro: {e}", exc_info=True)
        fallback_reason = "PIPELINE_ERROR"
        response_text = (
            "Desculpe, tive uma dificuldade técnica para processar sua pergunta. "
            "Poderia reformular ou tentar novamente?"
        )

    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            result = await viseme_sync.synthesize_with_visemes(sanitize_for_tts(response_text), avatar_id, language)
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
        "response_id": request_id,
        "text_response": response_text,
        "audio_data": audio_data,
        "visemes": visemes,
        "visemes_count": len(visemes),
        "language": language,
        "avatar_id": avatar_id,
        "source": llm_source,
        "request_id": request_id,
        "metrics": structured_log
    }
@app.post("/api/tts")
async def text_to_speech(request: dict):
    """Endpoint TTS puro — recebe texto, retorna áudio + visemes."""
    text = request.get("text", "").strip()
    language = request.get("language", "pt-BR")
    avatar_id = request.get("avatar_id", "sofia")

    if not text:
        raise HTTPException(status_code=400, detail="text é obrigatório")

    clean_text = sanitize_for_tts(text)

    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            result = await viseme_sync.synthesize_with_visemes(clean_text, avatar_id, language)
            if result:
                audio_data = result.get("audio")
                visemes = result.get("visemes", [])
        except Exception as e:
            logger.error(f"Erro TTS: {e}")
            raise HTTPException(status_code=500, detail=f"TTS falhou: {str(e)}")

    return {
        "success": True,
        "audio_data": audio_data,
        "visemes": visemes,
        "text": clean_text,
        "language": language
    }

@app.post("/api/tts-direct")
async def tts_direct(request: dict):
    """Endpoint TTS direto — sem RAG, sem LLM. Apenas texto → áudio + visemes."""
    text = request.get("text", "").strip()
    language = request.get("language", "pt-BR")
    avatar_id = request.get("avatar_id", "sofia")

    if not text:
        raise HTTPException(status_code=400, detail="text é obrigatório")

    if not viseme_sync:
        raise HTTPException(status_code=503, detail="Motor TTS não disponível")

    # Sanitizar texto para TTS
    clean_text = sanitize_for_tts(text)

    try:
        result = await viseme_sync.synthesize_with_visemes(clean_text, avatar_id, language)
        if result and result.get("audio"):
            return {
                "success": True,
                "audio_data": result["audio"],
                "visemes": result.get("visemes", []),
                "text": clean_text,
                "avatar_id": avatar_id,
                "language": language,
                "sample_rate": result.get("sample_rate", 24000)
            }
        else:
            raise HTTPException(status_code=500, detail="TTS não retornou áudio")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro /api/tts-direct: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS falhou: {str(e)}")


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

# ==================== AVATARES ====================
@app.get("/api/avatars")
async def get_avatars():
    """
    Endpoint dinâmico que varre o diretório /app/knowledge
    e retorna lista de avatares com metadados extraídos.
    """
    knowledge_dir = Path("/app/knowledge")
    avatares = []
    
    # Fallback para ambiente local
    if not knowledge_dir.exists():
        knowledge_dir = Path("./knowledge")
    
    if not knowledge_dir.exists():
        return {"success": False, "avatares": [], "total": 0, "error": "Knowledge directory not found"}
        
    for avatar_dir in sorted(knowledge_dir.iterdir()):
        # Ignora arquivos ou pastas de sistema
        if not avatar_dir.is_dir() or avatar_dir.name.startswith((".", "__", "docs")):
            continue
            
        avatar_id = avatar_dir.name
        role = "Consultor(a) Digital"  # Fallback padrão
        
        # Tenta extrair a role dinamicamente do system_prompt
        prompt_file = avatar_dir / "prompts" / "system_prompt.txt"
        if prompt_file.exists():
            try:
                with open(prompt_file, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip().lower()
                    if "você é" in first_line or "voce é" in first_line:
                        # Extrai simplificado: "Você é Marina, assistente..." -> "assistente"
                        parts = first_line.split("você é")[-1].split(",")[0].strip()
                        if parts:
                            role = parts.title()
                        else:
                            role = "Consultor(a) Digital"
            except Exception as e:
                logger.warning(f"Erro ao ler prompt de {avatar_id}: {e}")
                pass
                
        avatares.append({
            "avatar_id": avatar_id,
            "nome": avatar_id.replace("_", " ").title(),
            "role": role,
            "saudacao": f"Oi! Eu sou {avatar_id.replace('_', ' ').title()}. Como posso ajudar?",
            "imagem": f"/assets/avatares/estaticas/{avatar_id}-principal.png"
        })
        
    return {"success": True, "avatares": avatares, "total": len(avatares)}

# ==================== STARTUP ====================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
