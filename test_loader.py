import logging
from src.persona_loader import PersonaLoader

logging.basicConfig(level=logging.INFO)

loader = PersonaLoader(base_dir="/tmp/atti-media-server/assets")
print(f"=== TESTE PERSONA LOADER ===")
print(f"Avatares carregados: {list(loader.personas.keys())}")

sofia = loader.get_persona("sofia")
if sofia:
    print("\n--- System Prompt Compilado (Sofia) ---")
    print(sofia["compiled_system_prompt"][:400] + "...\n")

marcos = loader.get_persona("marcos_carol")
if marcos:
    print("\n--- System Prompt Compilado (Marcos & Carol) ---")
    print(marcos["compiled_system_prompt"][:400] + "...\n")
    print("Brand Bias:", marcos.get("brand_loyalty_bias"))
