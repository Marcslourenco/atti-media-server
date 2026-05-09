#!/usr/bin/env python3
"""
AÇÃO 1 - Teste de query local
Verifica se a query funciona com os dados indexados
"""
import sys
import os
sys.path.append(os.getcwd())

from src.chroma_engine import AvatarRAGEngine

print("=" * 70)
print("🔍 TESTE DE QUERY LOCAL")
print("=" * 70)

engine = AvatarRAGEngine()

test_queries = [
    ("lais", "Como funciona o internato médico?"),
    ("paula", "Quais tratamentos odontológicos estão disponíveis?"),
    ("bruno_giovana", "Qual foi o último título do São Paulo?")
]

for avatar, pergunta in test_queries:
    print(f"\n🔍 {avatar} perguntado: {pergunta}")
    try:
        resultado = engine.generate_response(pergunta, avatar)
        print(f"   Resposta: {resultado[:200] if resultado else 'VAZIO'}")
        if "Conhecimento não disponível" in resultado:
            print("   ❌ FALLBACK - Dados não encontrados!")
        else:
            print("   ✅ RESPOSTA COM DADOS")
    except Exception as e:
        print(f"   ❌ ERRO: {e}")
    print("-" * 70)
