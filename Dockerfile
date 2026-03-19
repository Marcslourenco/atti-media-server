# syntax=docker/dockerfile:1

# ==========================================================
# Dockerfile (multi-stage) - ATTI Media Server
# ----------------------------------------------------------
# - Otimizado para builds rápidos (cache de deps)
# - Suporta projetos com requirements.txt OU pyproject.toml
# - Cria usuário não-root
# ==========================================================

ARG PYTHON_VERSION=3.11

# ---------- Stage 1: builder (instala dependências) ----------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Dependências de compilação (mantidas só no builder)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      git \
      curl \
    && rm -rf /var/lib/apt/lists/*

# (1) Copiamos SOMENTE manifests primeiro para maximizar cache
#     - Se você usa Poetry, mantenha pyproject.toml + poetry.lock
#     - Se você usa pip, mantenha requirements*.txt
COPY pyproject.toml poetry.lock* requirements*.txt* ./

# Criamos um venv "portável" para copiar no runtime
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Instalador (pip) e deps
RUN pip install --upgrade pip wheel setuptools

# Instala dependências com fallback:
# - Se existir requirements.txt -> usa pip
# - Se existir pyproject.toml com Poetry -> instala via pip (PEP517) ou Poetry (opcional)
# Observação: aqui evitamos depender do Poetry por padrão para simplificar.
RUN if [ -f requirements.txt ]; then \
      pip install -r requirements.txt; \
    elif [ -f pyproject.toml ]; then \
      pip install .; \
    else \
      echo "ERRO: Nenhum requirements.txt ou pyproject.toml encontrado" && exit 1; \
    fi

# ---------- Stage 2: runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Usuário não-root
RUN useradd -m -u 10001 appuser

# Diretórios padrão (modelos + logs)
RUN mkdir -p /models /var/log/atti && chown -R appuser:appuser /models /var/log/atti

WORKDIR /app

# Copia venv do builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia o código da aplicação
# Importante: este Dockerfile assume que, no seu repositório, existe app/main.py
COPY . /app

# ----------------------------------------------------------
# IMPORTANTE: evitar colisão de nome entre:
# - pacote oficial "celery" (pip)
# - diretório local "./celery" deste repo
#
# Se o diretório local se chamar "celery" na raiz do projeto,
# o import do Celery pode quebrar (shadowing).
# Para o MVP, renomeamos no container para "atti_celery".
# ----------------------------------------------------------
RUN if [ -d /app/celery ]; then mv /app/celery /app/atti_celery; fi

# Ajuste permissões (somente o necessário)
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Healthcheck simples (opcional) - depende de um endpoint /health (se existir)
# Se não existir, remova/ajuste.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

# O comando final é definido no docker-compose (uvicorn/celery)
