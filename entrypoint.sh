#!/bin/bash
set -e

echo "🔧 MODO DIAGNÓSTICO - Teste mínimo"
cd /app

# Roda o script mínimo
python /app/scripts/ingest_minimo.py

# Se passou, então o problema está no worker_ingest_buildtime.py
echo ""
echo "✅ Script mínimo passou. Agora vamos testar o worker original com import isolado de onnxruntime"
echo ""

# Teste isolado de onnxruntime (causa mais provável de OOM)
python -c "
import sys, os
sys.stdout.reconfigure(line_buffering=True)
print('Testando import de onnxruntime...', flush=True)
try:
    import onnxruntime
    print(f'✅ onnxruntime versão: {onnxruntime.__version__}', flush=True)
except Exception as e:
    print(f'❌ onnxruntime falhou: {e}', flush=True)
    import traceback; traceback.print_exc()
    sys.exit(1)
"

echo "✅ Import do onnxruntime OK. Agora testando worker_ingest_buildtime.py com timeout de 10s"
timeout 10s python /app/scripts/worker_ingest_buildtime.py 2>&1 || echo "❌ Worker falhou ou timeout"

# Mantém o container vivo para inspeção (opcional)
echo "🔍 Diagnóstico concluído. Mantendo container vivo por 1 hora para logs..."
sleep 3600
