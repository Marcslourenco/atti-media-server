# ATTI Media Server — Integrado

## Visão Geral

Pacote final com a infraestrutura Docker/Celery/Redis **totalmente integrada** com os módulos reais do pipeline de avatares:

| Módulo | Arquivo |
|---|---|
| TTS (Síntese de Voz) | `src/tts/xtts_engine_real.py` |
| Visemas / Lip Sync | `src/avatar/viseme_sync.py` |
| Animação Facial | `src/avatar/liveportrait_engine_real.py` |
| Pipeline Completo | `src/media/pipeline_real.py` |
| Streaming de Áudio | `src/streaming/audio_stream.py` |
| API FastAPI | `app/main.py` |
| Tasks Celery | `atti_celery/tasks.py` |

---

## Estrutura de Arquivos

```
atti-media-server-integrado/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── app/
│   └── main.py                  ← FastAPI: todos os endpoints
├── atti_celery/
│   ├── __init__.py
│   ├── worker.py                ← Configuração Celery + router de status
│   └── tasks.py                 ← Tasks integradas com pipeline real
├── redis/
│   └── cache_config.py          ← Cache TTS Redis (TTL 24h)
├── auth/
│   ├── api_key.py               ← Autenticação X-API-Key
│   └── rate_limit.py            ← Rate limiting SlowAPI
├── logging_atti/
│   └── logger.py                ← Logging JSON + RequestIdMiddleware
├── logrotate/
│   └── atti                     ← Rotação de logs diária (7 arquivos)
├── src/
│   ├── tts/
│   │   └── xtts_engine_real.py  ← XTTS v2 + fallback gTTS
│   ├── avatar/
│   │   ├── viseme_sync.py       ← Extração de visemas + blend shapes
│   │   └── liveportrait_engine_real.py ← Animação facial LivePortrait
│   ├── media/
│   │   └── pipeline_real.py     ← Pipeline completo: TTS→visemas→avatar→MP4
│   └── streaming/
│       └── audio_stream.py      ← Streaming HTTP de áudio
├── test_integracao.sh           ← Testes automatizados
├── README_FINAL.md              ← Este arquivo
└── INTEGRACAO_FINAL.md          ← Guia detalhado para o Manus
```

---

## Início Rápido

```bash
# 1. Copiar variáveis de ambiente
cp .env.example .env

# 2. Gerar API key e configurar
echo "ATTI_API_KEYS=$(openssl rand -hex 32)" >> .env

# 3. Subir todos os serviços
docker compose up --build

# 4. Testar
curl http://localhost:8000/health
curl http://localhost:8000/api/voices
```

---

## Endpoints Disponíveis

| Método | Endpoint | Autenticação | Descrição |
|---|---|---|---|
| GET | `/health` | Não | Healthcheck |
| GET | `/api/voices` | Não | Lista vozes disponíveis |
| GET | `/api/stream-audio?texto=...` | Não | TTS síncrono (curto) |
| POST | `/api/avatar/speak` | X-API-Key | Gera vídeo completo (Celery) |
| POST | `/api/tts/async` | X-API-Key | TTS assíncrono (Celery) |
| GET | `/api/task/{task_id}` | Não | Status de task Celery |
| GET | `/outputs/{filename}` | Não | Serve vídeos gerados |
| GET | `/stream/{filename}` | Não | Serve streams de áudio |

---

## Pré-requisitos de Modelos

### XTTS v2
```bash
# Os modelos são baixados automaticamente pelo TTS na primeira execução.
# Para pré-baixar manualmente:
python3 -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

### LivePortrait
```bash
git clone https://github.com/KwaiVGI/LivePortrait /opt/liveportrait
pip install -r /opt/liveportrait/requirements.txt
# Configure no .env:
echo "LIVEPORTRAIT_PATH=/opt/liveportrait" >> .env
```

### Vozes de Referência (Voice Cloning)
Coloque arquivos WAV (3–30s, 22050Hz) em `/models/voices/`:
```
/models/voices/
├── pt_br_01.wav   ← voz Ana (PT-BR)
├── pt_br_02.wav   ← voz Carlos (PT-BR)
└── default.wav    ← voz padrão
```

---

## Dependências Python

Todas declaradas em `requirements.txt`. Principais:

```
fastapi, uvicorn, celery, redis, slowapi
TTS>=0.22.0 (XTTS), gtts (fallback)
torch, torchvision, torchaudio
numpy, scipy, librosa, opencv-python
```
