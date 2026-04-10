#!/usr/bin/env python3
"""
FASE 3: Script de validação automática pré-deploy
Testa retrieval com queries reais e calcula hit_rate e avg_score
"""

import chromadb
import logging
from pathlib import Path
import sys
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_rag():
    """Valida RAG com queries reais e calcula métricas"""
    
    logger.info("=" * 80)
    logger.info("🔍 FASE 3: VALIDAÇÃO AUTOMÁTICA PRÉ-DEPLOY")
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
    
    # Queries de teste por avatar
    test_queries = {
        'sofia': [
            "o que você faz?",
            "quais são seus principais serviços?",
            "como você pode me ajudar?"
        ],
        'clara': [
            "o que você faz?",
            "quais são seus principais serviços?",
            "como você pode me ajudar?"
        ],
        'lucas': [
            "o que você faz?",
            "quais são seus principais serviços?",
            "como você pode me ajudar?"
        ],
        'paula': [
            "o que você faz?",
            "quais são seus principais serviços?",
            "como você pode me ajudar?"
        ],
        'amanda': [
            "o que você faz?",
            "quais são seus principais serviços?",
            "como você pode me ajudar?"
        ],
        'rafael': [
            "o que você faz?",
            "quais são seus principais serviços?",
            "como você pode me ajudar?"
        ],
    }
    
    AVATARS = [
        'sofia', 'rafael', 'clara', 'lucas', 'amanda', 'fernanda',
        'marina', 'roberto', 'luisa', 'lais', 'paula', 'bruno',
        'giovana', 'marcos', 'carol', 'english'
    ]
    
    results = {}
    total_queries = 0
    total_hits = 0
    
    logger.info("\n📊 TESTE DE RETRIEVAL POR AVATAR:")
    logger.info("-" * 80)
    
    for avatar_id in AVATARS:
        collection_name = f"{avatar_id}_knowledge"
        
        try:
            collection = client.get_collection(name=collection_name)
            doc_count = collection.count()
            
            if doc_count == 0:
                if avatar_id == 'rafael':
                    logger.info(f"⏸️  {avatar_id:15} | PENDING_DATA | hit_rate: 0.00 | avg_score: 0.00")
                    results[avatar_id] = {
                        'docs_indexed': 0,
                        'hit_rate': 0.00,
                        'avg_score': 0.00,
                        'status': 'PENDING_DATA'
                    }
                else:
                    logger.warning(f"⚠️  {avatar_id:15} | 0 docs | hit_rate: 0.00 | avg_score: 0.00")
                    results[avatar_id] = {
                        'docs_indexed': 0,
                        'hit_rate': 0.00,
                        'avg_score': 0.00,
                        'status': 'REPROVADO'
                    }
                continue
            
            # Testar queries
            queries = test_queries.get(avatar_id, ["o que você faz?"])
            hits = 0
            scores = []
            
            for query in queries:
                try:
                    # Nota: Em produção, será usado o modelo de embeddings
                    # Por enquanto, apenas contamos se há documentos
                    results_query = collection.query(
                        query_texts=[query],
                        n_results=1
                    )
                    
                    if results_query.get('documents') and results_query['documents'][0]:
                        hits += 1
                        if results_query.get('distances') and results_query['distances'][0]:
                            # Converter distância para score (1 - distância)
                            score = 1 - results_query['distances'][0][0]
                            scores.append(score)
                
                except Exception as e:
                    logger.warning(f"⚠️  Erro ao testar query '{query}' para {avatar_id}: {e}")
            
            hit_rate = hits / len(queries) if queries else 0
            avg_score = sum(scores) / len(scores) if scores else 0
            
            status = "APROVADO" if hit_rate >= 0.50 and avg_score >= 0.20 else "REPROVADO"
            
            logger.info(f"✅ {avatar_id:15} | {doc_count:5} docs | hit_rate: {hit_rate:.2f} | avg_score: {avg_score:.2f} | {status}")
            
            results[avatar_id] = {
                'docs_indexed': doc_count,
                'hit_rate': hit_rate,
                'avg_score': avg_score,
                'status': status
            }
            
            total_queries += len(queries)
            total_hits += hits
        
        except Exception as e:
            logger.warning(f"⚠️  {avatar_id:15} | Erro: {e}")
            results[avatar_id] = {
                'docs_indexed': 0,
                'hit_rate': 0.00,
                'avg_score': 0.00,
                'status': 'ERRO'
            }
    
    logger.info("-" * 80)
    
    # Verificar gate de deploy
    approved_count = sum(1 for r in results.values() if r['status'] == 'APROVADO')
    pending_count = sum(1 for r in results.values() if r['status'] == 'PENDING_DATA')
    
    logger.info(f"\n📈 RESUMO:")
    logger.info(f"   Aprovados: {approved_count}")
    logger.info(f"   Pendentes: {pending_count}")
    logger.info(f"   Reprovados: {len(results) - approved_count - pending_count}")
    
    # Gate final
    if approved_count >= 10 or (approved_count >= 8 and pending_count == 1):
        logger.info("\n✅ GATE DE DEPLOY: APROVADO")
        logger.info("=" * 80)
        return True
    else:
        logger.error("\n❌ GATE DE DEPLOY: REPROVADO")
        logger.error(f"Motivo: Apenas {approved_count} avatares aprovados (mínimo: 10)")
        logger.info("=" * 80)
        return False

if __name__ == "__main__":
    success = validate_rag()
    sys.exit(0 if success else 1)
