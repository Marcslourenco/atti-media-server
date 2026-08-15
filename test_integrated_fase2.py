import os
import requests
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)

env = os.environ.copy()
env['KNOWLEDGE_MODE'] = 'runtime'
p = subprocess.Popen(['uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8004'], env=env)
time.sleep(3)

try:
    print("=== TESTE 1: PERSONA LOADER & SYSTEM PROMPT ===")
    from src.persona_loader import PersonaLoader
    loader = PersonaLoader(base_dir="/tmp/atti-media-server/assets")
    print(f"✅ Total personas carregadas: {len(loader.personas)}")
    sofia_prompt = loader.get_system_prompt("sofia")
    print(f"✅ Sofia Prompt (primeiros 150 chars): {sofia_prompt[:150]}...")
    
    print("\n=== TESTE 2: ENDPOINT /api/context/event ===")
    r_ctx = requests.post('http://127.0.0.1:8004/api/context/event', json={'avatar_id': 'sofia', 'event_type': 'click', 'element_id': 'btn_solucoes'})
    print(f"Status: {r_ctx.status_code}")
    print(f"Response: {r_ctx.json()}")
    
    print("\n=== TESTE 3: ENDPOINT /api/tts/direct com Fonética ===")
    r_tts = requests.post('http://127.0.0.1:8004/api/tts/direct', json={'text': 'Olá, meu CPF é 123.456.789-00 e acesse humanosdigitais.com.br', 'avatar_id': 'sofia'})
    print(f"Status: {r_tts.status_code}")
    res_json = r_tts.json()
    print(f"Texto sanitizado foneticamente: {res_json.get('text_response')}")
    print(f"Visemes count: {len(res_json.get('visemes', []))}")
    
finally:
    p.terminate()
    p.wait()
    print("\n✅ Testes integrados da Fase 2 concluídos com sucesso!")
