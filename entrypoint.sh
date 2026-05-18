#!/bin/bash
set -e

echo "📦 Iniciando serviço ATTI Media Server (produção)"

cd /app

# Diagnóstico rápido (opcional, mas ajuda nos logs)
echo "🔧 Verificando imports críticos..."
python -c "import chromadb; print('✅ chromadb OK')"
python -c "import onnxruntime; print(f'✅ onnxruntime {onnxruntime.__version__} OK')"

# IMPORTANTE: Ingestão em background
# Uvicorn sobe IMEDIATAMENTE para que o Render detecte a porta
echo "📥 Iniciando ingestão de conhecimento em background..."
python /app/scripts/worker_ingest_buildtime.py > /tmp/ingestao.log 2>&1 &
INGEST_PID=$!
echo "  PID da ingestão: $INGEST_PID"

# Monitoramento de conclusão da ingestão em background
(
  wait $INGEST_PID
  EXIT_CODE=$?
  if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Ingestão concluída com sucesso (PID: $INGEST_PID)"
    # Criar arquivo de flag para indicar que ingestão foi concluída
    touch /tmp/ingestion_complete
    echo "✅ Flag de ingestão criada: /tmp/ingestion_complete"
  else
    echo "❌ Ingestão falhou com código: $EXIT_CODE (PID: $INGEST_PID)"
  fi
) &

echo "🚀 Iniciando servidor web (porta ${PORT:-8000})..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
