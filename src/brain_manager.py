import os
import json
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BrainManager:
    """Gerenciador de prompts do sistema (brain files) para cada avatar"""
    
    def __init__(self, knowledge_dir: str = "./knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.prompts_cache = {}
        self._load_all_prompts()
    
    def _load_all_prompts(self):
        """Carrega todos os system prompts na inicialização"""
        logger.info("[BrainManager] Iniciando carregamento de prompts...")
        
        if not self.knowledge_dir.exists():
            logger.warning(f"[BrainManager] Diretório {self.knowledge_dir} não encontrado")
            return
        
        # Procura por todos os avatares
        for avatar_dir in self.knowledge_dir.iterdir():
            if not avatar_dir.is_dir():
                continue
            
            avatar_id = avatar_dir.name
            prompts_dir = avatar_dir / "prompts"
            
            if not prompts_dir.exists():
                logger.warning(f"[BrainManager] Diretório prompts não encontrado para {avatar_id}")
                continue
            
            # Carrega system_prompt.txt
            system_prompt_file = prompts_dir / "system_prompt.txt"
            if system_prompt_file.exists():
                try:
                    with open(system_prompt_file, 'r', encoding='utf-8') as f:
                        prompt = f.read().strip()
                    self.prompts_cache[avatar_id] = prompt
                    logger.info(f"[BrainManager] ✅ {avatar_id}: {len(prompt)} caracteres carregados")
                except Exception as e:
                    logger.error(f"[BrainManager] ❌ Erro ao carregar {avatar_id}: {e}")
            else:
                logger.warning(f"[BrainManager] system_prompt.txt não encontrado para {avatar_id}")
        
        logger.info(f"[BrainManager] Total de avatares com prompts: {len(self.prompts_cache)}")
    
    def get_system_prompt(self, avatar_id: str) -> str:
        """Retorna o system prompt de um avatar"""
        if avatar_id in self.prompts_cache:
            return self.prompts_cache[avatar_id]
        
        # Fallback: prompt genérico
        logger.warning(f"[BrainManager] Prompt não encontrado para {avatar_id}, usando fallback")
        return f"Você é um assistente digital chamado {avatar_id.capitalize()}. Seja prestativo, amigável e profissional."
    
    def reload_prompts(self):
        """Recarrega todos os prompts (útil para desenvolvimento)"""
        self.prompts_cache.clear()
        self._load_all_prompts()
        logger.info("[BrainManager] Prompts recarregados")
