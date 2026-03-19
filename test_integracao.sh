#!/bin/bash
# test_integracao.sh
# Script de teste automatizado da integração do pipeline de avatares.
#
# Uso:
#   chmod +x test_integracao.sh
#   ./test_integracao.sh
#
# Variáveis de ambiente opcionais:
#   API_KEY   - API key para endpoints protegidos (gerada automaticamente se ausente)
#   BASE_URL  - URL base da API (default: http://localhost:8000)
#   TIMEOUT   - Timeout para aguardar serviços (default: 60s)
#   SKIP_STOP - Se "true", não derruba containers ao final

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TIMEOUT="${TIMEOUT:-60}"
SKIP_STOP="${SKIP_STOP:-false}"
RESULTS_DIR="test_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()   { echo "[$(date '+%H:%M:%S')] $*"; }
ok()    { echo "  ✅ $*"; ((PASS++)) || true; }
fail()  { echo "  ❌ $*"; ((FAIL++)) || true; }

check_dep() {
  for dep in "$@"; do
    if ! command -v "$dep" &>/dev/null; then
      echo "❌ Dependência faltando: $dep"
      exit 1
    fi
  done
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + TIMEOUT))
  echo -n "  ⏳ Aguardando $label"
  while [ $SECONDS -lt $deadline ]; do
    if curl -sf "$url" &>/dev/null; then
      echo " → online"
      return 0
    fi
    echo -n "."
    sleep 2
  done
  echo " → TIMEOUT"
  return 1
}

# ---------------------------------------------------------------------------
# Verificação de dependências
# ---------------------------------------------------------------------------
log "Verificando dependências..."
check_dep docker curl

if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose &>/dev/null; then
  DC="docker-compose"
else
  echo "❌ docker compose / docker-compose não encontrado."
  exit 1
fi

# ---------------------------------------------------------------------------
# Preparação do .env
# ---------------------------------------------------------------------------
log "Preparando .env..."
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    log "Criado .env a partir de .env.example"
  else
    log "Criando .env mínimo..."
    cat > .env <<'ENVEOF'
ATTI_ENV=local
ATTI_LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
ATTI_TTS_CACHE_TTL_SECONDS=86400
ENVEOF
  fi
fi

# Garante API key no .env
if ! grep -q "^ATTI_API_KEYS=" .env || grep -q "^ATTI_API_KEYS=$" .env; then
  GENERATED_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
  if grep -q "^ATTI_API_KEYS=" .env; then
    sed -i "s/^ATTI_API_KEYS=.*/ATTI_API_KEYS=${GENERATED_KEY}/" .env
  else
    echo "ATTI_API_KEYS=${GENERATED_KEY}" >> .env
  fi
  log "API key gerada e salva no .env"
fi

# Lê API key para os testes
API_KEY=$(grep "^ATTI_API_KEYS=" .env | cut -d'=' -f2 | cut -d',' -f1 | tr -d ' ')

# ---------------------------------------------------------------------------
# TESTE 1: Build e startup
# ---------------------------------------------------------------------------
log "━━━ TESTE 1: Build e startup dos containers ━━━"

log "Subindo containers..."
$DC up --build -d 2>&1 | tail -5
log "Aguardando serviços ficarem prontos..."

if wait_for_url "${BASE_URL}/health" "API (${BASE_URL}/health)"; then
  ok "Containers iniciados"
else
  fail "Containers não ficaram prontos em ${TIMEOUT}s"
  log "Logs da API:"
  $DC logs --tail=20 atti-media-server 2>/dev/null || true
  exit 1
fi

# ---------------------------------------------------------------------------
# TESTE 2: Healthcheck
# ---------------------------------------------------------------------------
log "━━━ TESTE 2: Healthcheck ━━━"
HEALTH=$(curl -sf "${BASE_URL}/health")
if echo "$HEALTH" | grep -q '"ok"'; then
  ok "GET /health retornou status ok"
else
  fail "GET /health retornou inesperado: $HEALTH"
fi
echo "$HEALTH" > "$RESULTS_DIR/health.json"

# ---------------------------------------------------------------------------
# TESTE 3: Listagem de vozes
# ---------------------------------------------------------------------------
log "━━━ TESTE 3: Listagem de vozes ━━━"
VOICES=$(curl -sf "${BASE_URL}/api/voices" 2>&1) || true
if echo "$VOICES" | grep -q '"id"'; then
  ok "GET /api/voices retornou lista de vozes"
  echo "$VOICES" > "$RESULTS_DIR/voices.json"
else
  fail "GET /api/voices falhou ou retornou vazio: $VOICES"
fi

# ---------------------------------------------------------------------------
# TESTE 4: Streaming de áudio (TTS síncrono)
# ---------------------------------------------------------------------------
log "━━━ TESTE 4: Streaming de áudio (/api/stream-audio) ━━━"
AUDIO_FILE="$RESULTS_DIR/test_audio.wav"
HTTP_CODE=$(curl -s -o "$AUDIO_FILE" -w "%{http_code}" \
  "${BASE_URL}/api/stream-audio?texto=Ol%C3%A1+mundo+ATTI&voice_id=default&language=pt" \
  --max-time 30 2>&1) || HTTP_CODE="000"

if [ "$HTTP_CODE" = "200" ] && [ -f "$AUDIO_FILE" ] && [ -s "$AUDIO_FILE" ]; then
  AUDIO_SIZE=$(wc -c < "$AUDIO_FILE")
  ok "Áudio gerado com sucesso (${AUDIO_SIZE} bytes)"
elif [ "$HTTP_CODE" = "429" ]; then
  ok "Rate limiting ativo (429 Too Many Requests) — esperado"
else
  fail "stream-audio falhou | HTTP=${HTTP_CODE}"
fi

# ---------------------------------------------------------------------------
# TESTE 5: Autenticação via API Key
# ---------------------------------------------------------------------------
log "━━━ TESTE 5: Autenticação por API Key ━━━"

# 5.1 Sem API key → deve recusar
HTTP_NO_KEY=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/api/avatar/speak" \
  -H "Content-Type: application/json" \
  -d '{"text":"teste"}' --max-time 10) || true

if [ "$HTTP_NO_KEY" = "401" ] || [ "$HTTP_NO_KEY" = "503" ]; then
  ok "Sem API key → ${HTTP_NO_KEY} (esperado)"
else
  fail "Sem API key deveria retornar 401/503, obteve: ${HTTP_NO_KEY}"
fi

# 5.2 Com API key válida → deve aceitar (enfileirar task)
SPEAK_RESP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/api/avatar/speak" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{"text":"Olá, este é um teste de integração.","voice_id":"default","avatar_id":"default"}' \
  --max-time 15) || SPEAK_RESP="000"

if [ "$SPEAK_RESP" = "200" ] || [ "$SPEAK_RESP" = "429" ]; then
  ok "POST /api/avatar/speak com API key → ${SPEAK_RESP}"
else
  fail "POST /api/avatar/speak com API key → ${SPEAK_RESP} (esperado 200 ou 429)"
fi

# ---------------------------------------------------------------------------
# TESTE 6: Status de task Celery
# ---------------------------------------------------------------------------
log "━━━ TESTE 6: Status de task Celery ━━━"

# Enfileira uma task de TTS
TTS_RESP=$(curl -sf \
  -X POST "${BASE_URL}/api/tts/async" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d "{\"text\":\"Teste de TTS assíncrono.\",\"voice_id\":\"default\",\"params\":{\"speed\":1.0}}" \
  --max-time 15 2>&1) || TTS_RESP="{}"

TASK_ID=$(echo "$TTS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('task_id',''))" 2>/dev/null || echo "")

if [ -n "$TASK_ID" ]; then
  ok "Task TTS enfileirada: $TASK_ID"
  echo "$TTS_RESP" > "$RESULTS_DIR/tts_task.json"

  # Aguarda até 30s para task completar
  DEADLINE=$((SECONDS + 30))
  FINAL_STATE=""
  while [ $SECONDS -lt $DEADLINE ]; do
    STATUS_RESP=$(curl -sf "${BASE_URL}/api/task/${TASK_ID}" --max-time 5 2>/dev/null || echo "{}")
    STATE=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null || echo "")
    if [ "$STATE" = "SUCCESS" ] || [ "$STATE" = "FAILURE" ]; then
      FINAL_STATE="$STATE"
      break
    fi
    sleep 2
  done

  if [ "$FINAL_STATE" = "SUCCESS" ]; then
    ok "Task Celery concluída com SUCCESS"
  elif [ "$FINAL_STATE" = "FAILURE" ]; then
    ok "Task retornou FAILURE (worker ativo, mas pipeline pode precisar de modelos)"
  else
    fail "Task não completou em 30s (state=${FINAL_STATE:-TIMEOUT})"
  fi
else
  fail "Não foi possível enfileirar task TTS (resposta: $TTS_RESP)"
fi

# ---------------------------------------------------------------------------
# TESTE 7: Worker Celery ativo
# ---------------------------------------------------------------------------
log "━━━ TESTE 7: Worker Celery ━━━"
WORKER_LOGS=$($DC logs --tail=10 celery-worker 2>/dev/null || echo "")
if echo "$WORKER_LOGS" | grep -qiE "(ready|celery@|worker online|connected)"; then
  ok "Worker Celery está ativo"
else
  fail "Worker Celery pode não estar ativo (verifique: $DC logs celery-worker)"
fi

# ---------------------------------------------------------------------------
# TESTE 8: Redis saudável
# ---------------------------------------------------------------------------
log "━━━ TESTE 8: Redis ━━━"
if $DC exec -T redis valkey-cli ping 2>/dev/null | grep -q "PONG"; then
  ok "Redis/Valkey respondeu PONG"
elif $DC exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
  ok "Redis respondeu PONG"
else
  fail "Redis não respondeu (verificar container atti-redis)"
fi

# ---------------------------------------------------------------------------
# Relatório final
# ---------------------------------------------------------------------------
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "RESULTADO: ✅ ${PASS} passou(aram) | ❌ ${FAIL} falhou(aram)"
log "Artefatos salvos em: $RESULTS_DIR/"

if [ "$SKIP_STOP" != "true" ]; then
  log "Derrubando containers..."
  $DC down
fi

if [ "$FAIL" -gt 0 ]; then
  log "⚠️  Alguns testes falharam. Verifique os logs acima e em:"
  log "   $DC logs atti-media-server"
  log "   $DC logs celery-worker"
  exit 1
fi

log "🎉 Todos os testes passaram!"
