# Integração Final — ATTI Media Server (Para o Manus)

Documento técnico detalhado de integração da infraestrutura com o pipeline de avatares.

---

## 1. O Que Foi Integrado

### Hooks substituídos em `atti_celery/tasks.py`

| Hook original (placeholder) | Implementação real |
|---|---|
| `_run_tts_pipeline()` | `XTTSEngineReal.synthesize()` + fallback `gTTS` |
| `_run_full_video_pipeline()` | `pipeline_real.generate_full_video()` ou pipeline modular |

### Novos módulos criados

| Arquivo | Responsabilidade |
|---|---|
| `src/tts/xtts_engine_real.py` | Motor XTTS v2 com voice registry e fallback gTTS |
| `src/avatar/viseme_sync.py` | Extração de visemas (energia + ZCR) e blend shapes |
| `src/avatar/liveportrait_engine_real.py` | Animação facial via LivePortrait |
| `src/media/pipeline_real.py` | Orquestração completa: TTS→visemas→frames→MP4 |
| `src/streaming/audio_stream.py` | Registro e serving de streams HTTP |
| `app/main.py` | API FastAPI com todos os endpoints integrados |

---

## 2. Como Executar os Testes Automatizados

```bash
# Tornar executável
chmod +x test_integracao.sh

# Executar testes (sobe containers, testa, derruba)
./test_integracao.sh

# Manter containers ao final (para inspecionar)
SKIP_STOP=true ./test_integracao.sh

# Timeout customizado (segundos para aguardar serviços)
TIMEOUT=120 ./test_integracao.sh
```

### O que o script testa:

1. **Build e startup** — containers sobem sem erro
2. **Healthcheck** — `GET /health` retorna `{"status":"ok"}`
3. **Listagem de vozes** — `GET /api/voices` retorna lista válida
4. **TTS síncrono** — `GET /api/stream-audio` gera arquivo WAV
5. **Autenticação** — sem key → 401, com key → 200
6. **Celery** — task enfileirada, status consultável
7. **Worker ativo** — logs indicam worker online
8. **Redis saudável** — `PING → PONG`

---

## 3. Como Verificar Logs

### Logs em tempo real via Docker

```bash
# API principal
docker compose logs -f atti-media-server

# Worker Celery
docker compose logs -f celery-worker

# Redis
docker compose logs -f redis

# Todos os serviços ao mesmo tempo
docker compose logs -f
```

### Logs em arquivo (JSON Lines)

```bash
# Dentro do container
docker compose exec atti-media-server tail -f /var/log/atti/atti.jsonl

# Com filtragem por request_id
docker compose exec atti-media-server \
  grep '"request_id":"SEU_ID"' /var/log/atti/atti.jsonl | python3 -m json.tool
```

### Formato do log JSON

```json
{
  "ts": 1710000000000,
  "level": "INFO",
  "logger": "app.main",
  "msg": "stream-audio | chars=25 | voice=default",
  "request_id": "abc123-uuid"
}
```

---

## 4. Como Monitorar a Fila Celery

### Ver workers ativos

```bash
docker compose exec celery-worker \
  celery -A atti_celery.worker inspect active
```

### Ver tasks na fila

```bash
docker compose exec celery-worker \
  celery -A atti_celery.worker inspect reserved
```

### Ver tasks agendadas

```bash
docker compose exec celery-worker \
  celery -A atti_celery.worker inspect scheduled
```

### Flower (interface web — opcional)

Adicione ao `docker-compose.yml`:
```yaml
  flower:
    image: mher/flower:2.0
    command: celery --broker=redis://redis:6379/0 flower --port=5555
    ports:
      - "5555:5555"
    depends_on: [redis]
```

Acesse em: `http://localhost:5555`

### Consultar status de uma task específica

```bash
# Via API
curl http://localhost:8000/api/task/SEU_TASK_ID

# Via Python
python3 -c "
from atti_celery.worker import celery_app
r = celery_app.AsyncResult('SEU_TASK_ID')
print(r.state, r.result)
"
```

---

## 5. Como Adicionar Novas Vozes ao Voice Registry

### Opção A: Arquivo de referência WAV

1. Grave ou baixe um arquivo WAV limpo (3–30 segundos, 22050 Hz, mono)
2. Copie para o volume de modelos:
   ```bash
   cp minha_voz.wav /models/voices/pt_br_custom01.wav
   ```
3. A voz aparecerá automaticamente em `GET /api/voices`

### Opção B: Variável de ambiente

```bash
# No .env, adicione:
XTTS_VOICE_PT_BR_CUSTOM01=/path/para/referencia.wav
```

### Opção C: Registro em código (`src/tts/xtts_engine_real.py`)

```python
_VOICE_REGISTRY: dict[str, str] = {
    "pt_br_custom01": "/models/voices/pt_br_custom01.wav",
    # ... adicione aqui
}
```

### Requisitos do arquivo de referência WAV:
- Duração: 3–30 segundos
- Sample rate: 22050 Hz (recomendado) ou 16000 Hz
- Canais: mono
- Formato: PCM 16-bit WAV
- Qualidade: sem ruído de fundo, voz clara e natural

---

## 6. Variáveis de Ambiente Importantes

| Variável | Default | Descrição |
|---|---|---|
| `ATTI_API_KEYS` | — | API keys válidas (separadas por vírgula) |
| `ATTI_ENV` | `local` | Ambiente (local/staging/prod) |
| `ATTI_LOG_LEVEL` | `INFO` | Nível de log (DEBUG/INFO/WARNING/ERROR) |
| `REDIS_URL` | `redis://redis:6379/0` | URL do Redis |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Broker Celery |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Backend de resultados |
| `ATTI_TTS_CACHE_TTL_SECONDS` | `86400` | TTL cache TTS (24h) |
| `ATTI_TTS_CACHE_MAX_BYTES` | `15728640` | Máx bytes cacheados (15MB) |
| `ATTI_MODELS_DIR` | `/models` | Diretório de modelos |
| `ATTI_OUTPUT_DIR` | `/tmp/atti_outputs` | Saída de vídeos |
| `ATTI_BASE_URL` | `http://localhost:8000` | URL base pública |
| `XTTS_MODEL_NAME` | `tts_models/multilingual/...` | Modelo XTTS |
| `XTTS_MODEL_PATH` | — | Path local pré-baixado do XTTS |
| `LIVEPORTRAIT_PATH` | `/opt/liveportrait` | Instalação do LivePortrait |
| `ATTI_S3_BUCKET` | — | Bucket S3/MinIO (opcional) |
| `ATTI_RATE_LIMIT_PUBLIC` | `100/hour` | Limite rate limiter público |
| `ATTI_RATE_LIMIT_GENERATE` | `30/hour` | Limite rate limiter geração |

---

## 7. Estratégias de Fallback

O pipeline foi projetado para degradar graciosamente:

```
TTS:
  XTTSEngineReal disponível → alta qualidade, voice cloning
       ↓ fallback
  gTTS → qualidade básica, sem voice cloning

Visemas:
  Gentle aligner disponível → precisão fonética por fonema
       ↓ fallback
  Análise de energia/ZCR → visemas aproximados (sem GPU)

Animação:
  LivePortrait disponível + imagem do avatar → animação facial realista
       ↓ fallback
  Vídeo preto com áudio → funcional, sem visual

Pipeline completo:
  pipeline_real.generate_full_video() → caminho ideal
       ↓ fallback
  Pipeline modular (TTS + visemas + LivePortrait separados)
```

---

## 8. Deploy em Produção

### Checklist pré-produção

- [ ] `ATTI_API_KEYS` configurado com chave forte (`openssl rand -hex 32`)
- [ ] `ATTI_ENV=production` no `.env`
- [ ] Volume `models-cache` apontando para SSD rápido
- [ ] GPU disponível para XTTS e LivePortrait (`nvidia-docker` ou `device_requests`)
- [ ] `ATTI_S3_BUCKET` configurado para armazenamento de artefatos
- [ ] Reverse proxy (nginx/Traefik) na frente do uvicorn
- [ ] Rate limits ajustados (`ATTI_RATE_LIMIT_*`)
- [ ] Logrotate configurado e testado
- [ ] Alertas de healthcheck configurados (Prometheus/Grafana ou UptimeRobot)

### Adicionar GPU ao docker-compose (NVIDIA)

```yaml
services:
  atti-media-server:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 9. Troubleshooting

| Sintoma | Causa provável | Solução |
|---|---|---|
| `503` em todos os endpoints protegidos | `ATTI_API_KEYS` vazio | Configure no `.env` |
| Task Celery sempre `PENDING` | Worker não conectou ao Redis | `docker compose logs celery-worker` |
| `XTTSEngineReal` falhou ao inicializar | Modelos não baixados / sem GPU | Verifique `XTTS_MODEL_PATH` ou aguarde download |
| `LivePortrait` não encontrado | `LIVEPORTRAIT_PATH` incorreto | Configure variável e instale dependências |
| Áudio gerado vazio | gTTS sem conexão de rede | Verifique conectividade do container |
| `redis.exceptions.ConnectionError` | Redis não subiu | `docker compose ps` → verificar healthcheck |
| Visemas todos `"rest"` | librosa não instalado | `pip install librosa` |
