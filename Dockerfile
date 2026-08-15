FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN for i in 1 2 3 4 5; do pip install --no-cache-dir --timeout 120 -r requirements.txt && break || sleep 15; done

# Copiar todos os arquivos Python necessários
COPY main.py .
COPY i18n_engine.py .
COPY src/avatar/viseme_sync.py ./viseme_sync.py
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY knowledge/ ./knowledge/

# Copiar entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ============================================================================
# RUNTIME: INGESTÃO EM RUNTIME VIA ENTRYPOINT
# ============================================================================

# Expor porta
EXPOSE 8000

# Variáveis de ambiente
ENV KNOWLEDGE_MODE=runtime
ENV ALLOW_MISSING_AVATARS=true
ENV PORT=8000

# Usar entrypoint que verifica e ingere dados se necessário
ENTRYPOINT ["/entrypoint.sh"]
