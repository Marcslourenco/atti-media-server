# ─────────────────────────────────────────────────────────────
# Humanos Digitais TTS — Dockerfile
# Engine: Edge-TTS (custo zero, sem GPU necessária)
# Base: Python 3.11-slim (~120MB)
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

LABEL maintainer="humanosdigitais.com.br"
LABEL description="TTS API para 15 avatares PT-BR — edge-tts, custo zero"
LABEL version="2.0.0"

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Instalar dependências Python primeiro (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY main.py .

# Criar usuário não-root para segurança
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Porta
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Iniciar servidor (2 workers para Render free tier)
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--access-log"]
