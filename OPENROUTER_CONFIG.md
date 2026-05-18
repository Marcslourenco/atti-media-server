# Configuração OpenRouter — ATTI Media Server

Última atualização: 2026-05-17  
Status: ✅ Testado e aprovado localmente

---

## Modelo validado

Modelo testado e aprovado nos testes locais: **`baidu/cobuddy:free`**

Este é o único modelo que funciona com a conta OpenRouter fornecida.

---

## Variáveis de ambiente para o Render

Configure em: Dashboard > seu serviço > Environment > Add Variable

| Variável | Valor |
|----------|-------|
| `OPENROUTER_API_KEY` | sua chave `sk-or-v1-...` |
| `OPENROUTER_MODEL` | `baidu/cobuddy:free` |
| `KNOWLEDGE_MODE` | `runtime` |
| `ALLOW_MISSING_AVATARS` | `true` |
| `PORT` | `8000` |

**ATENÇÃO:** NÃO configure `OLLAMA_URL` nem `REDIS_URL` no Render.

---

## Comportamento do sistema em produção

1. **Tenta Ollama local** → falha silenciosamente (não instalado no Render)
2. **Tenta OpenRouter** (`baidu/cobuddy:free`) → resposta em 5-10s
3. **Fallback RAG interno** → instantâneo (se OpenRouter falhar)

---

## Teste pós-deploy

Execute após configurar o Render:

### Teste intro
```bash
curl -X POST https://seu-servico.onrender.com/api/avatar/speak \
  -H "Content-Type: application/json" \
  -d '{"avatar_id":"sofia","text":"","event_type":"intro"}'
```

**Esperado:**
```json
{
  "text_response": "Olá! Sou Sofia. Como posso ajudar?",
  "source": "intro"
}
```

### Teste query com LLM
```bash
curl -X POST https://seu-servico.onrender.com/api/avatar/speak \
  -H "Content-Type: application/json" \
  -d '{"avatar_id":"sofia","text":"O que você faz?","event_type":"query"}'
```

**Esperado:**
```json
{
  "source": "openrouter",
  "text_response": "Sou a Sofia, sua assistente digital especializada em..."
}
```

---

## Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| `source=rag_fallback` | OpenRouter não configurado | Verifique `OPENROUTER_API_KEY` no Render |
| Erro 404 no modelo | Modelo não existe | Confirme `OPENROUTER_MODEL=baidu/cobuddy:free` |
| Erro 401 | Chave inválida | Gere nova chave em https://openrouter.ai/keys |
| Timeout (>30s) | Modelo sobrecarregado | Tente novamente em alguns minutos |

---

**Versão:** 1.0  
**Commit:** c7340d4  
**Status:** 🟢 Pronto para deploy
