#!/usr/bin/env python3
"""
Script de diagnóstico do ChromaDB para Humanos Digitais
Uso: python diagnosticar_chroma.py
Não requer intervenção manual - gera relatório completo.
"""
import json
import sys
import os
from datetime import datetime

def diagnosticar():
    print("=" * 70)
    print("🔍 DIAGNÓSTICO AUTOMÁTICO DO CHROMADB")
    print("=" * 70)
    
    try:
        # Tenta importar o AvatarRAGEngine do projeto
        sys.path.append(os.getcwd())
        from src.chroma_engine import AvatarRAGEngine
        engine = AvatarRAGEngine()
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: Não foi possível importar AvatarRAGEngine")
        print(f"   Erro: {e}")
        print("\n   Isso indica que o código não está encontrando o módulo.")
        print("   Solução: Rode este script a partir da RAIZ do projeto.")
        return False
    
    # 1. Verifica conexão
    print("\n📡 1. TESTANDO CONEXÃO COM CHROMADB...")
    try:
        # Tenta listar collections (melhor teste de conexão)
        collections = list(engine.client.list_collections())
        collection_names = [c.name for c in collections]
        print(f"   ✅ Conexão OK. Collections encontradas: {len(collections)}")
    except Exception as e:
        print(f"   ❌ Falha na conexão: {e}")
        print("   Isso explica o problema: ChromaDB não está respondendo.")
        return False
    
    # 2. Lista todas as collections
    print(f"\n📚 2. COLLECTIONS EXISTENTES: {collection_names if collection_names else 'NENHUMA'}")
    
    # 3. Avatares esperados
    avatares_esperados = [
        'lais', 'paula', 'bruno_giovana', 'sofia', 'clara', 'lucas',
        'amanda', 'marina', 'fernanda', 'rafael', 'marcos_carol',
        'luisa'
    ]
    
    # 4. Verifica cada avatar
    print("\n🔍 3. VERIFICANDO CADA AVATAR:")
    resultados = {}
    
    for avatar in avatares_esperados:
        collection_name = f"{avatar}_knowledge"
        if collection_name in collection_names:
            try:
                collection = engine.client.get_collection(collection_name)
                count = collection.count()
                # Pega uma amostra
                amostra = collection.get(limit=1)
                tem_documento = len(amostra.get('documents', [])) > 0 if amostra else False
                resultados[avatar] = {
                    "existe": True,
                    "documentos": count,
                    "tem_conteudo": tem_documento
                }
                status = "✅" if tem_documento else "⚠️"
                print(f"   {status} {avatar}: {count} documentos - {'TEM CONTEÚDO' if tem_documento else 'VAZIA'}")
            except Exception as e:
                resultados[avatar] = {"existe": True, "erro": str(e)}
                print(f"   ❌ {avatar}: erro ao acessar - {e}")
        else:
            resultados[avatar] = {"existe": False, "documentos": 0, "tem_conteudo": False}
            print(f"   ❌ {avatar}: NÃO EXISTE")
    
    # 5. DIAGNÓSTICO FINAL
    print("\n" + "=" * 70)
    print("📋 DIAGNÓSTICO FINAL")
    print("=" * 70)
    
    # Conta os problemas
    nao_existem = [a for a, r in resultados.items() if not r.get("existe", False)]
    existem_vazios = [a for a, r in resultados.items() if r.get("existe") and not r.get("tem_conteudo", False)]
    existem_com_dados = [a for a, r in resultados.items() if r.get("existe") and r.get("tem_conteudo", False)]
    
    print(f"\n📊 Resumo:")
    print(f"   Avatares que NÃO EXISTEM no ChromaDB: {len(nao_existem)}")
    print(f"   Avatares que EXISTEM mas estão VAZIOS: {len(existem_vazios)}")
    print(f"   Avatares com DADOS carregados: {len(existem_com_dados)}")
    
    # PROBLEMA RAIZ
    print(f"\n🎯 PROBLEMA IDENTIFICADO:")
    if len(nao_existem) > 0:
        print(f"   ❌ COLLECTIONS FALTANDO: {', '.join(nao_existem[:5])}{'...' if len(nao_existem) > 5 else ''}")
        print(f"\n   ➡ CAUSA: O processo de 'ingestão' (carregar documentos) NUNCA rodou.")
        print(f"   ➡ SOLUÇÃO: Executar o script de ingestão para criar e popular as collections.")
    elif len(existem_vazios) > 0:
        print(f"   ⚠️ COLLECTIONS VAZIAS: {', '.join(existem_vazios)}")
        print(f"\n   ➡ CAUSA: As collections foram criadas, mas nenhum documento foi adicionado.")
        print(f"   ➡ SOLUÇÃO: Executar o script de ingestão para POPULAR as collections.")
    else:
        print(f"   ✅ Todas as collections existem e têm documentos? {len(existem_com_dados)} de {len(avatares_esperados)}")
        if len(existem_com_dados) == len(avatares_esperados):
            print(f"   ✅ TUDO OK! O problema então é na RECUPERAÇÃO (query), não nos dados.")
        else:
            print(f"   ⚠️ Diagnóstico incompleto - algumas collections não foram verificadas.")
    
    # GERA RELATÓRIO JSON
    relatorio = {
        "data": datetime.now().isoformat(),
        "conexao_ok": True,
        "collections_encontradas": collection_names,
        "avatares_esperados": avatares_esperados,
        "resultados": resultados,
        "diagnostico": {
            "nao_existem": nao_existem,
            "existem_vazios": existem_vazios,
            "existem_com_dados": existem_com_dados,
            "problema_raiz": "FALTA_DE_INGESTAO" if (nao_existem or existem_vazios) else "PODE_SER_QUERY"
        }
    }
    
    # Salva arquivo
    with open("diagnostico_chroma.json", "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 Relatório completo salvo em: diagnostico_chroma.json")
    print("\n✅ Diagnóstico concluído. Este arquivo pode ser enviado ao time técnico.")
    
    return len(nao_existem) == 0 and len(existem_vazios) == 0

if __name__ == "__main__":
    sucesso = diagnosticar()
    sys.exit(0 if sucesso else 1)
