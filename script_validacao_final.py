import chromadb
import os
import json

client = chromadb.PersistentClient(path='/tmp/chroma_db')
print("--- VALIDAÇÃO DE COLEÇÕES (PÓS-SWAP) ---")
avatares = ['sofia','rafael','clara','lucas','amanda','fernanda','marina','roberto','luisa','lais','paula','bruno_giovana','marcos_carol']
for av in avatares:
    try:
        col = client.get_collection(f'{av}_knowledge')
        print(f"✅ {av}: {col.count()} docs (OFICIAL)")
        try:
            old = client.get_collection(f'{av}_knowledge_old')
            print(f"   🛡️ Quarentena ativa: {old.count()} docs")
        except Exception:
            pass
    except Exception as e:
        print(f"❌ {av}: ERRO - {e}")

print("\n--- VALIDAÇÃO DE ARQUIVOS DE PERSONA ---")
manifest_path = '/tmp/atti-media-server/assets/personas_manifest.json'
if os.path.exists(manifest_path):
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Manifesto lido: {len(data.get('avatares', []))} avatares listados.")
else:
    print("❌ ERRO: personas_manifest.json não encontrado no path esperado.")

print("\n--- TESTE DO BRAIN MANAGER ---")
try:
    from src.brain_manager import BrainManager
    bm = BrainManager(base_dir="/tmp/atti-media-server/assets")
    print(f"BrainManager carregado com sucesso! Avatares em memória: {list(bm.personas_cache.keys())}")
    print(f"Greeting Sofia: {bm.get_greeting('sofia')}")
except Exception as e:
    print(f"❌ Erro no BrainManager: {e}")
