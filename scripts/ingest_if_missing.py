#!/usr/bin/env python3
"""Ingestão seletiva - apenas avatares que faltam em produção"""
import sys
import json
import glob
from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

# Avatares que precisam de ingestão (baseado na AÇÃO 4)
AVATARES_PARA_INGERIR = [
    'sofia', 'clara', 'lucas', 'amanda', 'paula', 'bruno_giovana', 'marcos_carol', 'luisa'
]

CHROMA_DB_PATH = Path("/tmp/chroma_db")

def ingest_selective():
    print("\n" + "="*70)
    print("🚀 AÇÃO 5 - INGESTÃO SELETIVA")
    print("="*70 + "\n")
    
    embedding_fn = ONNXMiniLM_L6_V2()
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    
    for avatar in AVATARES_PARA_INGERIR:
        print(f"📥 Ingerindo {avatar}...")
        
        # Busca arquivos do avatar
        docs = []
        
        # Procura em atti-knowledge-packages
        json_files = list(Path("atti-knowledge-packages").glob(f"{avatar}/**/*.json"))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extrai conforme estrutura encontrada na AÇÃO 3
                if isinstance(data, dict):
                    # Estrutura 1: nucleo_conhecimento (Lais, Paula, etc)
                    if 'nucleo_conhecimento' in data:
                        nc = data['nucleo_conhecimento']
                        for key, values in nc.items():
                            if isinstance(values, list):
                                for v in values:
                                    if v and isinstance(v, str):
                                        docs.append({
                                            "text": v,
                                            "metadata": {"fonte": key, "arquivo": json_file.name}
                                        })
                    
                    # Estrutura 2: faq_estruturado (Rafael)
                    elif 'faq_estruturado' in data:
                        for item in data['faq_estruturado']:
                            if isinstance(item, dict):
                                pergunta = item.get('pergunta', '')
                                resposta = item.get('resposta', '')
                                if pergunta and resposta:
                                    docs.append({
                                        "text": f"{pergunta}\n{resposta}",
                                        "metadata": {"fonte": "faq", "arquivo": json_file.name}
                                    })
                    
                    # Estrutura 3: items (Sofia)
                    elif 'items' in data:
                        for item in data['items']:
                            if isinstance(item, dict):
                                pergunta = item.get('pergunta', '')
                                resposta_base = item.get('resposta_base', '')
                                if pergunta and resposta_base:
                                    docs.append({
                                        "text": f"{pergunta}\n{resposta_base}",
                                        "metadata": {"fonte": "qa", "arquivo": json_file.name}
                                    })
                    
                    # Estrutura 4: SPFC/Corinthians (Bruno/Marcos)
                    elif 'clube' in data or 'arquetipo' in data:
                        # Extrai descrição e perfil
                        descricao = data.get('descricao_arquetipo', '')
                        if descricao:
                            docs.append({
                                "text": descricao,
                                "metadata": {"fonte": "persona", "arquivo": json_file.name}
                            })
                        
                        # Extrai linguagem
                        linguagem = data.get('linguagem', {})
                        if isinstance(linguagem, dict):
                            girias = linguagem.get('girias_especificas', [])
                            for gíria in girias:
                                if gíria:
                                    docs.append({
                                        "text": f"Expressão comum: {gíria}",
                                        "metadata": {"fonte": "linguagem", "arquivo": json_file.name}
                                    })
                
                print(f"   ✅ {json_file.name}: {len(docs)} documentos extraídos")
            
            except Exception as e:
                print(f"   ❌ Erro ao processar {json_file}: {e}")
        
        if not docs:
            print(f"  ⚠️ Nenhum documento encontrado para {avatar}")
            continue
        
        # Obtém ou cria collection
        try:
            collection = client.get_collection(f"{avatar}_knowledge")
            existing = collection.get()
            if existing and existing.get('ids'):
                collection.delete(ids=existing['ids'])
                print(f"  🗑️ Limpos {len(existing['ids'])} documentos antigos")
        except:
            collection = client.create_collection(
                name=f"{avatar}_knowledge",
                embedding_function=embedding_fn
            )
            print(f"  ✨ Collection '{avatar}_knowledge' criada")
        
        # Ingestão em lote
        batch_size = 50
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i+batch_size]
            collection.add(
                documents=[d['text'] for d in batch],
                metadatas=[d['metadata'] for d in batch],
                ids=[f"{avatar}_{i+j}" for j in range(len(batch))]
            )
        
        final_count = collection.count()
        print(f"  ✅ {final_count} documentos ingeridos")
        
        # TESTE OBRIGATÓRIO
        try:
            test = collection.query(query_texts=['teste'], n_results=1)
            if test.get('documents') and test['documents'][0]:
                print(f"  ✅ Query teste OK")
            else:
                print(f"  ⚠️ Query teste retornou vazio")
        except Exception as e:
            print(f"  ❌ Query teste falhou: {e}")
    
    print("\n" + "="*70)
    print(f"🎉 INGESTÃO SELETIVA CONCLUÍDA")
    print("="*70 + "\n")

if __name__ == "__main__":
    ingest_selective()
