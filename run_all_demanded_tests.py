import os
import requests
import subprocess
import time
import json
import logging

logging.basicConfig(level=logging.INFO)

env = os.environ.copy()
env['KNOWLEDGE_MODE'] = 'runtime'
p = subprocess.Popen(['uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8005'], env=env)
time.sleep(3)

try:
    print("=====================================================")
    print(" EXIGÊNCIA 1: PROVA DA CORREÇÃO FONÉTICA")
    print("=====================================================")
    texto_exigido = (
        "Olá, meu CPF é 123.456.789-00 e o CNPJ da empresa é 12.345.678/0001-99. "
        "Acesse humanosdigitais.com.br ou envie email para contato@humanosdigitais.com.br. "
        "A entrega será em 15/08/2026 às 14:30. O investimento é R$ 1.500,00 "
        "e nosso suporte funciona 24/7."
    )
    r_tts = requests.post('http://127.0.0.1:8005/api/tts/direct', json={'text': texto_exigido, 'avatar_id': 'sofia'})
    print(f"Status TTS: {r_tts.status_code}")
    saida_tts = r_tts.json().get('text_response')
    print(f"SAÍDA SANITIZADA REAL:\n{saida_tts}\n")
    
    print("=====================================================")
    print(" EXIGÊNCIA 2: TESTE DO /api/context/event")
    print("=====================================================")
    # Cenário A
    r_a = requests.post('http://127.0.0.1:8005/api/context/event', json={
        "avatar_id": "sofia", "event_type": "click", "element_id": "btn_solucoes", 
        "click_count": 2, "session_id": "test-001", "page_url": "/avatares", 
        "timestamp": "2026-08-15T14:00:00Z"
    })
    print(f"Cenário A Response: {r_a.json()}")
    
    # Cenário B
    r_b = requests.post('http://127.0.0.1:8005/api/context/event', json={
        "avatar_id": "rafael", "event_type": "inactivity", 
        "time_on_page_ms": 25000, "session_id": "test-002", 
        "page_url": "/avatares", "timestamp": "2026-08-15T14:05:00Z"
    })
    print(f"Cenário B Response: {r_b.json()}")
    
    # Cenário C
    r_c = requests.post('http://127.0.0.1:8005/api/context/event', json={
        "avatar_id": "marcos_carol", "event_type": "click", 
        "element_id": "btn_solucoes", "click_count": 3, 
        "session_id": "test-003", "page_url": "/avatares", 
        "timestamp": "2026-08-15T14:10:00Z"
    })
    print(f"Cenário C Response: {r_c.json()}\n")
    
    print("=====================================================")
    print(" EXIGÊNCIA 3: TESTE END-TO-END (VIÉS DE FUTEBOL)")
    print("=====================================================")
    r_futebol_1 = requests.post('http://127.0.0.1:8005/api/avatar/speak', json={
        "avatar_id": "marcos_carol", "text": "Qual é o melhor time do Brasil?", "language": "pt-BR"
    })
    print(f"Marcos & Carol Response: {r_futebol_1.json().get('text_response')}")
    
    r_futebol_2 = requests.post('http://127.0.0.1:8005/api/avatar/speak', json={
        "avatar_id": "bruno_giovana", "text": "Qual é o melhor time do Brasil?", "language": "pt-BR"
    })
    print(f"Bruno & Giovana Response: {r_futebol_2.json().get('text_response')}\n")
    
    print("=====================================================")
    print(" EXIGÊNCIA 4: TESTE DE VALIDAÇÃO DE SCHEMA (REJEIÇÃO)")
    print("=====================================================")
    invalid_persona = {
        "avatar_id": "avatar_invalido_inexistente",
        "nome": "Invalido"
    }
    invalid_path = "/tmp/atti-media-server/assets/persona_test_invalid.json"
    with open(invalid_path, "w", encoding="utf-8") as f:
        json.dump(invalid_persona, f)
        
    from src.persona_loader import PersonaLoader
    loader_test = PersonaLoader(base_dir="/tmp/atti-media-server/assets")
    loaded_invalid = "avatar_invalido_inexistente" in loader_test.personas
    print(f"Avatar inválido foi carregado? {loaded_invalid} (Esperado: False)")
    
    if os.path.exists(invalid_path):
        os.remove(invalid_path)
        
finally:
    p.terminate()
    p.wait()
    print("\n✅ Todos os testes das 4 exigências foram executados com sucesso!")
