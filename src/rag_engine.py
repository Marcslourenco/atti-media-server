"""
RAG Engine - Retrieval Augmented Generation
Busca conhecimento na base de dados e gera respostas contextuais
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger("humanos-digitais-tts-rag-llm")

class RAGEngine:
    def __init__(self):
        self.knowledge_dir = Path("./knowledge")
        self.knowledge_blocks = {}
        self.avatar_knowledge = {}
        self.load_knowledge()
    
    def load_knowledge(self):
        """Carrega base de conhecimento dos avatares"""
        try:
            if not self.knowledge_dir.exists():
                logger.warning(f"Diretório de conhecimento não encontrado: {self.knowledge_dir}")
                return
            
            # Carregar knowledge_blocks.json se existir
            blocks_file = self.knowledge_dir / "knowledge_blocks.json"
            if blocks_file.exists():
                with open(blocks_file, 'r', encoding='utf-8') as f:
                    self.knowledge_blocks = json.load(f)
                logger.info(f"Carregados {len(self.knowledge_blocks)} blocos de conhecimento")
            
            # Carregar conhecimento específico de cada avatar
            for avatar_dir in self.knowledge_dir.iterdir():
                if avatar_dir.is_dir() and not avatar_dir.name.startswith('_'):
                    avatar_id = avatar_dir.name
                    avatar_knowledge = []
                    
                    # Carregar todos os arquivos JSON do avatar
                    for json_file in avatar_dir.glob("*.json"):
                        try:
                            with open(json_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                if isinstance(data, list):
                                    avatar_knowledge.extend(data)
                                elif isinstance(data, dict):
                                    avatar_knowledge.append(data)
                        except Exception as e:
                            logger.warning(f"Erro ao carregar {json_file}: {e}")
                    
                    if avatar_knowledge:
                        self.avatar_knowledge[avatar_id] = avatar_knowledge
                        logger.info(f"Avatar {avatar_id}: {len(avatar_knowledge)} itens de conhecimento")
            
            logger.info("RAG inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao carregar conhecimento: {e}")
    
    def generate_response(self, text: str, avatar_id: str = None, language: str = "pt-BR") -> str:
        """
        Gera resposta contextual baseada na pergunta e conhecimento do avatar
        
        Args:
            text: Pergunta do usuário
            avatar_id: ID do avatar (para contexto específico)
            language: Idioma
        
        Returns:
            Resposta gerada
        """
        try:
            logger.info("=" * 60)
            logger.info("🔍 RAG GENERATE_RESPONSE - INICIO")
            logger.info(f"🔍 Query: {text}")
            logger.info(f"🔍 Avatar ID: {avatar_id}")
            logger.info(f"🔍 Language: {language}")
            logger.info(f"🔍 Avatar knowledge carregado: {len(self.avatar_knowledge)} avatares")
            logger.info(f"🔍 Knowledge blocks carregado: {len(self.knowledge_blocks)} blocos")
            
            # Se não há conhecimento, retornar resposta padrão
            if not self.avatar_knowledge and not self.knowledge_blocks:
                logger.warning("🔍 Nenhuma base de conhecimento carregada, retornando eco")
                logger.info("=" * 60)
                return text
            
            # Buscar conhecimento relevante
            logger.info("🔍 Iniciando busca de conhecimento relevante...")
            relevant_knowledge = self._search_relevant_knowledge(text, avatar_id, language)
            logger.info(f"🔍 Busca concluída: {len(relevant_knowledge)} itens encontrados")
            
            # Gerar resposta baseada no conhecimento
            logger.info("🔍 Iniciando geração de resposta...")
            response = self._generate_from_knowledge(text, relevant_knowledge, avatar_id, language)
            logger.info(f"🔍 Resposta gerada: {response[:100]}...")
            logger.info("🔍 RAG GENERATE_RESPONSE - FIM")
            logger.info("=" * 60)
            
            return response
        except Exception as e:
            logger.error(f"🔍 ERRO ao gerar resposta: {e}", exc_info=True)
            logger.info("=" * 60)
            return text
    
    def _search_relevant_knowledge(self, text: str, avatar_id: str = None, language: str = "pt-BR"):
        """Busca conhecimento relevante para a pergunta"""
        relevant = []
        
        logger.info(f"🔍 RAG SEARCH - Buscando conhecimento para query: '{text[:80]}'")
        logger.info(f"🔍 RAG SEARCH - Avatar ID: {avatar_id}")
        logger.info(f"🔍 RAG SEARCH - Avatar knowledge disponível: {list(self.avatar_knowledge.keys())}")
        
        # Buscar em conhecimento específico do avatar
        if avatar_id and avatar_id in self.avatar_knowledge:
            avatar_data = self.avatar_knowledge[avatar_id]
            logger.info(f"🔍 RAG SEARCH - Buscando em conhecimento específico de {avatar_id} ({len(avatar_data)} itens)")
            for idx, item in enumerate(avatar_data):
                if self._is_relevant(text, item):
                    logger.info(f"🔍 RAG SEARCH - Item {idx} é relevante")
                    relevant.append(item)
        
        logger.info(f"🔍 RAG SEARCH - Encontrados {len(relevant)} itens relevantes no avatar específico")
        
        # Se não encontrou, buscar em todos os avatares
        if not relevant:
            logger.info(f"🔍 RAG SEARCH - Nenhum item encontrado, buscando em todos os avatares")
            for avatar_id_key, avatar_data in self.avatar_knowledge.items():
                logger.info(f"🔍 RAG SEARCH - Buscando em {avatar_id_key} ({len(avatar_data)} itens)")
                for item in avatar_data:
                    if self._is_relevant(text, item):
                        relevant.append(item)
                        logger.info(f"🔍 RAG SEARCH - Item encontrado em {avatar_id_key}")
                        if len(relevant) >= 3:  # Limitar a 3 itens
                            break
        
        logger.info(f"🔍 RAG SEARCH - Retornando {len(relevant[:3])} itens relevantes")
        return relevant[:3]  # Retornar top 3
    
    def _is_relevant(self, query: str, item) -> bool:
        """Verifica se um item de conhecimento é relevante para a query"""
        query_lower = query.lower()
        
        if isinstance(item, dict):
            # Buscar em todos os valores do dicionário
            for key, value in item.items():
                if isinstance(value, str):
                    if any(word in value.lower() for word in query_lower.split()):
                        return True
        elif isinstance(item, str):
            if any(word in item.lower() for word in query_lower.split()):
                return True
        
        return False
    
    def _generate_from_knowledge(self, query: str, knowledge: list, avatar_id: str = None, language: str = "pt-BR") -> str:
        """Gera resposta baseada no conhecimento encontrado - ESTRUTURA REAL"""
        
        logger.info(f"🔍 RAG GENERATE - Gerando resposta com {len(knowledge)} itens de conhecimento")
        logger.info(f"🔍 RAG GENERATE - Query: {query[:80]}")
        
        # Se não há conhecimento relevante, usar resposta padrão
        if not knowledge:
            logger.info(f"🔍 RAG GENERATE - Nenhum conhecimento, usando resposta padrão")
            return self._get_default_response(query, avatar_id, language)
        
        resposta_partes = []
        query_lower = query.lower()
        
        for idx, item in enumerate(knowledge):
            logger.info(f"🔍 RAG GENERATE - Processando item {idx}: tipo={type(item).__name__}")
            
            if not isinstance(item, dict):
                logger.info(f"🔍 RAG GENERATE - Item {idx} não é dicionário, pulando")
                continue
            
            logger.info(f"🔍 RAG GENERATE - Chaves disponíveis: {list(item.keys())}")
            
            # 1. FAQ estruturado (prioridade máxima)
            if 'faq_estruturado' in item:
                logger.info(f"🔍 RAG GENERATE - Buscando em faq_estruturado ({len(item['faq_estruturado'])} itens)")
                for faq in item['faq_estruturado']:
                    pergunta = faq.get('pergunta', '').lower()
                    # Busca por palavras-chave com comprimento > 3
                    if any(word in pergunta for word in query_lower.split() if len(word) > 3):
                        resposta = faq.get('resposta', '')
                        if resposta:
                            logger.info(f"🔍 RAG GENERATE - FAQ encontrado: {resposta[:80]}")
                            resposta_partes.append(resposta)
            
            # 2. Buscar em nucleo_conhecimento
            if 'nucleo_conhecimento' in item:
                logger.info(f"🔍 RAG GENERATE - Buscando em nucleo_conhecimento")
                nucleo = item['nucleo_conhecimento']
                
                # Problemas comuns
                for problema in nucleo.get('problemas_comuns', []):
                    texto = problema.get('problema', '').lower()
                    if any(word in texto for word in query_lower.split() if len(word) > 3):
                        solucao = problema.get('solucao_sugerida', '')
                        if solucao:
                            logger.info(f"🔍 RAG GENERATE - Problema comum encontrado: {solucao[:80]}")
                            resposta_partes.append(solucao)
                
                # Objeções de clientes
                for objecao in nucleo.get('objeções_clientes', []):
                    texto = objecao.get('objecao', '').lower()
                    if any(word in texto for word in query_lower.split() if len(word) > 3):
                        resposta = objecao.get('resposta', '')
                        if resposta:
                            logger.info(f"🔍 RAG GENERATE - Objeção encontrada: {resposta[:80]}")
                            resposta_partes.append(resposta)
                
                # Argumentos de venda
                for arg in nucleo.get('argumentos_venda', []):
                    texto = arg.get('argumento', '').lower()
                    if any(word in texto for word in query_lower.split() if len(word) > 3):
                        descricao = arg.get('descricao', '')
                        if descricao:
                            logger.info(f"🔍 RAG GENERATE - Argumento encontrado: {descricao[:80]}")
                            resposta_partes.append(descricao)
            
            # 3. Buscar em areas_tecnicas
            if 'areas_tecnicas' in item:
                logger.info(f"🔍 RAG GENERATE - Buscando em areas_tecnicas ({len(item['areas_tecnicas'])} áreas)")
                for area in item['areas_tecnicas']:
                    if 'detalhes' in area:
                        for key, val in area['detalhes'].items():
                            if isinstance(val, dict):
                                texto = str(val.get('descricao', '')).lower()
                                if any(word in texto for word in query_lower.split() if len(word) > 3):
                                    descricao = val.get('descricao', '')
                                    if descricao:
                                        logger.info(f"🔍 RAG GENERATE - Área técnica encontrada: {descricao[:80]}")
                                        resposta_partes.append(descricao)
            
            # 4. Fallback: descrição do avatar
            if 'descricao' in item and not resposta_partes:
                logger.info(f"🔍 RAG GENERATE - Usando descrição como fallback")
                resposta_partes.append(item['descricao'])
        
        logger.info(f"🔍 RAG GENERATE - Extraídas {len(resposta_partes)} partes de resposta")
        
        if resposta_partes:
            # Limitar a 3 partes e juntar
            response = " ".join(resposta_partes[:3])
            logger.info(f"🔍 RAG GENERATE - Resposta final: {response[:150]}...")
            return response
        
        logger.info(f"🔍 RAG GENERATE - Nenhuma parte de resposta extraída, usando padrão")
        return self._get_default_response(query, avatar_id, language)
    
    def _get_default_response(self, query: str, avatar_id: str = None, language: str = "pt-BR") -> str:
        """Retorna resposta padrão baseada no avatar"""
        
        avatar_responses = {
            "sofia": {
                "pt-BR": "Sou a Sofia, assistente de inteligência artificial. Estou aqui para conversar e ajudar com informações sobre humanos digitais.",
                "en": "I'm Sofia, an AI assistant. I'm here to chat and help with information about digital humans.",
            },
            "lucas": {
                "pt-BR": "Olá, sou Lucas, especialista em vendas de veículos. Como posso ajudá-lo?",
                "en": "Hello, I'm Lucas, a vehicle sales specialist. How can I help you?",
            },
            "rafael": {
                "pt-BR": "Oi, sou Rafael, especialista tributário. Posso ajudá-lo com questões fiscais.",
                "en": "Hi, I'm Rafael, a tax specialist. I can help you with tax questions.",
            },
            "clara": {
                "pt-BR": "Olá, sou Clara, consultora hospitalar. Estou aqui para ajudar com informações sobre saúde.",
                "en": "Hello, I'm Clara, a hospital consultant. I'm here to help with health information.",
            },
        }
        
        if avatar_id and avatar_id in avatar_responses:
            return avatar_responses[avatar_id].get(language, avatar_responses[avatar_id].get("pt-BR", query))
        
        return query  # Fallback: retornar a pergunta original


# Instância global
rag_engine = RAGEngine()
