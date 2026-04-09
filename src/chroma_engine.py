import chromadb
import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
import uuid

logger = logging.getLogger(__name__)

class AvatarRAGEngine:
    """
    Motor de RAG para avatares com suporte a múltiplos formatos de dados
    """
    
    AVATARS = [
        'sofia', 'rafael', 'clara', 'lucas', 'amanda', 'fernanda',
        'marina', 'roberto', 'luisa', 'lais', 'paula', 'bruno',
        'giovana', 'marcos', 'carol', 'english'
    ]
    
    def __init__(self, persist_dir: str = "./chroma_db"):
        """
        Inicializa ChromaDB com persistência
        
        Args:
            persist_dir: Diretório para armazenar dados do ChromaDB
        """
        logger.info(f"🔍 ARQUIVO CHROMA EM USO: {__file__}")
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        
        # Configurar ChromaDB com nova API (v0.5+) - SEM FALLBACK
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
            logger.error(f"❌ ChromaDB NÃO será inicializado. Verifique a versão e configuração.")
            raise ValueError(f"ChromaDB initialization failed: {e}")
        
        # Modelo de embeddings - LAZY LOADING (carrega sob demanda)
        self.embedding_model = None
        self._embedding_model_name = 'sentence-transformers/paraphrase-MiniLM-L3-v2'
        logger.info(f"🔍 Embeddings configurados para lazy loading: {self._embedding_model_name}")
        
        # Coleções por avatar
        self.collections = {}
        self._init_collections()
        
        # Carregar documentos de conhecimento
        self._load_knowledge_base()
        
        logger.info(f"✅ RAG Engine inicializado com {len(self.AVATARS)} avatares")
        logger.info(f"✅ Embeddings serão carregados sob demanda (lazy loading)")
    
    
    def _get_embedding_model(self):
        """Carrega SentenceTransformer sob demanda (lazy loading)"""
        if self.embedding_model is None:
            logger.info(f"📥 Carregando modelo de embeddings: {self._embedding_model_name}")
            try:
                self.embedding_model = SentenceTransformer(self._embedding_model_name)
                logger.info(f"✅ Modelo de embeddings carregado com sucesso")
            except Exception as e:
                logger.error(f"❌ Erro ao carregar modelo: {e}", exc_info=True)
                raise
        return self.embedding_model
    
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
        Divide texto em chunks com overlap
        
        Args:
            text: Texto a dividir
            chunk_size: Tamanho máximo do chunk
            overlap: Tamanho do overlap entre chunks
        
        Returns:
            Lista de chunks
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
                    doc_id = f"{avatar_id}_problema_{idx}"
                    text = f"{item.get('problema', '')} - {item.get('solucao_sugerida', '')}"
                elif isinstance(item, str):
                    doc_id = f"{avatar_id}_problema_{idx}"
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
                logger.warning(f"⚠️ Erro ao processar problema_comum em {file_name}: {e}")
        
        # Objeções
        for idx, item in enumerate(nucleo.get('objeções_clientes', [])):
            try:
                if isinstance(item, dict):
                    doc_id = f"{avatar_id}_objecao_{idx}"
                    text = f"{item.get('objecao', '')} - {item.get('resposta', '')}"
                elif isinstance(item, str):
                    doc_id = f"{avatar_id}_objecao_{idx}"
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
                logger.warning(f"⚠️ Erro ao processar objeção em {file_name}: {e}")
        
        # Argumentos de venda
        for idx, item in enumerate(nucleo.get('argumentos_venda', [])):
            try:
                if isinstance(item, dict):
                    doc_id = f"{avatar_id}_argumento_{idx}"
                    text = f"{item.get('argumento', '')} - {item.get('descricao', '')}"
                elif isinstance(item, str):
                    doc_id = f"{avatar_id}_argumento_{idx}"
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
                logger.warning(f"⚠️ Erro ao processar argumento em {file_name}: {e}")
        
        return documents
    
    def _load_knowledge_base(self):
        """Carrega base de conhecimento dos arquivos JSON com parser unificado"""
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
        
        logger.info(f"📚 Carregando base de conhecimento de {knowledge_dir.absolute()}")
        
        for avatar_dir in knowledge_dir.iterdir():
            if not avatar_dir.is_dir() or avatar_dir.name.startswith('_'):
                continue
            
            avatar_id = avatar_dir.name
            if avatar_id not in self.AVATARS:
                logger.warning(f"⚠️ Avatar {avatar_id} não reconhecido")
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
                            logger.info(f"📋 Formato detectado: Sofia (items)")
                            for idx, item in enumerate(data['items']):
                                if isinstance(item, dict):
                                    doc_id = f"{avatar_id}_item_{idx}"
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
                                doc_id = f"{avatar_id}_faq_{idx}"
                                text = f"{faq.get('pergunta', '')} - {faq.get('resposta', '')}"
                                if text.strip():
                                    documents.append({
                                        'id': doc_id,
                                        'text': text,
                                        'metadata': {'type': 'faq', 'file': json_file.name}
                                    })
                                    doc_count += 1
                        
                        # Extrair núcleo de conhecimento
                        if 'nucleo_conhecimento' in data:
                            logger.info(f"📋 Formato detectado: Núcleo de conhecimento")
                            nucleo_docs = self._parse_nucleo_conhecimento(
                                data['nucleo_conhecimento'],
                                avatar_id,
                                json_file.name
                            )
                            documents.extend(nucleo_docs)
                            doc_count += len(nucleo_docs)
                        
                        # Extrair áreas técnicas
                        if 'areas_tecnicas' in data:
                            logger.info(f"📋 Formato detectado: Áreas técnicas")
                            for area_idx, area in enumerate(data['areas_tecnicas']):
                                if 'detalhes' in area:
                                    for detail_key, detail_val in area['detalhes'].items():
                                        if isinstance(detail_val, dict):
                                            doc_id = f"{avatar_id}_area_{area_idx}_{detail_key}"
                                            text = detail_val.get('descricao', '')
                                            if text.strip():
                                                documents.append({
                                                    'id': doc_id,
                                                    'text': text,
                                                    'metadata': {'type': 'area_tecnica', 'file': json_file.name}
                                                })
                                                doc_count += 1
                
                except Exception as e:
                    logger.warning(f"⚠️ WARN: Erro ao carregar {json_file.name}: {e}")
            
            # Adicionar documentos ao ChromaDB
            if documents:
                try:
                    self.add_documents(avatar_id, documents)
                    logger.info(f"✅ Avatar {avatar_id}: {doc_count} documentos indexados na coleção {avatar_id}_knowledge")
                except Exception as e:
                    logger.error(f"❌ Erro ao adicionar documentos para {avatar_id}: {e}", exc_info=True)
            else:
                logger.warning(f"⚠️ Nenhum documento encontrado para {avatar_id}")
    
    def add_documents(self, avatar_id: str, documents: List[Dict[str, str]]):
        """
        Adiciona documentos à base de conhecimento de um avatar
        
        Args:
            avatar_id: ID do avatar
            documents: Lista de documentos com 'id', 'text', 'metadata'
        """
        if avatar_id not in self.collections:
            raise ValueError(f"Avatar {avatar_id} não encontrado")
        
        collection = self.collections[avatar_id]
        
        # Chunking: dividir textos longos
        chunked_documents = []
        for doc in documents:
            chunks = self._chunk_text(doc['text'])
            for chunk_idx, chunk in enumerate(chunks):
                chunked_documents.append({
                    'id': f"{doc['id']}_chunk_{chunk_idx}",
                    'text': chunk,
                    'metadata': {**doc.get('metadata', {}), 'chunk': chunk_idx}
                })
        
        # Extrair textos e embeddings
        texts = [doc['text'] for doc in chunked_documents]
        embeddings = self._get_embedding_model().encode(texts).tolist()
        
        # Adicionar ao ChromaDB
        collection.add(
            ids=[doc['id'] for doc in chunked_documents],
            embeddings=embeddings,
            documents=texts,
            metadatas=[doc.get('metadata', {}) for doc in chunked_documents]
        )
        
        logger.info(f"✅ {len(chunked_documents)} chunks adicionados para {avatar_id}")
    
    def query(self, avatar_id: str, query_text: str, top_k: int = 5) -> List[Dict]:
        """
        Busca documentos relevantes na base de conhecimento de um avatar
        
        Args:
            avatar_id: ID do avatar
            query_text: Texto da busca
            top_k: Número de resultados
            
        Returns:
            Lista de documentos relevantes com scores
        """
        if avatar_id not in self.collections:
            raise ValueError(f"Avatar {avatar_id} não encontrado")
        
        collection = self.collections[avatar_id]
        
        # Gerar embedding da query
        query_embedding = self._get_embedding_model().encode([query_text])[0].tolist()
        
        # Buscar no ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Formatar resultados
        documents = []
        if results and results['documents'] and len(results['documents']) > 0:
            for idx, (doc, distance, metadata) in enumerate(zip(
                results['documents'][0],
                results['distances'][0],
                results['metadatas'][0]
            )):
                # ChromaDB retorna distância, converter para similaridade
                similarity = 1 - distance
                documents.append({
                    'id': results['ids'][0][idx],
                    'text': doc,
                    'score': similarity,
                    'metadata': metadata
                })
        
        return documents
    
    def generate_response(self, query_text: str, avatar_id: str, language: str = 'pt-BR') -> str:
        """
        Gera resposta usando RAG
        
        Args:
            query_text: Pergunta do usuário
            avatar_id: ID do avatar
            language: Idioma da resposta
        
        Returns:
            Resposta gerada
        """
        try:
            # Buscar documentos relevantes
            documents = self.query(avatar_id, query_text, top_k=3)
            
            if documents and documents[0]['score'] > 0.20:
                logger.info(f"✅ USANDO RAG COM RESULTADOS: {len(documents)} documentos encontrados")
                # Retornar o documento mais relevante
                return documents[0]['text']
            else:
                logger.info(f"⚠️ RAG: Nenhum documento com score > 0.20")
                return None
        
        except Exception as e:
            logger.error(f"❌ Erro no RAG: {e}", exc_info=True)
            return None
