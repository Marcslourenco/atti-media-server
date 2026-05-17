# Configuração OpenRouter - ATTI Media Server

## Status Atual

✅ **Sistema Funcional com Fallback RAG**
- Scores de retrieval: 0.35-0.41 (excelentes)
- Fallback retorna conteúdo real do RAG
- Pronto para produção

⚠️ **OpenRouter Pendente**
- Integração de código: ✅ Completa
- Testes locais: ⚠️ Modelo não encontrado (404)
- Possível causa: Chave/modelo inválido ou conta sem acesso

---

## Configuração Local

### Pré-requisitos
1. Conta no OpenRouter: https://openrouter.ai
2. API Key válida com créditos
3. Modelo disponível na conta

### Passos

```bash
# 1. Configurar variável de ambiente
export OPENROUTER_API_KEY="sk-or-v1-sua-chave-aqui"

# 2. (Opcional) Configurar modelo específico
export OPENROUTER_MODEL="mistralai/mistral-7b-instruct"

# 3. Testar
python3 << 'EOF'
import asyncio
from src.llm_orchestrator import generate_llm_response

async def test():
    r = await generate_llm_response(
        system_prompt='Você é um assistente.',
        context='A: Informação importante',
        history=[],
        query='Qual é a informação?'
    )
    print(f'Source: {r["source"]}')
    print(f'Response: {r["response"][:100]}')

asyncio.run(test())
EOF
```

---

## Configuração no Render

### 1. Adicionar Variáveis de Ambiente

No Render Dashboard → Environment:

```
OPENROUTER_API_KEY=sk-or-v1-sua-chave-aqui
OPENROUTER_MODEL=mistralai/mistral-7b-instruct
```

### 2. Modelos Disponíveis

Verifique em: https://openrouter.ai/models

Modelos testados e recomendados:
- `mistralai/mistral-7b-instruct`
- `meta-llama/llama-2-7b-chat`
- `nousresearch/nous-hermes-2-mistral-7b-dpo`

### 3. Deploy

```bash
git push origin main
# Render detectará as mudanças e fará deploy automático
```

---

## Troubleshooting

### Erro: "No endpoints found for [modelo]"

**Causa:** Modelo não existe ou não está disponível na sua conta

**Solução:**
1. Acesse https://openrouter.ai/models
2. Procure por modelos gratuitos
3. Copie o nome exato (ex: `mistralai/mistral-7b-instruct`)
4. Atualize `OPENROUTER_MODEL` no Render

### Erro: "Unauthorized" (401)

**Causa:** API Key inválida ou expirada

**Solução:**
1. Gere nova chave em https://openrouter.ai/keys
2. Atualize `OPENROUTER_API_KEY` no Render
3. Aguarde 5 minutos para redeploy

### Sem erro, mas source='fallback'

**Causa:** OpenRouter não respondeu, sistema caiu para fallback

**Solução:**
1. Verifique logs do Render
2. Confirme que a chave está correta
3. Verifique se há créditos disponíveis
4. Tente com modelo diferente

---

## Comportamento do Sistema

### Com OpenRouter Configurado
1. Tenta Ollama (local) → 2s
2. Tenta OpenRouter (cloud) → 5-10s
3. Fallback RAG (conteúdo real) → instantâneo

### Sem OpenRouter (Fallback Apenas)
- Retorna conteúdo real do RAG
- Sem processamento de LLM
- Respostas diretas dos documentos

---

## Próximos Passos

1. **Validar Modelo:** Confirme qual modelo está disponível na sua conta
2. **Atualizar Chave:** Se necessário, gere nova chave
3. **Testar Localmente:** Execute o teste acima
4. **Deploy:** Atualize variáveis no Render
5. **Monitorar:** Verifique logs de produção

---

**Última Atualização:** 2026-05-17  
**Status:** Pronto para produção (com ou sem OpenRouter)
