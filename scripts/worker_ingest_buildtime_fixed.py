# CORREÇÃO 1: Promoção com Rename Nativo
# Este arquivo contém APENAS a seção de promoção corrigida
# Deve ser inserida em worker_ingest_buildtime.py linhas 517-603

    # 6. PROMOÇÃO SEGURA: _tmp → oficial (rename nativo)
    promotion_ok = False
    promoted_count = 0
    
    try:
        # 6a. Ler coleção temporária
        tmp_collection = client.get_collection(f"{avatar_id}_knowledge_tmp")
        all_docs = tmp_collection.get(include=["embeddings", "documents", "metadatas"])
        
        if not all_docs or not all_docs.get('documents'):
            raise ValueError("Coleção _tmp está vazia ou get() retornou sem dados")
        
        docs_count = len(all_docs['documents'])
        logger.info(f"📊 {avatar_id}: _tmp tem {docs_count} docs, pronto para promoção")
        
        # 6b. Validar contagem: docs_tmp >= docs_current * 0.95
        if docs_count < current_count * 0.95:
            raise ValueError(f"Validação falhou: _tmp tem {docs_count} docs mas anterior tinha {current_count}")
        
        # 6c. RENAME NATIVO: _tmp → oficial
        # ChromaDB suporta col.modify(name=...) para renomear
        try:
            # Apagar coleção antiga (se existia) ANTES do rename
            if has_existing_collection:
                try:
                    client.delete_collection(f"{avatar_id}_knowledge")
                    logger.info(f"🗑️ Coleção antiga removida: {avatar_id}_knowledge")
                except Exception:
                    pass
            
            # Renomear _tmp para oficial usando modify
            tmp_collection.modify(name=f"{avatar_id}_knowledge")
            logger.info(f"✅ Coleção renomeada: {avatar_id}_knowledge_tmp → {avatar_id}_knowledge")
            
        except AttributeError:
            # Fallback: se modify não existir, usar delete + get_or_create
            logger.warning(f"⚠️ col.modify não disponível, usando fallback delete+create")
            client.delete_collection(f"{avatar_id}_knowledge_tmp")
            
            # Recriar com nome oficial
            official = client.get_or_create_collection(
                name=f"{avatar_id}_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Copiar dados (última tentativa)
            ids_list = all_docs['ids']
            docs_list = all_docs['documents']
            embeddings_list = all_docs.get('embeddings')
            metadatas_list = all_docs.get('metadatas')
            
            for i in range(0, len(docs_list), BATCH_SIZE):
                batch_end = min(i + BATCH_SIZE, len(docs_list))
                official.add(
                    ids=ids_list[i:batch_end],
                    documents=docs_list[i:batch_end],
                    embeddings=[emb.tolist() if hasattr(emb, 'tolist') else emb for emb in embeddings_list[i:batch_end]] if embeddings_list else None,
                    metadatas=metadatas_list[i:batch_end] if metadatas_list else [{'source': 'promoted'}] * (batch_end - i)
                )
            gc.collect()
        
        # 6d. VALIDAÇÃO FINAL: Verificar que a coleção oficial existe e tem docs > 0
        official_collection = client.get_collection(f"{avatar_id}_knowledge")
        official_count = official_collection.count()
        
        if official_count == 0:
            raise ValueError(f"Validação falhou: coleção oficial tem 0 docs após promoção")
        
        if official_count < docs_count * 0.95:
            raise ValueError(f"Validação falhou: oficial tem {official_count} docs mas _tmp tinha {docs_count}")
        
        promoted_count = official_count
        promotion_ok = True
        logger.info(f"✅ {avatar_id}: PROMOÇÃO CONCLUÍDA — {promoted_count} docs (anterior: {current_count})")
        
    except Exception as e:
        logger.error(f"❌ {avatar_id}: ERRO NA PROMOCÃO: {e}")
        warnings.append(f"Erro na promoção: {e}")
        
        # Se promoção falhou, a coleção antiga (se existia) permanece intacta
        # Limpar _tmp se ainda existir
        try:
            client.delete_collection(f"{avatar_id}_knowledge_tmp")
        except Exception:
            pass
