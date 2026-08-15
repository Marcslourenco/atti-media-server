import logging
from src.persona_loader import PersonaLoader

logging.basicConfig(level=logging.INFO)

loader = PersonaLoader(base_dir="/tmp/atti-media-server/assets")
print(f"=== TESTE DOS NOVOS ARTEFATOS DO RAR ===")
print(f"Total de personas carregadas: {len(loader.personas)}")
print(f"IDs carregados: {list(loader.personas.keys())}")

for av_id in ["sofia", "rafael", "marcos_carol"]:
    p = loader.get_persona(av_id)
    if p:
        print(f"\n--- {av_id.upper()} ---")
        print(f"Nome: {p.get('nome')}")
        print(f"Diálogos carregados: {len(p.get('dialogues', {}))}")
        print(f"Prompt (primeiras 120 chars): {p.get('compiled_system_prompt', '')[:120]}...")
