FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todos os arquivos Python necessários
COPY main.py .
COPY i18n_engine.py .
COPY src/avatar/viseme_sync.py ./viseme_sync.py
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY knowledge/ ./knowledge/

# FASE 2: Executar ingestão offline durante build
RUN echo "🔧 Iniciando ingestão offline..." && \
    python scripts/worker_ingest.py && \
    echo "✅ Ingestão concluída com sucesso"

# Expor porta
EXPOSE 5000

# Comando para rodar (SEM ingestão em runtime)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
