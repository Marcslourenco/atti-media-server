#!/usr/bin/env python3
import sys
import os
import resource
import traceback

# Força buffer de saída imediato
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("🚀 [MIN] Iniciando teste mínimo", flush=True)

# 1. Memória disponível
try:
    with open('/proc/meminfo', 'r') as f:
        meminfo = f.read()
    print("📊 [MIN] /proc/meminfo (linhas relevantes):", flush=True)
    for line in meminfo.split('\n'):
        if any(x in line for x in ['MemTotal', 'MemAvailable', 'MemFree']):
            print(f"    {line}", flush=True)
except Exception as e:
    print(f"⚠️ [MIN] Não foi ler /proc/meminfo: {e}", flush=True)

# 2. Import chromadb (sem onnxruntime por enquanto)
try:
    print("📦 [MIN] Importando chromadb...", flush=True)
    import chromadb
    print("✅ [MIN] chromadb importado", flush=True)
except Exception as e:
    print(f"❌ [MIN] Falha ao importar chromadb: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

# 3. Criar cliente ChromaDB em /tmp (persistente para teste)
CHROMA_PATH = "/tmp/chroma_db_minimo"
print(f"📂 [MIN] Criando PersistentClient em {CHROMA_PATH}", flush=True)
try:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # Tenta criar uma collection de teste
    col = client.get_or_create_collection(name="teste_minimo")
    col.add(documents=["Documento de teste"], ids=["1"])
    count = col.count()
    print(f"✅ [MIN] Collection criada, {count} documento(s)", flush=True)
    # Limpa
    client.delete_collection("teste_minimo")
    print("✅ [MIN] ChromaDB funcionando corretamente", flush=True)
except Exception as e:
    print(f"❌ [MIN] Erro no ChromaDB: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

print("🎉 [MIN] TESTE MÍNIMO PASSOU. Ambiente OK.", flush=True)
sys.exit(0)
