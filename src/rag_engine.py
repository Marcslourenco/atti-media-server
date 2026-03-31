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
            # Se não há conhecimento, retornar resposta padrão
            if not self.avatar_knowledge and not self.knowledge_blocks:
                logger.warning("Nenhuma base de conhecimento carregada, retornando eco")
                return text
            
            # Buscar conhecimento relevante
            relevant_knowledge = self._search_relevant_knowledge(text, avatar_id, language)
            
            # Gerar resposta baseada no conhecimento
            response = self._generate_from_knowledge(text, relevant_knowledge, avatar_id, language)
            
            return response
        except Exception as e:
            logger.error(f"Erro ao gerar resposta: {e}")
            return text
    
    def _search_relevant_knowledge(self, text: str, avatar_id: str = None, language: str = "pt-BR"):
        """Busca conhecimento relevante para a pergunta"""
        relevant = []
        
        # Buscar em conhecimento específico do avatar
        if avatar_id and avatar_id in self.avatar_knowledge:
            avatar_data = self.avatar_knowledge[avatar_id]
            for item in avatar_data:
                if self._is_relevant(text, item):
                    relevant.append(item)
        
        # Se não encontrou, buscar em todos os avatares
        if not relevant:
            for avatar_id_key, avatar_data in self.avatar_knowledge.items():
                for item in avatar_data:
                    if self._is_relevant(text, item):
                        relevant.append(item)
                        if len(relevant) >= 3:  # Limitar a 3 itens
                            break
        
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
        """Gera resposta baseada no conhecimento encontrado"""
        
        # Se não há conhecimento relevante, usar resposta padrão
        if not knowledge:
            return self._get_default_response(query, avatar_id, language)
        
        # Construir resposta a partir do conhecimento
        response_parts = []
        
        for item in knowledge:
            if isinstance(item, dict):
                # Procurar por campos de resposta
                for key in ['answer', 'response', 'description', 'content', 'text']:
                    if key in item and isinstance(item[key], str):
                        response_parts.append(item[key])
                        break
            elif isinstance(item, str):
                response_parts.append(item)
        
        if response_parts:
            # Combinar respostas
            response = " ".join(response_parts[:2])  # Limitar a 2 respostas
            return response[:200]  # Limitar comprimento
        
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
