#!/bin/bash
set -e

echo "📦 Iniciando serviço ATTI Media Server (produção)"

cd /app

# Diagnóstico rápido (opcional, mas ajuda nos logs)
echo "🔧 Verificando imports críticos..."
python -c "import chromadb; print('✅ chromadb OK')"
python -c "import onnxruntime; print(f'✅ onnxruntime {onnxruntime.__version__} OK')"

echo "📥 Executando ingestão de conhecimento (pode levar 1-2 minutos)..."
python /app/scripts/worker_ingest_buildtime.py

echo "✅ Ingestão concluída. Iniciando servidor web..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
