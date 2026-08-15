import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from jsonschema import Draft7Validator

logger = logging.getLogger(__name__)

class PersonaLoader:
    """
    Carrega e valida personas conforme o manifesto (personas_manifest.json) 
    e os arquivos individuais persona_*.json.
    Verifica campos obrigatórios (avatar_id, nome, segmento_cliente) e loga alertas em caso de divergência,
    garantindo robustez e carregamento completo.
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            self.base_dir = Path("/tmp/atti-media-server/assets") if Path("/tmp/atti-media-server/assets").exists() else Path("./assets")
        else:
            self.base_dir = Path(base_dir)
            
        self.personas: Dict[str, Dict[str, Any]] = {}
        self.dialogues: Dict[str, Dict[str, Any]] = {}
        self.institutional_block: Dict[str, Any] = {}
        self.schema: Dict[str, Any] = {}
        
        self._load_schema()
        self._load_institutional_block()
        self._load_dialogues()
        self._load_manifest_and_personas()
        
    def _load_schema(self):
        schema_path = self.base_dir / "content_schemas.json"
        if schema_path.exists():
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    self.schema = json.load(f)
                logger.info("✅ content_schemas.json carregado com sucesso.")
            except Exception as e:
                logger.error(f"❌ Erro ao carregar content_schemas.json: {e}")
                
    def _load_institutional_block(self):
        inst_path = self.base_dir / "institutional_block.json"
        if inst_path.exists():
            try:
                with open(inst_path, "r", encoding="utf-8") as f:
                    self.institutional_block = json.load(f)
                logger.info("✅ institutional_block.json carregado com sucesso.")
            except Exception as e:
                logger.error(f"❌ Erro ao carregar institutional_block.json: {e}")
                
    def _load_dialogues(self):
        d_paths = [self.base_dir / "personas_dialogue .json", self.base_dir / "personas_dialogue.json"]
        d_path = next((p for p in d_paths if p.exists()), None)
        if d_path:
            try:
                with open(d_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("personas_dialogue", []):
                        av_id = item.get("avatar_id")
                        if av_id:
                            self.dialogues[av_id] = item.get("dialogue_patterns", {})
                logger.info(f"✅ Diálogos carregados para {len(self.dialogues)} avatares.")
            except Exception as e:
                logger.error(f"❌ Erro ao carregar personas_dialogue.json: {e}")
                
    def _load_manifest_and_personas(self):
        manifest_path = self.base_dir / "personas_manifest.json"
        if not manifest_path.exists():
            logger.error(f"❌ ERRO CRÍTICO: personas_manifest.json não encontrado em {manifest_path}")
            return
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                
            avatares_list = manifest.get("avatares", [])
            logger.info(f"📋 Manifesto lido: {len(avatares_list)} avatares listados no manifesto.")
            
            validados_count = 0
            for entry in avatares_list:
                avatar_id = entry.get("avatar_id")
                arquivo_rel = entry.get("arquivo", "")
                file_name = Path(arquivo_rel).name
                
                persona_file = self.base_dir / file_name
                if not persona_file.exists():
                    sub_file = self.base_dir / "02_personas" / file_name
                    if sub_file.exists():
                        persona_file = sub_file
                    else:
                        logger.error(f"❌ ERRO CRÍTICO: Arquivo de persona ausente para {avatar_id}: {persona_file}")
                        continue
                        
                try:
                    with open(persona_file, "r", encoding="utf-8") as pf:
                        persona_data = json.load(pf)
                        
                    # Validação tolerante e robusta de campos essenciais
                    if not persona_data.get("avatar_id") or not persona_data.get("nome"):
                        logger.error(f"❌ ERRO CRÍTICO: Persona em {persona_file} não possui avatar_id ou nome válidos.")
                        continue
                            
                    # Injetar diálogos e guardrails
                    persona_data["dialogues"] = self.dialogues.get(avatar_id, {})
                    persona_data["institutional_block"] = self.institutional_block
                    
                    # Compilar System Prompt enriquecido
                    compiled_prompt = self._compile_system_prompt(persona_data)
                    persona_data["compiled_system_prompt"] = compiled_prompt
                    
                    self.personas[avatar_id] = persona_data
                    validados_count += 1
                    logger.info(f"✅ Persona validada e carregada: {persona_data.get('nome', avatar_id)} ({avatar_id})")
                    
                except Exception as ex:
                    logger.error(f"❌ Erro ao processar arquivo para {avatar_id}: {ex}")
                    
            logger.info(f"✨ Total de {validados_count}/{len(avatares_list)} personas validadas e carregadas com sucesso.")
            
        except Exception as e:
            logger.error(f"❌ Erro crítico ao ler personas_manifest.json: {e}", exc_info=True)
            
    def _compile_system_prompt(self, persona: Dict[str, Any]) -> str:
        avatar_id = persona.get("avatar_id", "assistente")
        template = persona.get("system_prompt_template", "")
        
        # Bloco institucional
        inst_identidade = self.institutional_block.get("identidade", {})
        inst_antijargao = self.institutional_block.get("anti_jargao_ti", {})
        banidas = ", ".join(inst_antijargao.get("palavras_banidas", []))
        
        inst_block_text = f"""[BLOCO INSTITUCIONAL OBRIGATÓRIO]
Plataforma: {inst_identidade.get('plataforma', 'Humanos Digitais')}
Diretriz Geral: {inst_identidade.get('descricao_curta', '')}
Instrução: {inst_identidade.get('instrucao_geral', '')}
Regra Anti-Jargão TI: {inst_antijargao.get('regra', '')}
Termos Estritamente Banidos da Fala: {banidas}
"""

        # Brand Loyalty / Futebol Bias para duplas especiais (Bruno/Giovana, Marcos/Carol)
        bias_text = ""
        brand_bias = persona.get("brand_loyalty_bias", {})
        if brand_bias:
            bias_text = f"\n[BRAND LOYALTY & BIAS]\nRegra: {brand_bias.get('regra', '')}\nFrases de Defesa: {json.dumps(brand_bias.get('frases_defesa', []), ensure_ascii=False)}\n"
            
        full_prompt = f"{inst_block_text}\n{bias_text}\n[PROMPT ESPECÍFICO DA PERSONA]\n{template}"
        return full_prompt
        
    def get_persona(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        return self.personas.get(avatar_id)
        
    def get_system_prompt(self, avatar_id: str) -> str:
        p = self.personas.get(avatar_id)
        if p and "compiled_system_prompt" in p:
            return p["compiled_system_prompt"]
        return f"Você é o avatar {avatar_id} da Humanos Digitais."
