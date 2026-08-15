import re

# Ler main.py e adicionar /api/context/event
with open("/tmp/atti-media-server/main.py", "r", encoding="utf-8") as f:
    content = f.read()

endpoint_code = """
class ContextEventRequest(BaseModel):
    avatar_id: str = Field(..., description="ID do avatar")
    event_type: str = Field(..., description="Tipo de evento (ex: click, hover, inactivity, scroll)")
    element_id: Optional[str] = Field(None, description="ID do elemento na UI")
    duration_ms: Optional[int] = Field(0, description="Duração do evento em ms")
    scroll_percent: Optional[float] = Field(0.0, description="Percentual de rolagem")

@app.post("/api/context/event")
async def context_event(request: ContextEventRequest):
    \"\"\"Recebe eventos de frontend (cliques, hover, inatividade) e retorna frase proativa mapeada.\"\"\"
    avatar_id = request.avatar_id
    event_type = request.event_type
    element_id = request.element_id
    
    # Carregar diálogos da persona via PersonaLoader se disponível
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
                if event_type in gatilho or (element_id and element_id in gatilho):
                    frase_sugerida = t.get("frase")
                    break
            if not frase_sugerida:
                aberturas = dialogues.get("aberturas_variadas", [])
                if aberturas:
                    import random
                    frase_sugerida = random.choice(aberturas)
    except Exception as e:
        logger.warning(f"Erro ao buscar frase proativa: {e}")
        
    if not frase_sugerida:
        frase_sugerida = f"Olá! Percebi que você está explorando a página. Quer que eu te ajude com algo específico?"
        
    return {
        "success": True,
        "avatar_id": avatar_id,
        "event_type": event_type,
        "proactive_phrase": frase_sugerida
    }
"""

if "/api/context/event" not in content:
    # Inserir antes de tts_direct
    content = content.replace("class TTSDirectRequest(BaseModel):", endpoint_code + "\nclass TTSDirectRequest(BaseModel):")
    with open("/tmp/atti-media-server/main.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Endpoint /api/context/event adicionado com sucesso em main.py")
else:
    print("Endpoint /api/context/event já existe em main.py")
