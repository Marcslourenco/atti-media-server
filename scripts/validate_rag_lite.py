#!/usr/bin/env python3
"""
Validação LEVE do RAG - sem carregar embeddings
Apenas verifica estrutura de dados e ingestão
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

print("="*80)
print("VALIDAÇÃO LEVE DO RAG (SEM EMBEDDINGS)")
print("="*80)

# Verificar estrutura de conhecimento
knowledge_dir = Path("./knowledge")
print(f"\n📁 Diretório de conhecimento: {knowledge_dir.absolute()}")
print(f"   Existe: {knowledge_dir.exists()}")

if not knowledge_dir.exists():
    print("❌ ERRO: Diretório de conhecimento não encontrado!")
    sys.exit(1)

# Contar arquivos por avatar
print("\n📊 INGESTÃO DE DADOS")
print("-" * 80)

avatars_data = {}
total_files = 0
total_lines = 0

for avatar_dir in sorted(knowledge_dir.iterdir()):
    if not avatar_dir.is_dir():
        continue
    
    avatar_id = avatar_dir.name
    json_files = list(avatar_dir.glob("*.json"))
    
    if not json_files:
        continue
    
    file_count = len(json_files)
    total_files += file_count
    
    # Contar linhas
    lines = 0
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines += len(content.split('\n'))
                total_lines += len(content.split('\n'))
        except:
            pass
    
    avatars_data[avatar_id] = {
        'files': file_count,
        'lines': lines,
        'status': '✅ OK' if file_count > 0 else '❌ VAZIO'
    }
    
    print(f"| {avatar_id:10} | {file_count:3} arquivos | {lines:5} linhas | {avatars_data[avatar_id]['status']} |")

print("-" * 80)
print(f"TOTAL: {total_files} arquivos | {total_lines} linhas")

# Validar estrutura
print("\n🔍 VALIDAÇÃO DE ESTRUTURA")
print("-" * 80)

approved = 0
for avatar_id, data in avatars_data.items():
    if data['files'] > 0:
        approved += 1
        print(f"✅ {avatar_id}: {data['files']} arquivos")
    else:
        print(f"❌ {avatar_id}: SEM DADOS")

print(f"\n✅ Avatares com dados: {approved}/{len(avatars_data)}")

# Gate final
print("\n" + "="*80)
print("GATE FINAL")
print("="*80)

if approved >= len(avatars_data) * 0.8:
    print("🚀 APROVADO PARA DEPLOY")
    print(f"   - {approved}/{len(avatars_data)} avatares com dados")
    print(f"   - {total_files} arquivos JSON")
    print(f"   - {total_lines} linhas de conhecimento")
    sys.exit(0)
else:
    print("🚫 REPROVADO")
    print(f"   - Apenas {approved}/{len(avatars_data)} avatares com dados")
    sys.exit(1)
