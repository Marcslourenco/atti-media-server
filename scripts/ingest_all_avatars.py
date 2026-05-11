#!/usr/bin/env python3
"""
Ingestão definitiva para produção - Acessa ChromaDB diretamente
Executado em runtime via entrypoint.sh
"""
import os
import sys
import json
import logging
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Diretório de conhecimento
KNOWLEDGE_DIR = Path("./knowledge")
CHROMA_DB_PATH = Path("/tmp/chroma_db")

def load_documents_from_json(avatar_name: str) -> list:
    """Carrega documentos dos arquivos JSON do avatar"""
    documents = []
    avatar_dir = KNOWLEDGE_DIR / avatar_name
    
    if not avatar_dir.exists():
        logger.warning(f"⚠️ Diretório não encontrado: {avatar_dir}")
        return documents
    
    # Procura por arquivos .json
    json_files = list(avatar_dir.glob("*.json"))
    logger.info(f"📁 {avatar_name}: encontrados {len(json_files)} arquivos JSON")
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extrai textos do núcleo de conhecimento
            if isinstance(data, dict) and 'nucleo_conhecimento' in data:
                nc = data['nucleo_conhecimento']
                
                # Coleta todos os textos de cada categoria
                for category, items in nc.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str) and item.strip():
                                documents.append({
                                    "text": item,
                                    "metadata": {
                                        "avatar": avatar_name,
                                        "fonte": json_file.name,
                                        "categoria": category
                                    }
                                })
            
            logger.info(f"  ✅ {json_file.name}: {len(documents)} documentos extraídos")
        
        except Exception as e:
            logger.error(f"  ❌ Erro ao processar {json_file}: {e}")
    
    return documents

def ingest_all():
    """Ingere todos os avatares diretamente no ChromaDB"""
    print("\n" + "=" * 70)
    print("🚀 INICIANDO INGESTÃO EM RUNTIME")
    print("=" * 70 + "\n")
    
    # Inicializa ChromaDB com ONNX
    logger.info(f"🔧 Inicializando ChromaDB em {CHROMA_DB_PATH}...")
    embedding_fn = ONNXMiniLM_L6_V2()
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    logger.info("✅ ChromaDB inicializado")
    
    # Lista de avatares esperados
    avatars = [
        "sofia", "clara", "lucas", "amanda", "fernanda",
        "marina", "roberto", "luisa", "lais", "paula",
        "rafael", "bruno_giovana", "marcos_carol"
    ]
    
    total_docs = 0
    successful_avatars = 0
    
    for avatar_name in avatars:
        try:
            logger.info(f"\n📝 Processando {avatar_name}...")
            
            # Carrega documentos
            documents = load_documents_from_json(avatar_name)
            
            if not documents:
                logger.warning(f"  ⚠️ Nenhum documento encontrado para {avatar_name}")
                continue
            
            # Cria/obtém collection
            collection_name = f"{avatar_name}_knowledge"
            collection = client.get_or_create_collection(
                name=collection_name,
                embedding_function=embedding_fn
            )
            
            # Limpa dados antigos (evita duplicação)
            try:
                collection.delete_all()
            except:
                pass
            
            # Adiciona documentos em lote
            batch_size = 50
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i+batch_size]
                
                collection.add(
                    documents=[d['text'] for d in batch],
                    metadatas=[d.get('metadata', {}) for d in batch],
                    ids=[f"{avatar_name}_{i+j}" for j in range(len(batch))]
                )
            
            # Verifica resultado
            final_count = collection.count()
            logger.info(f"  ✅ {final_count} documentos ingeridos em '{avatar_name}'")
            
            # TESTE CRÍTICO: query real
            try:
                test = collection.query(query_texts=["teste"], n_results=1)
                if test.get('documents') and len(test['documents']) > 0 and len(test['documents'][0]) > 0:
                    logger.info(f"  ✅ Teste de query OK")
                else:
                    logger.warning(f"  ⚠️ Teste de query retornou vazio")
            except Exception as e:
                logger.error(f"  ❌ Teste de query falhou: {e}")
            
            total_docs += final_count
            successful_avatars += 1
        
        except Exception as e:
            logger.error(f"  ❌ Erro ao processar {avatar_name}: {e}", exc_info=True)
    
    print("\n" + "=" * 70)
    print(f"🎉 INGESTÃO CONCLUÍDA")
    print(f"   ✅ {successful_avatars}/{len(avatars)} avatares processados")
    print(f"   📊 {total_docs} documentos totais ingeridos")
    print("=" * 70 + "\n")
    
    return successful_avatars == len(avatars)

if __name__ == "__main__":
    success = ingest_all()
    sys.exit(0 if success else 1)
