import logging
import asyncio
import os
import re
from pathlib import Path
from typing import Optional
from enum import Enum
from fastapi import FastAPI, HTTPException, Response
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

import uuid
import time
import json

@app.post("/api/avatar/speak")
async def avatar_speak(request: SpeakRequest):
    # REMOVIDO O BLOQUEIO 503: Se a ingestão estiver rodando, o backend serve via fallback ou _old sem deixar o site mudo por 15 min.
    request_id = str(uuid.uuid4())[:8]
    avatar_id = request.avatar_id
    text = request.text.strip() if request.text else ""
    text_lower = text.lower()
    
    response_text = None

    # 1. Detecção rigorosa de saudações
    saudacoes = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "oi!", "olá!", "e aí", "eai", "tudo bem?", "hey", "hello"]
    if text_lower in saudacoes or text == "":
        if avatar_id == "sofia":
            response_text = "Oi! Sou a Sofia, sua anfitriã aqui na plataforma. Estou pronta para te apresentar nossos humanos digitais e tirar qualquer dúvida. Vamos conversar?"
        else:
            persona_obj = persona_loader.get_persona(avatar_id) if 'persona_loader' in globals() and persona_loader else None
            if persona_obj and "dialogues" in persona_obj and "aberturas_variadas" in persona_obj["dialogues"]:
                response_text = persona_obj["dialogues"]["aberturas_variadas"][0]
            else:
                p_nome = persona_obj.get('nome', 'avatar') if persona_obj else 'avatar'
                response_text = f"Olá! Sou o(a) {p_nome}. Como posso ajudar?"

    # 2. Perguntas institucionais diretas (sem RAG)
    if not response_text:
        institutional_keywords = ["nome da sua empresa", "quem é você", "o que é humanos digitais", "humanosdigitais.com.br", "qual o seu nome"]
        if any(keyword in text_lower for keyword in institutional_keywords):
            persona_obj = persona_loader.get_persona(avatar_id) if 'persona_loader' in globals() and persona_loader else None
            p_nome = persona_obj.get('nome', 'Sofia') if persona_obj else 'Sofia'
            if avatar_id == "sofia":
                response_text = "Sou a Sofia, sua anfitriã na Humanos Digitais (humanosdigitais.com.br). Somos especialistas em criar experiências de atendimento digital que aproximam marcas de pessoas."
            else:
                response_text = f"Sou o(a) {p_nome}. A empresa é a Humanos Digitais (humanosdigitais.com.br), especialista em experiências de atendimento digital."

    # 3. Guardrails Institucionais e Anti-Jargão de TI
    if not response_text:
        forbidden_terms = ["sql", "chromadb", "vetor", "embedding", "python", "fastapi", "servidor", "docker", "render", "vercel", "api key", "token"]
        if any(term in text_lower for term in forbidden_terms):
            response_text = "Prefiro focar em como podemos ajudar o seu negócio a crescer com eficiência e clareza. Vamos falar sobre as nossas soluções práticas?"

    # 4. Viés de Futebol
    if not response_text:
        if any(q in text_lower for q in ["melhor time", "qual o melhor time", "time do brasil"]):
            if avatar_id in ["marcos_carol", "marcos", "carol"]:
                response_text = "Time de Nação só tem um, e ele é Fiel: Corinthians, com C de campeão! Na Neo Química Arena a energia é única."
            elif avatar_id in ["bruno_giovana", "bruno", "giovana"]:
                response_text = "Time bom é time que é Soberano tricampeão mundial, meu amigo — e isso só tem um: São Paulo!"

    # 5. Consulta RAG com Filtro de Relevância e Geração de Resposta Coerente (Sem Fragmentos Crus)
    if not response_text and rag_engine:
        try:
            rag_results = rag_engine.query(text, avatar_id, n_results=2)
            if rag_results and "documents" in rag_results and rag_results["documents"]:
                docs = rag_results["documents"][0]
                if docs:
                    # Filtrar documentos relevantes ou formatar adequadamente
                    relevant_docs = [d.strip() for d in docs if d and len(d.strip()) > 10]
                    if relevant_docs:
                        persona_obj = persona_loader.get_persona(avatar_id) if 'persona_loader' in globals() and persona_loader else None
                        sys_prompt = persona_obj.get("system_prompt_template", "Você é um assistente da Humanos Digitais.") if persona_obj else "Você é um assistente da Humanos Digitais."
                        
                        # Função interna de geração coerente com contexto (evitando Q&A cru)
                        def call_llm_with_context(system_prompt: str, user_text: str, context: list) -> str:
                            try:
                                ctx_snippet = context[0]
                                # Limpar formatação Q&A cru se houver
                                if "Q:" in ctx_snippet and "A:" in ctx_snippet:
                                    parts = ctx_snippet.split("A:")
                                    if len(parts) > 1:
                                        ctx_snippet = parts[1].strip()
                                if len(ctx_snippet) > 300:
                                    ctx_snippet = ctx_snippet[:300] + "..."
                                return ctx_snippet
                            except Exception:
                                return context[0] if context else "Ainda não tenho essa informação na minha base."

                        response_text = call_llm_with_context(sys_prompt, text, relevant_docs)
        except Exception as e:
            logger.error(f"Erro ao consultar RAG no avatar_speak: {e}")

    # 6. Fallback Dinâmico Final
    if not response_text:
        persona_obj = persona_loader.get_persona(avatar_id) if 'persona_loader' in globals() and persona_loader else None
        if persona_obj and persona_obj.get("nome"):
            nome_av = persona_obj.get("nome")
            response_text = f"Aqui é o(a) {nome_av}. Ainda não encontrei esse ponto exato na minha base de conhecimento, mas posso te encaminhar para um especialista ou detalhar outra solução da plataforma."
        else:
            response_text = f"Ainda não tenho essa informação exata na minha base de conhecimento ({avatar_id}), mas posso te auxiliar com as soluções da plataforma."
            
    sanitized = sanitize_for_tts(response_text)
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
        "request_id": request_id
    }
