"""
ChromaDB RAG Engine para Avatares ATTI

Suporta 16 avatares com bases de conhecimento especializadas.
"""

import os
import json
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)


class AvatarRAGEngine:
    """Engine RAG com ChromaDB para cada avatar"""
    
    AVATARS = {
        "sofia": {
            "name": "Sofia",
            "specialty": "Host Completa",
            "description": "Avatar host com acesso a todas as ferramentas",
            "color": "#FF6B6B"
        },
        "rafael": {
            "name": "Rafael",
            "specialty": "Tributário",
            "description": "Especialista em legislação tributária (800+ Q&A)",
            "color": "#4ECDC4"
        },
        "clara": {
            "name": "Clara",
            "specialty": "Saúde",
            "description": "Consultora em saúde e bem-estar",
            "color": "#95E1D3"
        },
        "lucas": {
            "name": "Lucas",
            "specialty": "Educação",
            "description": "Especialista em educação e treinamento",
            "color": "#F38181"
        },
        "amanda": {
            "name": "Amanda",
            "specialty": "RH",
            "description": "Consultora em recursos humanos",
            "color": "#AA96DA"
        },
        "fernanda": {
            "name": "Fernanda",
            "specialty": "Financeiro",
            "description": "Analista financeira",
            "color": "#FCBAD3"
        },
        "marina": {
            "name": "Marina",
            "specialty": "Marketing",
            "description": "Estrategista de marketing",
            "color": "#A8D8EA"
        },
        "roberto": {
            "name": "Roberto",
            "specialty": "Operações",
            "description": "Gerente de operações",
            "color": "#AA96DA"
        },
        "luisa": {
            "name": "Luisa",
            "specialty": "Jurídico",
            "description": "Consultora jurídica",
            "color": "#FFD3B6"
        },
        "lais": {
            "name": "Lais",
            "specialty": "Tecnologia",
            "description": "Especialista em tecnologia",
            "color": "#FFAAA5"
        },
        "paula": {
            "name": "Paula",
            "specialty": "Sustentabilidade",
            "description": "Consultora em sustentabilidade",
            "color": "#FF8B94"
        },
        "bruno": {
            "name": "Bruno",
            "specialty": "Vendas",
            "description": "Especialista em vendas",
            "color": "#A8E6CF"
        },
        "giovana": {
            "name": "Giovana",
            "specialty": "Atendimento",
            "description": "Especialista em atendimento ao cliente",
            "color": "#FFD3B6"
        },
        "marcos": {
            "name": "Marcos",
            "specialty": "Estratégia",
            "description": "Consultor estratégico",
            "color": "#FFAAA5"
        },
        "carol": {
            "name": "Carol",
            "specialty": "Inovação",
            "description": "Especialista em inovação",
            "color": "#FF8B94"
        },
        "english": {
            "name": "English",
            "specialty": "Multilíngue",
            "description": "Avatar multilíngue",
            "color": "#A8E6CF"
        }
    }
    
    def __init__(self, persist_dir: str = "./chroma_db"):
        """
        Inicializa ChromaDB com persistência
        
        Args:
            persist_dir: Diretório para armazenar dados do ChromaDB
        """
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        
        # Configurar ChromaDB com persistência
        settings = Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_dir,
            anonymized_telemetry=False
        )
        
        self.client = chromadb.Client(settings)
        
        # Modelo de embeddings
        self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        
        # Coleções por avatar
        self.collections = {}
        self._init_collections()
        
        logger.info(f"✅ RAG Engine inicializado com {len(self.AVATARS)} avatares")
    
    def _init_collections(self):
        """Inicializa coleções ChromaDB para cada avatar"""
        for avatar_id in self.AVATARS.keys():
            collection_name = f"{avatar_id}_knowledge"
            
            try:
                # Tenta obter coleção existente
                collection = self.client.get_collection(name=collection_name)
                logger.info(f"✅ Coleção {collection_name} carregada")
            except:
                # Cria nova coleção
                collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"avatar": avatar_id}
                )
                logger.info(f"✅ Coleção {collection_name} criada")
            
            self.collections[avatar_id] = collection
    
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
        
        # Extrair textos e embeddings
        texts = [doc['text'] for doc in documents]
        embeddings = self.embedding_model.encode(texts).tolist()
        
        # Adicionar ao ChromaDB
        collection.add(
            ids=[doc['id'] for doc in documents],
            embeddings=embeddings,
            documents=texts,
            metadatas=[doc.get('metadata', {}) for doc in documents]
        )
        
        logger.info(f"✅ {len(documents)} documentos adicionados para {avatar_id}")
    
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
        query_embedding = self.embedding_model.encode([query_text])[0].tolist()
        
        # Buscar no ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Formatar resultados
        formatted_results = []
        if results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': doc,
                    'distance': results['distances'][0][i],
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                })
        
        return formatted_results
    
    def generate_response(self, query_text: str, avatar_id: str = None, language: str = "pt-BR") -> str:
        """
        Gera resposta inteligente baseada em busca vetorial (ChromaDB)
        
        Args:
            query_text: Pergunta do usuário
            avatar_id: ID do avatar (opcional)
            language: Idioma (pt-BR, en, es)
        
        Returns:
            Resposta gerada baseada na base de conhecimento
        """
        try:
            # Se avatar_id não fornecido, usar sofia como padrão
            if not avatar_id or avatar_id not in self.AVATARS:
                avatar_id = "sofia"
            
            logger.info(f"✅ CHROMA_ENGINE.generate_response() chamado")
            logger.info(f"✅ Query: {query_text[:100]}")
            logger.info(f"✅ Avatar: {avatar_id}")
            logger.info(f"✅ Language: {language}")
            
            # Buscar documentos relevantes usando embeddings
            results = self.query(avatar_id, query_text, top_k=3)
            
            logger.info(f"✅ ChromaDB retornou {len(results)} resultados")
            
            if not results:
                logger.warning(f"⚠️ Nenhum resultado encontrado, usando resposta padrão")
                return self._get_default_response(avatar_id, language)
            
            # Combinar os resultados em uma resposta
            response_parts = []
            for result in results:
                text = result.get('text', '')
                score = result.get('distance', 1.0)
                
                # Apenas incluir resultados com score bom (distância pequena)
                if score < 0.7 and text:
                    logger.info(f"✅ Incluindo resultado: {text[:80]}... (score: {score:.3f})")
                    response_parts.append(text)
            
            if response_parts:
                # Combinar até 2 partes
                response = " ".join(response_parts[:2])
                logger.info(f"✅ Resposta gerada: {response[:100]}...")
                return response
            else:
                logger.warning(f"⚠️ Nenhum resultado com score bom, usando resposta padrão")
                return self._get_default_response(avatar_id, language)
                
        except Exception as e:
            logger.error(f"❌ ERRO em generate_response: {e}", exc_info=True)
            return self._get_default_response(avatar_id or "sofia", language)
    
    def _get_default_response(self, avatar_id: str, language: str = "pt-BR") -> str:
        """Retorna resposta padrão do avatar"""
        avatar_info = self.AVATARS.get(avatar_id, self.AVATARS["sofia"])
        
        default_responses = {
            "pt-BR": f"Olá, sou {avatar_info['name']}, {avatar_info['specialty'].lower()}. {avatar_info['description']}",
            "en": f"Hello, I'm {avatar_info['name']}, {avatar_info['specialty'].lower()}. {avatar_info['description']}",
            "es": f"Hola, soy {avatar_info['name']}, {avatar_info['specialty'].lower()}. {avatar_info['description']}"
        }
        
        return default_responses.get(language, default_responses["pt-BR"])
    
    def get_avatar_info(self, avatar_id: str) -> Dict:
        """Retorna informações do avatar"""
        if avatar_id not in self.AVATARS:
            raise ValueError(f"Avatar {avatar_id} não encontrado")
        
        avatar = self.AVATARS[avatar_id]
        collection = self.collections.get(avatar_id)
        
        # Contar documentos
        doc_count = 0
        if collection:
            try:
                doc_count = collection.count()
            except:
                pass
        
        return {
            **avatar,
            'id': avatar_id,
            'documents_count': doc_count
        }
    
    def list_avatars(self) -> List[Dict]:
        """Lista todos os avatares com informações"""
        return [self.get_avatar_info(avatar_id) for avatar_id in self.AVATARS.keys()]
    
    def export_collection(self, avatar_id: str, output_file: str):
        """Exporta coleção para JSON"""
        if avatar_id not in self.collections:
            raise ValueError(f"Avatar {avatar_id} não encontrado")
        
        collection = self.collections[avatar_id]
        
        # Obter todos os dados
        all_data = collection.get()
        
        # Salvar em JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Coleção {avatar_id} exportada para {output_file}")
    
    def import_collection(self, avatar_id: str, input_file: str):
        """Importa coleção de JSON"""
        if avatar_id not in self.collections:
            raise ValueError(f"Avatar {avatar_id} não encontrado")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        collection = self.collections[avatar_id]
        
        # Adicionar dados
        collection.add(
            ids=data['ids'],
            documents=data['documents'],
            embeddings=data['embeddings'],
            metadatas=data['metadatas']
        )
        
        logger.info(f"✅ Coleção {avatar_id} importada de {input_file}")


if __name__ == "__main__":
    # Teste
    logging.basicConfig(level=logging.INFO)
    
    engine = AvatarRAGEngine()
    
    # Listar avatares
    print("\n📋 Avatares Disponíveis:")
    for avatar in engine.list_avatars():
        print(f"  - {avatar['name']} ({avatar['specialty']}): {avatar['documents_count']} docs")
    
    # Adicionar documentos de teste
    print("\n➕ Adicionando documentos de teste...")
    test_docs = [
        {
            'id': 'rafael_001',
            'text': 'A reforma tributária 2026 introduz novas alíquotas de ICMS',
            'metadata': {'source': 'legislacao', 'year': 2026}
        },
        {
            'id': 'rafael_002',
            'text': 'Contribuintes devem se registrar no novo sistema até 31 de março',
            'metadata': {'source': 'regulamento', 'deadline': '2026-03-31'}
        }
    ]
    
    engine.add_documents('rafael', test_docs)
    
    # Testar busca
    print("\n🔍 Testando busca...")
    results = engine.query('rafael', 'reforma tributária', top_k=2)
    for result in results:
        print(f"  - {result['text']} (score: {result['distance']:.3f})")
