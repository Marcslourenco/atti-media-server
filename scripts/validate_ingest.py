#!/usr/bin/env python3
"""
FASE 2.5: Script de validação de ingestão
Conecta no ChromaDB pré-indexado e valida se documentos foram indexados
"""

import chromadb
import logging
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_ingest():
    """Valida se ChromaDB foi pré-indexado com sucesso"""
    
    logger.info("=" * 80)
    logger.info("🔍 FASE 2.5: VALIDAÇÃO DE INGESTÃO")
    logger.info("=" * 80)
    
    # Conectar no ChromaDB
    chroma_path = Path("/app/chroma_db") if Path("/app/chroma_db").exists() else Path("./chroma_db")
    
    logger.info(f"📁 Conectando no ChromaDB em: {chroma_path.absolute()}")
    
    try:
        client = chromadb.PersistentClient(path=str(chroma_path))
        logger.info("✅ ChromaDB conectado com sucesso")
    except Exception as e:
        logger.error(f"❌ Erro ao conectar no ChromaDB: {e}")
        return False
    
    # Listar coleções e contar documentos
    AVATARS = [
        'sofia', 'rafael', 'clara', 'lucas', 'amanda', 'fernanda',
        'marina', 'roberto', 'luisa', 'lais', 'paula', 'bruno',
        'giovana', 'marcos', 'carol', 'english'
    ]
    
    total_docs = 0
    avatars_with_docs = 0
    
    logger.info("\n📊 CONTAGEM DE DOCUMENTOS POR AVATAR:")
    logger.info("-" * 80)
    
    for avatar_id in AVATARS:
        collection_name = f"{avatar_id}_knowledge"
        try:
            collection = client.get_collection(name=collection_name)
            doc_count = collection.count()
            
            if doc_count > 0:
                avatars_with_docs += 1
                total_docs += doc_count
                logger.info(f"✅ {avatar_id:15} | {collection_name:25} | {doc_count:5} docs")
            else:
                if avatar_id == 'rafael':
                    logger.info(f"⏸️  {avatar_id:15} | {collection_name:25} | PENDING_DATA")
                else:
                    logger.warning(f"⚠️  {avatar_id:15} | {collection_name:25} | 0 docs")
        
        except Exception as e:
            logger.warning(f"⚠️  {avatar_id:15} | Coleção não encontrada")
    
    logger.info("-" * 80)
    logger.info(f"✅ Validação: {avatars_with_docs} avatares com conhecimento indexado")
    logger.info(f"✅ Total de documentos: {total_docs}")
    logger.info("=" * 80)
    
    # Gate de validação
    if total_docs > 0:
        logger.info("✅ VALIDAÇÃO APROVADA: Ingestão bem-sucedida")
        return True
    else:
        logger.error("❌ VALIDAÇÃO REPROVADA: Nenhum documento indexado")
        return False

if __name__ == "__main__":
    success = validate_ingest()
    sys.exit(0 if success else 1)
