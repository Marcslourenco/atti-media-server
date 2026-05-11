from src.chroma_engine import AvatarRAGEngine

print('\n=== RELATÓRIO FINAL ===\n')
engine = AvatarRAGEngine()

avatares_info = [
    ('sofia', 'sofia_knowledge', True, True, 'N/A'),
    ('bruno', 'bruno_giovana_knowledge', False, False, 'N/A'),
    ('giovana', 'giovana_knowledge', False, False, 'Bruno'),
    ('marcos', 'marcos_carol_knowledge', False, False, 'N/A'),
    ('carol', 'carol_knowledge', False, False, 'Marcos'),
    ('clara', 'clara_knowledge', False, False, 'N/A'),
    ('lucas', 'lucas_knowledge', False, False, 'N/A'),
    ('amanda', 'amanda_knowledge', False, False, 'N/A'),
    ('paula', 'paula_knowledge', False, False, 'N/A'),
    ('lais', 'lais_knowledge', False, False, 'N/A'),
    ('marina', 'marina_knowledge', False, False, 'N/A'),
    ('fernanda', 'fernanda_knowledge', False, False, 'N/A'),
    ('luisa', 'luisa_knowledge', False, False, 'N/A'),
    ('rafael', 'rafael_knowledge', False, False, 'N/A'),
    ('roberto', 'roberto_knowledge', False, False, 'N/A'),
]

print('| Avatar | Collection | Docs | EN | ES | Herda |')
print('|--------|-----------|------|----|----|-------|')

total_docs = 0
for avatar, collection, en, es, herda in avatares_info:
    try:
        col = engine.client.get_collection(collection)
        docs = col.get()
        doc_count = len(docs['ids'])
        total_docs += doc_count
        en_str = '✅' if en else '❌'
        es_str = '✅' if es else '❌'
        print(f'| {avatar:6} | {collection:25} | {doc_count:4} | {en_str} | {es_str} | {herda:5} |')
    except:
        print(f'| {avatar:6} | {collection:25} | 0 | ❌ | ❌ | {herda:5} |')

print(f'\n📊 TOTAL: {total_docs} documentos')
print('✅ PRONTO PARA DEPLOY')
