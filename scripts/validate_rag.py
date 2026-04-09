#!/usr/bin/env python3
"""
Script de validação automática do RAG pré-deploy
Testa ingestão, busca e calcula métricas de qualidade
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chroma_engine import AvatarRAGEngine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RAGValidator:
    """Validador de qualidade do RAG"""
    
    def __init__(self):
        self.results = {}
        self.queries = {
            'sofia': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona a triagem inicial?'
            ],
            'rafael': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona a integração?'
            ],
            'clara': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona o atendimento?'
            ],
            'lucas': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona o suporte?'
            ],
            'amanda': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona a consultoria?'
            ],
            'paula': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona o atendimento?'
            ],
            'fernanda': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona?'
            ],
            'marina': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona?'
            ],
            'roberto': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona?'
            ],
            'luisa': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona?'
            ],
            'lais': [
                'o que você faz?',
                'quais são seus principais serviços?',
                'como funciona?'
            ]
        }
    
    def validate(self) -> Dict:
        """Executa validação completa"""
        logger.info("="*70)
        logger.info("🔍 INICIANDO VALIDAÇÃO DO RAG")
        logger.info("="*70)
        
        try:
            # Inicializar RAG Engine
            logger.info("\n📦 Inicializando RAG Engine...")
            engine = AvatarRAGEngine()
            
            # Testar cada avatar
            for avatar_id in engine.AVATARS:
                self._test_avatar(engine, avatar_id)
            
            # Gerar relatório
            self._generate_report()
            
            return self.results
        
        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO: {e}", exc_info=True)
            return None
    
    def _test_avatar(self, engine: AvatarRAGEngine, avatar_id: str):
        """Testa um avatar específico"""
        logger.info(f"\n🧪 Testando avatar: {avatar_id}")
        
        collection = engine.collections.get(avatar_id)
        if not collection:
            logger.warning(f"⚠️ Coleção não encontrada para {avatar_id}")
            self.results[avatar_id] = {
                'docs_indexed': 0,
                'hit_rate': 0.0,
                'avg_score': 0.0,
                'status': 'FAIL',
                'reason': 'Coleção não encontrada'
            }
            return
        
        # Contar documentos
        doc_count = collection.count()
        logger.info(f"  📊 Documentos indexados: {doc_count}")
        
        if doc_count == 0:
            logger.warning(f"⚠️ Nenhum documento indexado para {avatar_id}")
            self.results[avatar_id] = {
                'docs_indexed': 0,
                'hit_rate': 0.0,
                'avg_score': 0.0,
                'status': 'FAIL',
                'reason': 'Coleção vazia'
            }
            return
        
        # Executar queries
        queries = self.queries.get(avatar_id, ['o que você faz?'])
        hits = 0
        scores = []
        
        for query in queries:
            try:
                results = engine.query(avatar_id, query, top_k=1)
                if results and len(results) > 0:
                    hits += 1
                    scores.append(results[0]['score'])
                    logger.info(f"  ✅ Query: '{query}' → score: {results[0]['score']:.2f}")
                else:
                    logger.info(f"  ❌ Query: '{query}' → sem resultados")
            except Exception as e:
                logger.error(f"  ❌ Erro na query: {e}")
        
        # Calcular métricas
        hit_rate = hits / len(queries) if queries else 0.0
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        # Determinar status
        status = 'APROVADO' if hit_rate >= 0.50 and avg_score >= 0.20 else 'REPROVADO'
        reason = None
        if hit_rate < 0.50:
            reason = f'hit_rate baixo: {hit_rate:.2f}'
        elif avg_score < 0.20:
            reason = f'avg_score baixo: {avg_score:.2f}'
        
        self.results[avatar_id] = {
            'docs_indexed': doc_count,
            'hit_rate': hit_rate,
            'avg_score': avg_score,
            'status': status,
            'reason': reason
        }
        
        logger.info(f"  📈 Hit rate: {hit_rate:.2%}")
        logger.info(f"  📈 Avg score: {avg_score:.2f}")
        logger.info(f"  🎯 Status: {status}")
    
    def _generate_report(self):
        """Gera relatório final"""
        logger.info("\n" + "="*70)
        logger.info("📋 RELATÓRIO FINAL DE VALIDAÇÃO")
        logger.info("="*70)
        
        # Tabela de resultados
        logger.info("\n| Avatar | Docs | Hit Rate | Avg Score | Status |")
        logger.info("|--------|------|----------|-----------|--------|")
        
        for avatar_id, result in self.results.items():
            status = "✅ APROVADO" if result['status'] == 'APROVADO' else "❌ REPROVADO"
            logger.info(
                f"| {avatar_id:6} | {result['docs_indexed']:4} | "
                f"{result['hit_rate']:7.1%} | {result['avg_score']:8.2f} | {status} |"
            )
        
        # Resumo
        approved = sum(1 for r in self.results.values() if r['status'] == 'APROVADO')
        total = len(self.results)
        
        logger.info(f"\n✅ Aprovados: {approved}/{total}")
        logger.info(f"❌ Reprovados: {total - approved}/{total}")
        
        # Gate final
        if approved >= total * 0.8:  # 80% de aprovação
            logger.info("\n🚀 GATE FINAL: APROVADO PARA DEPLOY")
        else:
            logger.info("\n🚫 GATE FINAL: REPROVADO - CORRIGIR ANTES DE DEPLOY")

if __name__ == '__main__':
    validator = RAGValidator()
    validator.validate()
