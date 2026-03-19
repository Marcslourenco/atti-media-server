# Integração de Infra — ATTI Media Server (para o Manus)

Este documento descreve como integrar e validar os componentes de infraestrutura do MVP.

---

## 1) Como fazer deploy com Docker Compose

### 1.1 Preparar variáveis de ambiente
1. Copie:
```bash
cp .env.example .env
```

2. Gere uma API key e configure:
```bash
openssl rand -hex 32
```
Depois:
```env
ATTI_API_KEYS=<cole_aqui>
```

### 1.2 Subir o stack
```bash
docker-compose up --build
```

Serviços:
- API: `http://localhost:8000`
- Redis/Valkey: `localhost:6379`

### 1.3 (Opcional) Subir com Postgres
```bash
docker-compose --profile with-postgres up --build
```

---

## 2) Como testar a fila Celery

### 2.1 Validar que o worker está ativo
- Verifique logs do serviço `celery-worker`:
```bash
docker-compose logs -f celery-worker
```

### 2.2 Enfileirar uma task (via código na API)
A integração esperada é:
- endpoint de geração chama `generate_full_video.delay(payload)` ou `synthesize_long_tts.delay(payload)`
- resposta retorna `task_id`

Exemplo de payload (sugestão):
```json
{
  "text": "Olá! Este é um teste.",
  "voice_id": "pt_br_01",
  "avatar_id": "avatar_a",
  "params": {"speed": 1.0},
  "request_id": "<opcional>"
}
```

### 2.3 Consultar status
O endpoint de status é:
- `GET /api/task/{task_id}`

Estados típicos:
- `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`

---

## 3) Como configurar rate limiting e API keys

### 3.1 Rate limiting (SlowAPI)
- Limite padrão sugerido para endpoints públicos:
  - `ATTI_RATE_LIMIT_PUBLIC=100/hour`

Aplique o decorator `@limiter.limit(...)` nos endpoints.

### 3.2 API keys
- Header: `X-API-Key`
- Chaves válidas: `ATTI_API_KEYS` (lista separada por vírgula)

Política MVP deste pacote:
- Se `ATTI_API_KEYS` estiver vazio → endpoints protegidos falham com 503 (evita exposição acidental).

---

## 4) Como monitorar logs

### 4.1 Logs via Docker
```bash
docker-compose logs -f atti-media-server
```

### 4.2 Logs em arquivo (volume)
- Caminho no container: `/var/log/atti/atti.jsonl`
- Serviço `logrotate` rotaciona diariamente e mantém 7 arquivos.

---

## 5) Checklist pós-deploy (MVP)

1. **API de pé**
   - `GET /health` retorna 200 (se você manter o healthcheck do Dockerfile)
   - se não existir `/health`, ajuste/remova o `HEALTHCHECK` do Dockerfile

2. **Redis saudável**
   - `docker-compose ps` mostra `healthy` no redis

3. **Worker Celery rodando**
   - logs do worker sem erro de conexão

4. **Enfileirar + consultar status**
   - task enfileirada retorna `task_id`
   - `GET /api/task/{task_id}` muda de `PENDING` → `SUCCESS`

5. **Rate limiting ativo**
   - endpoints públicos limitam por IP

6. **API key protegendo geração**
   - sem `X-API-Key` → 401/503 conforme configuração
   - com `X-API-Key` válida → ok

7. **Cache de TTS funcionando**
   - requisição repetida com mesmo texto/voice_id deve ser mais rápida (cache HIT)

8. **Logging rastreável**
   - response inclui `X-Request-ID`
   - logs JSON incluem `request_id`

