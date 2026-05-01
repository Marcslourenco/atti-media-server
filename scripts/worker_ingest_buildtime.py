#!/usr/bin/env python3
"""
WORKER INGESTÃO OFFLINE - Build-time only
Executa DURANTE docker build, NÃO em runtime.
Carrega modelo de embeddings UMA VEZ, indexa todos os avatares, salva ChromaDB em /app/chroma_db.
Controla RAM com batch_size=16 e limpeza de memória entre avatares.
"""

import os
import json
import logging
import hashlib
import gc
import sys
import psutil
from pathlib import Path
from typing import Dict, List, Any, Tuple
import chromadb
from chromadb.config import Settings

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use /tmp para testes locais, /app em Docker
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "/tmp/knowledge"))
CHROMA_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", "/tmp/chroma_db"))
BATCH_SIZE = 16  # Controle de RAM

# Avatares esperados (hardcoded)
EXPECTED_AVATARS = [
    "sofia", "clara", "lucas", "amanda", "fernanda",
    "marina", "roberto", "luisa", "lais", "paula",
    "rafael", "bruno_giovana", "marcos_carol"
]

# ============================================================================
# FASE 1: INICIALIZAR CHROMADB
# ============================================================================

def init_chromadb():
    """Inicializa ChromaDB com PersistentClient"""
    logger.info(f"🔧 Inicializando ChromaDB em {CHROMA_DB_PATH}...")
    
    # Criar diretório se não existir
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    
    # Inicializar cliente
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    logger.info("✅ ChromaDB inicializado")
    return client


# ============================================================================
# FASE 2: CARREGAR MODELO DE EMBEDDINGS (UMA VEZ)
# ============================================================================

def load_embedding_model():
    """Carrega modelo ONNX nativo do ChromaDB (mais leve que SentenceTransformer)"""
    logger.info("🔧 Carregando modelo ONNX nativo...")
    try:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        embedding_fn = ONNXMiniLM_L6_V2()
        logger.info("✅ Modelo ONNX carregado: MiniLM-L6-V2")
        return embedding_fn
    except Exception as e:
        logger.error(f"❌ Erro ao carregar modelo ONNX: {e}")
        logger.warning("⚠️ Fallback para SentenceTransformer...")
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L3-v2")
            logger.info("✅ Fallback: SentenceTransformer carregado")
            return model
        except Exception as e2:
            logger.error(f"❌ Erro ao carregar fallback: {e2}")
            sys.exit(1)


# ============================================================================
# FASE 3: PARSER ROBUSTO
# ============================================================================

def extract_documents(data: Dict[str, Any], avatar_id: str) -> List[Dict[str, str]]:
    """Extrai documentos de múltiplas estruturas JSON"""
    documents = []
    
    # ESTRUTURA 1: FAQ
    if 'faq' in data and isinstance(data['faq'], list):
        for item in data['faq']:
            if isinstance(item, dict) and 'pergunta' in item and 'resposta' in item:
                documents.append({
                    'id': f"faq_{len(documents)}",
                    'content': f"Q: {item['pergunta']}\nA: {item['resposta']}"
                })
    
    # ESTRUTURA 2: Núcleo de Conhecimento
    if 'nucleo_conhecimento' in data and isinstance(data['nucleo_conhecimento'], dict):
        nc = data['nucleo_conhecimento']
        for key in ['problemas_comuns', 'objeções_clientes', 'argumentos_venda']:
            if key in nc and isinstance(nc[key], list):
                for item in nc[key]:
                    if isinstance(item, str):
                        documents.append({
                            'id': f"{key}_{len(documents)}",
                            'content': item
                        })
                    elif isinstance(item, dict):
                        content = item.get('descricao') or item.get('argumento') or item.get('resposta', '')
                        if content:
                            documents.append({
                                'id': f"{key}_{len(documents)}",
                                'content': content
                            })
    
    # ESTRUTURA 3: Sofia (items[])
    if 'items' in data and isinstance(data['items'], list):
        for item in data['items']:
            if isinstance(item, dict) and 'pergunta' in item and 'resposta_base' in item:
                documents.append({
                    'id': f"sofia_{len(documents)}",
                    'content': f"Q: {item['pergunta']}\nA: {item['resposta_base']}"
                })
    
    # ESTRUTURA 4: Áreas Técnicas
    if 'areas_tecnicas' in data and isinstance(data['areas_tecnicas'], list):
        for area in data['areas_tecnicas']:
            if isinstance(area, dict):
                content = area.get('descricao') or area.get('area', '')
                if content:
                    documents.append({
                        'id': f"area_{len(documents)}",
                        'content': content
                    })
    
    # ESTRUTURA 5: Personas de Futebol (SPFC/Corinthians)
    if 'clube' in data and 'arquetipo' in data:
        # Extrair campos principais da persona
        persona_fields = []
        
        # Descrição do arquétipo
        if 'descricao_arquetipo' in data:
            persona_fields.append(f"Arquétipo: {data['descricao_arquetipo']}")
        
        # Perfil demográfico
        if 'perfil_demografico' in data and isinstance(data['perfil_demografico'], dict):
            perfil = data['perfil_demografico']
            if 'zona_urbana_primaria' in perfil:
                persona_fields.append(f"Zona: {perfil['zona_urbana_primaria']}")
            if 'referencias_culturais' in perfil:
                refs = ', '.join(perfil['referencias_culturais']) if isinstance(perfil['referencias_culturais'], list) else str(perfil['referencias_culturais'])
                persona_fields.append(f"Referências: {refs}")
        
        # Tom de voz
        if 'tom_de_voz' in data and isinstance(data['tom_de_voz'], dict):
            tom = data['tom_de_voz']
            if 'adjetivos' in tom:
                adjs = ', '.join(tom['adjetivos']) if isinstance(tom['adjetivos'], list) else str(tom['adjetivos'])
                persona_fields.append(f"Tom: {adjs}")
        
        # Linguagem
        if 'linguagem' in data and isinstance(data['linguagem'], dict):
            ling = data['linguagem']
            if 'girias_especificas' in ling:
                girias = ', '.join(ling['girias_especificas']) if isinstance(ling['girias_especificas'], list) else str(ling['girias_especificas'])
                persona_fields.append(f"Gírias: {girias}")
            if 'expressoes_de_torcida' in ling:
                exprs = ' | '.join(ling['expressoes_de_torcida']) if isinstance(ling['expressoes_de_torcida'], list) else str(ling['expressoes_de_torcida'])
                persona_fields.append(f"Expressões: {exprs}")
        
        # Criar documento com toda a persona
        if persona_fields:
            documents.append({
                'id': f"{avatar_id}_persona",
                'content': f"Persona {data.get('clube', 'Unknown')}: " + " | ".join(persona_fields)
            })
    
    # ESTRUTURA 6: Futebol - Outros arquivos (chants, history, etc.)
    if 'chants' in data and isinstance(data['chants'], list):
        for i, chant in enumerate(data['chants']):
            if isinstance(chant, str):
                documents.append({'id': f"chant_{i}", 'content': chant})
            elif isinstance(chant, dict) and 'text' in chant:
                documents.append({'id': f"chant_{i}", 'content': chant['text']})
    
    if 'matches' in data and isinstance(data['matches'], list):
        for i, match in enumerate(data['matches']):
            if isinstance(match, dict):
                match_info = match.get('description') or match.get('title') or str(match)
                if match_info:
                    documents.append({'id': f"match_{i}", 'content': match_info})
    
    if 'players' in data and isinstance(data['players'], list):
        for i, player in enumerate(data['players']):
            if isinstance(player, dict):
                player_info = player.get('name') or player.get('description') or str(player)
                if player_info:
                    documents.append({'id': f"player_{i}", 'content': player_info})
    
    # Fallback: descrição simples
    if not documents and 'descricao' in data and data['descricao']:
        documents.append({
            'id': f"{avatar_id}_desc",
            'content': data['descricao']
        })
    
    return documents


# ============================================================================
# FASE 4: INDEXAÇÃO COM CONTROLE DE RAM
# ============================================================================

def index_avatar(avatar_id: str, model, client) -> Tuple[int, List[str]]:
    """Indexa um avatar com controle de RAM"""
    avatar_dir = KNOWLEDGE_DIR / avatar_id
    warnings = []
    
    if not avatar_dir.exists():
        warnings.append(f"Diretório não encontrado: {avatar_dir}")
        return 0, warnings
    
    json_files = list(avatar_dir.glob("*.json"))
    if not json_files:
        warnings.append(f"Nenhum arquivo JSON em {avatar_dir}")
        return 0, warnings
    
    # Criar coleção
    try:
        collection = client.get_or_create_collection(
            name=f"{avatar_id}_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        warnings.append(f"Erro ao criar coleção: {e}")
        return 0, warnings
    
    total_indexed = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            documents = extract_documents(data, avatar_id)
            if not documents:
                continue
            
            # Indexar em batches para controlar RAM
            for i in range(0, len(documents), BATCH_SIZE):
                batch = documents[i:i+BATCH_SIZE]
                
                for doc in batch:
                    # Gerar ID único
                    unique_id = f"{avatar_id}_{hashlib.md5(doc['content'][:100].encode()).hexdigest()[:8]}"
                    
                    # Gerar embedding (ONNX usa __call__, não encode)
                    try:
                        if hasattr(model, 'encode'):
                            # SentenceTransformer
                            embedding = model.encode(doc['content']).tolist()
                        else:
                            # ONNX - usa __call__ ou _model.encode
                            embedding = model([doc['content']])[0].tolist()
                    except Exception as e:
                        logger.warning(f"Erro ao gerar embedding: {e}")
                        continue
                    
                    # Adicionar ao ChromaDB
                    collection.add(
                        ids=[unique_id],
                        documents=[doc['content']],
                        embeddings=[embedding],
                        metadatas=[{'source': json_file.name}]
                    )
                    total_indexed += 1
                
                # Limpeza de memória entre batches
                gc.collect()
        
        except json.JSONDecodeError as e:
            warnings.append(f"JSON inválido em {json_file.name}: {e}")
            continue
        except Exception as e:
            warnings.append(f"Erro ao processar {json_file.name}: {e}")
            continue
    
    # Limpeza final
    gc.collect()
    
    # Log de RAM
    ram_gb = psutil.Process().memory_info().rss / (1024**3)
    logger.info(f"💾 RAM pós-ingestão {avatar_id}: {ram_gb:.2f} GB")
    
    return total_indexed, warnings


# ============================================================================
# FASE 5: VALIDAÇÃO FINAL
# ============================================================================

def validate_ingest(client) -> bool:
    """Valida que todos os avatares esperados foram indexados"""
    logger.info("\n🔍 VALIDANDO INGESTÃO...")
    
    collections = {col.name: col for col in client.list_collections()}
    missing = []
    
    for avatar in EXPECTED_AVATARS:
        collection_name = f"{avatar}_knowledge"
        if collection_name not in collections:
            missing.append(avatar)
        else:
            count = collections[collection_name].count()
            if count == 0:
                missing.append(f"{avatar} (0 docs)")
            else:
                logger.info(f"✅ {avatar}: {count} docs | coleção: {collection_name}")
    
    if missing:
        logger.error(f"❌ Avatares faltantes ou vazios: {missing}")
        return False
    
    logger.info("✅ Todos os avatares indexados com sucesso")
    return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    logger.info("="*80)
    logger.info("🔧 WORKER INGESTÃO OFFLINE - BUILD-TIME")
    logger.info("="*80)
    
    # Inicializar
    client = init_chromadb()
    model = load_embedding_model()
    
    # Indexar avatares
    total_docs = 0
    all_warnings = []
    
    for avatar in EXPECTED_AVATARS:
        try:
            count, warnings = index_avatar(avatar, model, client)
            total_docs += count
            all_warnings.extend(warnings)
            
            if count > 0:
                logger.info(f"✅ {avatar}: {count} docs indexados")
            elif warnings:
                logger.warning(f"⚠️ {avatar}: {warnings[0]}")
        except Exception as e:
            logger.error(f"❌ Erro ao indexar {avatar}: {e}")
            all_warnings.append(f"{avatar}: {e}")
    
    # RAM final
    final_ram = psutil.Process().memory_info().rss / (1024**3)
    logger.info(f"🏁 RAM final: {final_ram:.2f} GB")
    if final_ram > 1.8:
        logger.warning("⚠️ Pico de RAM > 1.8GB – considere reduzir batch_size para 8")
    
    # Validar
    logger.info(f"\n📊 RESUMO: {total_docs} documentos indexados")
    
    if validate_ingest(client):
        logger.info("\n✅ Build com RAG pré-indexado concluído")
        sys.exit(0)
    else:
        logger.error("\n❌ Validação falhou")
        sys.exit(1)
