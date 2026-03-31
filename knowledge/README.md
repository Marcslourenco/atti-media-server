# ATTI Knowledge Packages

Base de conhecimento consolidada para o ecossistema ATTI com 624 embeddings reais (384 dimensões).

## Conteúdo

- **8 Documentos Sofia**: Treinamento de avatar host
- **12 Documentos Avatares**: Conhecimento por persona
- **624 Chunks**: Estruturados e indexados em FAISS
- **384 Dimensões**: Embeddings otimizados

## Estrutura

```
packages/
├── sofia/          # Conhecimento de Sofia
├── personas/       # Conhecimento por avatar
├── sports/         # Domínio esportivo
└── general/        # Conhecimento geral
```

## Uso

```python
from atti_knowledge_packages import KnowledgePackage

kb = KnowledgePackage(domain="sports")
results = kb.search("qual é o resultado do jogo?", top_k=5)
```

## Índices

- **FAISS**: 937 KB (624 vetores x 384 dim)
- **Metadata**: JSON com timestamps e versões
- **Versionamento**: Suporta rollback automático

## Status

✅ Pronto para produção
