#!/bin/bash
# diagnostic.sh - Script de diagnóstico para encontrar o erro exato no Render

set -e

echo "================================================================================"
echo "🔍 DIAGNÓSTICO COMPLETO DO AMBIENTE"
echo "================================================================================"

# 1. Verificar diretório de trabalho
echo ""
echo "1️⃣  WORKING DIRECTORY:"
echo "   PWD: $(pwd)"
echo "   Conteúdo:"
ls -la | head -20

# 2. Verificar diretório knowledge
echo ""
echo "2️⃣  DIRETÓRIO KNOWLEDGE:"
if [ -d "./knowledge" ]; then
    echo "   ✅ ./knowledge encontrado"
    ls -la ./knowledge/ | head -15
else
    echo "   ❌ ./knowledge NÃO encontrado"
fi

if [ -d "/app/knowledge" ]; then
    echo "   ✅ /app/knowledge encontrado"
    ls -la /app/knowledge/ | head -15
else
    echo "   ❌ /app/knowledge NÃO encontrado"
fi

# 3. Verificar cada avatar individualmente
echo ""
echo "3️⃣  VERIFICANDO CADA AVATAR:"
for avatar in sofia clara lucas amanda fernanda marina roberto luisa lais paula rafael bruno_giovana marcos_carol; do
    if [ -d "./knowledge/$avatar" ]; then
        count=$(find ./knowledge/$avatar -type f 2>/dev/null | wc -l)
        echo "   ✅ $avatar: $count arquivos"
    elif [ -d "/app/knowledge/$avatar" ]; then
        count=$(find /app/knowledge/$avatar -type f 2>/dev/null | wc -l)
        echo "   ✅ $avatar (em /app): $count arquivos"
    else
        echo "   ❌ $avatar: DIRETÓRIO NÃO ENCONTRADO"
    fi
done

# 4. Verificar Python
echo ""
echo "4️⃣  AMBIENTE PYTHON:"
echo "   Python version: $(python3 --version)"
echo "   Pip version: $(pip3 --version)"

# 5. Verificar dependências críticas
echo ""
echo "5️⃣  DEPENDÊNCIAS CRÍTICAS:"
python3 -c "
import sys
deps = ['chromadb', 'sentence_transformers', 'psutil', 'pathlib']
for dep in deps:
    try:
        __import__(dep)
        print(f'   ✅ {dep}')
    except ImportError:
        print(f'   ❌ {dep} NÃO INSTALADO')
" || echo "   ❌ Erro ao verificar dependências"

# 6. Executar worker com trace completo
echo ""
echo "6️⃣  EXECUTANDO WORKER COM TRACE:"
export PYTHONTRACEMALLOC=1
cd /tmp/atti-media-server-onnx
timeout 600 python3 scripts/worker_ingest_buildtime.py 2>&1
EXIT_CODE=$?

echo ""
echo "7️⃣  EXIT CODE: $EXIT_CODE"
if [ $EXIT_CODE -ne 0 ]; then
    echo "   ❌ WORKER FALHOU COM EXIT CODE $EXIT_CODE"
else
    echo "   ✅ WORKER CONCLUÍDO COM SUCESSO"
fi

# 8. Verificar ChromaDB
echo ""
echo "8️⃣  VERIFICANDO CHROMADB:"
if [ -d "/tmp/chroma_db" ]; then
    echo "   ✅ ChromaDB criado em /tmp/chroma_db"
    ls -la /tmp/chroma_db/ | head -10
else
    echo "   ❌ ChromaDB NÃO criado em /tmp/chroma_db"
fi

# 9. Contar documentos no ChromaDB
echo ""
echo "9️⃣  CONTANDO DOCUMENTOS NO CHROMADB:"
python3 << 'PYTHON_EOF'
try:
    import chromadb
    client = chromadb.PersistentClient(path='/tmp/chroma_db')
    collections = client.list_collections()
    total = 0
    print(f"   Total de coleções: {len(collections)}")
    for coll in collections:
        count = coll.count()
        total += count
        print(f"   - {coll.name}: {count} docs")
    print(f"   TOTAL: {total} docs")
except Exception as e:
    print(f"   ❌ Erro ao contar documentos: {e}")
PYTHON_EOF

echo ""
echo "================================================================================"
echo "✅ DIAGNÓSTICO COMPLETO FINALIZADO"
echo "================================================================================"
