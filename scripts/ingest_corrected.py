#!/usr/bin/env python3
"""Ingestão seletiva CORRIGIDA - usa IF em vez de ELIF"""
import sys
import json
import glob
from pathlib import Path
sys.path.append('.')
from src.chroma_engine import AvatarRAGEngine

# Preencha APENAS os avatares que falharam no teste local
AVATARES_PARA_INGERIR = [
    'sofia', 'clara', 'lucas', 'amanda', 
    'paula', 'bruno_giovana', 'marcos_carol', 'luisa'
]

def extrair_documentos(avatar, json_file, data):
    """Extrai documentos independente da estrutura - usa IF para cada tipo"""
    docs = []
    
    # Estrutura 1: nucleo_conhecimento
    if 'nucleo_conhecimento' in data:
        for key, values in data['nucleo_conhecimento'].items():
            if isinstance(values, list):
                for v in values:
                    if v and isinstance(v, str):
                        docs.append({"text": v, "metadata": {"fonte": key, "arquivo": json_file}})
    
    # Estrutura 2: items (Sofia)
    if 'items' in data:
        for item in data['items']:
            if isinstance(item, dict):
                if 'pergunta' in item and 'resposta_base' in item:
                    text = f"P: {item['pergunta']}\nR: {item['resposta_base']}"
                    docs.append({"text": text, "metadata": {"tipo": "qa", "arquivo": json_file}}) 
    
    # Estrutura 3: clube/arquetipo (Futebol)
    if 'clube' in data or 'arquetipo' in data:
        text = f"Clube: {data.get('clube', '')}\nArquétipo: {data.get('arquetipo', '')}\nDescrição: {data.get('descricao_arquetipo', '')}\nLinguagem: {data.get('linguagem', '')}"
        if len(text) > 10:
            docs.append({"text": text, "metadata": {"tipo": "persona", "arquivo": json_file}}) 
    
    # Estrutura 4: faq_estruturado (Rafael)
    if 'faq_estruturado' in data:
        for faq in data['faq_estruturado']:
            if 'pergunta' in faq and 'resposta' in faq:
                text = f"P: {faq['pergunta']}\nR: {faq['resposta']}"
                docs.append({"text": text, "metadata": {"tipo": "faq", "arquivo": json_file}})
    
    return docs 

def ingest_selective():
    print("=== INGESTÃO SELETIVA CORRIGIDA ===")
    engine = AvatarRAGEngine()
    
    for avatar in AVATARES_PARA_INGERIR:
        print(f"\n📥 Processando {avatar}...")
        
        # Busca arquivos do avatar
        docs = []
        for json_file in glob.glob(f"**/{avatar}/**/*.json", recursive=True):
            print(f"   Lendo: {json_file}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                docs.extend(extrair_documentos(avatar, json_file, data))
            except Exception as e:
                print(f"   ERRO ao ler {json_file}: {e}")
        
        # Busca alternativa se não encontrou
        if not docs:
            for json_file in glob.glob(f"**/*{avatar}*.json", recursive=True):
                if avatar in json_file.lower():
                    print(f"   Lendo (alternativo): {json_file}")
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        docs.extend(extrair_documentos(avatar, json_file, data))
                    except Exception as e:
                        print(f"   ERRO: {e}")
        
        if not docs:
            print(f"   ⚠️ NENHUM documento encontrado para {avatar}")
            continue
        
        print(f"   📄 {len(docs)} documentos extraídos")
        
        # Obtém ou cria collection
        collection_name = f"{avatar}_knowledge"
        try:
            collection = engine.client.get_collection(collection_name)
            existing = collection.get()
            if existing['ids']:
                collection.delete(ids=existing['ids'])
                print(f"   🗑️ Limpos {len(existing['ids'])} documentos antigos")
        except:
            collection = engine.client.create_collection(collection_name)
            print(f"   ✨ Collection '{collection_name}' criada")
        
        # Ingestão
        batch_size = 50
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i+batch_size]
            collection.add(
                documents=[d['text'] for d in batch],
                metadatas=[d['metadata'] for d in batch],
                ids=[f"{collection_name}_{i+j}" for j in range(len(batch))] 
            )
        
        print(f"   ✅ {collection.count()} documentos ingeridos")
        
        # TESTE OBRIGATÓRIO
        test = collection.query(query_texts=["teste"], n_results=1)
        if test.get('documents') and test['documents'][0]:
            print(f"   ✅ Query teste OK")
        else:
            print(f"   ❌ Query teste FALHOU")

if __name__ == "__main__":
    ingest_selective()
