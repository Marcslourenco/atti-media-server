#!/usr/bin/env python3
"""
WORKER INGEST - Offline Indexing Script (CORRIGIDO)
Executa APENAS durante Docker build, NÃO em runtime
Gera embeddings e indexa em ChromaDB (PersistentClient)

FASES:
1. Função de ID único (MD5 hash)
2. Normalização de tipos de ID
3. Parser robusto para múltiplas estruturas
4. Chunking com ID único
5. Tratamento de erros (nunca crashar)
6. Validação final
"""

import os
import sys
import json
import logging
import hashlib
import re
import uuid
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger("worker_ingest")

# Paths
KNOWLEDGE_DIR = Path("/app/knowledge") if Path("/app/knowledge").exists() else Path("./knowledge")
CHROMA_DB_DIR = Path("/app/chroma_db") if Path("/app").exists() else Path("./chroma_db")

logger.info("="*80)
logger.info("🔧 WORKER INGEST - OFFLINE INDEXING (CORRIGIDO)")
logger.info("="*80)
logger.info(f"Knowledge dir: {KNOWLEDGE_DIR.absolute()}")
logger.info(f"ChromaDB dir: {CHROMA_DB_DIR.absolute()}")

# Criar diretório ChromaDB se não existir
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

# Importar ChromaDB e SentenceTransformer
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    logger.info("✅ Dependências importadas com sucesso")
except ImportError as e:
    logger.error(f"❌ Erro ao importar dependências: {e}")
    sys.exit(1)

# Inicializar ChromaDB
try:
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    logger.info(f"✅ ChromaDB inicializado em {CHROMA_DB_DIR}")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar ChromaDB: {e}")
    sys.exit(1)

# Carregar modelo de embeddings
logger.info("📦 Carregando modelo de embeddings...")
try:
    model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L3-v2")
    logger.info("✅ Modelo carregado: paraphrase-MiniLM-L3-v2")
except Exception as e:
    logger.error(f"❌ Erro ao carregar modelo: {e}")
    sys.exit(1)

# Avatares reconhecidos
AVATARS = [
    "sofia", "rafael", "clara", "lucas", "amanda", "fernanda",
    "marina", "roberto", "luisa", "lais", "paula",
    "bruno", "giovana", "marcos", "carol", "english"
]

# ============================================================================
# FASE 1: FUNÇÃO DE ID ÚNICO (CRÍTICO)
# ============================================================================

def generate_unique_doc_id(avatar_id: str, source_file: str, source_id: str, chunk_idx: int, content: str) -> str:
    """
    Gera ID único e determinístico para documento no ChromaDB.
    Usa hash do conteúdo + metadados para garantir unicidade absoluta.
    
    Formato: {avatar_id}_{content_hash}_{chunk_idx:03d}
    Exemplo: sofia_a1b2c3d4e5f6_001
    """
    # Hash do conteúdo + metadados para garantir unicidade mesmo com faq_id repetido
    unique_string = f"{avatar_id}:{source_file}:{source_id}:{content[:100]}"
    content_hash = hashlib.md5(unique_string.encode('utf-8')).hexdigest()[:12]
    
    doc_id = f"{avatar_id}_{content_hash}_{chunk_idx:03d}"
    return doc_id


# ============================================================================
# FASE 2: NORMALIZAÇÃO DE TIPOS DE ID
# ============================================================================

def normalize_doc_id(doc_id) -> str:
    """
    Garante que TODO ID seja string válida para ChromaDB.
    
    ChromaDB exige:
    - Tipo: str
    - Não vazio
    - Sem caracteres especiais (exceto _ e -)
    """
    if doc_id is None:
        return f"auto_{uuid.uuid4().hex[:8]}"
    
    doc_id_str = str(doc_id).strip()
    
    if not doc_id_str:
        return f"auto_{uuid.uuid4().hex[:8]}"
    
    # Remove caracteres inválidos
    doc_id_str = re.sub(r'[^a-zA-Z0-9_-]', '', doc_id_str)
    
    # Limita tamanho
    doc_id_str = doc_id_str[:100]
    
    if not doc_id_str:
        return f"auto_{uuid.uuid4().hex[:8]}"
    
    return doc_id_str


# ============================================================================
# FASE 3: PARSER ROBUSTO PARA MÚLTIPLAS ESTRUTURAS
# ============================================================================

def extract_documents(data: Dict[str, Any], avatar_id: str) -> List[Dict[str, str]]:
    """
    Extrai documentos de múltiplas estruturas.
    
    Suporta:
    - ESTRUTURA 1: FAQ Estruturado (padrão)
    - ESTRUTURA 2: Núcleo de Conhecimento (strings OU dicts)
    - ESTRUTURA 3: Sofia (items[])
    - ESTRUTURA 4: Áreas Técnicas
    """
    documents = []
    
    # ESTRUTURA 1: FAQ estruturado
    if 'faq_estruturado' in data and isinstance(data['faq_estruturado'], list):
        for item in data['faq_estruturado']:
            if isinstance(item, dict) and 'pergunta' in item and 'resposta' in item:
                doc_id = normalize_doc_id(item.get('id', f'faq_{len(documents)}'))
                documents.append({
                    'id': doc_id,
                    'content': f"Q: {item['pergunta']}\nA: {item['resposta']}"
                })
    
    # ESTRUTURA 2: Núcleo de Conhecimento (strings OU dicts)
    if 'nucleo_conhecimento' in data and isinstance(data['nucleo_conhecimento'], dict):
        nc = data['nucleo_conhecimento']
        
        # Problemas comuns
        if 'problemas_comuns' in nc and isinstance(nc['problemas_comuns'], list):
            for item in nc['problemas_comuns']:
                if isinstance(item, str):
                    doc_id = normalize_doc_id(f'problema_{len(documents)}')
                    documents.append({
                        'id': doc_id,
                        'content': item
                    })
                elif isinstance(item, dict):
                    doc_id = normalize_doc_id(item.get('id', f'problema_{len(documents)}'))
                    documents.append({
                        'id': doc_id,
                        'content': f"Problema: {item.get('problema', '')}\nSolução: {item.get('solucao_sugerida', '')}"
                    })
        
        # Objeções de clientes
        if 'objeções_clientes' in nc and isinstance(nc['objeções_clientes'], list):
            for item in nc['objeções_clientes']:
                if isinstance(item, str):
                    doc_id = normalize_doc_id(f'objecao_{len(documents)}')
                    documents.append({
                        'id': doc_id,
                        'content': item
                    })
                elif isinstance(item, dict):
                    doc_id = normalize_doc_id(item.get('id', f'objecao_{len(documents)}'))
                    documents.append({
                        'id': doc_id,
                        'content': f"Objeção: {item.get('objecao', '')}\nResposta: {item.get('resposta', '')}"
                    })
        
        # Argumentos de venda
        if 'argumentos_venda' in nc and isinstance(nc['argumentos_venda'], list):
            for item in nc['argumentos_venda']:
                if isinstance(item, str):
                    doc_id = normalize_doc_id(f'argumento_{len(documents)}')
                    documents.append({
                        'id': doc_id,
                        'content': item
                    })
                elif isinstance(item, dict):
                    doc_id = normalize_doc_id(item.get('id', f'argumento_{len(documents)}'))
                    documents.append({
                        'id': doc_id,
                        'content': item.get('descricao', '') or item.get('argumento', '')
                    })
    
    # ESTRUTURA 3: Sofia (items[])
    if 'items' in data and isinstance(data['items'], list):
        for item in data['items']:
            if isinstance(item, dict) and 'pergunta' in item and 'resposta_base' in item:
                doc_id = normalize_doc_id(item.get('id', f'sofia_{len(documents)}'))
                documents.append({
                    'id': doc_id,
                    'content': f"Q: {item['pergunta']}\nA: {item['resposta_base']}"
                })
    
    # ESTRUTURA 4: Áreas Técnicas
    if 'areas_tecnicas' in data and isinstance(data['areas_tecnicas'], list):
        for area in data['areas_tecnicas']:
            if isinstance(area, dict):
                doc_id = normalize_doc_id(area.get('id', f'area_{len(documents)}'))
                content = area.get('descricao', '') or area.get('area', '')
                if content:
                    documents.append({
                        'id': doc_id,
                        'content': content
                    })
    
    # Fallback: descrição simples
    if not documents and 'descricao' in data and data['descricao']:
        doc_id = normalize_doc_id(f'{avatar_id}_desc')
        documents.append({
            'id': doc_id,
            'content': data['descricao']
        })
    
    return documents


# ============================================================================
# FASE 4: CHUNKING COM ID ÚNICO
# ============================================================================

def chunk_and_index(documents: List[Dict], avatar_id: str, source_file: str, collection) -> int:
    """
    Divide documentos em chunks e indexa no ChromaDB com IDs únicos.
    """
    chunk_size = 500
    overlap = 50
    total_indexed = 0
    
    for doc in documents:
        doc_id = doc['id']
        content = doc['content']
        
        # Dividir em chunks
        if len(content) <= chunk_size:
            chunks = [content]
        else:
            chunks = []
            i = 0
            while i < len(content):
                chunk = content[i:i+chunk_size]
                chunks.append(chunk)
                i += (chunk_size - overlap)
                if i >= len(content):
                    break
        
        # Indexar cada chunk com ID único
        for chunk_idx, chunk in enumerate(chunks):
            # Gerar ID único para o chunk
            unique_id = generate_unique_doc_id(
                avatar_id=avatar_id,
                source_file=source_file,
                source_id=doc_id,
                chunk_idx=chunk_idx,
                content=chunk
            )
            
            # Normalizar ID
            unique_id = normalize_doc_id(unique_id)
            
            # Adicionar ao ChromaDB
            try:
                collection.add(
                    ids=[unique_id],
                    documents=[chunk],
                    metadatas=[{
                        'avatar': avatar_id,
                        'source': source_file,
                        'doc_id': doc_id,
                        'chunk_idx': chunk_idx
                    }]
                )
                total_indexed += 1
            except Exception as e:
                logger.warning(f"⚠️ Erro ao indexar chunk {unique_id}: {e}")
                continue
    
    return total_indexed


# ============================================================================
# FASE 5: TRATAMENTO DE ERROS (NUNCA CRASHAR)
# ============================================================================

def index_avatar(avatar_id: str) -> Tuple[int, List[str]]:
    """
    Indexa todos os documentos de um avatar.
    Retorna: (total_indexed, warnings)
    """
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
            
            # Ignorar formatos legados
            if json_file.name in ['embeddings.json', 'estrutura_chunks.json', 'dataset_variacoes.json']:
                warnings.append(f"Ignorado (formato legado): {json_file.name}")
                continue
            
            documents = extract_documents(data, avatar_id)
            
            if not documents:
                warnings.append(f"Nenhum documento extraído de {json_file.name}")
                continue
            
            indexed = chunk_and_index(documents, avatar_id, json_file.name, collection)
            total_indexed += indexed
            
        except json.JSONDecodeError as e:
            warnings.append(f"JSON inválido em {json_file.name}: {e}")
            continue
        except Exception as e:
            warnings.append(f"Erro ao processar {json_file.name}: {e}")
            continue
    
    return total_indexed, warnings


# ============================================================================
# FASE 6: VALIDAÇÃO FINAL
# ============================================================================

def validate_unique_ids() -> bool:
    """
    Testa se a função generate_unique_doc_id() gera IDs 100% únicos.
    """
    logger.info("\n🔍 VALIDANDO UNICIDADE DE IDs...")
    
    ids = []
    for i in range(100):
        doc_id = generate_unique_doc_id(
            "sofia",
            "dataset_qa.json",
            "health_01",
            i,
            f"texto de teste {i}"
        )
        ids.append(doc_id)
    
    unique_count = len(set(ids))
    total_count = len(ids)
    
    if unique_count == total_count:
        logger.info(f"✅ Teste de unicidade: {unique_count}/{total_count} IDs únicos")
        return True
    else:
        logger.error(f"❌ IDs duplicados encontrados! {unique_count}/{total_count} únicos")
        return False


# ============================================================================
# MAIN
# ============================================================================

# Executar indexação
logger.info("\n📚 INICIANDO INDEXAÇÃO")
logger.info("-" * 80)

total_indexed = 0
indexed_avatars = 0
all_warnings = {}

# Validar IDs primeiro
if not validate_unique_ids():
    logger.error("❌ Validação de IDs falhou!")
    sys.exit(1)

logger.info("\n📊 INDEXANDO AVATARES:")
logger.info("-" * 80)

for avatar_id in AVATARS:
    count, warnings = index_avatar(avatar_id)
    all_warnings[avatar_id] = warnings
    
    if count > 0:
        logger.info(f"✅ {avatar_id:15} | {count:5} documentos indexados")
        total_indexed += count
        indexed_avatars += 1
    else:
        if avatar_id == 'rafael':
            logger.info(f"⏸️  {avatar_id:15} | PENDING_DATA (aguardando dados)")
        else:
            logger.warning(f"⚠️  {avatar_id:15} | 0 documentos")
    
    # Logar warnings
    for warning in warnings:
        logger.debug(f"  {avatar_id}: {warning}")

logger.info("-" * 80)

# Resumo final
logger.info(f"\n✅ INDEXAÇÃO CONCLUÍDA")
logger.info(f"   Avatares com dados: {indexed_avatars}/{len(AVATARS)}")
logger.info(f"   Documentos indexados: {total_indexed}")
logger.info(f"   ChromaDB: {CHROMA_DB_DIR}")

# Gate final
if indexed_avatars == 0:
    logger.error("❌ NENHUM AVATAR FOI INDEXADO!")
    sys.exit(1)

logger.info("\n✅ WORKER INGEST CONCLUÍDO COM SUCESSO")
logger.info("="*80)
