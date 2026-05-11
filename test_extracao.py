import json
import glob

def test_extracao():
    """Testa se o script consegue extrair documentos de CADA avatar"""
    
    avatares_para_testar = [
        'sofia', 'clara', 'lucas', 'amanda', 
        'paula', 'bruno_giovana', 'marcos_carol', 'luisa',
        'giovana', 'carol', 'english'
    ]
    
    resultados = {}
    
    for avatar in avatares_para_testar:
        docs = []
        
        # Busca arquivos do avatar
        for json_file in glob.glob(f"**/{avatar}/**/*.json", recursive=True):
            print(f"Lendo: {json_file}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Usa IF (não elif) para capturar MÚLTIPLAS estruturas
                if 'nucleo_conhecimento' in data:
                    for key, values in data['nucleo_conhecimento'].items():
                        if isinstance(values, list):
                            for v in values:
                                if v and isinstance(v, str):
                                    docs.append(v)
                if 'items' in data:
                    for item in data['items']:
                        if isinstance(item, dict) and 'pergunta' in item:
                            docs.append(f"P: {item['pergunta']}\nR: {item.get('resposta_base', '')}")
                if 'clube' in data or 'arquetipo' in data:
                    docs.append(f"Clube: {data.get('clube', '')}")
                    docs.append(f"Arquétipo: {data.get('arquetipo', '')}")
                    docs.append(f"Descrição: {data.get('descricao_arquetipo', '')}")
                if 'faq_estruturado' in data:
                    for faq in data['faq_estruturado']:
                        if 'pergunta' in faq and 'resposta' in faq:
                            docs.append(f"P: {faq['pergunta']}\nR: {faq['resposta']}")

            except Exception as e:
                print(f"  ERRO: {e}")
        
        resultados[avatar] = {
            "arquivos_encontrados": len(glob.glob(f"**/{avatar}/**/*.json", recursive=True)),
            "documentos_extraidos": len(docs),
            "primeiro_doc": docs[0][:100] if docs else "NENHUM"
        }
        
        print(f"\n{avatar}:")
        print(f"  Arquivos: {resultados[avatar]['arquivos_encontrados']}")
        print(f"  Documentos extraídos: {resultados[avatar]['documentos_extraidos']}")
        print(f"  Amostra: {resultados[avatar]['primeiro_doc']}")
    
    print("\n=== RESUMO ===")
    for avatar, r in resultados.items():
        status = "✅" if r['documentos_extraidos'] > 0 else "❌"
        print(f"{status} {avatar}: {r['documentos_extraidos']} docs")
    
    return resultados

if __name__ == "__main__":
    test_extracao()
