#!/usr/bin/env python3
"""
WORKER INGEST - Offline Indexing Script
Executa APENAS durante Docker build, NÃO em runtime
Gera embeddings e indexa em ChromaDB (PersistentClient)
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("worker_ingest")

# Paths
KNOWLEDGE_DIR = Path("/app/knowledge") if Path("/app/knowledge").exists() else Path("./knowledge")
CHROMA_DB_DIR = Path("/app/chroma_db") if Path("/app").exists() else Path("./chroma_db")

logger.info("="*80)
logger.info("🔧 WORKER INGEST - OFFLINE INDEXING")
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

def extract_documents(data: Dict[str, Any], avatar_id: str) -> List[Dict[str, str]]:
    """Extrai documentos de múltiplos formatos"""
    docs = []
    
    # Formato Sofia (items com pergunta/resposta_base)
    if "items" in data and isinstance(data["items"], list):
        for item in data["items"]:
            if isinstance(item, dict) and "pergunta" in item and "resposta_base" in item:
                docs.append({
                    "id": item.get("id", f"sofia_{len(docs)}"),
                    "content": f"Q: {item['pergunta']}\nA: {item['resposta_base']}"
                })
    
    # Formato FAQ estruturado
    if "faq_estruturado" in data and isinstance(data["faq_estruturado"], list):
        for faq in data["faq_estruturado"]:
            if isinstance(faq, dict):
                pergunta = faq.get("pergunta", "")
                resposta = faq.get("resposta", "")
                if pergunta and resposta:
                    docs.append({
                        "id": faq.get("id", f"faq_{len(docs)}"),
                        "content": f"Q: {pergunta}\nA: {resposta}"
                    })
    
    # Formato Núcleo de Conhecimento
    if "nucleo_conhecimento" in data and isinstance(data["nucleo_conhecimento"], dict):
        nk = data["nucleo_conhecimento"]
        
        # Problemas comuns
        if "problemas_comuns" in nk and isinstance(nk["problemas_comuns"], list):
            for prob in nk["problemas_comuns"]:
                if isinstance(prob, dict):
                    problema = prob.get("problema", "")
                    solucao = prob.get("solucao_sugerida", "")
                    if problema and solucao:
                        docs.append({
                            "id": prob.get("id", f"prob_{len(docs)}"),
                            "content": f"Problema: {problema}\nSolução: {solucao}"
                        })
        
        # Objeções de clientes
        if "objeções_clientes" in nk and isinstance(nk["objeções_clientes"], list):
            for obj in nk["objeções_clientes"]:
                if isinstance(obj, dict):
                    objecao = obj.get("objecao", "")
                    resposta = obj.get("resposta", "")
                    if objecao and resposta:
                        docs.append({
                            "id": obj.get("id", f"obj_{len(docs)}"),
                            "content": f"Objeção: {objecao}\nResposta: {resposta}"
                        })
        
        # Argumentos de venda
        if "argumentos_venda" in nk and isinstance(nk["argumentos_venda"], list):
            for arg in nk["argumentos_venda"]:
                if isinstance(arg, dict):
                    descricao = arg.get("descricao", "")
                    if descricao:
                        docs.append({
                            "id": arg.get("id", f"arg_{len(docs)}"),
                            "content": descricao
                        })
    
    # Formato Áreas Técnicas
    if "areas_tecnicas" in data and isinstance(data["areas_tecnicas"], list):
        for area in data["areas_tecnicas"]:
            if isinstance(area, dict):
                descricao = area.get("descricao", "")
                if descricao:
                    docs.append({
                        "id": area.get("id", f"area_{len(docs)}"),
                        "content": descricao
                    })
    
    # Fallback: descrição simples
    if not docs and "descricao" in data:
        docs.append({
            "id": f"{avatar_id}_desc",
            "content": data["descricao"]
        })
    
    return docs

def index_avatar(avatar_id: str) -> int:
    """Indexa todos os documentos de um avatar"""
    avatar_dir = KNOWLEDGE_DIR / avatar_id
    
    if not avatar_dir.exists():
        logger.warning(f"⚠️ Diretório não encontrado: {avatar_dir}")
        return 0
    
    json_files = list(avatar_dir.glob("*.json"))
    if not json_files:
        logger.warning(f"⚠️ Nenhum arquivo JSON em {avatar_dir}")
        return 0
    
    # Criar coleção
    try:
        collection = client.get_or_create_collection(
            name=f"{avatar_id}_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        logger.error(f"❌ Erro ao criar coleção para {avatar_id}: {e}")
        return 0
    
    total_docs = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            docs = extract_documents(data, avatar_id)
            
            if not docs:
                logger.warning(f"⚠️ Nenhum documento extraído de {json_file.name}")
                continue
            
            # Chunking: dividir documentos longos
            chunked_docs = []
            for doc in docs:
                content = doc["content"]
                chunk_size = 500
                overlap = 50
                
                if len(content) <= chunk_size:
                    chunked_docs.append(doc)
                else:
                    for i in range(0, len(content), chunk_size - overlap):
                        chunk = content[i:i+chunk_size]
                        chunked_docs.append({
                            "id": f"{doc['id']}_chunk_{i//chunk_size}",
                            "content": chunk
                        })
            
            # Gerar embeddings
            contents = [d["content"] for d in chunked_docs]
            embeddings = model.encode(contents, show_progress_bar=False)
            
            # Adicionar ao ChromaDB
            ids = [d["id"] for d in chunked_docs]
            metadatas = [{"avatar": avatar_id, "source": json_file.name} for _ in chunked_docs]
            
            collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                documents=contents,
                metadatas=metadatas
            )
            
            total_docs += len(chunked_docs)
            logger.info(f"  ✅ {json_file.name}: {len(chunked_docs)} chunks indexados")
        
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Erro JSON em {json_file.name}: {e}")
        except Exception as e:
            logger.error(f"❌ Erro ao processar {json_file.name}: {e}")
    
    return total_docs

# Executar indexação
logger.info("\n📚 INICIANDO INDEXAÇÃO")
logger.info("-" * 80)

total_indexed = 0
indexed_avatars = 0

for avatar_id in AVATARS:
    count = index_avatar(avatar_id)
    if count > 0:
        logger.info(f"✅ {avatar_id}: {count} documentos indexados")
        total_indexed += count
        indexed_avatars += 1
    else:
        logger.warning(f"⚠️ {avatar_id}: nenhum documento indexado")

logger.info("-" * 80)
logger.info(f"\n✅ INDEXAÇÃO CONCLUÍDA")
logger.info(f"   Avatares: {indexed_avatars}/{len(AVATARS)}")
logger.info(f"   Documentos: {total_indexed}")
logger.info(f"   ChromaDB: {CHROMA_DB_DIR}")

if indexed_avatars == 0:
    logger.error("❌ NENHUM AVATAR FOI INDEXADO!")
    sys.exit(1)

logger.info("\n✅ WORKER INGEST CONCLUÍDO COM SUCESSO")
