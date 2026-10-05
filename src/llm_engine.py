import os
import logging
import httpx
import time
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

LLM_MODELS_FALLBACK = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "cohere/north-mini-code:free",
]
_rate_limit_cache = {}  # {model: timestamp_do_429_or_upstream_failure}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SAFE_FALLBACK = "Desculpe, não consegui elaborar uma boa resposta agora. Pode reformular a pergunta?"

def _salvage_portuguese_tail(text: str) -> Optional[str]:
    """Preserva a resposta em português após um preâmbulo de CoT."""
    starters = ("olá", "ola", "oi", "sou ", "eu ", "posso ", "um humano", "uma pessoa")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        lower = line.lower()
        if any(char in lower for char in "ãõçáéíóúâêôà") or lower.startswith(starters):
            candidate = " ".join(lines[index:]).strip()
            if len(candidate) >= 40:
                return candidate
    return None

async def call_llm(avatar_id: str, user_text: str, context: str, persona_loader=None) -> Optional[str]:
    if not OPENROUTER_API_KEY:
        logger.error(f"❌ LLM pulado para {avatar_id}: OPENROUTER_API_KEY ausente")
        return None

    persona = persona_loader.get_persona(avatar_id) if persona_loader else None
    sys_prompt = (persona or {}).get(
        "compiled_system_prompt",
        (persona or {}).get(
            "system_prompt_template",
            "Você é um assistente da plataforma Humanos Digitais (humanosdigitais.com.br)."
        )
    )

    nome = (persona or {}).get("nome", "Sofia")
    fem = {"sofia", "clara", "amanda", "fernanda", "marina", "luisa", "lais", "paula", "giovana", "carol"}
    artigo = "a" if avatar_id.lower() in fem else "o"
    identity = (
        f"IDENTIDADE: Você É {nome}. Fale SEMPRE em 1ª pessoa (\"Eu sou {artigo}...\", \"Eu posso...\"). "
        f"NUNCA se descreva em 3ª pessoa (\"{nome} é...\"). Use o gênero correto ({artigo} {nome})."
    )

    roster = getattr(persona_loader, "platform_roster", "") if persona_loader else ""
    roster_rule = f"\nAVATARES DA PLATAFORMA: {roster}\n" if roster else ""
    system = (
        f"{sys_prompt}{roster_rule}\n"
        f"{identity}\n\n"
        "REGRAS DE RESPOSTA:\n"
        "- Responda no idioma do usuário: português brasileiro por padrão; se o usuário escrever em inglês ou espanhol, responda no mesmo idioma, mantendo tom natural e falado.\n"
        "- Se o contexto indicar a página atual (context_url/element_id), use essa informação para responder onde o visitante está.\n"
        "- Quando fizer sentido, finalize com um encaminhamento comercial curto (oferecer especialista, solução ou demonstração), sem insistir.\n"
        "- Máximo de 2 frases curtas. Nunca ultrapasse 280 caracteres.\n"
        "- Use APENAS o contexto abaixo como fonte factual. Se o contexto não responder, "
        "diga brevemente que não tem essa informação e ofereça ajuda com as soluções da plataforma.\n"
        "- Nunca repita o formato 'Q:' / 'A:' do contexto. Nunca cite fontes ou documentos.\n"
        "- Termine SEMPRE com pontuação final (. ! ou ?). Nunca termine no meio de uma frase.\n"
        "- NUNCA inclua explicações internas, raciocínio ou 'thinking process'.\n"
        "- NUNCA narre raciocínio, instruções internas ou análise da pergunta; responda DIRETAMENTE ao usuário.\n\n"
        f"CONTEXTO:\n{context}"
    )

    for model in LLM_MODELS_FALLBACK:
        cached_at = _rate_limit_cache.get(model)
        if cached_at is not None and time.time() - cached_at < 90:
            logger.info(f"⏭️ Pulando {model} (rate limit ativo)")
            continue
        if cached_at is not None:
            _rate_limit_cache.pop(model, None)
        try:
            logger.info(f"🤖 Tentando LLM: {model} para {avatar_id}")
            start = time.time()
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                "max_tokens": 150,
                "temperature": 0.4,
            }
            if "-reasoning" in model:
                payload["reasoning"] = {"enabled": False}
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://humanosdigitais-website-fix.vercel.app",
                        "X-Title": "Humanos Digitais",
                    },
                    json=payload,
                )
            if resp.status_code == 200:
                body_lower = resp.text.lower()
                data = resp.json()
                choices = data.get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                content = (message.get("content") or "").strip()
                if not content and ("resourceexhausted" in body_lower or '"code":502' in body_lower or '"code": 502' in body_lower):
                    _rate_limit_cache[model] = time.time()
                    logger.warning(f"⚠️ {model} HTTP 200 com upstream ResourceExhausted/502; cache por 90s")
                    continue
                if not content:
                    content = (message.get("reasoning") or "").strip()
                if not content:
                    logger.warning(f"⚠️ {model} HTTP 200 sem conteúdo útil: {resp.text[:300]}")
                    continue
                lower_content = content.lower()
                reasoning_markers = [
                    "here's a thinking", "thinking process", "analyze user",
                    "i need to respond", "i need to check", "looking at the context",
                    "according to the instructions", "they want to know",
                    "this is a straightforward",
                ]
                if lower_content.startswith("the user") or any(marker in lower_content for marker in reasoning_markers):
                    salvaged = _salvage_portuguese_tail(content)
                    if salvaged:
                        logger.warning(f"⚠️ {model} tinha reasoning; segmento pt-BR preservado ({len(salvaged)} chars)")
                        content = salvaged
                    else:
                        logger.warning(f"⚠️ {model} retornou reasoning em inglês; conteúdo descartado")
                        continue
                logger.info(f"⏱️ {model} latência {time.time() - start:.1f}s")
                logger.info(f"✅ LLM respondeu via {model}: {len(content)} chars")
                return content
            else:
                if resp.status_code in (429, 502):
                    _rate_limit_cache[model] = time.time()
                    logger.warning(f"⚠️ {model} HTTP {resp.status_code}; rate limit/upstream failure em cache por 90s")
                else:
                    logger.warning(f"⚠️ {model} HTTP {resp.status_code}, tentando próximo...")
                continue
        except Exception as e:
            logger.warning(f"⚠️ {model} falhou: {e}, tentando próximo...")
            continue

    logger.error(f"❌ TODOS os modelos falharam para {avatar_id}")
    return None


def finalize_for_tts(text: Optional[str]) -> str:
    if not text:
        return SAFE_FALLBACK

    text = text.strip()

    reasoning_markers = [
        "here's a thinking", "thinking process", "analyze user",
        "i need to respond", "i need to check", "looking at the context",
        "according to the instructions", "they want to know",
        "this is a straightforward",
    ]
    if text.lower().startswith("the user") or any(marker in text.lower() for marker in reasoning_markers):
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            ls = line.strip()
            if not ls:
                continue
            lower_l = ls.lower()
            if any(skip in lower_l for skip in [
                "here's", "thinking", "analyze", "constraints", "context",
                "user input", "determine", "role:", "assistant", "step ",
                "wait,", "but looking", "the company name"
            ]):
                continue
            if ls.startswith(("1.", "2.", "3.", "4.", "5.", "-", "*", "#")):
                continue
            if any(c in ls for c in 'ãõçáéíóúâêôà'):
                clean_lines.append(ls)
        if clean_lines:
            text = " ".join(clean_lines)
        else:
            return SAFE_FALLBACK

    if len(text) > 280:
        truncated = text[:280]
        last_punct = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
        if last_punct > 5:
            text = truncated[:last_punct + 1]
        else:
            last_space = truncated.rfind(' ')
            if last_space > 50:
                text = truncated[:last_space] + "."
            else:
                text = truncated + "."

    if text and text[-1] not in ['.', '!', '?']:
        text += "."

    return text
