#!/bin/bash
# entrypoint.sh - Verificação e ingestão em runtime

set -e

echo "🔍 Verificando ChromaDB em produção..."

# Tenta conectar e verificar se há dados
python -c "
import sys
import os
sys.path.append(os.getcwd())
from src.chroma_engine import AvatarRAGEngine

try:
    engine = AvatarRAGEngine()
    collections = list(engine.client.list_collections())
    collection_names = [c.name for c in collections]
    
    if len(collection_names) == 0:
        print('⚠️ Nenhuma collection encontrada. Executando ingestão...')
        sys.exit(1)  # Sinaliza que precisa ingerir
    else:
        print(f'✅ {len(collection_names)} collections encontradas')
        sys.exit(0)
except Exception as e:
    print(f'❌ Erro ao verificar ChromaDB: {e}')
    sys.exit(1)
"

# Se não há dados, executa ingestão
if [ $? -ne 0 ]; then
    echo "📚 Ingerindo documentos no ChromaDB..."
    python scripts/worker_ingest_buildtime.py
    if [ $? -eq 0 ]; then
        echo "✅ Ingestão concluída com sucesso"
    else
        echo "❌ Erro durante ingestão"
        exit 1
    fi
fi

# Inicia o servidor principal
echo "🚀 Iniciando servidor..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
