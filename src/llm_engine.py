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
    reasoning_prefixes = (
        "the user", "thinking process", "here's a thinking", "according to", "analyze user",
        "o usuário está perguntando", "o usuário está", "o usuário quer", "o usuário mencionou",
        "hmm, o usuário", "preciso responder", "preciso verificar", "preciso checar",
        "olhando o contexto", "vou confirmar", "vamos analisar", "deixa eu verificar",
        "a pergunta é sobre", "a pergunta do usuário", "o visitante está", "o visitante quer",
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        lower = line.lower()
        if lower.startswith(reasoning_prefixes):
            continue
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
        f"NUNCA se descreva em 3ª pessoa (\"{nome} é...\"). Use o gênero correto ({artigo} {nome}). "
        f"Seu gênero é {artigo} {nome}. Sempre use o artigo correto ao se referir a si mesmo."
    )

    roster = getattr(persona_loader, "platform_roster", "") if persona_loader else ""
    roster_rule = f"\nAVATARES DA PLATAFORMA: {roster}\n" if roster else ""
    sofia_business_rules = ""
    if avatar_id.lower() == "sofia":
        sofia_business_rules = (
            "\nREGRAS COMERCIAIS DA SOFIA:\n"
            "- A integração de envio automático de catálogo ou PDF por WhatsApp ainda está em implementação.\n"
            "- NUNCA prometa enviar catálogo, PDF ou arquivo automaticamente.\n"
            "- Se o usuário pedir envio por WhatsApp, diga: \"A integração de envio automático ainda está em implementação. Posso te encaminhar para um contato humano ou você pode usar o QR Code na tela.\"\n"
            "- Não invente preços, descontos, prazos ou condições específicas.\n"
            "- Se perguntarem sobre preços, informe: Starter R$497, Profissional R$997, Business R$1.997 e Enterprise sob consulta, e ofereça falar com um especialista.\n"
        )
    system = (
        f"{sys_prompt}{roster_rule}{sofia_business_rules}\n"
        f"{identity}\n\n"
        "REGRAS DE RESPOSTA:\n"
        "REGRA DE IDIOMA (OBRIGATÓRIA): detecte o idioma da mensagem do usuário. Se escrever em inglês, responda SOMENTE em inglês; se escrever em espanhol, responda SOMENTE em espanhol; se escrever em português, responda SOMENTE em português brasileiro. Nunca misture idiomas na mesma resposta.\n"
        "- Se o contexto indicar a página atual (context_url/element_id), use essa informação para responder onde o visitante está.\n"
        "REGRA DE FLUIDEZ: Você já se apresentou no início da conversa. Nas respostas seguintes, NUNCA repita seu nome, cargo ou segmento, a menos que o usuário pergunte explicitamente 'quem é você'. Responda diretamente à pergunta de forma natural, sem se reapresentar.\n"
        "- REGRA DE IMPARCIALIDADE (LUCAS): NUNCA cite marcas específicas de veículos (ex: Toyota, Honda, Fiat, Chevrolet). Fale apenas sobre categorias (SUV, Sedan, Hatch) e características genéricas. Se perguntarem de uma marca, diga: 'Posso te ajudar a comparar as categorias e características, mas não cito marcas específicas aqui. Quer ver as opções de SUV?'\n" if avatar_id.lower() == "lucas" else ""
        "- REGRA DE ENGAJAMENTO: sempre que apropriado, finalize com uma pergunta curta de continuação, como \"Quer saber mais sobre isso?\" ou \"Posso te mostrar como funciona?\". Quando fizer sentido comercial, sugira um próximo passo sutil, sem insistir. Mantenha tom caloroso e humano.\n"
        "- Máximo de 2 frases curtas. Nunca ultrapasse 280 caracteres.\n"
        "- Use APENAS o contexto abaixo como fonte factual. Se o contexto não responder, "
        "diga brevemente que não tem essa informação e ofereça ajuda com as soluções da plataforma.\n"
        "- Nunca repita o formato 'Q:' / 'A:' do contexto. Nunca cite fontes ou documentos.\n"
        "- Termine SEMPRE com pontuação final (. ! ou ?). Termine sempre com frase completa. Nunca corte no meio de uma palavra ou frase.\n"
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
                "max_tokens": 280,
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
                    "the user is", "the user wants", "i need to respond",
                    "i need to check", "looking at the context", "according to",
                    "they want to know", "this is a straightforward",
                    "o usuário está perguntando", "o usuário está", "o usuário quer",
                    "o usuário mencionou", "hmm, o usuário", "preciso responder",
                    "preciso verificar", "preciso checar", "olhando o contexto",
                    "vou confirmar", "vamos analisar", "deixa eu verificar",
                    "a pergunta é sobre", "a pergunta do usuário", "o visitante está",
                    "o visitante quer",
                ]
                if lower_content.startswith(("the user", "thinking process", "according to")) or any(marker in lower_content for marker in reasoning_markers):
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


def _is_majoritariamente_portugues(text: str) -> bool:
    words = [w.lower() for w in __import__("re").findall(r"[A-Za-zÀ-ÿ]+", text)]
    if not words:
        return False
    pt_words = {
        "a", "à", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
        "e", "em", "é", "eu", "foi", "isso", "na", "nas", "não", "no", "nos", "o",
        "os", "para", "por", "que", "se", "ser", "sua", "suas", "também", "um", "uma",
        "você", "vocês", "sobre", "posso", "podemos", "está", "são", "mais", "ou"
    }
    recognized = sum(1 for word in words if word in pt_words or any(ch in word for ch in "áàâãéêíóôõúç"))
    return recognized / len(words) >= 0.5


def finalize_for_tts(text: Optional[str]) -> str:
    if not text:
        return SAFE_FALLBACK

    text = text.strip()
    brutal_reasoning_markers = (
        "the user is", "i need to", "thinking process", "according to the", "looking at the context"
    )
    lower_text = text.lower()
    if any(marker in lower_text for marker in brutal_reasoning_markers) and not _is_majoritariamente_portugues(text):
        logger.warning("⚠️ reasoning leak em inglês detectado; resposta inteira descartada")
        return SAFE_FALLBACK

    reasoning_markers = [
        "here's a thinking", "thinking process", "analyze user",
        "the user is", "the user wants", "i need to respond",
        "i need to check", "looking at the context", "according to",
        "they want to know", "this is a straightforward",
        "o usuário está perguntando", "o usuário está", "o usuário quer",
        "o usuário mencionou", "hmm, o usuário", "preciso responder",
        "preciso verificar", "preciso checar", "olhando o contexto",
        "vou confirmar", "vamos analisar", "deixa eu verificar",
        "a pergunta é sobre", "a pergunta do usuário", "o visitante está",
        "o visitante quer",
    ]
    if text.lower().startswith(("the user", "thinking process", "according to")) or any(marker in text.lower() for marker in reasoning_markers):
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
                "wait,", "but looking", "the company name", "the user is", "the user wants",
                "according to", "o usuário está perguntando", "o usuário está", "o usuário quer",
                "o usuário mencionou", "hmm, o usuário", "preciso responder", "preciso verificar",
                "preciso checar", "olhando o contexto", "vou confirmar", "vamos analisar",
                "deixa eu verificar", "a pergunta é sobre", "a pergunta do usuário",
                "o visitante está", "o visitante quer"
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
        truncated = text[:280].rstrip()
        recent = truncated[-100:]
        recent_punct = max(recent.rfind('.'), recent.rfind('!'), recent.rfind('?'))
        if recent_punct >= 0:
            absolute_punct = len(truncated) - len(recent) + recent_punct
            text = truncated[:absolute_punct + 1]
        else:
            last_space = truncated.rfind(' ')
            text = (truncated[:last_space] if last_space > 0 else truncated).rstrip() + "."

    if text and text[-1] not in ['.', '!', '?']:
        text += "."

    return text
