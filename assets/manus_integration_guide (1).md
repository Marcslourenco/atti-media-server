# Guia de Integração — Manus Agent
## Ingestão segura de conteúdo (Onboarding, Personas, Guardrails) no RAG Humanos Digitais

---

## 🔴 REGRA CRÍTICA — LEIA ANTES DE EXECUTAR QUALQUER COMANDO

> **O MANUS NÃO PODE, EM NENHUMA HIPÓTESE, EXECUTAR `collection.delete()` OU RECRIAR UMA COLEÇÃO CHROMADB ATIVA ANTES DE UM NOVO ÍNDICE ESTAR 100% VALIDADO.**
>
> Já ocorreu perda de dados (um avatar caiu de 805 para 232 documentos) por ingestão destrutiva direta. A partir de agora, **toda ingestão é atômica (swap por alias)**. Se o Manus identificar qualquer código que apague uma coleção `avatar_<nome>` diretamente, ele deve **parar e reportar**, nunca executar.

Fluxo proibido (❌ NUNCA FAZER):
```python
# ❌ PROIBIDO
client.delete_collection("avatar_sofia")
client.create_collection("avatar_sofia")
# ... reingestão direta na coleção viva
```

Fluxo obrigatório (✅ SEMPRE FAZER): coleção temporária → validação → troca de ponteiro.

---

## Visão geral do fluxo atômico

```
JSON novo → validação de Schema → indexação em "<avatar>_tmp"
   → contagem de docs (esperado vs. obtido) → se OK: swap de alias
   → remove coleção antiga (SOMENTE após swap confirmado)
   → RAG_READY = True
```

Enquanto `RAG_READY == False` para um avatar, o backend deve responder **HTTP 503** para qualquer request de RAG daquele avatar (nunca servir contexto parcial ou vazio silenciosamente).

---

## Passo 1 — Ler o JSON e validar contra o Schema

```python
import json
from jsonschema import validate, Draft7Validator

with open("content_schemas.json") as f:
    schema = json.load(f)

with open(caminho_arquivo_novo) as f:
    conteudo = json.load(f)

validator = Draft7Validator(schema)
erros = sorted(validator.iter_errors(conteudo), key=lambda e: e.path)

if erros:
    for e in erros:
        log.error(f"Schema inválido em {caminho_arquivo_novo}: {e.message} (path: {list(e.path)})")
    raise ValueError("Ingestão abortada: JSON não passou na validação de schema.")
```

**Critério de bloqueio:** qualquer erro de schema interrompe o pipeline imediatamente. Nenhum dado inválido chega ao ChromaDB.

---

## Passo 2 — Indexar em coleção temporária (`_tmp`)

Nunca escreva na coleção de produção. Toda escrita nova vai para um nome temporário exclusivo:

```python
nome_avatar = "sofia"
nome_producao = f"avatar_{nome_avatar}"
nome_tmp = f"avatar_{nome_avatar}_tmp_{int(time.time())}"

colecao_tmp = chroma_client.create_collection(nome_tmp)

docs, metadatas, ids = preparar_chunks(conteudo)  # a partir do JSON validado
colecao_tmp.add(documents=docs, metadatas=metadatas, ids=ids)
```

A coleção de produção (`avatar_sofia`) permanece intacta e servindo tráfego normalmente durante todo este passo.

---

## Passo 3 — Validar contagem de documentos

Antes de qualquer swap, comparar o número de documentos esperado (baseado no JSON de origem) com o número efetivamente indexado:

```python
esperado = len(docs)
obtido = colecao_tmp.count()

if obtido != esperado:
    log.error(f"Contagem divergente: esperado={esperado}, obtido={obtido}")
    chroma_client.delete_collection(nome_tmp)  # aqui SIM pode deletar: é a coleção _tmp, não a de produção
    raise ValueError("Ingestão abortada: divergência de contagem de documentos.")

# Checagem extra recomendada: nunca aceitar shrinkage > 5% frente à coleção de produção atual
colecao_producao = chroma_client.get_collection(nome_producao)
contagem_atual = colecao_producao.count()
if obtido < contagem_atual * 0.95:
    log.error(f"Possível ingestão destrutiva detectada: {obtido} < 95% de {contagem_atual}")
    raise ValueError("Ingestão abortada: shrinkage suspeito. Requer aprovação manual.")
```

---

## Passo 4 — Atualizar o alias de memória (ponteiro) e só então remover a coleção antiga

O sistema deve manter um **ponteiro lógico** (tabela/arquivo de alias, ex.: `alias_map.json` ou linha em banco de configuração) que diz qual coleção física está ativa para cada avatar. O swap é a troca desse ponteiro — **nunca** uma operação destrutiva direta:

```python
# alias_map: { "sofia": "avatar_sofia_tmp_1723000000" }
def swap_alias(avatar_id: str, nova_colecao: str):
    antiga = alias_map.get(avatar_id)
    alias_map[avatar_id] = nova_colecao
    persistir_alias_map(alias_map)
    return antiga

antiga = swap_alias(nome_avatar, nome_tmp)

# Só remove a coleção antiga DEPOIS do alias já apontar para a nova
# e depois de um período de "quarentena" (ex.: manter por 24h para rollback)
agendar_remocao_segura(antiga, apos_horas=24)
```

**Nunca remova `antiga` de forma síncrona no mesmo passo do swap.** Mantenha-a por um período de quarentena configurável, permitindo rollback instantâneo caso algo dê errado no consumo do novo índice.

---

## Passo 5 — Controle de `RAG_READY` e bloqueio de tráfego

```python
RAG_READY = {"sofia": False}  # estado por avatar, inicia bloqueado durante swap

def iniciar_ingestao(avatar_id):
    RAG_READY[avatar_id] = False
    # ... passos 1 a 4 ...
    RAG_READY[avatar_id] = True  # só libera após swap + quarentena agendada

@app.middleware("http")
async def checar_rag_ready(request: Request, call_next):
    avatar_id = extrair_avatar_id(request)
    if avatar_id and not RAG_READY.get(avatar_id, True):
        return JSONResponse(
            status_code=503,
            content={"erro": "RAG em atualização, tente novamente em instantes."}
        )
    return await call_next(request)
```

**Nunca sirva um avatar com `RAG_READY == False`** — é melhor retornar 503 (o frontend pode reexibir "carregando conhecimento...") do que servir contexto incompleto ou corrompido.

---

## Checklist de execução para o Manus (resuma em cada PR/commit)

- [ ] Validei o JSON contra `content_schemas.json` antes de tocar no banco?
- [ ] Indexei em coleção `_tmp`, nunca na coleção de produção?
- [ ] Comparei contagem de documentos (esperado vs. obtido, e vs. produção atual)?
- [ ] Fiz o swap via alias/ponteiro, não via delete direto?
- [ ] A coleção antiga ficou em quarentena (não foi deletada na hora)?
- [ ] `RAG_READY` foi corretamente setado como `False` durante o processo e `True` só ao final?
- [ ] Testei que o endpoint responde 503 quando `RAG_READY == False`?

Se qualquer item acima não puder ser marcado, **a PR deve ser rejeitada antes do merge.**
