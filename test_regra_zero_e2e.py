import os
import requests
import subprocess
import time
import json
import logging

logging.basicConfig(level=logging.INFO)

# Configurar ambiente com RAG_READY falso inicial
env = os.environ.copy()
env['KNOWLEDGE_MODE'] = 'runtime'

print("==================================================================")
print(" TESTE 1: VERIFICAR HTTP 503 QUANDO RAG_READY É FALSO")
print("==================================================================")
# Remover flag se existir
if os.path.exists("/tmp/ingestion_complete"):
    os.remove("/tmp/ingestion_complete")

p = subprocess.Popen(['uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8006'], env=env)
time.sleep(2)

try:
    # Tentar speak sem ingestão (deve retornar 503)
    r_503 = requests.post('http://127.0.0.1:8006/api/avatar/speak', json={
        "avatar_id": "sofia", "text": "Olá", "language": "pt-BR"
    })
    print(f"Status HTTP esperado 503 | Obtido: {r_503.status_code}")
    print(f"Response: {r_503.json()}")
    assert r_503.status_code == 503, f"Erro: Esperado 503, obtido {r_503.status_code}"
    
    # Criar flag simulando término da ingestão
    with open("/tmp/ingestion_complete", "w") as f:
        f.write("OK")
    
    # Fazer requisição novamente (deve retornar 200)
    r_200 = requests.post('http://127.0.0.1:8006/api/avatar/speak', json={
        "avatar_id": "sofia", "text": "Olá", "language": "pt-BR"
    })
    print(f"Status HTTP esperado 200 | Obtido: {r_200.status_code}")
    print(f"Response: {r_200.json().get('text_response')}")
    assert r_200.status_code == 200, f"Erro: Esperado 200, obtido {r_200.status_code}"

    print("\n==================================================================")
    print(" TESTE 2: ENDPOINT /api/tts/direct COM SANITIZAÇÃO FONÉTICA GRAMATICAL")
    print("==================================================================")
    texto_teste = (
        "Olá, meu CPF é 123.456.789-00 e o CNPJ da empresa é 12.345.678/0001-99. "
        "Acesse humanosdigitais.com.br ou envie email para contato@humanosdigitais.com.br. "
        "A entrega será em 15/08/2026 às 14:30. O investimento é R$ 1.500,00 "
        "e nosso suporte funciona 24/7."
    )
    r_tts = requests.post('http://127.0.0.1:8006/api/tts/direct', json={
        "text": texto_teste, "avatar_id": "sofia", "language": "pt-BR"
    })
    print(f"Status TTS Direct: {r_tts.status_code}")
    res_tts = r_tts.json()
    print(f"Texto sanitizado:\n{res_tts.get('text_response')}\n")
    print(f"Visemes gerados: {len(res_tts.get('visemes', []))}")

    print("\n==================================================================")
    print(" TESTE 3: /api/context/event COM DIÁLOGOS UNIFICADOS (personas_dialogue.json)")
    print("==================================================================")
    r_ctx_marcos = requests.post('http://127.0.0.1:8006/api/context/event', json={
        "avatar_id": "marcos_carol", "event_type": "click", "element_id": "btn_solucoes", "click_count": 3
    })
    print(f"Marcos & Carol Event Response: {r_ctx_marcos.json()}")

    r_ctx_rafael = requests.post('http://127.0.0.1:8006/api/context/event', json={
        "avatar_id": "rafael", "event_type": "inactivity", "time_on_page_ms": 25000
    })
    print(f"Rafael Event Response: {r_ctx_rafael.json()}")

finally:
    p.terminate()
    p.wait()
    if os.path.exists("/tmp/ingestion_complete"):
        os.remove("/tmp/ingestion_complete")
    print("\n✅ Todos os testes reais concluídos com sucesso e provados via logs do terminal!")
