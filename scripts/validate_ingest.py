#!/usr/bin/env python3
"""
VALIDATE INGEST - Validação pós-build (v2.0 otimizada)
Executa DURANTE docker build após worker_ingest_buildtime.py.
Verifica que TODOS os avatares esperados têm coleções com >0 documentos.
Falha com exit(1) se houver coleções faltantes ou vazias.
"""

import sys
import logging
from pathlib import Path
import chromadb

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CHROMA_DB_PATH = Path("/app/chroma_db")

# Avatares esperados (deve corresponder a worker_ingest_buildtime.py)
EXPECTED_AVATARS = [
    "sofia", "clara", "lucas", "amanda", "fernanda",
    "marina", "roberto", "luisa", "lais", "paula",
    "rafael", "bruno_giovana", "marcos_carol"
]

# ============================================================================
# VALIDAÇÃO
# ============================================================================

def validate_ingest():
    """Valida que todos os avatares esperados foram indexados"""
    logger.info("="*80)
    logger.info("🔍 VALIDAÇÃO PÓS-BUILD")
    logger.info("="*80)
    
    # Conectar ao ChromaDB
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
        logger.info(f"✅ Conectado ao ChromaDB em {CHROMA_DB_PATH}")
    except Exception as e:
        logger.error(f"❌ Erro ao conectar ao ChromaDB: {e}")
        return False
    
    # Listar coleções
    collections = {col.name: col for col in client.list_collections()}
    logger.info(f"\n📊 Coleções encontradas: {len(collections)}")
    
    # Validar avatares esperados
    missing = []
    empty = []
    
    for avatar in EXPECTED_AVATARS:
        collection_name = f"{avatar}_knowledge"
        
        if collection_name not in collections:
            missing.append(avatar)
            logger.warning(f"⚠️ {avatar}: COLEÇÃO NÃO ENCONTRADA")
        else:
            count = collections[collection_name].count()
            if count == 0:
                empty.append(avatar)
                logger.warning(f"⚠️ {avatar}: COLEÇÃO VAZIA (0 docs)")
            else:
                logger.info(f"✅ {avatar}: {count} docs | coleção: {collection_name}")
    
    # Relatório final
    logger.info("\n" + "="*80)
    logger.info("📋 RELATÓRIO FINAL")
    logger.info("="*80)
    
    total_expected = len(EXPECTED_AVATARS)
    total_indexed = len(EXPECTED_AVATARS) - len(missing) - len(empty)
    
    logger.info(f"Avatares esperados: {total_expected}")
    logger.info(f"Avatares indexados: {total_indexed}")
    logger.info(f"Avatares faltantes: {len(missing)}")
    logger.info(f"Avatares vazios: {len(empty)}")
    
    if missing:
        logger.error(f"\n❌ Coleções faltantes: {missing}")
    
    if empty:
        logger.error(f"\n❌ Coleções vazias: {empty}")
    
    # Gate de validação
    if missing or empty:
        logger.error("\n❌ VALIDAÇÃO FALHOU")
        return False
    else:
        logger.info("\n✅ TODOS OS AVATARES INDEXADOS COM SUCESSO")
        return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    success = validate_ingest()
    sys.exit(0 if success else 1)
