import os
import requests
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)

env = os.environ.copy()
env['KNOWLEDGE_MODE'] = 'runtime'

if os.path.exists("/tmp/ingestion_complete"):
    os.remove("/tmp/ingestion_complete")

print("==================================================================")
print(" TESTE AUTOMATIZADO: VALIDAÇÃO ANTI-ECHO BUG")
print("==================================================================")

p = subprocess.Popen(['uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8011'], env=env)
time.sleep(4)

with open("/tmp/ingestion_complete", "w") as f:
    f.write("OK")

try:
    test_cases = [
        {"pergunta": "O que é um humano digital?", "esperado_nao_contem": ["O que é um humano digital?"]},
        {"pergunta": "Como você se chama?", "esperado_nao_contem": ["Como você se chama?"]},
        {"pergunta": "O que vocês fazem?", "esperado_nao_contem": ["O que vocês fazem?"]}
    ]

    for case in test_cases:
        print(f"\nTestando pergunta: '{case['pergunta']}'")
        r = requests.post('http://127.0.0.1:8011/api/avatar/speak', json={
            "text": case["pergunta"],
            "avatar_id": "sofia",
            "language": "pt-BR"
        })
        
        assert r.status_code == 200, f"Erro HTTP {r.status_code}"
        data = r.json()
        text_response = data.get("text_response", "")
        print(f"  -> Resposta obtida: {text_response}")
        
        for frase in case["esperado_nao_contem"]:
            if frase.lower() in text_response.lower():
                raise Exception(f"❌ ECHO BUG DETECTED: A resposta contém a pergunta literal '{frase}'!")
        
        print("  -> ✅ Passou: Sem eco!")

    print("\n✅ Todos os testes anti-echo passaram com 100% de sucesso!")

finally:
    p.terminate()
    p.wait()
    if os.path.exists("/tmp/ingestion_complete"):
        os.remove("/tmp/ingestion_complete")
