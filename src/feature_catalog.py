"""
FEATURE_CATALOG — Catálogo institucional de funcionalidades.

Este módulo define quais funcionalidades estão disponíveis, em beta,
planejadas, indisponíveis ou em investigação.

Os avatares NÃO podem declarar funcionalidade inexistente como disponível.
"""

from typing import Dict, List

# Status permitidos para funcionalidades
ALLOWED_STATUSES = ["AVAILABLE", "BETA", "PLANNED", "UNAVAILABLE", "INVESTIGATING"]

# Catálogo de funcionalidades
FEATURE_CATALOG: Dict[str, str] = {
    # --- Núcleo operacional (funcionando) ---
    "avatar_conversacional": "AVAILABLE",
    "tts_visemes": "AVAILABLE",
    "rag_por_avatar": "AVAILABLE",
    "faq_verbal": "AVAILABLE",
    "multi_idioma": "AVAILABLE",

    # --- Em investigação técnica ---
    "personalizacao_avatar_teste": "PLANNED",
    "scraper_site_cliente": "INVESTIGATING",
    "pdf_parsing": "INVESTIGATING",
    "rag_temporario_sessao": "INVESTIGATING",
    "whatsapp_onboarding": "PLANNED",
    "crm_integracao": "PLANNED",
    "analytics_dashboard": "PLANNED",

    # --- Plataforma ---
    "plataforma_humanos_digitais": "AVAILABLE",
    "site_humanosdigitais": "AVAILABLE",
    "onboarding_gratuito": "AVAILABLE",
    "demonstracao_avatares": "AVAILABLE",
}


def is_feature_available(feature: str) -> bool:
    """Verifica se uma funcionalidade está AVAILABLE ou BETA."""
    status = FEATURE_CATALOG.get(feature, "UNAVAILABLE")
    return status in ("AVAILABLE", "BETA")


def get_feature_status(feature: str) -> str:
    """Retorna o status de uma funcionalidade."""
    return FEATURE_CATALOG.get(feature, "UNAVAILABLE")


def list_available_features() -> List[str]:
    """Retorna lista de funcionalidades AVAILABLE ou BETA."""
    return [
        k for k, v in FEATURE_CATALOG.items()
        if v in ("AVAILABLE", "BETA")
    ]


# Bloco institucional obrigatório para TODOS os avatares
INSTITUTIONAL_BLOCK = """
BLOCO INSTITUCIONAL OBRIGATÓRIO:
Você é um humano digital da plataforma Humanos Digitais (humanosdigitais.com.br).
Você nunca deve inventar nome de empresa, preço, prazo, produto, integração, veículo, procedimento médico, serviço municipal ou funcionalidade.
Se uma funcionalidade não estiver marcada como AVAILABLE no catálogo interno, você deve dizer que ela está em análise, beta, planejada ou indisponível, conforme o caso.
Você deve priorizar o conhecimento RAG autorizado sobre conhecimento genérico.
Se não houver conhecimento confiável, diga que não tem essa informação e ofereça encaminhamento para especialista humano.

CATÁLOGO DE FUNCIONALIDADES:
""" + "\n".join(
    f"- {k}: {v}" for k, v in FEATURE_CATALOG.items()
) + """

REGRAS DE RESPOSTA SOBRE FUNCIONALIDADES:
- Se AVAILABLE: pode descrever livremente.
- Se BETA: dizer que está em teste, pode haver limitações.
- Se PLANNED: dizer que está no roadmap, ainda não disponível.
- Se UNAVAILABLE: dizer que não está disponível no momento.
- Se INVESTIGATING: dizer que está em análise técnica, sem previsão.
"""
