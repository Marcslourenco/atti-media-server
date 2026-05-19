#!/bin/bash
set -e

echo "📦 Iniciando serviço ATTI Media Server (produção)"
echo "🔧 Verificando imports críticos..."

python3 -c "import chromadb; print('✅ chromadb OK')"
python3 -c "
import onnxruntime
print(f'✅ onnxruntime {onnxruntime.__version__} OK')
"

# Remove flag antiga se existir (deploy novo = ingestão nova)
rm -f /tmp/ingestion_complete
echo "🗑️ Flag de ingestão anterior removida"

# Inicia ingestão em background com wrapper que cria a flag
(
    echo "📥 Iniciando ingestão de conhecimento em background..."
    python3 scripts/worker_ingest_buildtime.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        touch /tmp/ingestion_complete
        echo "✅ Ingestão concluída — flag criada: /tmp/ingestion_complete"
    else
        echo "❌ Ingestão falhou com código: $EXIT_CODE — flag NÃO criada"
    fi
) &

echo "🚀 Iniciando servidor web (porta ${PORT:-8000})..."

# Uvicorn roda em FOREGROUND (processo principal)
# NÃO use & aqui — o container precisa de um processo principal
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --log-level info
