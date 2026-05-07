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

# ============================================================================
# FASE BUILD-TIME: INGESTÃO OFFLINE COM VALIDAÇÃO EM CADEIA
# ============================================================================

# DIAGNÓSTICO PRÉ-BUILD
RUN echo "=== DIAGNÓSTICO PRÉ-BUILD ===" && \
    echo "Working dir: $(pwd)" && \
    echo "Listando knowledge:" && ls -la ./knowledge/ && \
    echo "Contando arquivos por avatar:" && \
    for avatar in sofia clara lucas amanda fernanda marina roberto luisa lais paula rafael bruno_giovana marcos_carol; do \
        if [ -d "./knowledge/$avatar" ]; then \
            count=$(find ./knowledge/$avatar -type f | wc -l); \
            echo "✅ $avatar: $count arquivos"; \
        else \
            echo "❌ $avatar: NÃO ENCONTRADO"; \
        fi \
    done

# Executar worker de ingestão (build-time only)
RUN echo "🔧 Iniciando ingestão offline..." && \
    python scripts/worker_ingest_buildtime.py || (echo "❌ ERRO NA INGESTÃO"; exit 1) && \
    echo "✅ Ingestão offline concluída"

# Executar validação pós-build
RUN echo "🔍 Validando ChromaDB..." && \
    python scripts/validate_ingest.py || (echo "❌ ERRO NA VALIDAÇÃO"; exit 1) && \
    echo "✅ Build com RAG pré-indexado concluído"

# ============================================================================
# RUNTIME: SEM INGESTÃO, APENAS LEITURA
# ============================================================================

# Expor porta
EXPOSE 5000

# Variáveis de ambiente para indicar modo runtime
ENV KNOWLEDGE_MODE=runtime
ENV ALLOW_MISSING_AVATARS=true

# Comando para rodar (SEM ingestão em runtime)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
