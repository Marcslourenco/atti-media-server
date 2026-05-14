#!/bin/bash
set -e

echo "🔍 Verificando ambiente no Render..."
echo "Diretório atual: $(pwd)"
echo "Usuário: $(whoami)"
echo "Diretório /app/knowledge:"
ls -la /app/knowledge/ 2>&1 || echo "  (diretório não encontrado)"
echo "Diretório /app/scripts:"
ls -la /app/scripts/ 2>&1 | head -20

echo "🔍 Verificando ChromaDB..."
python -c "
import sys, os, traceback
sys.path.append(os.getcwd())
try:
    from src.chroma_engine import AvatarRAGEngine
    engine = AvatarRAGEngine()
    collections = list(engine.client.list_collections())
    print(f'✅ Collections encontradas: {len(collections)}')
    if len(collections) == 0:
        print('⚠️ Nenhuma collection. Iniciando ingestão...')
        sys.exit(1)
    else:
        sys.exit(0)
except Exception as e:
    print(f'❌ Erro ao verificar ChromaDB: {e}')
    traceback.print_exc()
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "📚 Ingerindo documentos (modo DEBUG)..."
    cd /app
    set -x
    python /app/scripts/worker_ingest_buildtime.py 2>&1
    set +x
    if [ $? -eq 0 ]; then
        echo "✅ Ingestão concluída com sucesso"
    else
        echo "❌ Ingestão falhou com código $?"
        exit 1
    fi
fi

echo "🚀 Iniciando servidor..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
