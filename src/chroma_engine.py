import chromadb
import json
import os
import logging
import threading
from pathlib import Path
from typing import List, Dict, Optional
import uuid

logger = logging.getLogger(__name__)

# FASE 4: Singleton thread-safe para lazy loading de embeddings
_embedding_model = None
_embedding_model_lock = threading.Lock()

def _get_embedding_model_singleton():
    """Carrega SentenceTransformer sob demanda (thread-safe singleton)"""
    global _embedding_model
    if _embedding_model is None:
        with _embedding_model_lock:
            if _embedding_model is None:
                logger.info("📥 Carregando modelo de embeddings (singleton)...")
                try:
                    from sentence_transformers import SentenceTransformer
                    _embedding_model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L3-v2")
                    logger.info("✅ Modelo de embeddings carregado com sucesso (singleton)")
                except Exception as e:
                    logger.error(f"❌ Erro ao carregar modelo: {e}", exc_info=True)
                    raise
    return _embedding_model

class AvatarRAGEngine:
    """
    Motor de RAG para avatares com parser unificado e contrato de dados
    """
    
    AVATARS = [
        'sofia', 'rafael', 'clara', 'lucas', 'amanda', 'fernanda',
        'marina', 'roberto', 'luisa', 'lais', 'paula', 'bruno',
        'giovana', 'marcos', 'carol', 'english'
    ]
    
    # Mapeamento de pastas com nomes compostos
    AVATAR_FOLDER_MAP = {
        'bruno_giovana': ['bruno', 'giovana'],
        'marcos_carol': ['marcos', 'carol']
    }
    
    def __init__(self, persist_dir: str = "./chroma_db"):
        """
        Inicializa ChromaDB com persistência
        
        Args:
            persist_dir: Diretório para armazenar dados do ChromaDB
        """
        logger.info(f"🔍 ARQUIVO CHROMA EM USO: {__file__}")
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        
        # Configurar ChromaDB com nova API (v0.5+)
        logger.info(f"🔍 Inicializando ChromaDB com PersistentClient...")
        try:
            self.client = chromadb.PersistentClient(
                path=persist_dir,
                settings=chromadb.config.Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            logger.info(f"✅ ChromaDB inicializado com PersistentClient (nova API)")
        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO ao inicializar ChromaDB: {e}", exc_info=True)
            raise ValueError(f"ChromaDB initialization failed: {e}")
        
        # Modelo de embeddings - LAZY LOADING
        self.embedding_model = None
        self._embedding_model_name = 'sentence-transformers/paraphrase-MiniLM-L3-v2'
        logger.info(f"🔍 Embeddings configurados para lazy loading: {self._embedding_model_name}")
        
        # Coleções por avatar
        self.collections = {}
        self._init_collections()
        
        # FASE 2: Carregar documentos de conhecimento com ingestão
        self._load_knowledge_base()
        
        logger.info(f"✅ RAG Engine inicializado com {len(self.AVATARS)} avatares")
        logger.info(f"✅ Embeddings: lazy loading (carregam sob demanda)")
    
    def _get_embedding_model(self):
        """Usa singleton thread-safe para lazy loading"""
        return _get_embedding_model_singleton()
    
    def _init_collections(self):
        """Inicializa coleções ChromaDB para cada avatar"""
        for avatar_id in self.AVATARS:
            collection_name = f"{avatar_id}_knowledge"
            try:
                # Tentar obter coleção existente
                collection = self.client.get_collection(name=collection_name)
                logger.info(f"📦 Coleção existente: {collection_name}")
            except:
                # Criar nova coleção
                collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info(f"✨ Coleção criada: {collection_name}")
            
            self.collections[avatar_id] = collection
    
    def _chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 60) -> List[str]:
        """
        Divide texto em chunks com overlap (300-500 chars, 15% overlap)
        """
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        
        return chunks
    
    def _parse_nucleo_conhecimento(self, nucleo: dict, avatar_id: str, file_name: str) -> List[Dict]:
        """
        Parse flexível para nucleo_conhecimento (aceita strings ou dicts)
        """
        documents = []
        
        # Problemas comuns
        for idx, item in enumerate(nucleo.get('problemas_comuns', [])):
            try:
                if isinstance(item, dict):
                    doc_id = f"{avatar_id}_problema_{idx}_{uuid.uuid4().hex[:8]}"
                    text = f"{item.get('problema', '')} - {item.get('solucao_sugerida', '')}"
                elif isinstance(item, str):
                    doc_id = f"{avatar_id}_problema_{idx}_{uuid.uuid4().hex[:8]}"
                    text = item
                else:
                    continue
                
                if text.strip():
                    documents.append({
                        'id': doc_id,
                        'text': text,
                        'metadata': {'type': 'problema', 'file': file_name}
                    })
            except Exception as e:
                logger.warning(f"⚠️ WARN: Erro ao processar problema_comum em {file_name}: {e}")
        
        # Objeções
        for idx, item in enumerate(nucleo.get('objeções_clientes', [])):
            try:
                if isinstance(item, dict):
                    doc_id = f"{avatar_id}_objecao_{idx}_{uuid.uuid4().hex[:8]}"
                    text = f"{item.get('objecao', '')} - {item.get('resposta', '')}"
                elif isinstance(item, str):
                    doc_id = f"{avatar_id}_objecao_{idx}_{uuid.uuid4().hex[:8]}"
                    text = item
                else:
                    continue
                
                if text.strip():
                    documents.append({
                        'id': doc_id,
                        'text': text,
                        'metadata': {'type': 'objecao', 'file': file_name}
                    })
            except Exception as e:
                logger.warning(f"⚠️ WARN: Erro ao processar objeção em {file_name}: {e}")
        
        # Argumentos de venda
        for idx, item in enumerate(nucleo.get('argumentos_venda', [])):
            try:
                if isinstance(item, dict):
                    doc_id = f"{avatar_id}_argumento_{idx}_{uuid.uuid4().hex[:8]}"
                    text = f"{item.get('argumento', '')} - {item.get('descricao', '')}"
                elif isinstance(item, str):
                    doc_id = f"{avatar_id}_argumento_{idx}_{uuid.uuid4().hex[:8]}"
                    text = item
                else:
                    continue
                
                if text.strip():
                    documents.append({
                        'id': doc_id,
                        'text': text,
                        'metadata': {'type': 'argumento', 'file': file_name}
                    })
            except Exception as e:
                logger.warning(f"⚠️ WARN: Erro ao processar argumento em {file_name}: {e}")
        
        return documents
    
    def _load_knowledge_base(self):
        """FASE 2: Carrega base de conhecimento com parser unificado e ingestão"""
        # Tentar múltiplos caminhos possíveis
        possible_paths = [
            Path("./knowledge"),
            Path("/app/knowledge"),
            Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "knowledge",
        ]
        
        knowledge_dir = None
        for path in possible_paths:
            logger.info(f"🔍 Verificando path: {path.absolute()}")
            if path.exists():
                knowledge_dir = path
                logger.info(f"✅ Encontrado em: {knowledge_dir.absolute()}")
                break
        
        if not knowledge_dir:
            logger.error(f"❌ Diretório de conhecimento NÃO encontrado!")
            logger.error(f"Paths testados: {[str(p.absolute()) for p in possible_paths]}")
            return
        
        logger.info(f"📚 FASE 2: Carregando base de conhecimento de {knowledge_dir.absolute()}")
        
        total_docs_indexed = 0
        
        # Varredura recursiva em /app/knowledge/
        for avatar_dir in knowledge_dir.iterdir():
            if not avatar_dir.is_dir() or avatar_dir.name.startswith('_'):
                continue
            
            folder_name = avatar_dir.name
            
            # Normalizar nomes de pasta (bruno_giovana → bruno + giovana)
            avatar_ids = self.AVATAR_FOLDER_MAP.get(folder_name, [folder_name])
            
            for avatar_id in avatar_ids:
                if avatar_id not in self.AVATARS:
                    logger.warning(f"⚠️ WARN: Avatar {avatar_id} não reconhecido")
                    continue
                
                documents = []
                doc_count = 0
                
                # Carregar todos os arquivos JSON do avatar
                for json_file in avatar_dir.glob("*.json"):
                    # Ignorar arquivos legados
                    if json_file.name in ['embeddings.json', 'estrutura_chunks.json', 'dataset_variacoes.json']:
                        logger.info(f"⏭️ Ignorando arquivo legado: {json_file.name}")
                        continue
                    
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Extrair documentos da estrutura real
                        if isinstance(data, dict):
                            # Estrutura tipo Sofia (items com pergunta/resposta_base)
                            if 'items' in data and isinstance(data['items'], list):
                                logger.info(f"⚠️ WARN: Formato não padronizado em {json_file.name}, adaptando (Sofia format)")
                                for idx, item in enumerate(data['items']):
                                    if isinstance(item, dict):
                                        doc_id = f"{avatar_id}_item_{idx}_{uuid.uuid4().hex[:8]}"
                                        pergunta = item.get('pergunta', '')
                                        resposta = item.get('resposta_base', '')
                                        text = f"{pergunta} - {resposta}"
                                        if text.strip():
                                            documents.append({
                                                'id': doc_id,
                                                'text': text,
                                                'metadata': {'type': 'qa', 'file': json_file.name}
                                            })
                                            doc_count += 1
                            
                            # Extrair FAQ
                            if 'faq_estruturado' in data:
                                logger.info(f"📋 Formato detectado: FAQ estruturado")
                                for idx, faq in enumerate(data['faq_estruturado']):
                                    doc_id = f"{avatar_id}_faq_{idx}_{uuid.uuid4().hex[:8]}"
                                    text = f"{faq.get('pergunta', '')} - {faq.get('resposta', '')}"
                                    if text.strip():
                                        documents.append({
                                            'id': doc_id,
                                            'text': text,
                                            'metadata': {'type': 'faq', 'file': json_file.name}
                                        })
                                        doc_count += 1
                            
                            # Extrair Núcleo de Conhecimento
                            if 'nucleo_conhecimento' in data:
                                logger.info(f"📋 Formato detectado: Núcleo de Conhecimento")
                                nucleo_docs = self._parse_nucleo_conhecimento(
                                    data['nucleo_conhecimento'], 
                                    avatar_id, 
                                    json_file.name
                                )
                                documents.extend(nucleo_docs)
                                doc_count += len(nucleo_docs)
                            
                            # Extrair Áreas Técnicas
                            if 'areas_tecnicas' in data:
                                logger.info(f"📋 Formato detectado: Áreas Técnicas")
                                for idx, area in enumerate(data['areas_tecnicas']):
                                    doc_id = f"{avatar_id}_area_{idx}_{uuid.uuid4().hex[:8]}"
                                    text = area.get('descricao', '')
                                    if text.strip():
                                        documents.append({
                                            'id': doc_id,
                                            'text': text,
                                            'metadata': {'type': 'area_tecnica', 'file': json_file.name}
                                        })
                                        doc_count += 1
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️ WARN: Erro ao decodificar JSON em {json_file.name}: {e}")
                    except Exception as e:
                        logger.warning(f"⚠️ WARN: Erro ao processar {json_file.name}: {e}")
                
                # Limpar coleção existente e recriar (garantir dados frescos)
                collection_name = f"{avatar_id}_knowledge"
                try:
                    self.client.delete_collection(name=collection_name)
                    logger.info(f"🔄 Limpando coleção: {collection_name}")
                except:
                    pass
                
                # Recriar coleção
                collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                self.collections[avatar_id] = collection
                
                # FASE 2: Ingerir documentos com chunking e embeddings
                if documents:
                    logger.info(f"📥 Ingestando {len(documents)} documentos para {avatar_id}...")
                    
                    # Aplicar chunking
                    all_chunks = []
                    for doc in documents:
                        chunks = self._chunk_text(doc['text'], chunk_size=400, overlap=60)
                        for chunk_idx, chunk in enumerate(chunks):
                            all_chunks.append({
                                'id': f"{doc['id']}_chunk_{chunk_idx}",
                                'text': chunk,
                                'metadata': doc['metadata']
                            })
                    
                    # Gerar embeddings e inserir no ChromaDB
                    try:
                        model = self._get_embedding_model()
                        
                        # Preparar dados para inserção
                        ids = [chunk['id'] for chunk in all_chunks]
                        texts = [chunk['text'] for chunk in all_chunks]
                        metadatas = [chunk['metadata'] for chunk in all_chunks]
                        
                        # Gerar embeddings
                        embeddings = model.encode(texts, convert_to_numpy=True)
                        
                        # Inserir no ChromaDB
                        collection.add(
                            ids=ids,
                            embeddings=embeddings.tolist(),
                            documents=texts,
                            metadatas=metadatas
                        )
                        
                        logger.info(f"✅ {avatar_id}: {len(all_chunks)} chunks indexados na coleção {collection_name}")
                        total_docs_indexed += len(all_chunks)
                    
                    except Exception as e:
                        logger.warning(f"⚠️ WARN: Erro ao indexar {avatar_id}: {e}")
                else:
                    logger.warning(f"⚠️ WARN: Nenhum documento encontrado para {avatar_id}")
        
        # Protocolo Rafael
        logger.info(f"📋 Protocolo Rafael: estado PENDING_DATA (aguardando 320 Q&As Genspark)")
        
        logger.info(f"✅ FASE 2 concluída: {total_docs_indexed} chunks indexados no total")
    
    def query(self, query_text: str, avatar_id: str, n_results: int = 3) -> Dict:
        """
        Busca documentos relevantes no ChromaDB
        """
        if avatar_id not in self.collections:
            return {"error": f"Avatar {avatar_id} não encontrado"}
        
        try:
            model = self._get_embedding_model()
            query_embedding = model.encode([query_text], convert_to_numpy=True)[0]
            
            collection = self.collections[avatar_id]
            results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n_results
            )
            
            return {
                "documents": results.get('documents', []),
                "distances": results.get('distances', []),
                "metadatas": results.get('metadatas', [])
            }
        
        except Exception as e:
            logger.error(f"❌ Erro ao buscar em {avatar_id}: {e}")
            return {"error": str(e)}
    
    def generate_response(self, text: str, avatar_id: str, language: str = "pt-BR") -> Dict:
        """
        Gera resposta usando RAG
        """
        logger.info(f"🔍 Query do usuário: {text}")
        logger.info(f"🔍 Avatar ID: {avatar_id}")
        
        # Buscar documentos relevantes
        search_results = self.query(text, avatar_id, n_results=3)
        
        if "error" in search_results:
            logger.warning(f"⚠️ Erro na busca: {search_results['error']}")
            return {"response": f"Desculpe, não consegui encontrar informações sobre isso."}
        
        documents = search_results.get("documents", [])
        distances = search_results.get("distances", [])
        
        if not documents or not documents[0]:
            logger.warning(f"⚠️ Nenhum documento encontrado para {avatar_id}")
            return {"response": f"Desculpe, não tenho informações sobre isso."}
        
        # Usar o documento mais relevante
        best_doc = documents[0][0] if documents[0] else ""
        best_score = 1 - distances[0][0] if distances and distances[0] else 0
        
        logger.info(f"✅ USANDO RAG COM RESULTADOS: {len(documents[0])} documentos encontrados")
        logger.info(f"✅ Score de similaridade: {best_score:.2f}")
        
        if best_score < 0.20:
            logger.warning(f"⚠️ Score baixo ({best_score:.2f}), usando fallback")
            return {"response": f"Desculpe, não tenho uma resposta precisa sobre isso."}
        
        return {"response": best_doc}
