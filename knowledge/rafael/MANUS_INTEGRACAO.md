# RELATÓRIO DE INTEGRAÇÃO — AVATAR RAFAEL (TRIBUTÁRIO)

## Pré-requisitos
- [ ] Backend: atti-media-server (Render)
- [ ] Pasta: `/app/knowledge/rafael/` criada
- [ ] Acesso ao repositório GitHub: `Marcslourenco/atti-media-server`
- [ ] Observação: `FASE1_ANALISE_SCHEMA.json` não foi disponibilizado neste lote de entrada

## Passo 1 — Copiar Arquivos
```bash
cp rafael_800_final.json /app/knowledge/rafael/rafael_knowledge.json
cp chroma_collection_config.json /app/knowledge/rafael/config.json
cp rag_chunking_strategy.json /app/knowledge/rafael/strategy.json
```

## Passo 2 — Validar Ingestão
```bash
python scripts/worker_ingest.py --avatar rafael --validate
```
Esperado: `rafael: 800 docs indexados | coleção: rafael_knowledge`

## Passo 3 — Testar Retrieval
```bash
curl -X POST https://humanos-digitais-tts-v2.onrender.com/api/avatar/speak   -H "Content-Type: application/json"   -d '{"text":"O que é MVA ajustada em operação interestadual?","avatar_id":"rafael","language":"pt-BR"}'
```
Esperado: resposta técnica com cálculo, sem fallback genérico.

## Troubleshooting
| Erro | Causa | Solução |
|---|---|---|
| collection not found | Pasta não copiada ou nome errado | Verificar `/app/knowledge/rafael/rafael_knowledge.json` |
| fallback genérico | Threshold alto ou chunk ruim | Ajustar `min_score=0.20` no `chroma_engine.py` |
| OOM no build | Embedding no startup | Garantir lazy loading ativo |
| IDs duplicados | Migração sem renumeração | Reexecutar script com contador sequencial |

## Validação Pós-Deploy
```bash
curl https://humanos-digitais-tts-v2.onrender.com/api/validate-rag
```
Esperado: `{"status":"OK","gate":"APPROVED_FOR_DEPLOY",...}`
