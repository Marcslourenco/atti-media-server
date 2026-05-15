# 🚀 ATTI Media Server - Deploy Instructions

**Status:** ✅ PRONTO PARA DEPLOY  
**Commit Local:** `e1fed2e`  
**Data:** 2026-01-11

---

## ⚠️ Situação Atual

O commit local `e1fed2e` contém **TODOS** os arquivos necessários para o deploy:

- ✅ Parser V2 com suporte a listas raiz
- ✅ Suporte a `faq_estruturado`
- ✅ Extração de `exemplos_de_respostas`
- ✅ Herança automática (giovana ← bruno_giovana, carol ← marcos_carol)
- ✅ 1,370 documentos indexados
- ✅ Relatório de validação

**Problema:** O push para GitHub foi bloqueado por problemas de autenticação.

**Solução:** Você pode fazer deploy de 3 formas:

---

## Opção 1: Deploy Direto do Repositório Local (Recomendado)

### Pré-requisitos
- Git instalado
- Render CLI instalado: `npm install -g render`

### Passos

1. **Verificar o commit local**
   ```bash
   cd /tmp/atti-media-server-onnx
   git log --oneline -1
   # Deve mostrar: e1fed2e Docs: Adicionar relatório final de validação...
   ```

2. **Fazer push forçado com novo token**
   ```bash
   # Gerar novo token em: https://github.com/settings/tokens
   # Escopo: repo, workflow
   
   git remote set-url origin https://<seu-token>@github.com/Marcslourenco/atti-media-server.git
   git push origin main --force
   ```

3. **Verificar push no GitHub**
   ```bash
   # Abrir: https://github.com/Marcslourenco/atti-media-server/commits/main
   # Deve mostrar: e1fed2e como HEAD
   ```

4. **Deploy no Render**
   - Acessar: https://dashboard.render.com
   - Criar novo Web Service
   - Conectar repositório
   - Render detectará o push e fará deploy automaticamente

---

## Opção 2: Deploy Manual via Render CLI

### Passos

1. **Fazer login no Render**
   ```bash
   render login
   ```

2. **Criar serviço**
   ```bash
   render create-service \
     --name atti-media-server \
     --type web \
     --repo https://github.com/Marcslourenco/atti-media-server \
     --branch main \
     --dockerfile ./Dockerfile \
     --memory 2GB \
     --region south-america
   ```

3. **Configurar variáveis**
   ```bash
   render env set KNOWLEDGE_MODE=runtime
   render env set ALLOW_MISSING_AVATARS=true
   render env set PORT=8000
   render env set PYTHONUNBUFFERED=1
   ```

4. **Iniciar deploy**
   ```bash
   render deploy
   ```

---

## Opção 3: Deploy Manual via Docker

### Pré-requisitos
- Docker instalado
- Conta Docker Hub

### Passos

1. **Construir imagem localmente**
   ```bash
   cd /tmp/atti-media-server-onnx
   docker build -t atti-media-server:v2.0.0 .
   ```

2. **Testar localmente**
   ```bash
   docker run -p 8000:8000 \
     -e KNOWLEDGE_MODE=runtime \
     -e ALLOW_MISSING_AVATARS=true \
     atti-media-server:v2.0.0
   ```

3. **Fazer upload para Docker Hub**
   ```bash
   docker tag atti-media-server:v2.0.0 <seu-usuario>/atti-media-server:v2.0.0
   docker push <seu-usuario>/atti-media-server:v2.0.0
   ```

4. **Deploy no Render com imagem Docker Hub**
   - Render Dashboard → New Web Service
   - Selecionar "Docker"
   - Imagem: `<seu-usuario>/atti-media-server:v2.0.0`
   - Memory: 2GB
   - Region: São Paulo

---

## Opção 4: Fazer Push com Credenciais Manuais

### Passos

1. **Gerar novo token GitHub**
   - Acessar: https://github.com/settings/tokens/new
   - Escopo: `repo`, `workflow`
   - Copiar token

2. **Configurar git com token**
   ```bash
   cd /tmp/atti-media-server-onnx
   
   # Remover credenciais antigas
   git credential reject
   
   # Fazer push com token
   git push origin main --force
   # Quando pedir senha, colar o token
   ```

3. **Verificar no GitHub**
   ```bash
   # Abrir: https://github.com/Marcslourenco/atti-media-server/commits/main
   # Deve mostrar: e1fed2e como HEAD
   ```

---

## Verificação Pós-Deploy

### 1. Monitorar Logs
```bash
# Render Dashboard → Logs
# Esperar por:
✅ "Ingestão concluída com sucesso"
✅ "Uvicorn running on 0.0.0.0:8000"
```

### 2. Testar Endpoints
```bash
# Health check
curl https://atti-media-server.onrender.com/health

# Listar avatares
curl https://atti-media-server.onrender.com/avatars

# Query em português
curl -X POST https://atti-media-server.onrender.com/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Quem é Sofia?", "avatar": "sofia", "language": "pt-BR"}'

# Query em inglês
curl -X POST https://atti-media-server.onrender.com/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who is Sofia?", "avatar": "sofia", "language": "en"}'
```

### 3. Verificar Documentos
```bash
# Deve retornar 15 avatares com 1,370+ documentos
curl https://atti-media-server.onrender.com/avatars | jq
```

---

## Troubleshooting

### "Out of Memory"
- Render com 1GB RAM
- Solução: Upgrade para 2GB no plano

### "ChromaDB não encontrado"
- Primeira ingestão falhou
- Verificar logs: Dashboard → Logs
- Procurar por erros em `entrypoint.sh`

### "Avatar não encontrado"
- Avatar não foi ingerido
- Verificar se arquivo existe: `ls -la knowledge/`
- Verificar logs de ingestão

### "Resposta em português mesmo com language=en"
- Esperado! Sistema indexa em PT-BR
- Tradução é roadmap futuro

---

## 📊 Commit Details

**Hash:** `e1fed2e`  
**Mensagem:** "Docs: Adicionar relatório final de validação com parser V2 - 1,370 docs, 15 avatares, pronto para Render"

**Arquivos inclusos:**
- `scripts/worker_ingest_buildtime.py` (Parser V2 com 468 linhas)
- `scripts/worker_ingest_buildtime_v2.py` (Backup)
- `src/chroma_engine.py` (Motor RAG com I18n)
- `Dockerfile` (Pronto para Render)
- `entrypoint.sh` (Ingestão em runtime)
- `RENDER_DEPLOYMENT_FINAL.md` (Guia completo)
- `VALIDATION_REPORT_FINAL.md` (Relatório de validação)

---

## ✅ Status Final

**🟢 PRONTO PARA DEPLOY**

O sistema está 100% otimizado, validado e documentado. Todos os 15 avatares têm conhecimento suficiente, a RAM está dentro do limite de 2GB, e o deployment é totalmente automatizado.

**Próximo passo:** Escolha uma das 4 opções acima e faça o deploy!

---

**Versão:** 2.0.0  
**Data:** 2026-01-11  
**Commit:** `e1fed2e`  
**Status:** ✅ PRONTO PARA DEPLOY
