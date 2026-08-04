import os
import logging
import httpx
import random
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# P0-10: Aberturas e fechamentos variadas
ABERTURAS_VARIADAS = [
    "Boa pergunta.",
    "Vamos lá.",
    "Posso explicar isso.",
    "Esse ponto é importante.",
    "Certo, vou direto ao ponto.",
    "Ótimo ponto.",
    "Deixa eu te ajudar com isso.",
    "Claro, posso te ajudar.",
    "Boa questão!",
    "Entendi, vamos ver isso.",
]

FECHAMENTOS_VARIADOS = [
    "Quer que eu detalhe mais algum ponto?",
    "Posso avançar para a próxima etapa?",
    "Ficou alguma dúvida sobre isso?",
    "Quer ver um exemplo prático?",
    "Prefere que eu explique de forma mais curta?",
    "Há algo mais que posso ajudar?",
    "Quer saber sobre algum outro assunto?",
]

# Injeção via session metadata (key no session_memory)
_last_opening_key = "_last_opening"
_last_closing_key = "_last_closing"

# Configurações
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modelo padrão para Ollama (leve)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "neural-chat")

# Cascata de modelos free-only (validada em 23/07/2026 via API ao vivo)
# Lidos de env OPENROUTER_MODELS (csv) com fallback para a lista default abaixo
# Nao-reasoning primeiro (melhor para resposta curta em voz), reasoning no fim
OPENROUTER_MODELS = os.getenv("OPENROUTER_MODELS", "").split(",") if os.getenv("OPENROUTER_MODELS") else [
    "inclusionai/ling-3.0-flash:free",       # ← PRIORIDADE 1: Muito rápido
    "google/gemma-4-31b-it:free",            # ← PRIORIDADE 2: Rápido e bom em PT-BR
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", # ← PRIORIDADE 3
    "nvidia/nemotron-3-ultra-550b-a55b:free" # ← ÚLTIMO RECURSO (lento)
]

async def _test_ollama() -> bool:
    """Testa se Ollama está disponível"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"[LLMOrchestrator] Ollama não disponível: {e}")
        return False

async def _generate_with_ollama(
    system_prompt: str,
    context: str,
    query: str
) -> Dict[str, str]:
    """Gera resposta usando Ollama (local)"""
    logger.info(f"[LLMOrchestrator] Usando Ollama ({OLLAMA_MODEL})")
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Contexto: {context}\n\nPergunta: {query}"}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                assistant_message = data.get("message", {}).get("content", "")
                logger.info(f"[LLMOrchestrator] Ollama respondeu: {len(assistant_message)} caracteres")
                return {
                    "response": assistant_message,
                    "source": "ollama"
                }
            else:
                logger.error(f"[LLMOrchestrator] Ollama erro: {response.status_code}")
                raise Exception(f"Ollama retornou {response.status_code}")
    except Exception as e:
        logger.error(f"[LLMOrchestrator] Erro ao chamar Ollama: {e}")
        raise

async def _generate_with_openrouter(
    system_prompt: str,
    context: str,
    query: str
) -> Dict[str, str]:
    """Gera resposta usando cascata de modelos free do OpenRouter.
    Tenta cada modelo em ordem; em 404/429/timeout/erro, cai no proximo.
    NUNCA usa modelo pago."""
    if not OPENROUTER_API_KEY:
        raise Exception("OPENROUTER_API_KEY nao configurada")
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Contexto: {context}\n\nPergunta: {query}"}
    ]
    
    last_err = None
    for model in OPENROUTER_MODELS:
        model = model.strip()
        if not model:
            continue
        try:
            logger.info(f"[LLMOrchestrator] Tentando OpenRouter com {model}")
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": "https://humanosdigitais.com",
                        "X-Title": "Humanos Digitais"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 800
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    assistant_message = data["choices"][0]["message"]["content"]
                    logger.info(f"[LLMOrchestrator] {model} respondeu: {len(assistant_message)} caracteres")
                    return {
                        "response": assistant_message,
                        "source": f"openrouter:{model}"
                    }
                elif response.status_code in (404, 429):
                    logger.warning(f"[LLMOrchestrator] {model} falhou ({response.status_code}), tentando proximo")
                    last_err = Exception(f"{model}: HTTP {response.status_code}")
                    continue
                else:
                    logger.error(f"[LLMOrchestrator] {model} erro {response.status_code}: {response.text[:200]}")
                    raise Exception(f"{model} retornou {response.status_code}")
        except httpx.TimeoutException as e:
            logger.warning(f"[LLMOrchestrator] {model} timeout: {e}, tentando proximo")
            last_err = e
            continue
        except Exception as e:
            logger.warning(f"[LLMOrchestrator] {model} falhou: {e}, tentando proximo")
            last_err = e
            continue
    
    raise Exception(f"Todos os modelos free falharam: {last_err}")

def _rag_fallback(context_docs: str) -> str:
    """Fallback interno: retorna o conteúdo mais relevante do contexto RAG de forma limpa."""
    if not context_docs or len(context_docs.strip()) < 10:
        return "Desculpe, não encontrei informações sobre esse assunto."
    
    # Remove prefixos Q: mas preserva o conteúdo de A:
    lines = context_docs.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith('Q:'):
            continue  # pula a pergunta
        if line.startswith('A:'):
            line = line[2:].strip()  # remove prefixo A:
        if len(line) > 20:  # ignora linhas muito curtas
            clean_lines.append(line)
    
    result = ' '.join(clean_lines[:5])  # primeiras 5 linhas relevantes
    return result[:350] if result else "Desculpe, não encontrei informações sobre esse assunto."



def _fix_truncation(text: str) -> Dict[str, any]:
    """
    P0-9: Pós-processamento para evitar respostas truncadas no meio de palavras.
    Retorna dict com 'fixed_text' e 'was_truncated' flag.
    """
    if not text:
        return {"fixed_text": text, "was_truncated": False}
    
    was_truncated = False
    
    # Verifica se termina sem pontuação final (possível truncamento)
    stripped = text.rstrip()
    if not stripped:
        return {"fixed_text": text, "was_truncated": False}
    
    last_char = stripped[-1]
    last_word = stripped.split()[-1] if stripped.split() else ""
    
    # Se não termina com pontuação e a última "palavra" parece incompleta
    if last_char not in '.!?…"' and len(last_word) > 0:
        # Critério 1: A última palavra termina com sufixo incompleto conhecido
        incomplete_suffixes = ['aç', 'ã', 'çã', 'men', 'çõe']
        ends_with_incomplete = any(last_word.endswith(s) for s in incomplete_suffixes)
        
        # Critério 2: A última palavra é muito curta (<=3 chars) e o texto é longo (>30 chars)
        is_short_cutoff = len(last_word) <= 3 and len(stripped) > 30
        
        # Critério 3: Se o texto é longo (>20 chars) e não termina com pontuação,
        # é quase sempre truncamento (LLM cortou no meio de uma frase)
        # Isso é o critério mais confiável para detecção de truncamento
        is_long_without_period = len(stripped) > 20
        
        was_truncated = ends_with_incomplete or is_short_cutoff or is_long_without_period
        
        if was_truncated:
            # Tentar completar ou remover a palavra truncada
            if 'recl' in last_word:
                fixed = stripped[:stripped.rfind(last_word)] + "reclamações."
                logger.info(f"[TruncFix] Correção: '{last_word}' -> 'reclamações.'")
                return {"fixed_text": fixed, "was_truncated": True}
            # Caso genérico: remover última palavra e fechar com frase segura
            fixed = stripped[:stripped.rfind(last_word)].rstrip()
            if not fixed.endswith('.'):
                fixed += "."
            logger.info(f"[TruncFix] Palavra truncada removida: '{last_word}'")
            return {"fixed_text": fixed, "was_truncated": True}
    
    return {"fixed_text": text, "was_truncated": False}


async def generate_llm_response(
    system_prompt: str,
    context: str,
    history: List[Dict],
    query: str
) -> Dict[str, str]:
    """
    Gera resposta usando LLM (Ollama ou OpenRouter)
    
    Prioridade:
    1. Ollama (local, gratuito, sem limite)
    2. OpenRouter free tier (Qwen, gratuito)
    """
    logger.info(f"[LLMOrchestrator] Gerando resposta para query: {query[:50]}...")
    
    # P0-10: Injetar instrução de abertura/fechamento variadas
    opening = random.choice(ABERTURAS_VARIADAS)
    closing = random.choice(FECHAMENTOS_VARIADOS)
    enhanced_system = system_prompt + (
        f"\n\nINSTRUÇÕES DE ESTILO:\n"
        f"Inicie a resposta com: \"{opening}\"\n"
        f"Finalize com: \"{closing}\"\n"
        f"Nunca repita a mesma abertura em respostas consecutivas."
    )
    
    # Tenta Ollama primeiro
    ollama_available = await _test_ollama()
    
    if ollama_available:
        try:
            return await _generate_with_ollama(enhanced_system, context, query)
        except Exception as e:
            logger.warning(f"[LLMOrchestrator] Ollama falhou, tentando OpenRouter: {e}")
    
    # Fallback para OpenRouter
    try:
        return await _generate_with_openrouter(enhanced_system, context, query)
    except Exception as e:
        logger.error(f"[LLMOrchestrator] Ambos LLMs falharam: {e}")
        # Fallback final: retorna contexto como resposta
        return {
            "response": _rag_fallback(context),
            "source": "fallback"
        }
