# 🔍 ATTI Media Server - Render Debug Instructions

**Commit:** `630be28`  
**Data:** 2026-05-14  
**Objetivo:** Capturar o erro real da ingestão no Render

---

## 📋 Instruções para Deploy e Coleta de Logs

### Passo 1: Fazer Deploy no Render

1. **Acessar Render Dashboard**
   - https://dashboard.render.com

2. **Selecionar o serviço `atti-media-server`**
   - Ou criar novo se não existir

3. **Fazer deploy do commit `630be28`**
   - Render deve detectar automaticamente o push
   - Se não detectar, clique em "Redeploy"

4. **Aguardar o build concluir**
   - Tempo estimado: 3-5 minutos

---

### Passo 2: Coletar os Logs

**IMPORTANTE:** Copie TODA a saída a partir da linha `🔍 Verificando ambiente no Render...`

1. **Acessar Logs do Render**
   - Dashboard → Serviço → Logs

2. **Procurar pela linha:**
   ```
   🔍 Verificando ambiente no Render...
   ```

3. **Copiar TUDO a partir dessa linha**
   - Incluindo:
     - Diretório atual
     - Usuário
     - Listagem de `/app/knowledge/`
     - Listagem de `/app/scripts/`
     - Verificação de ChromaDB
     - Execução do script de ingestão
     - Qualquer erro que apareça

4. **Colar os logs aqui**
   - Responda com os logs completos

---

## 📊 O que o Diagnóstico Vai Mostrar

O novo `entrypoint.sh` vai exibir:

```
🔍 Verificando ambiente no Render...
Diretório atual: /app
Usuário: root (ou outro)
Diretório /app/knowledge/:
  (listagem de arquivos)
Diretório /app/scripts/:
  (listagem de arquivos)

🔍 Verificando ChromaDB...
✅ Collections encontradas: 0

⚠️ Nenhuma collection. Iniciando ingestão...

📚 Ingerindo documentos (modo DEBUG)...
+ python /app/scripts/worker_ingest_buildtime.py 2>&1
  (saída do script com erros detalhados)
+ set +x

✅ Ingestão concluída com sucesso
(ou ❌ Ingestão falhou com código X)

🚀 Iniciando servidor...
```

---

## 🎯 O Que Procurar nos Logs

| Problema Potencial | Sinal nos Logs |
|------------------|----------------|
| Arquivo não encontrado | `FileNotFoundError: [Errno 2]` |
| Módulo não importado | `ModuleNotFoundError` ou `ImportError` |
| Permissão negada | `Permission denied` |
| ChromaDB corrompido | `sqlite3.DatabaseError` |
| Memória insuficiente | `MemoryError` ou `Killed` |
| Erro de sintaxe Python | `SyntaxError` |
| Erro de importação de dependência | `ImportError` ou `No module named` |

---

## 📝 Próximos Passos

1. **Fazer deploy com commit `630be28`**
2. **Coletar logs completos**
3. **Enviar logs para análise**
4. **Implementar correção baseada no erro real**
5. **Novo deploy com correção**

---

## ⚠️ Importante

- **NÃO** tente adivinhar o erro
- **COPIE** toda a saída dos logs
- **INCLUA** todas as mensagens de erro
- **NÃO** corte ou resuma os logs

---

**Status:** 🟡 **AGUARDANDO LOGS DO RENDER**

Commit `630be28` está pronto. Agora precisamos dos logs para identificar o erro real.
