# Knowledge Packages Architecture

## Overview

The knowledge packages system provides a centralized repository for all domain-specific knowledge used by ATTI agents.

## Structure

```
packages/
├── sofia/          # Sofia Master Persona knowledge
├── personas/       # Persona library (football, basketball, etc.)
├── sports/         # Sports domain knowledge
└── general/        # General fallback knowledge
```

## Embeddings

- **Total**: 624 embeddings
- **Dimension**: 384
- **Vector DB**: FAISS
- **Format**: .npy (NumPy)

## Indexing

Knowledge blocks are indexed using FAISS for fast similarity search:

```python
import faiss
index = faiss.read_index("indices/atti_tax_knowledge_faiss.bin")
distances, indices = index.search(query_vector, k=5)
```

## Integration

Knowledge packages are loaded by ATTI agents via the RAG adapter:

```python
from atti_rag_adapter import FAISSIntegration
rag = FAISSIntegration(index_path="indices/atti_tax_knowledge_faiss.bin")
results = rag.search("query", top_k=5)
```

## Adding New Knowledge

1. Create a new package directory
2. Add documents to the package
3. Update `package_metadata.json`
4. Run `ingest_knowledge.py`
5. Commit and push changes
