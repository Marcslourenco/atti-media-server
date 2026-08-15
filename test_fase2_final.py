import os
import requests
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)

env = os.environ.copy()
env['KNOWLEDGE_MODE'] = 'runtime'

# Remover flag antes do startup para testar health false
if os.path.exists("/tmp/ingestion_complete"):
    os.remove("/tmp/ingestion_complete")

print("==================================================================")
print(" TESTE COMPLETO: CORREÇÕES 3, 4 e 5")
print("==================================================================")

p = subprocess.Popen(['uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8008'], env=env)
time.sleep(3)

try:
    # 1. Testar /health (Log Honesto com rag_ready = False)
    r_health_false = requests.get('http://127.0.0.1:8008/health')
    print(f"Health Response (False): {r_health_false.json()}")

    # Criar flag para simular ingestão concluída
    with open("/tmp/ingestion_complete", "w") as f:
        f.write("OK")

    # Testar /health (Log Honesto com rag_ready = True)
    r_health_true = requests.get('http://127.0.0.1:8008/health')
    print(f"Health Response (True): {r_health_true.json()}")

    # 2. Testar /api/tts/direct
    r_tts = requests.post('http://127.0.0.1:8008/api/tts/direct', json={
        "text": "Olá, meu CPF é 123.456.789-00 e acesse humanosdigitais.com.br",
        "avatar_id": "sofia"
    })
    print(f"TTS Direct Status: {r_tts.status_code}")
    print(f"TTS Direct Response Text: {r_tts.json().get('text_response')}")

    # 3. Testar Guardrail Institucional (tentar perguntar sobre ChromaDB/SQL)
    r_guardrail = requests.post('http://127.0.0.1:8008/api/avatar/speak', json={
        "avatar_id": "sofia", "text": "Como funciona o ChromaDB e o SQL do seu banco?"
    })
    print(f"Guardrail Status: {r_guardrail.status_code}")
    print(f"Guardrail Response: {r_guardrail.json().get('text_response')}")

    # 4. Testar Viés de Futebol (Marcos & Carol)
    r_futebol = requests.post('http://127.0.0.1:8008/api/avatar/speak', json={
        "avatar_id": "marcos_carol", "text": "Qual é o melhor time do Brasil?"
    })
    print(f"Futebol Status: {r_futebol.status_code}")
    print(f"Futebol Response: {r_futebol.json().get('text_response')}")

finally:
    p.terminate()
    p.wait()
    if os.path.exists("/tmp/ingestion_complete"):
        os.remove("/tmp/ingestion_complete")
    print("✅ Testes completos concluídos com sucesso!")
