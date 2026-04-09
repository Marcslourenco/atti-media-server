"""
Endpoint de validação do RAG para execução em tempo real no Render
Retorna métricas estruturadas sobre ingestão e retrieval
"""

import json
from typing import Dict, List
from fastapi import APIRouter, HTTPException

router = APIRouter()

def validate_rag_engine(rag_engine) -> Dict:
    """Valida o RAG engine e retorna métricas"""
    
    if not rag_engine:
        return {
            "status": "ERROR",
            "message": "RAG engine não inicializado",
            "avatars": []
        }
    
    results = {
        "status": "OK",
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "avatars": [],
        "summary": {
            "total_avatars": 0,
            "avatars_with_docs": 0,
            "total_docs": 0,
            "avg_docs_per_avatar": 0.0
        }
    }
    
    try:
        # Validar cada avatar
        for avatar_id in rag_engine.AVATARS:
            avatar_result = {
                "avatar_id": avatar_id,
                "docs_indexed": 0,
                "queries_tested": 0,
                "queries_with_results": 0,
                "avg_score": 0.0,
                "status": "UNKNOWN"
            }
            
            try:
                collection = rag_engine.collections.get(avatar_id)
                if not collection:
                    avatar_result["status"] = "NO_COLLECTION"
                else:
                    doc_count = collection.count()
                    avatar_result["docs_indexed"] = doc_count
                    
                    if doc_count == 0:
                        avatar_result["status"] = "EMPTY"
                    else:
                        # Testar retrieval
                        test_queries = [
                            "o que você faz?",
                            "quais são seus serviços?",
                            "como funciona?"
                        ]
                        
                        scores = []
                        for query in test_queries:
                            try:
                                results_list = rag_engine.query(avatar_id, query, top_k=1)
                                if results_list and len(results_list) > 0:
                                    avatar_result["queries_with_results"] += 1
                                    scores.append(results_list[0].get('score', 0.0))
                            except:
                                pass
                        
                        avatar_result["queries_tested"] = len(test_queries)
                        if scores:
                            avatar_result["avg_score"] = sum(scores) / len(scores)
                        
                        # Determinar status
                        hit_rate = avatar_result["queries_with_results"] / len(test_queries) if test_queries else 0
                        if hit_rate >= 0.5 and avatar_result["avg_score"] >= 0.20:
                            avatar_result["status"] = "APPROVED"
                        elif hit_rate > 0:
                            avatar_result["status"] = "PARTIAL"
                        else:
                            avatar_result["status"] = "NO_RESULTS"
                        
                        results["summary"]["avatars_with_docs"] += 1
                        results["summary"]["total_docs"] += doc_count
            
            except Exception as e:
                avatar_result["status"] = "ERROR"
                avatar_result["error"] = str(e)
            
            results["avatars"].append(avatar_result)
        
        # Calcular resumo
        results["summary"]["total_avatars"] = len(results["avatars"])
        if results["summary"]["total_avatars"] > 0:
            results["summary"]["avg_docs_per_avatar"] = (
                results["summary"]["total_docs"] / results["summary"]["total_avatars"]
            )
        
        # Determinar gate final
        approved = sum(1 for a in results["avatars"] if a["status"] == "APPROVED")
        total = len(results["avatars"])
        
        if approved >= total * 0.8:
            results["gate"] = "APPROVED_FOR_DEPLOY"
        else:
            results["gate"] = "BLOCKED"
        
        return results
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Erro durante validação: {str(e)}",
            "avatars": []
        }


def setup_validation_endpoint(app, rag_engine):
    """Configura o endpoint de validação"""
    
    @app.get("/api/validate-rag")
    async def validate_rag():
        """Endpoint de validação do RAG em tempo real"""
        
        validation_result = validate_rag_engine(rag_engine)
        
        if validation_result["gate"] == "BLOCKED":
            raise HTTPException(
                status_code=503,
                detail=validation_result
            )
        
        return validation_result
