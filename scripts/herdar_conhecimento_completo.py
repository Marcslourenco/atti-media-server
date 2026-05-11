from src.chroma_engine import AvatarRAGEngine

engine = AvatarRAGEngine()

# Mapeamento de herança com nomes CORRETOS das collections
heranca = [
    ('bruno_giovana', 'giovana'),     # Giovana herda de Bruno (SPFC)
    ('marcos_carol', 'carol'),         # Carol herda de Marcos (Corinthians)
]

for fonte, filho in heranca:
    collection_fonte = f"{fonte}_knowledge"
    collection_filho = f"{filho}_knowledge"
    
    print(f"\n📥 Copiando de '{collection_fonte}' para '{collection_filho}'...")
    
    # Pega TODOS os documentos da fonte
    try:
        fonte_collection = engine.client.get_collection(collection_fonte)
        total_docs = fonte_collection.count()
        print(f"   📄 {total_docs} documentos encontrados na fonte")
        
        if total_docs == 0:
            print(f"   ⚠️ Nenhum documento na fonte!")
            continue
        
        # Busca em lotes (ChromaDB pode ter limite)
        all_docs = fonte_collection.get()
        
        # Prepara para inserção no filho
        documentos = all_docs['documents']
        metadatas = all_docs['metadatas']
        novos_ids = [f"{filho}_{doc_id.split('_')[-1]}" for doc_id in all_docs['ids']]
        
        # Cria ou limpa collection do filho
        try:
            filho_collection = engine.client.get_collection(collection_filho)
            # Limpa existente
            existing = filho_collection.get()
            if existing['ids']:
                filho_collection.delete(ids=existing['ids'])
                print(f"   🗑️ Removidos {len(existing['ids'])} documentos existentes")
        except:
            filho_collection = engine.client.create_collection(collection_filho)
            print(f"   ✨ Collection '{collection_filho}' criada")
        
        # Copia em lotes
        batch_size = 100
        for i in range(0, len(documentos), batch_size):
            batch_docs = documentos[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            batch_ids = novos_ids[i:i+batch_size]
            filho_collection.add(
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids
            )
        
        # Verifica
        count = filho_collection.count()
        print(f"   ✅ {count} documentos copiados para '{filho}'")
        
        # Teste de query
        test = filho_collection.query(query_texts=["título"], n_results=3)
        if test.get('documents') and test['documents'][0]:
            print(f"   ✅ Query teste OK - encontrou: {len(test['documents'][0])} resultados")
        
    except Exception as e:
        print(f"   ❌ ERRO: {e}")

print("\n✅ Herança concluída")
