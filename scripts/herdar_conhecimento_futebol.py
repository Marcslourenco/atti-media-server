#!/usr/bin/env python3
"""Herança de conhecimento entre avatares de futebol"""
import sys
sys.path.append('.')
from src.chroma_engine import AvatarRAGEngine

print("=== HERANÇA DE CONHECIMENTO FUTEBOL ===\n")
engine = AvatarRAGEngine()

# Mapeamento de herança: avatar_filho -> avatar_fonte
heranca = {
    'giovana': 'bruno_giovana',      # Giovana herda conhecimento do Bruno (SPFC)
    'carol': 'marcos_carol',         # Carol herda conhecimento do Marcos (Corinthians)
}

for filho, fonte in heranca.items():
    print(f"📥 Copiando conhecimento de '{fonte}' para '{filho}'...")
    try:
        # Pega coleção fonte
        fonte_collection = engine.client.get_collection(f"{fonte}_knowledge")
        fonte_docs = fonte_collection.get()
        
        if not fonte_docs['ids']:
            print(f"   ⚠️ Fonte '{fonte}' não tem documentos")
            continue
        
        print(f"   📄 {len(fonte_docs['ids'])} documentos encontrados em '{fonte}'")
        
        # Cria ou limpa coleção filho
        try:
            filho_collection = engine.client.get_collection(f"{filho}_knowledge")
            existing = filho_collection.get()
            if existing['ids']:
                filho_collection.delete(ids=existing['ids'])
                print(f"   🗑️ Limpos {len(existing['ids'])} documentos antigos")
        except:
            filho_collection = engine.client.create_collection(f"{filho}_knowledge")
            print(f"   ✨ Collection '{filho}_knowledge' criada")
        
        # Copia documentos
        filho_collection.add(
            documents=fonte_docs['documents'],
            metadatas=fonte_docs['metadatas'],
            ids=[f"{filho}_{doc_id}" for doc_id in fonte_docs['ids']]
        )
        
        print(f"   ✅ {len(fonte_docs['ids'])} documentos copiados para '{filho}'")
        
        # Testa query
        test = filho_collection.query(query_texts=["São Paulo"], n_results=1)
        if test.get('documents') and test['documents'][0]:
            print(f"   ✅ Query teste OK")
        else:
            print(f"   ⚠️ Query teste retornou vazio")
        
    except Exception as e:
        print(f"   ❌ ERRO: {e}")
    
    print()

print("✅ Herança de conhecimento concluída")
