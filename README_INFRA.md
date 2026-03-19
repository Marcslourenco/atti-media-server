# ATTI Media Server — Infra MVP (Fases 2–4 priorizando essencial)

## Visão geral
Este pacote adiciona **robustez, segurança e deploy simples** ao pipeline de avatares que vocês já têm funcional.

Componentes incluídos (MVP):
- Docker Compose orquestrando: **FastAPI**, **Redis/Valkey**, **Celery Worker** e **Postgres opcional**
- Fila assíncrona com **Celery + Redis/Valkey**
- **Rate limiting** por IP com `slowapi`
- **Autenticação por API Key** (header `X-API-Key`) para endpoints de geração
- **Cache de TTS** em Redis com TTL 24h
- **Logging estruturado (JSON)** + **request_id** e **logrotate**

> Tudo com ferramentas open-source com licença amigável (Redis, Celery, FastAPI, SlowAPI, Postgres, Alpine + logrotate).

---

## 1) Como usar (local) com Docker Compose

### Pré-requisitos
- Docker + Docker Compose (plugin)

### Dependências Python (no seu projeto)
Garanta que seu `requirements.txt`/`pyproject.toml` inclua (mínimo):
- `fastapi`
- `uvicorn`
- `celery`
- `redis` (redis-py)
- `slowapi`

> Observação: este pacote entrega os arquivos de infra e módulos utilitários; a instalação das dependências Python ocorre no build do seu container.

### Passos
1. Copie `.env.example` para `.env` e ajuste:
   - `ATTI_API_KEYS` (obrigatório para endpoints protegidos)

2. Suba o stack:
```bash
docker-compose up --build
```

3. A API sobe em:
- `http://localhost:8000`

---

## 2) Healthcheck (atenção)
O `Dockerfile` inclui um `HEALTHCHECK` chamando `GET /health`.

- Se seu app **já** possui `/health`, está ok.
- Se **não** possui, você pode:
  1) implementar um endpoint `/health` simples, **ou**
  2) remover/ajustar o `HEALTHCHECK` do `Dockerfile`.

## 3) Volumes importantes (persistência)
- **models-cache** → montado em `/models`
  - objetivo: não baixar modelos toda vez
- **logs-data** → montado em `/var/log/atti`
  - logs em JSONL + rotação via `logrotate`
- **redis-data** → persistência Redis (AOF)
- **postgres-data** → persistência Postgres (se habilitado)

---

## 4) Celery + Redis/Valkey (fila)

### Worker
O worker é iniciado pelo `docker-compose` com:
- filas: `media`, `tts`
- concorrência: `CELERY_CONCURRENCY` (default: 2)

### Tasks implementadas
Arquivos:
- `celery/tasks.py` (renomeado para `atti_celery/` dentro do container)
  - `generate_full_video(payload)`
  - `synthesize_long_tts(payload)`

> **IMPORTANTE:** as funções `_run_tts_pipeline` e `_run_full_video_pipeline` estão como *hooks*.
> Você deve trocar pelos imports/chamadas do pipeline real.

---

## 5) Endpoint de status da task
Arquivo `celery/worker.py` expõe helper `create_task_status_router()`.

### Como integrar no seu FastAPI
No seu `app/main.py` (exemplo):
```python
from fastapi import FastAPI

from logging.logger import init_logging, RequestIdMiddleware
from atti_celery.worker import create_task_status_router

init_logging()
app = FastAPI()
app.add_middleware(RequestIdMiddleware)

# Status endpoint
app.include_router(create_task_status_router(prefix="/api"))
```

Isso cria:
- `GET /api/task/{task_id}`

---

## 6) Rate limiting (SlowAPI)

### Dependência
Adicione ao seu projeto:
- `slowapi`

### Integração (exemplo)
Este pacote já inclui o helper `auth/rate_limit.py`.

```python
import os
from fastapi import FastAPI

from auth.rate_limit import init_rate_limiter

app = FastAPI()
limiter = init_rate_limiter(app)

@app.get("/public")
@limiter.limit(os.getenv("ATTI_RATE_LIMIT_PUBLIC", "100/hour"))
async def public_endpoint():
    return {"ok": True}
```

Recomendação MVP:
- endpoints públicos: `100/hour`
- endpoints de geração: além de API key, aplicar um limite menor (ex: `30/hour`).

---

## 7) Autenticação via API Key (MVP)

### Dependência
- `fastapi` (já existe)

### Como gerar uma chave
Use um desses métodos:

**Opção A (openssl):**
```bash
openssl rand -hex 32
```

**Opção B (python):**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Adicione no `.env`:
```env
ATTI_API_KEYS=cole_a_chave_aqui
```

### Como proteger endpoints de geração
```python
from fastapi import Depends
from auth.api_key import require_api_key

@app.post("/api/generate", dependencies=[Depends(require_api_key)])
async def generate(...):
    ...
```

Cliente deve enviar:
- Header: `X-API-Key: <sua-chave>`

---

## 8) Cache de TTS (Redis/Valkey)
Implementado em `redis/cache_config.py`.

Estratégia:
- chave: hash de `{text, voice_id, params}`
- TTL: `ATTI_TTS_CACHE_TTL_SECONDS` (default 86400)

No MVP, `celery/tasks.py` já tenta reaproveitar cache antes de sintetizar.

---

## 9) Logging estruturado (JSON) + request_id
Arquivo: `logging/logger.py`

O middleware:
- lê `X-Request-ID` ou gera UUID
- devolve `X-Request-ID` no response

Logs:
- stdout (Docker)
- arquivo: `/var/log/atti/atti.jsonl` (volume `logs-data`)

### Rotação de logs
- serviço `logrotate` no compose
- config em `logrotate/atti`

---

## 10) Postgres (opcional)
Para subir com Postgres:
```bash
docker-compose --profile with-postgres up --build
```

Configure `DATABASE_URL` no `.env` (exemplo no `.env.example`).

---

## Melhorias futuras (não prioritárias / fora do MVP)
- WebRTC
- Observabilidade completa (Prometheus/Grafana)
- Clusterização/Kubernetes
- Storage para artefatos (S3/MinIO) + cache de URL em vez de bytes

