import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
import numpy as np

client = chromadb.PersistentClient(path='/tmp/test_chroma_diag')
model = ONNXMiniLM_L6_V2()
col = client.get_or_create_collection('test_col', metadata={'hnsw:space': 'cosine'})

doc = 'Teste de documento'
embedding = model([doc])[0].tolist()
col.add(ids=['test1'], documents=[doc], embeddings=[embedding], metadatas=[{'source': 'test'}])

# Testar get() com include
result = col.get(include=['embeddings', 'documents', 'metadatas'])
print('get(include=[embeddings, docs, metas]):')
print('  embeddings is None:', result.get('embeddings') is None)
emb = result.get('embeddings')
if emb is not None:
    print('  embeddings type:', type(emb))
    print('  embeddings length:', len(emb))
    print('  embeddings[0] type:', type(emb[0]))
print('  documents:', result['documents'])
print('  metadatas:', result['metadatas'])
print()

# Simular o que acontece no código de promoção:
print('=== SIMULAÇÃO DO BUG ===')
result_no_include = col.get()  # sem include
print('get() sem include:')
emb_no = result_no_include.get('embeddings')
print('  embeddings:', emb_no)
print('  type:', type(emb_no))
print()

# Limpar
client.delete_collection('test_col')
print('CAUSA RAIZ: get() sem include= retorna embeddings=None')
print('Isso causa official.add(embeddings=None) -> crash')
print()
print('SOLUÇÃO: Usar get(include=["embeddings", "documents", "metadatas"])')
