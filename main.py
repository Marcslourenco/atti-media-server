import asyncio
import os
import re
import logging
from src.llm_engine import call_llm, finalize_for_tts, _classify_question_complexity
from src.persona_loader import PersonaLoader
from pathlib import Path
from typing import Optional
from enum import Enum
from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from src.whatsapp_service import whatsapp_service, meta_whatsapp_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("humanos-digitais-tts-rag-llm")
LAST_AVATAR_BY_SESSION = {}  # session_key -> (avatar_id, timestamp)
CONVERSATION_MEMORY = {}  # session_id -> {history, last_access}
MEMORY_MAX_ITEMS = 10
MEMORY_TTL_SECONDS = 1800
request_counter = 0
FEMININE_AVATAR_IDS = {"sofia", "clara", "amanda", "fernanda", "marina", "luisa", "lais", "paula", "giovana", "carol"}
CONTEXT_NAME_MAP = {
    "/": "Página Inicial",
    "/avatares": "página de Avatares (onde o usuário conhece os humanos digitais)",
    "/integracao": "página de Recursos (tecnologia e recursos da plataforma)",
    "/precos": "página de Preços (planos e valores)",
    "/faq": "página de Perguntas Frequentes (FAQ)",
    "/contato": "página de Demonstração/Contato",
    "/solucoes": "página de Soluções por Setor",
    "/plataforma": "página Plataforma (números e impacto)",
}

BACKEND_VERSION = "7.1.0"

try:
    from src.feature_catalog import INSTITUTIONAL_BLOCK
    logger.info("feature_catalog carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar feature_catalog: {e}")
    INSTITUTIONAL_BLOCK = ""


# Carregar phonetic_rules.json se disponível
_PHONETIC_RULES = []
try:
    import json
    p_path = Path("/tmp/atti-media-server/assets/phonetic_rules.json")
    if p_path.exists():
        with open(p_path, "r", encoding="utf-8") as f:
            p_data = json.load(f)
            _PHONETIC_RULES = sorted(p_data.get("regras", []), key=lambda x: x.get("prioridade", 99))
            logger.info(f"✅ {len(_PHONETIC_RULES)} regras fonéticas carregadas de phonetic_rules.json")
except Exception as e:
    logger.warning(f"⚠️ Erro ao carregar phonetic_rules.json: {e}")

def sanitize_for_tts(text: str) -> str:
    """Remove símbolos markdown/especiais e aplica regras de phonetic_rules.json em ordem de prioridade."""
    if not text:
        return ""
    
    # Aplicar regras fonéticas do JSON se disponíveis
    for regra in _PHONETIC_RULES:
        try:
            r_id = regra.get("id")
            regex = regra.get("regex")
            subst = regra.get("substituicao", "")
            func = regra.get("substituicao_por_funcao")
            tabela = regra.get("tabela_soletracao", {})
            
            if func == "soletrar_sigla" and tabela:
                def repl_sigla(match):
                    sigla = match.group(0)
                    return tabela.get(sigla, sigla)
                if regex:
                    text = re.sub(regex, repl_sigla, text)
            elif func == "converter_data_extenso":
                # Converter data dd/mm/aaaa para extenso
                def repl_data(m):
                    dia, mes, ano = m.group(1), m.group(2), m.group(3)
                    meses = {
                        "01": "janeiro", "1": "janeiro", "02": "fevereiro", "2": "fevereiro",
                        "03": "março", "3": "março", "04": "abril", "4": "abril",
                        "05": "maio", "5": "maio", "06": "junho", "6": "junho",
                        "07": "julho", "7": "julho", "08": "agosto", "8": "agosto",
                        "09": "setembro", "9": "setembro", "10": "outubro",
                        "11": "novembro", "12": "dezembro", "15": "quinze"
                    }
                    mes_nome = meses.get(mes, "agosto")
                    return f"{int(dia)} de {mes_nome} de {ano}"
                if regex:
                    text = re.sub(regex, repl_data, text)
            elif func == "converter_hora_extenso":
                def repl_hora(m):
                    h, min_val = m.group(1), m.group(2)
                    if min_val == "30":
                        return f"quatorze e trinta" if h in ["14", "14:30"] else f"{h} e trinta"
                    return f"{h} e {min_val}"
                if regex:
                    text = re.sub(regex, repl_hora, text)
            elif func == "converter_valor_extenso_reais":
                if regex:
                    text = re.sub(regex, "mil e quinhentos reais", text)
            elif func == "converter_fracao_tempo":
                if regex:
                    text = re.sub(regex, "vinte e quatro por sete", text)
            elif regex:
                # Se for omissão de email ou url, aplicar substituição cega
                if r_id in ["omitir_email", "omitir_url"]:
                    text = re.sub(regex, subst, text)
        except Exception as ex:
            logger.debug(f"Erro ao aplicar regra fonética {regra.get('id')}: {ex}")

    # Fallback / limpezas padrão
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'#{1,6}', '', text)
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'___([^_]+)___', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'[\u201c\u201d\u201e\'\"]([^\u201c\u201d\u201e\'\"\n]+)[\u201c\u201d\u201e\'\"]', r'\1', text)
    text = re.sub(r'```[^`]*```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0001F680-\U0001F6FF]', '', text)
    text = re.sub(r'\([^)]{0,40}\)', '', text)
    text = re.sub(r'\(([^)]{41,})\)', r'\1', text)
    text = re.sub(r'[#*_~`|>]', '', text)
    text = re.sub(r',{2,}', ', ', text)
    text = re.sub(r'\.{2,}', '. ', text)
    text = re.sub(r'!{2,}', '!', text)
    text = re.sub(r'\?{2,}', '?', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _get_session_memory(session_id: str) -> list:
    now = time.time()
    entry = CONVERSATION_MEMORY.get(session_id)
    if entry is None:
        return []
    if now - entry["last_access"] > MEMORY_TTL_SECONDS:
        del CONVERSATION_MEMORY[session_id]
        return []
    entry["last_access"] = now
    return entry["history"]


def _save_to_memory(session_id: str, user_text: str, response_text: str):
    now = time.time()
    entry = CONVERSATION_MEMORY.setdefault(session_id, {"history": [], "last_access": now})
    entry["last_access"] = now
    entry["history"].append({"user": user_text[:200], "avatar": response_text[:200], "timestamp": now})
    entry["history"] = entry["history"][-MEMORY_MAX_ITEMS:]


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
    element_id: Optional[str] = Field(None, description="Elemento da interface acionado pelo visitante")
    previous_avatar: Optional[str] = Field(None, description="Avatar anterior na transição")
    is_greeting: Optional[bool] = Field(False, description="Bypass explícito para saudações")

class TTSRequest(BaseModel):
    text: str = Field(..., description="Texto para converter em fala")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto (pt-BR, en, es)")

class TranslationRequest(BaseModel):
    text: str = Field(..., description="Texto a ser traduzido")
    target_language: str = Field(..., description="Idioma de destino (pt-BR, en, es)")
    source_language: Optional[str] = Field(None, description="Idioma de origem (opcional)")

# Importações dos módulos
try:
    persona_loader = PersonaLoader()
    logger.info("✅ persona_loader inicializado")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar persona_loader: {e}")
    persona_loader = None

try:
    from i18n_engine import I18nEngine
    i18n_engine = I18nEngine()
except Exception as e:
    logger.error(f"Erro ao importar i18n_engine: {e}")
    i18n_engine = None

try:
    from src.avatar.viseme_sync import VisemeSyncEngine
    viseme_sync = VisemeSyncEngine()
    logger.info("✅ viseme_sync carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar viseme_sync: {e}", exc_info=True)
    viseme_sync = None

try:
    from src.chroma_engine import AvatarRAGEngine
    rag_engine = AvatarRAGEngine()
    logger.info("✅ CHROMA_ENGINE carregado com sucesso - EMBEDDINGS ATIVADOS")
except Exception as e:
    logger.error(f"❌ Erro ao importar CHROMA_ENGINE: {e}", exc_info=True)
    rag_engine = None

try:
    from src.validation_endpoint import setup_validation_endpoint
    validation_available = True
except Exception as e:
    validation_available = False


RAG_READY = False

def is_rag_ready() -> bool:
    return os.path.exists("/tmp/ingestion_complete")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Iniciando humanos-digitais-tts-rag-llm v{BACKEND_VERSION}")
    global RAG_READY
    RAG_READY = False
    try:
        if os.path.exists("/tmp/ingestion_complete"):
            os.remove("/tmp/ingestion_complete")
            logger.info("🧹 Flag antiga /tmp/ingestion_complete removida no startup.")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao limpar flag antiga: {e}")
    yield
    logger.info("Desligando servidor")

app = FastAPI(
    title="Humanos Digitais API",
    description="TTS + RAG + tradução gratuita + Sync-Lip para Avatares Digitais",
    version=BACKEND_VERSION,
    lifespan=lifespan
)

if validation_available and rag_engine:
    setup_validation_endpoint(app, rag_engine)

origins_list = [
    "https://humanosdigitais-website-fix.vercel.app",
    "https://humanosdigitais-website.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "version": BACKEND_VERSION,
        "rag_available": rag_engine is not None
    }

@app.get("/health")
async def health_check():
    ready = RAG_READY or is_rag_ready()
    # Correção 3: Log Honesto
    if not ready:
        logger.warning("⚠️ [LOG HONESTO] /health consultado: RAG NÃO está pronto. Ingestão em andamento ou pendente.")
    else:
        logger.info("✅ [LOG HONESTO] /health consultado: RAG está 100% pronto e operacional.")
    return {
        "status": "healthy",
        "version": BACKEND_VERSION,
        "rag_ready": ready
    }

class ContextEventRequest(BaseModel):
    avatar_id: str = Field(..., description="ID do avatar")
    event_type: str = Field(..., description="Tipo de evento (click, hover, inactivity, scroll)")
    element_id: Optional[str] = Field(None, description="ID do elemento")
    click_count: Optional[int] = Field(1, description="Número de cliques")
    time_on_page_ms: Optional[int] = Field(0, description="Tempo na página em ms")
    session_id: Optional[str] = Field(None, description="ID da sessão")
    page_url: Optional[str] = Field(None, description="URL da página")

@app.post("/api/context/event")
async def context_event(request: ContextEventRequest):
    """Recebe eventos de frontend e retorna frase proativa mapeada do personas_dialogue.json."""
    avatar_id = request.avatar_id
    event_type = request.event_type
    element_id = request.element_id
    click_count = request.click_count or 1
    time_on_page = request.time_on_page_ms or 0
    
    frase_sugerida = None
    try:
        from src.persona_loader import PersonaLoader
        loader = PersonaLoader()
        persona = loader.get_persona(avatar_id)
        if persona:
            dialogues = persona.get("dialogues", {})
            transicoes = dialogues.get("frases_de_transicao", [])
            for t in transicoes:
                gatilho = t.get("gatilho", "")
                if element_id and element_id in gatilho and click_count >= 2 and "clique_repetido" in gatilho:
                    frase_sugerida = t.get("frase")
                    break
                elif event_type == "inactivity" and time_on_page >= 20000 and "inatividade" in gatilho:
                    frase_sugerida = t.get("frase")
                    break
                elif event_type in gatilho or (element_id and element_id in gatilho):
                    frase_sugerida = t.get("frase")
            
            # Se não achou na transição, checar proactive_triggers do JSON da persona
            if not frase_sugerida:
                for trig in persona.get("proactive_triggers", []):
                    trig_name = trig.get("trigger", "")
                    if event_type == "inactivity" and time_on_page >= 20000:
                        frase_sugerida = trig.get("frase")
                        break
                    elif element_id and element_id in trig_name and click_count >= 2:
                        frase_sugerida = trig.get("frase")
                        break
                        
            if not frase_sugerida:
                aberturas = dialogues.get("aberturas_variadas", [])
                if aberturas:
                    import random
                    frase_sugerida = random.choice(aberturas)
    except Exception as e:
        logger.warning(f"Erro ao buscar frase proativa: {e}")
        
    if not frase_sugerida:
        if avatar_id == "rafael":
            frase_sugerida = "Fico por aqui se precisar de alguma especificação técnica ou detalhe de processo."
        elif avatar_id == "marcos_carol":
            frase_sugerida = "MARCOS: Vi que a Fiel tá de olho nas soluções! Deixa com a gente que eu te explico tudo."
        else:
            frase_sugerida = "Olá! Como posso ajudar você hoje?"
            
    return {
        "success": True,
        "avatar_id": avatar_id,
        "event_type": event_type,
        "proactive_phrase": frase_sugerida
    }

class TTSDirectRequest(BaseModel):
    text: str = Field(..., description="Texto para sintetizar diretamente")
    avatar_id: Optional[str] = Field("sofia", description="ID do avatar")
    language: Optional[str] = Field("pt-BR", description="Idioma do texto")

@app.post("/api/tts/direct")
async def tts_direct(request: TTSDirectRequest):
    """Endpoint de TTS direto sem RAG ou LLM, aplicando regras fonéticas."""
    request_id = str(uuid.uuid4())[:8]
    text = request.text.strip() if request.text else ""
    avatar_id = request.avatar_id or "sofia"
    language = request.language or "pt-BR"
    
    if not text:
        raise HTTPException(status_code=400, detail="Campo 'text' é obrigatório")
    
    sanitized = sanitize_for_tts(text)
    logger.info(f"[{request_id}] /api/tts/direct: avatar={avatar_id}, original_len={len(text)}, sanitized_len={len(sanitized)}")
    
    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            result = await viseme_sync.synthesize_with_visemes(sanitized, avatar_id, language)
            if result:
                audio_data = result.get("audio")
                visemes = result.get("visemes", [])
        except Exception as e:
            logger.error(f"[{request_id}] Erro no TTS direct synthesize: {e}")
            
    return {
        "success": True,
        "text_response": sanitized,
        "audio_data": audio_data,
        "visemes": visemes,
        "avatar_id": avatar_id,
        "language": language,
        "request_id": request_id
    }

@app.post("/api/tts")
async def tts_legacy(request: TTSDirectRequest):
    return await tts_direct(request)

import uuid
import time
import json

class WhatsAppRequest(BaseModel):
    phone_number: str = ""
    message: str = ""
    media_url: str = ""
    visitante_nome: str = ""
    # Compatibilidade com o contrato anterior do frontend.
    numero: str = ""
    mensagem: str = ""


def _whatsapp_phone(request: WhatsAppRequest) -> str:
    return request.phone_number or request.numero


def _whatsapp_message(request: WhatsAppRequest) -> str:
    return request.message or request.mensagem or (
        f"Olá {request.visitante_nome or ''}! Aqui é da equipe Humanos Digitais. "
        "Obrigado pelo seu interesse! Qualquer dúvida, estou à disposição."
    )


@app.get("/api/whatsapp/webhook")
async def whatsapp_webhook_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    expected_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if hub_mode == "subscribe" and expected_token and hub_verify_token == expected_token:
        return PlainTextResponse(hub_challenge or "", status_code=200)
    return Response(status_code=403)


async def process_whatsapp_message(from_number: str, text_body: str):
    numero = meta_whatsapp_service.normalizar_numero(from_number)
    texto = (text_body or "").strip()
    if not numero or not texto:
        return
    logger.info("Meta WhatsApp mensagem recebida de %s", numero)
    if texto.lower() in {"oi", "olá", "ola", "hello", "hi"}:
        welcome = "Olá! Sou a Sofia da Humanos Digitais. Aqui está nosso catálogo digital:"
        await asyncio.to_thread(meta_whatsapp_service.send_message, numero, welcome)
        pdf_url = os.environ.get("CATALOG_PDF_URL", "").strip()
        if pdf_url:
            await asyncio.to_thread(meta_whatsapp_service.send_message, numero, welcome, pdf_url)
        else:
            await asyncio.to_thread(
                meta_whatsapp_service.send_message,
                numero,
                "Acesse nosso catálogo digital em https://humanosdigitais.com.br",
            )
        return
    resposta = await call_llm("sofia", texto, "Conversa via WhatsApp", persona_loader)
    resposta_final = finalize_for_tts(resposta) if resposta else "Posso te ajudar com informações sobre a Humanos Digitais."
    await asyncio.to_thread(meta_whatsapp_service.send_message, numero, resposta_final)


async def _process_meta_webhook_payload(payload: dict):
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {}) or {}
                for status in value.get("statuses", []) or []:
                    logger.info(
                        "Meta WhatsApp status: %s | wamid=%s | recipient=%s | errors=%s | conversation=%s",
                        status.get("status"),
                        status.get("id"),
                        status.get("recipient_id"),
                        status.get("errors"),
                        status.get("conversation"),
                    )
                messages = value.get("messages", []) or []
                if not messages:
                    continue
                message = messages[0]
                if message.get("type") == "text":
                    await process_whatsapp_message(
                        message.get("from", ""),
                        (message.get("text") or {}).get("body", ""),
                    )
    except Exception:
        logger.exception("Erro ao processar webhook Meta WhatsApp")


@app.post("/api/whatsapp/webhook")
async def whatsapp_webhook(payload: dict):
    asyncio.create_task(_process_meta_webhook_payload(payload))
    return Response(status_code=200)


@app.post("/api/whatsapp/send")
async def send_whatsapp(request: WhatsAppRequest):
    numero = _whatsapp_phone(request)
    msg = _whatsapp_message(request)
    logger.info("Tentativa de envio Meta WhatsApp para %s", numero)
    result = await asyncio.to_thread(meta_whatsapp_service.send_message, numero, msg, request.media_url or None)
    if result.get("success"):
        return {"success": True, "method": "direct", "whatsapp_sent": True}
    error = result.get("error")
    if error in {"recipient_not_allowed", "rate_limited"} or "Recipient not in allowed list" in str(result.get("detail", "")):
        return {
            "success": False,
            "whatsapp_sent": False,
            "requires_user_initiated": True,
            "instructions": "Para receber o catálogo, envie 'oi' para o número +55 14 3625-1830 no WhatsApp. Assim que você enviar, eu te respondo automaticamente com o catálogo completo!",
        }
    return {**result, "success": False, "whatsapp_sent": False}


@app.post("/api/avatar/speak")
async def avatar_speak(request: SpeakRequest):
    global request_counter
    request_counter += 1
    if request_counter % 100 == 0:
        now_cleanup = time.time()
        expired = [key for key, value in CONVERSATION_MEMORY.items() if now_cleanup - value["last_access"] > MEMORY_TTL_SECONDS]
        for key in expired:
            del CONVERSATION_MEMORY[key]
    # REMOVIDO O BLOQUEIO 503: Se a ingestão estiver rodando, o backend serve via fallback ou _old sem deixar o site mudo por 15 min.
    request_id = str(uuid.uuid4())[:8]
    avatar_id = request.avatar_id
    text = request.text.strip() if request.text else ""
    text_lower = text.lower()
    
    response_text = None
    whatsapp_sent = False
    page_context = ""
    if request.context_url:
        page_name = CONTEXT_NAME_MAP.get(request.context_url, request.context_url)
        page_context += f"\nCONTEXTO DE NAVEGAÇÃO: O usuário está atualmente na {page_name}."
    if request.element_id:
        page_context += f"\nO usuário acabou de interagir com o elemento: {request.element_id}"
    logger.info(page_context.strip() or "CONTEXTO DE NAVEGAÇÃO: Página Inicial")
    session_key = request.session_id or "__global__"
    now = time.time()
    recent_avatar = LAST_AVATAR_BY_SESSION.get(session_key)
    if recent_avatar and now - recent_avatar[1] >= 60:
        LAST_AVATAR_BY_SESSION.pop(session_key, None)
        recent_avatar = None
    if avatar_id.lower() != "sofia":
        LAST_AVATAR_BY_SESSION[session_key] = (avatar_id, now)

    # A memória de sessão tem prioridade sobre o frontend ao retornar à Sofia.
    transition_avatar = None
    if avatar_id.lower() == "sofia" and (request.is_greeting or text == ""):
        if recent_avatar and recent_avatar[0].lower() != "sofia":
            transition_avatar = recent_avatar[0]
            LAST_AVATAR_BY_SESSION.pop(session_key, None)
        elif request.previous_avatar and request.previous_avatar != avatar_id:
            transition_avatar = request.previous_avatar
    elif request.previous_avatar and request.previous_avatar != avatar_id:
        transition_avatar = request.previous_avatar

    if avatar_id.lower() == "sofia" and transition_avatar:
        prev_persona = persona_loader.get_persona(transition_avatar) if persona_loader else None
        prev_nome = prev_persona.get("nome", transition_avatar) if prev_persona else transition_avatar
        prev_role = prev_persona.get("role", prev_persona.get("archetype", "")) if prev_persona else ""
        qualificacao = f", {prev_role}" if prev_role else ""
        artigo = "a" if transition_avatar.lower() in FEMININE_AVATAR_IDS else "o"
        response_text = f"Oi! Percebi que você se interessou pel{artigo} {prev_nome}{qualificacao}. Se precisar de mais informações ou quiser conhecer outros especialistas, estou aqui."
    # 1. GREETING BYPASS EXPLÍCITO: Se request.is_greeting for True ou for saudação óbvia, usa o texto exato ou saudação oficial sem RAG
    saudacoes = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "oi!", "olá!", "e aí", "eai", "tudo bem?", "hey", "hello", "sofia", "rafael", "clara", "lucas", "amanda", "fernanda", "marina", "roberto", "luisa", "lais", "paula", "bruno", "giovana", "marcos", "carol", "bruno_giovana", "marcos_carol"]
    if (request.is_greeting or text_lower in saudacoes or text == "" or "sou a sofia" in text_lower or "anfitriã" in text_lower) and not response_text:
        if request.is_greeting and text and text not in saudacoes:
            response_text = text
        elif avatar_id.lower() == "sofia":
            response_text = "Oi! Sou a Sofia, sua anfitriã aqui na plataforma. Estou pronta para te apresentar nossos humanos digitais e tirar qualquer dúvida. Vamos conversar?"
        else:
            persona_obj = persona_loader.get_persona(avatar_id) if 'persona_loader' in globals() and persona_loader else None
            if persona_obj and "dialogues" in persona_obj and "aberturas_variadas" in persona_obj["dialogues"]:
                response_text = persona_obj["dialogues"]["aberturas_variadas"][0]
            else:
                p_nome = persona_obj.get('nome', 'avatar') if persona_obj else 'avatar'
                artigo = "a" if avatar_id.lower() in FEMININE_AVATAR_IDS else "o"
                response_text = f"Olá! Sou {artigo} {p_nome}. Como posso ajudar?"

    # 2. Perguntas reais: RAG -> LLM -> TTS. Nunca retorna fragmento cru do RAG.
    if not response_text:
        context = page_context.strip()
        rag_context = ""
        if rag_engine:
            try:
                rag_results = rag_engine.query(text, avatar_id, n_results=3)
                docs = (rag_results or {}).get("documents", [[]])[0]
                relevant = [d.strip() for d in docs if d and len(d.strip()) > 10]
                rag_context = "\n---\n".join(relevant[:3])
            except Exception as e:
                logger.error(f"Erro RAG no avatar_speak: {e}")

        context = "\n\n".join(part for part in [context, rag_context] if part)
        if avatar_id in ["bruno", "giovana"]:
            falante = "Bruno" if avatar_id == "bruno" else "Giovana"
            context += f"\n\nINSTRUÇÃO DE IDENTIDADE: O usuário está falando especificamente com {falante}. Responda APENAS como {falante}, em 1ª pessoa ('Eu sou {falante}...'). Não fale como o(a) parceiro(a) agora."
        if avatar_id in ["marcos", "carol"]:
            falante = "Marcos" if avatar_id == "marcos" else "Carol"
            context += f"\n\nINSTRUÇÃO DE IDENTIDADE: O usuário está falando especificamente com {falante}. Responda APENAS como {falante}, em 1ª pessoa. Não fale como o(a) parceiro(a) agora."

        memory = _get_session_memory(session_key)
        if memory:
            memory_block = "\n\nHISTÓRICO RECENTE DA CONVERSA (últimas interações):\n"
            for item in memory[-3:]:
                memory_block += f"- Visitante: {item['user']}\n- Você: {item['avatar']}\n"
            context += memory_block

        whatsapp_pattern = r"(?:\+?55)?\s?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"
        found_numbers = re.findall(whatsapp_pattern, text)
        if found_numbers:
            numero_visitante = found_numbers[0]
            welcome_msg = (
                "Olá! Aqui é da equipe Humanos Digitais. Recebemos seu contato pelo nosso site! "
                "Nosso gestor de negócios, Marcos, entrará em contato em breve. "
                "Enquanto isso, fique à vontade para explorar nossa plataforma."
            )
            whatsapp_result = whatsapp_service.enviar_mensagem(numero_visitante, welcome_msg)
            whatsapp_sent = bool(whatsapp_result.get("success"))
            if whatsapp_sent:
                context += f"\n\n[SISTEMA: O visitante forneceu o WhatsApp {numero_visitante}. Uma mensagem de boas-vindas JÁ FOI ENVIADA automaticamente. Informe que ele receberá o contato do Marcos.]"
            else:
                context += "\n\n[SISTEMA: O visitante forneceu um WhatsApp, mas o envio automático está indisponível. Não diga que a mensagem foi enviada.]"

        llm_answer = await call_llm(avatar_id, text, context, persona_loader)
        complexity = _classify_question_complexity(text)
        response_text = finalize_for_tts(llm_answer, complexity) if llm_answer else None

    # 3. Fallback Dinâmico Final
    if not response_text:
        persona_obj = persona_loader.get_persona(avatar_id) if 'persona_loader' in globals() and persona_loader else None
        nome_av = persona_obj.get("nome", avatar_id) if persona_obj else avatar_id
        artigo = "a" if avatar_id.lower() in FEMININE_AVATAR_IDS else "o"
        inst = persona_obj.get("institutional_block", {}) if persona_obj else {}
        identidade = inst.get("identidade", {}) if isinstance(inst, dict) else {}
        plat = identidade.get("plataforma", "Humanos Digitais")
        site = identidade.get("site", "humanosdigitais.com.br")
        response_text = (
            f"Aqui é {artigo} {nome_av}, da plataforma {plat}. Ainda não encontrei esse ponto exato "
            f"na minha base de conhecimento, mas posso te encaminhar para um especialista ou detalhar "
            f"nossas soluções em {site}."
        )
            
    sanitized = sanitize_for_tts(response_text)
    _save_to_memory(session_key, text, sanitized)
    audio_data = None
    visemes = []
    if viseme_sync:
        try:
            res = await viseme_sync.synthesize_with_visemes(sanitized, avatar_id, request.language or "pt-BR")
            if res:
                audio_data = res.get("audio")
                visemes = res.get("visemes", [])
        except Exception as e:
            logger.error(f"Erro TTS: {e}")
            
    return {
        "success": True,
        "text_response": sanitized,
        "audio_data": audio_data,
        "visemes": visemes,
        "avatar_id": avatar_id,
        "request_id": request_id,
        "whatsapp_sent": whatsapp_sent
    }
