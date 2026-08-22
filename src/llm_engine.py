import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

LLM_MODELS_FALLBACK = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SAFE_FALLBACK = "Desculpe, não consegui elaborar uma boa resposta agora. Pode reformular a pergunta?"

async def call_llm(avatar_id: str, user_text: str, context: str, persona_loader=None) -> Optional[str]:
    if not OPENROUTER_API_KEY:
        logger.error(f"❌ LLM pulado para {avatar_id}: OPENROUTER_API_KEY ausente")
        return None

    persona = persona_loader.get_persona(avatar_id) if persona_loader else None
    sys_prompt = (persona or {}).get(
        "system_prompt_template",
        "Você é um assistente da plataforma Humanos Digitais (humanosdigitais.com.br)."
    )

    system = (
        f"{sys_prompt}\n\n"
        "REGRAS DE RESPOSTA:\n"
        "- Responda em português brasileiro, tom natural e falado (a resposta será convertida em voz).\n"
        "- Máximo de 2 frases curtas. Nunca ultrapasse 280 caracteres.\n"
        "- Use APENAS o contexto abaixo como fonte factual. Se o contexto não responder, "
        "diga brevemente que não tem essa informação e ofereça ajuda com as soluções da plataforma.\n"
        "- Nunca repita o formato 'Q:' / 'A:' do contexto. Nunca cite fontes ou documentos.\n"
        "- Termine SEMPRE com pontuação final (. ! ou ?). Nunca termine no meio de uma frase.\n"
        "- NUNCA inclua explicações internas, raciocínio ou 'thinking process'.\n\n"
        f"CONTEXTO:\n{context}"
    )

    for model in LLM_MODELS_FALLBACK:
        try:
            logger.info(f"🤖 Tentando LLM: {model} para {avatar_id}")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://humanosdigitais-website-fix.vercel.app",
                        "X-Title": "Humanos Digitais",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_text},
                        ],
                        "max_tokens": 150,
                        "temperature": 0.4,
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    answer = data["choices"][0]["message"]["content"].strip()
                    logger.info(f"✅ LLM respondeu via {model}: {len(answer)} chars")
                    return answer
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

    if any(marker in text.lower() for marker in ["here's a thinking", "thinking process", "analyze user"]):
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

    if len(text) > 300:
        truncated = text[:300]
        last_punct = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
        if last_punct > 5:
            text = truncated[:last_punct + 1]
        else:
            text = truncated

    if text and text[-1] not in ['.', '!', '?']:
        text += "."

    return text
