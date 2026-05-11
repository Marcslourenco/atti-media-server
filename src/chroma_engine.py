#!/usr/bin/env python3
"""
CHROMA ENGINE v2.0 - Read-Only Runtime + Lazy Loading
Separação clara: ingestão em build-time, leitura em runtime.
NUNCA faz collection.add() ou create_collection() em runtime.
"""

import json
import os
import logging
import threading
import psutil
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# I18N INTEGRATION
# ============================================================================
try:
    from i18n_engine import I18nEngine
    I18N_AVAILABLE = True
    logger.info("✅ i18n_engine disponível - tradução ativada")
except ImportError:
    I18N_AVAILABLE = False
    logger.warning("⚠️ i18n_engine não encontrado. Tradução desabilitada.")

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

KNOWLEDGE_MODE = os.getenv("KNOWLEDGE_MODE", "runtime")  # build ou runtime
logger.info(f"🔧 KNOWLEDGE_MODE: {KNOWLEDGE_MODE}")

# ============================================================================
# LAZY LOADING - SINGLETON THREAD-SAFE
# ============================================================================

_embedding_model = None
_embedding_model_lock = threading.Lock()

def _get_embedding_model_singleton():
    """Carrega ONNX nativo sob demanda (thread-safe singleton)"""
    global _embedding_model
    if _embedding_model is None:
        with _embedding_model_lock:
            if _embedding_model is None:
                logger.info("📥 Carregando modelo ONNX nativo (singleton)...")
                try:
                    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                    _embedding_model = ONNXMiniLM_L6_V2()
                    logger.info("✅ Modelo ONNX nativo carregado com sucesso")
                except Exception as e:
                    logger.error(f"❌ Erro ao carregar modelo ONNX: {e}", exc_info=True)
                    logger.warning("⚠️ Fallback para SentenceTransformer...")
                    try:
                        from sentence_transformers import SentenceTransformer
                        _embedding_model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L3-v2")
                        logger.info("✅ Fallback: SentenceTransformer carregado")
                    except Exception as e2:
                        logger.error(f"❌ Erro ao carregar fallback: {e2}", exc_info=True)
                        raise
    return _embedding_model


# ============================================================================
# DECORATOR: RUNTIME_ONLY
# ============================================================================

def runtime_only(func):
    """Decorator que falha se KNOWLEDGE_MODE != 'build'"""
    def wrapper(*args, **kwargs):
        if KNOWLEDGE_MODE != "build":
            raise RuntimeError(f"Função {func.__name__} só pode ser chamada em build-time (KNOWLEDGE_MODE=build)")
        return func(*args, **kwargs)
    return wrapper


# ============================================================================
# AVATAR RAG ENGINE - READ-ONLY
# ============================================================================

class AvatarRAGEngine:
    """
    Motor de RAG para avatares - MODO READ-ONLY em runtime
    Ingestão acontece em build-time via scripts/worker_ingest_buildtime.py
    """
    
    AVATARS = [
        'sofia', 'rafael', 'clara', 'lucas', 'amanda', 'fernanda',
        'marina', 'roberto', 'luisa', 'lais', 'paula', 'bruno_giovana', 'marcos_carol',
        'giovana', 'carol'
    ]
    
    def __init__(self, persist_dir: str = None):
        """
        Inicializa ChromaDB em modo READ-ONLY
        Não faz ingestão em runtime.
        """
        # Usar /tmp/chroma_db em runtime, /app/chroma_db em build
        if persist_dir is None:
            persist_dir = "/tmp/chroma_db" if KNOWLEDGE_MODE == "runtime" else "/app/chroma_db"
        
        logger.info(f"🔍 ARQUIVO CHROMA EM USO: {__file__}")
        logger.info(f"🔍 PERSIST_DIR: {persist_dir} (KNOWLEDGE_MODE={KNOWLEDGE_MODE})")
        self.persist_dir = persist_dir
        self.knowledge_mode = KNOWLEDGE_MODE
        
        # Criar diretório se não existir (para desenvolvimento local)
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        
        # Inicializar ChromaDB como cliente de leitura
        logger.info(f"🔍 Inicializando ChromaDB em modo {self.knowledge_mode}...")
        try:
            import chromadb
            self.client = chromadb.PersistentClient(
                path=persist_dir,
                settings=chromadb.config.Settings(
                    anonymized_telemetry=False,
                    allow_reset=False  # ← IMPORTANTE: Não permitir reset em runtime
                )
            )
            logger.info(f"✅ ChromaDB inicializado (modo {self.knowledge_mode})")
        except Exception as e:
            logger.error(f"❌ ERRO ao inicializar ChromaDB: {e}", exc_info=True)
            self.client = None
            return
        
        # Modelo de embeddings - LAZY LOADING
        self.embedding_model = None
        logger.info(f"🔍 Embeddings configurados para lazy loading")
        
        # Coleções por avatar
        self.collections = {}
        self._init_collections_readonly()
        
        logger.info(f"✅ RAG Engine inicializado em modo {self.knowledge_mode}")
        logger.info(f"✅ Coleções disponíveis: {len(self.collections)}")
        
        # Log de RAM no startup
        ram_gb = psutil.Process().memory_info().rss / (1024**3)
        logger.info(f"💾 RAM no startup: {ram_gb:.2f} GB")
    
    def _get_embedding_model(self):
        """Usa singleton thread-safe para lazy loading"""
        return _get_embedding_model_singleton()
    
    def _init_collections_readonly(self):
        """
        Inicializa coleções em modo READ-ONLY
        NÃO cria coleções, apenas lista as pré-existentes
        """
        if self.client is None:
            logger.warning("⚠️ ChromaDB não inicializado, skipping collection init")
            return
        
        try:
            # Listar coleções existentes
            existing_collections = {col.name: col for col in self.client.list_collections()}
            logger.info(f"📊 Coleções encontradas: {len(existing_collections)}")
            
            # Mapear avatares para coleções
            for avatar_id in self.AVATARS:
                collection_name = f"{avatar_id}_knowledge"
                
                if collection_name in existing_collections:
                    self.collections[avatar_id] = existing_collections[collection_name]
                    count = existing_collections[collection_name].count()
                    logger.info(f"✅ {avatar_id}: {count} docs disponíveis")
                else:
                    logger.warning(f"⚠️ {avatar_id}: Coleção não encontrada (será retornado fallback)")
        
        except Exception as e:
            logger.error(f"❌ Erro ao listar coleções: {e}", exc_info=True)
    
    def query(self, query_text: str, avatar_id: str, n_results: int = 3) -> Dict:
        """
        Busca documentos relevantes no ChromaDB
        Retorna fallback seguro se coleção não for encontrada
        """
        # Verificar se coleção existe
        if avatar_id not in self.collections:
            logger.warning(f"⚠️ Coleção não encontrada para {avatar_id} - retornando fallback")
            return {
                "error": "collection_not_found",
                "fallback": True,
                "documents": [],
                "metadatas": [],
                "distances": []
            }
        
        try:
            # Lazy loading do modelo ONNX
            embedding_fn = self._get_embedding_model()
            
            # ONNX usa __call__() diretamente, retorna lista de embeddings
            query_embeddings = embedding_fn([query_text])
            logger.info(f"🔍 Query embedding gerado com ONNX: {len(query_embeddings)} embeddings")
            
            # Query no ChromaDB com embedding ONNX
            collection = self.collections[avatar_id]
            results = collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results
            )
            
            logger.info(f"✅ Query executada para {avatar_id}: {len(results.get('documents', [[]])[0])} documentos encontrados")
            
            return {
                "documents": results.get('documents', []),
                "metadatas": results.get('metadatas', []),
                "distances": results.get('distances', []),
                "fallback": False
            }
        
        except Exception as e:
            logger.error(f"❌ Erro ao fazer query: {e}", exc_info=True)
            return {
                "error": str(e),
                "fallback": True,
                "documents": [],
                "metadatas": [],
                "distances": []
            }
    
    def generate_response(self, query_text: str, avatar_id: str, language: str = "pt-BR") -> str:
        """
        Gera resposta baseada em RAG
        Retorna fallback seguro se não encontrar documentos
        """
        try:
            # ========================================================================
            # TRADUÇÃO DE CONSULTA (I18N)
            # ========================================================================
            original_language = language
            query_for_search = query_text
            
            # Traduz consulta para português se não for PT-BR
            if I18N_AVAILABLE and language != "pt-BR":
                try:
                    i18n = I18nEngine()
                    i18n.set_language(language)
                    # Nota: i18n.translate() espera uma chave, não um texto. Usar fallback.
                    logger.info(f"🔄 Consulta em {language}: '{query_text[:50]}...'")
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao traduzir consulta: {e}")
                    query_for_search = query_text
            
            # Query no ChromaDB com consulta traduzida
            results = self.query(query_for_search, avatar_id, n_results=3)
            
            # Se coleção não foi encontrada
            if results.get("fallback"):
                logger.warning(f"⚠️ Fallback para {avatar_id}: coleção não encontrada")
                return f"Conhecimento não disponível para este avatar ({avatar_id})."
            
            # Se documentos foram encontrados
            documents = results.get("documents", [])
            if documents and len(documents) > 0 and len(documents[0]) > 0:
                # Retornar primeiro documento mais relevante
                response_pt = documents[0][0]
                logger.info(f"✅ Usando RAG: {len(response_pt)} chars retornados")
                
                # ========================================================================
                # TRADUCAO DE RESPOSTA (I18N)
                # ========================================================================
                if I18N_AVAILABLE and original_language != "pt-BR" and response_pt:
                    try:
                        i18n = I18nEngine()
                        i18n.set_language(original_language)
                        # Nota: Resposta já está em PT-BR, retornar como está
                        logger.info(f"🔄 Resposta em {original_language}: {len(response_pt)} chars")
                        return response_pt
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao traduzir resposta: {e}")
                        return response_pt
                
                return response_pt
            else:
                logger.warning(f"⚠️ Nenhum documento relevante encontrado para {avatar_id}")
                return f"Não encontrei informações relevantes sobre '{query_text}' para este avatar."
        
        except Exception as e:
            logger.error(f"❌ Erro ao gerar resposta: {e}", exc_info=True)
            return f"Erro ao processar sua pergunta. Tente novamente."
    
    # ========================================================================
    # FUNÇÕES DE INGESTÃO - BUILD-TIME ONLY
    # ========================================================================
    
    @runtime_only
    def ingest_documents(self, avatar_id: str, documents: List[Dict]) -> int:
        """
        Ingere documentos no ChromaDB
        PROIBIDO em runtime (KNOWLEDGE_MODE=runtime)
        """
        raise RuntimeError("Ingestão proibida em runtime")
    
    @runtime_only
    def create_collection(self, avatar_id: str):
        """
        Cria coleção no ChromaDB
        PROIBIDO em runtime (KNOWLEDGE_MODE=runtime)
        """
        raise RuntimeError("Criação de coleção proibida em runtime")


# ============================================================================
# HEALTH CHECK COM VALIDAÇÃO DE COLEÇÕES
# ============================================================================

def validate_collections() -> Dict:
    """
    Valida que coleções esperadas existem
    Usado em health check
    """
    try:
        import chromadb
        client = chromadb.PersistentClient(path="/app/chroma_db")
        collections = {col.name: col for col in client.list_collections()}
        
        expected = [f"{avatar}_knowledge" for avatar in AvatarRAGEngine.AVATARS]
        missing = [c for c in expected if c not in collections]
        
        if missing:
            logger.warning(f"⚠️ Coleções faltantes: {missing}")
            return {
                "status": "missing_collections",
                "missing": missing,
                "total_expected": len(expected),
                "total_found": len(collections)
            }
        else:
            return {
                "status": "ok",
                "total_collections": len(collections)
            }
    
    except Exception as e:
        logger.error(f"❌ Erro ao validar coleções: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
