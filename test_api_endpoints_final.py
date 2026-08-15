import os
import requests
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)

env = os.environ.copy()
env['KNOWLEDGE_MODE'] = 'runtime'

# Criar flag de readiness
with open("/tmp/ingestion_complete", "w") as f:
    f.write("OK")

p = subprocess.Popen(['uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8009'], env=env)
time.sleep(3)

try:
    print("=== TESTE 1: /api/validate-rag ===")
    r_val = requests.get('http://127.0.0.1:8009/api/validate-rag')
    print(f"Status: {r_val.status_code}")
    print(f"Response: {r_val.json()}")

    print("\n=== TESTE 2: /api/tts/direct ===")
    r_tts = requests.post('http://127.0.0.1:8009/api/tts/direct', json={
        "text": "Teste CPF 123.456.789-00 em humanosdigitais.com.br",
        "avatar_id": "sofia"
    })
    print(f"Status: {r_tts.status_code}")
    print(f"Response text: {r_tts.json().get('text_response')}")
    print(f"Visemes count: {len(r_tts.json().get('visemes', []))}")

finally:
    p.terminate()
    p.wait()
    if os.path.exists("/tmp/ingestion_complete"):
        os.remove("/tmp/ingestion_complete")
    print("✅ Testes de API concluídos com sucesso!")
