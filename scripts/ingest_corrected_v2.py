#!/usr/bin/env python3
"""
INGESTÃO CORRIGIDA V2 - Extrai TODOS os documentos de avatares de futebol
Especialmente os 20 exemplos_de_respostas que faltavam
"""

import json
import glob
import sys
sys.path.insert(0, '/tmp/atti-media-server-onnx')

from src.chroma_engine import AvatarRAGEngine

def extrair_documentos_completos(avatar, json_file, data):
    """Extrai TODOS os documentos de um JSON de avatar de futebol"""
    docs = []
    
    # 1. Extrai a descrição principal
    if 'descricao_arquetipo' in data and data['descricao_arquetipo']:
        docs.append({
            "text": f"Descrição do torcedor: {data['descricao_arquetipo']}",
            "metadata": {"tipo": "descricao", "fonte": json_file}
        })
    
    # 2. EXTRAI TODOS OS EXEMPLOS DE RESPOSTAS (era isso que faltava!)
    if 'exemplos_de_respostas' in data and isinstance(data['exemplos_de_respostas'], list):
        for i, exemplo in enumerate(data['exemplos_de_respostas']):
            if isinstance(exemplo, dict):
                contexto = exemplo.get('contexto', '')
                resposta = exemplo.get('resposta', '')
                if resposta:
                    docs.append({
                        "text": f"Contexto: {contexto}\nResposta: {resposta}",
                        "metadata": {"tipo": "exemplo_resposta", "indice": i, "fonte": json_file}
                    })
    
    # 3. Extrai perfil demográfico
    if 'perfil_demografico' in data and isinstance(data['perfil_demografico'], dict):
        docs.append({
            "text": json.dumps(data['perfil_demografico'], indent=2),
            "metadata": {"tipo": "perfil_demografico", "fonte": json_file}
        })
    
    # 4. Extrai tom de voz
    if 'tom_de_voz' in data and isinstance(data['tom_de_voz'], dict):
        docs.append({
            "text": json.dumps(data['tom_de_voz'], indent=2),
            "metadata": {"tipo": "tom_de_voz", "fonte": json_file}
        })
    
    # 5. Extrai linguagem
    if 'linguagem' in data and isinstance(data['linguagem'], dict):
        docs.append({
            "text": json.dumps(data['linguagem'], indent=2),
            "metadata": {"tipo": "linguagem", "fonte": json_file}
        })
    
    # 6. Extrai modos emocionais
    if 'modos_emocionais' in data and isinstance(data['modos_emocionais'], dict):
        docs.append({
            "text": json.dumps(data['modos_emocionais'], indent=2),
            "metadata": {"tipo": "modos_emocionais", "fonte": json_file}
        })
    
    return docs

def ingest_all_avatars_corrected():
    engine = AvatarRAGEngine()
    avatares_futebol = ['bruno_giovana', 'marcos_carol']
    
    for avatar in avatares_futebol:
        print(f"\n📥 Processando {avatar}...")
        docs = []
        
        # Busca JSONs do avatar
        for json_file in glob.glob(f"**/{avatar}/*.json", recursive=True):
            print(f"   Lendo: {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            docs.extend(extrair_documentos_completos(avatar, json_file, data))
        
        print(f"   📄 {len(docs)} documentos extraídos (antes era 1)")
        
        if not docs:
            continue
        
        # Obtém collection
        collection_name = f"{avatar}_knowledge"
        try:
            collection = engine.client.get_collection(collection_name)
            existing = collection.get()
            if existing['ids']:
                collection.delete(ids=existing['ids'])
                print(f"   🗑️ Removidos {len(existing['ids'])} documentos antigos")
        except:
            collection = engine.client.create_collection(collection_name)
            print(f"   ✨ Collection '{collection_name}' criada")
        
        # Ingestão
        for i, doc in enumerate(docs):
            collection.add(
                documents=[doc['text']],
                metadatas=[doc['metadata']],
                ids=[f"{collection_name}_{i}"]
            )
        
        final_count = collection.count()
        print(f"   ✅ {final_count} documentos ingeridos")
        
        # Teste de query
        test = collection.query(query_texts=["título"], n_results=3)
        print(f"   ✅ Query teste: {len(test.get('documents', [[]])[0])} resultados encontrados")

if __name__ == "__main__":
    ingest_all_avatars_corrected()
