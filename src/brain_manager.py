import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BrainManager:
    """Gerenciador unificado de personas, diálogos e guardrails para a Humanos Digitais"""
    
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            # Detectar diretório base correto (assets ou knowledge)
            if Path("/tmp/atti-media-server/assets").exists():
                self.base_dir = Path("/tmp/atti-media-server/assets")
            else:
                self.base_dir = Path("./assets")
        else:
            self.base_dir = Path(base_dir)
            
        self.personas_cache: Dict[str, Dict[str, Any]] = {}
        self.dialogues_cache: Dict[str, Dict[str, Any]] = {}
        self.institutional_block: str = ""
        self._load_all_assets()
        
    def _load_all_assets(self):
        logger.info(f"[BrainManager] 🔍 Carregando ativos de persona a partir de {self.base_dir}...")
        
        # 1. Carregar Institutional Block
        inst_path = self.base_dir / "institutional_block.json"
        if inst_path.exists():
            try:
                with open(inst_path, "r", encoding="utf-8") as f:
                    inst_data = json.load(f)
                    desc = inst_data.get("identidade", {}).get("descricao_curta", "")
                    anti_jargao = inst_data.get("anti_jargao_ti", {}).get("regra", "")
                    banidas = ", ".join(inst_data.get("anti_jargao_ti", {}).get("palavras_banidas", []))
                    self.institutional_block = f"[BLOCO INSTITUCIONAL OBRIGATÓRIO]\n{desc}\n{anti_jargao}\nTermos estritamente proibidos na fala: {banidas}\n"
                    logger.info(f"[BrainManager] ✅ institutional_block.json carregado com sucesso.")
            except Exception as e:
                logger.error(f"[BrainManager] ❌ Erro ao carregar institutional_block.json: {e}")
                
        # 2. Carregar Personas Dialogue
        dialogue_paths = [
            self.base_dir / "personas_dialogue .json",
            self.base_dir / "personas_dialogue.json"
        ]
        d_path = next((p for p in dialogue_paths if p.exists()), None)
        if d_path:
            try:
                with open(d_path, "r", encoding="utf-8") as f:
                    d_data = json.load(f)
                    for item in d_data.get("personas_dialogue", []):
                        av_id = item.get("avatar_id")
                        if av_id:
                            self.dialogues_cache[av_id] = item.get("dialogue_patterns", {})
                    logger.info(f"[BrainManager] ✅ Diálogos carregados para {len(self.dialogues_cache)} avatares.")
            except Exception as e:
                logger.error(f"[BrainManager] ❌ Erro ao carregar personas_dialogue.json: {e}")
                
        # 3. Carregar Personas Manifest
        manifest_path = self.base_dir / "personas_manifest.json"
        if not manifest_path.exists():
            logger.error(f"[BrainManager] ❌ CRÍTICO: personas_manifest.json não encontrado em {manifest_path}")
            return
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                
            avatares_list = manifest.get("avatares", [])
            logger.info(f"[BrainManager] 📋 Manifesto lido: {len(avatares_list)} avatares listados.")
            
            for entry in avatares_list:
                avatar_id = entry.get("avatar_id")
                arquivo_rel = entry.get("arquivo", "")
                
                # Normalizar caminho do arquivo (pode estar como 02_personas/persona_sofia.json ou persona_sofia.json)
                file_name = Path(arquivo_rel).name
                persona_file = self.base_dir / file_name
                if not persona_file.exists():
                    # Tentar no subdiretório 02_personas se existir
                    sub_file = self.base_dir / "02_personas" / file_name
                    if sub_file.exists():
                        persona_file = sub_file
                    else:
                        logger.error(f"[BrainManager] ❌ ERRO CRÍTICO: Arquivo de persona ausente para {avatar_id}: {persona_file}")
                        raise FileNotFoundError(f"Persona obrigatória {avatar_id} ausente em {persona_file}")
                        
                with open(persona_file, "r", encoding="utf-8") as pf:
                    persona_data = json.load(pf)
                    
                # Injetar bloco institucional no template
                template = persona_data.get("system_prompt_template", "")
                full_prompt = f"{self.institutional_block}\n[PROMPT ESPECÍFICO DA PERSONA]\n{template}"
                persona_data["compiled_system_prompt"] = full_prompt
                
                self.personas_cache[avatar_id] = persona_data
                logger.info(f"[BrainManager] ✅ Carregando persona: {avatar_id.capitalize()} ({avatar_id}).")
                
        except Exception as e:
            logger.error(f"[BrainManager] ❌ ERRO CRÍTICO NO CARREGAMENTO DE PERSONAS: {e}", exc_info=True)
            raise
            
        logger.info(f"[BrainManager] ✨ Total de avatares validados e carregados em memória: {len(self.personas_cache)}")
        
    def get_system_prompt(self, avatar_id: str) -> str:
        """Retorna o system prompt compilado com guardrails institucionais"""
        if avatar_id in self.personas_cache:
            return self.personas_cache[avatar_id].get("compiled_system_prompt", "")
        # Fallback genérico
        return f"{self.institutional_block}\nVocê é um assistente digital da Humanos Digitais chamado {avatar_id.capitalize()}."
        
    def get_greeting(self, avatar_id: str) -> str:
        """Retorna uma saudação variada a partir do dialogues_cache ou do prompt"""
        if avatar_id in self.dialogues_cache:
            aberturas = self.dialogues_cache[avatar_id].get("aberturas_variadas", [])
            if aberturas:
                import random
                return random.choice(aberturas)
                
        # Fallback para o nome da persona
        if avatar_id in self.personas_cache:
            nome = self.personas_cache[avatar_id].get("nome", avatar_id.capitalize())
            return f"Olá! Sou {nome}, especialista da Humanos Digitais. Como posso ajudar?"
            
        return f"Olá! Sou {avatar_id.capitalize()}. Como posso ajudar?"
        
    def reload_prompts(self):
        self.personas_cache.clear()
        self.dialogues_cache.clear()
        self._load_all_assets()
        logger.info("[BrainManager] Prompts e personas recarregados com sucesso.")
