#!/usr/bin/env python3
"""
WORKER INGESTÃO OFFLINE - Build-time only
Executa DURANTE docker build, NÃO em runtime.
Carrega modelo de embeddings UMA VEZ, indexa todos os avatares, salva ChromaDB em /app/chroma_db.
Controla RAM com batch_size=16 e limpeza de memória entre avatares.
"""

import os
import json
import logging
import hashlib
import gc
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
import chromadb
from chromadb.config import Settings

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path("/app/knowledge")
CHROMA_DB_PATH = Path("/app/chroma_db")
BATCH_SIZE = 16  # Controle de RAM

# Avatares esperados (hardcoded)
EXPECTED_AVATARS = [
    "sofia", "clara", "lucas", "amanda", "fernanda",
    "marina", "roberto", "luisa", "lais", "paula",
    "rafael", "bruno_giovana", "marcos_carol"
]

# ============================================================================
# FASE 1: INICIALIZAR CHROMADB
# ============================================================================

def init_chromadb():
    """Inicializa ChromaDB com PersistentClient"""
    logger.info(f"🔧 Inicializando ChromaDB em {CHROMA_DB_PATH}...")
    
    # Criar diretório se não existir
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    
    # Inicializar cliente
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    logger.info("✅ ChromaDB inicializado")
    return client


# ============================================================================
# FASE 2: CARREGAR MODELO DE EMBEDDINGS (UMA VEZ)
# ============================================================================

def load_embedding_model():
    """Carrega modelo de embeddings UMA VEZ no build"""
    logger.info("🔧 Carregando modelo de embeddings...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L3-v2")
        logger.info("✅ Modelo carregado: paraphrase-MiniLM-L3-v2")
        return model
    except Exception as e:
        logger.error(f"❌ Erro ao carregar modelo: {e}")
        sys.exit(1)


# ============================================================================
# FASE 3: PARSER ROBUSTO
# ============================================================================

def extract_documents(data: Dict[str, Any], avatar_id: str) -> List[Dict[str, str]]:
    """Extrai documentos de múltiplas estruturas JSON"""
    documents = []
    
    # ESTRUTURA 1: FAQ
    if 'faq' in data and isinstance(data['faq'], list):
        for item in data['faq']:
            if isinstance(item, dict) and 'pergunta' in item and 'resposta' in item:
                documents.append({
                    'id': f"faq_{len(documents)}",
                    'content': f"Q: {item['pergunta']}\nA: {item['resposta']}"
                })
    
    # ESTRUTURA 2: Núcleo de Conhecimento
    if 'nucleo_conhecimento' in data and isinstance(data['nucleo_conhecimento'], dict):
        nc = data['nucleo_conhecimento']
        for key in ['problemas_comuns', 'objeções_clientes', 'argumentos_venda']:
            if key in nc and isinstance(nc[key], list):
                for item in nc[key]:
                    if isinstance(item, str):
                        documents.append({
                            'id': f"{key}_{len(documents)}",
                            'content': item
                        })
                    elif isinstance(item, dict):
                        content = item.get('descricao') or item.get('argumento') or item.get('resposta', '')
                        if content:
                            documents.append({
                                'id': f"{key}_{len(documents)}",
                                'content': content
                            })
    
    # ESTRUTURA 3: Sofia (items[])
    if 'items' in data and isinstance(data['items'], list):
        for item in data['items']:
            if isinstance(item, dict) and 'pergunta' in item and 'resposta_base' in item:
                documents.append({
                    'id': f"sofia_{len(documents)}",
                    'content': f"Q: {item['pergunta']}\nA: {item['resposta_base']}"
                })
    
    # ESTRUTURA 4: Áreas Técnicas
    if 'areas_tecnicas' in data and isinstance(data['areas_tecnicas'], list):
        for area in data['areas_tecnicas']:
            if isinstance(area, dict):
                content = area.get('descricao') or area.get('area', '')
                if content:
                    documents.append({
                        'id': f"area_{len(documents)}",
                        'content': content
                    })
    
    # Fallback: descrição simples
    if not documents and 'descricao' in data and data['descricao']:
        documents.append({
            'id': f"{avatar_id}_desc",
            'content': data['descricao']
        })
    
    return documents


# ============================================================================
# FASE 4: INDEXAÇÃO COM CONTROLE DE RAM
# ============================================================================

def index_avatar(avatar_id: str, model, client) -> Tuple[int, List[str]]:
    """Indexa um avatar com controle de RAM"""
    avatar_dir = KNOWLEDGE_DIR / avatar_id
    warnings = []
    
    if not avatar_dir.exists():
        warnings.append(f"Diretório não encontrado: {avatar_dir}")
        return 0, warnings
    
    json_files = list(avatar_dir.glob("*.json"))
    if not json_files:
        warnings.append(f"Nenhum arquivo JSON em {avatar_dir}")
        return 0, warnings
    
    # Criar coleção
    try:
        collection = client.get_or_create_collection(
            name=f"{avatar_id}_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        warnings.append(f"Erro ao criar coleção: {e}")
        return 0, warnings
    
    total_indexed = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            documents = extract_documents(data, avatar_id)
            if not documents:
                continue
            
            # Indexar em batches para controlar RAM
            for i in range(0, len(documents), BATCH_SIZE):
                batch = documents[i:i+BATCH_SIZE]
                
                for doc in batch:
                    # Gerar ID único
                    unique_id = f"{avatar_id}_{hashlib.md5(doc['content'][:100].encode()).hexdigest()[:8]}"
                    
                    # Gerar embedding
                    embedding = model.encode(doc['content']).tolist()
                    
                    # Adicionar ao ChromaDB
                    collection.add(
                        ids=[unique_id],
                        documents=[doc['content']],
                        embeddings=[embedding],
                        metadatas=[{'source': json_file.name}]
                    )
                    total_indexed += 1
                
                # Limpeza de memória entre batches
                gc.collect()
        
        except json.JSONDecodeError as e:
            warnings.append(f"JSON inválido em {json_file.name}: {e}")
            continue
        except Exception as e:
            warnings.append(f"Erro ao processar {json_file.name}: {e}")
            continue
    
    # Limpeza final
    gc.collect()
    
    return total_indexed, warnings


# ============================================================================
# FASE 5: VALIDAÇÃO FINAL
# ============================================================================

def validate_ingest(client) -> bool:
    """Valida que todos os avatares esperados foram indexados"""
    logger.info("\n🔍 VALIDANDO INGESTÃO...")
    
    collections = {col.name: col for col in client.list_collections()}
    missing = []
    
    for avatar in EXPECTED_AVATARS:
        collection_name = f"{avatar}_knowledge"
        if collection_name not in collections:
            missing.append(avatar)
        else:
            count = collections[collection_name].count()
            if count == 0:
                missing.append(f"{avatar} (0 docs)")
            else:
                logger.info(f"✅ {avatar}: {count} docs | coleção: {collection_name}")
    
    if missing:
        logger.error(f"❌ Avatares faltantes ou vazios: {missing}")
        return False
    
    logger.info("✅ Todos os avatares indexados com sucesso")
    return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    logger.info("="*80)
    logger.info("🔧 WORKER INGESTÃO OFFLINE - BUILD-TIME")
    logger.info("="*80)
    
    # Inicializar
    client = init_chromadb()
    model = load_embedding_model()
    
    # Indexar avatares
    total_docs = 0
    all_warnings = []
    
    for avatar in EXPECTED_AVATARS:
        try:
            count, warnings = index_avatar(avatar, model, client)
            total_docs += count
            all_warnings.extend(warnings)
            
            if count > 0:
                logger.info(f"✅ {avatar}: {count} docs indexados")
            elif warnings:
                logger.warning(f"⚠️ {avatar}: {warnings[0]}")
        except Exception as e:
            logger.error(f"❌ Erro ao indexar {avatar}: {e}")
            all_warnings.append(f"{avatar}: {e}")
    
    # Validar
    logger.info(f"\n📊 RESUMO: {total_docs} documentos indexados")
    
    if validate_ingest(client):
        logger.info("\n✅ Build com RAG pré-indexado concluído")
        sys.exit(0)
    else:
        logger.error("\n❌ Validação falhou")
        sys.exit(1)
