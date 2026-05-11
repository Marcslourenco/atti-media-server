#!/usr/bin/env python3
"""Ingestão seletiva - apenas avatares que faltam em produção - VERSÃO 2"""
import sys
import json
from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

AVATARES_PARA_INGERIR = [
    'sofia', 'clara', 'lucas', 'amanda', 'paula', 'bruno_giovana', 'marcos_carol', 'luisa'
]

CHROMA_DB_PATH = Path("/tmp/chroma_db")

def extract_documents(avatar, data):
    """Extrai documentos conforme a estrutura do JSON"""
    docs = []
    
    if not isinstance(data, dict):
        return docs
    
    # Estrutura 1: nucleo_conhecimento (Clara, Lucas, Amanda, Paula, Luisa)
    if 'nucleo_conhecimento' in data:
        nc = data['nucleo_conhecimento']
        if isinstance(nc, dict):
            for key, values in nc.items():
                if isinstance(values, list):
                    for v in values:
                        if v and isinstance(v, str):
                            docs.append({
                                "text": v,
                                "metadata": {"fonte": key, "avatar": avatar}
                            })
    
    # Estrutura 2: items (Sofia)
    elif 'items' in data:
        for item in data.get('items', []):
            if isinstance(item, dict):
                pergunta = item.get('pergunta', '')
                resposta_base = item.get('resposta_base', '')
                if pergunta and resposta_base:
                    docs.append({
                        "text": f"{pergunta}\n{resposta_base}",
                        "metadata": {"fonte": "qa", "avatar": avatar}
                    })
    
    # Estrutura 3: SPFC/Corinthians (Bruno/Marcos)
    elif 'clube' in data or 'arquetipo' in data:
        descricao = data.get('descricao_arquetipo', '')
        if descricao:
            docs.append({
                "text": descricao,
                "metadata": {"fonte": "persona", "avatar": avatar}
            })
        
        linguagem = data.get('linguagem', {})
        if isinstance(linguagem, dict):
            girias = linguagem.get('girias_especificas', [])
            for gíria in girias:
                if gíria:
                    docs.append({
                        "text": gíria,
                        "metadata": {"fonte": "linguagem", "avatar": avatar}
                    })
            
            expressoes = linguagem.get('expressoes_de_torcida', [])
            for expr in expressoes:
                if expr:
                    docs.append({
                        "text": expr,
                        "metadata": {"fonte": "expressao", "avatar": avatar}
                    })
        
        perfil = data.get('perfil_demografico', {})
        if isinstance(perfil, dict):
            desc_arq = perfil.get('zona_urbana_primaria', '')
            if desc_arq:
                docs.append({
                    "text": f"Zona urbana: {desc_arq}",
                    "metadata": {"fonte": "perfil", "avatar": avatar}
                })
    
    return docs

def ingest_selective():
    print("\n" + "="*70)
    print("🚀 AÇÃO 5 - INGESTÃO SELETIVA (V2)")
    print("="*70 + "\n")
    
    embedding_fn = ONNXMiniLM_L6_V2()
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    
    total_ingeridos = 0
    
    for avatar in AVATARES_PARA_INGERIR:
        print(f"📥 Ingerindo {avatar}...")
        
        docs = []
        json_files = list(Path("atti-knowledge-packages").glob(f"{avatar}/**/*.json"))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                file_docs = extract_documents(avatar, data)
                docs.extend(file_docs)
                
                print(f"   ✅ {json_file.name}: {len(file_docs)} documentos extraídos")
            
            except Exception as e:
                print(f"   ❌ Erro ao processar {json_file}: {e}")
        
        if not docs:
            print(f"  ⚠️ Nenhum documento encontrado para {avatar}")
            continue
        
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
        total_ingeridos += final_count
        
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
    print(f"   Total de documentos ingeridos: {total_ingeridos}")
    print("="*70 + "\n")

if __name__ == "__main__":
    ingest_selective()
