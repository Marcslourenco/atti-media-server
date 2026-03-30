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
COPY viseme_sync.py .
COPY src/ ./src/

# Expor porta
EXPOSE 5000

# Comando para rodar
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
