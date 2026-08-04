import json
from pathlib import Path

EXPECTED_AVATARS = [
    'sofia', 'clara', 'lucas', 'amanda', 'fernanda',
    'marina', 'roberto', 'luisa', 'lais', 'paula',
    'rafael', 'bruno_giovana', 'marcos_carol',
    'giovana', 'carol'
]

running_total = 0
for avatar in EXPECTED_AVATARS:
    if avatar in ['giovana', 'carol']:
        continue  # herança
    avatar_dir = Path(f'knowledge/{avatar}')
    if not avatar_dir.exists():
        print(f'{avatar}: DIR NOT FOUND')
        continue
    json_files = list(avatar_dir.glob('*.json'))
    total = 0
    for jf in json_files:
        try:
            with open(jf) as f:
                data = json.load(f)
            docs = []
            if isinstance(data, dict):
                faq_list = data.get('faq_estruturado') or data.get('faq') or []
                if isinstance(faq_list, list):
                    for item in faq_list:
                        if isinstance(item, dict) and 'pergunta' in item and 'resposta' in item:
                            docs.append(item)
                if 'nucleo_conhecimento' in data and isinstance(data['nucleo_conhecimento'], dict):
                    nc = data['nucleo_conhecimento']
                    for key in ['problemas_comuns', 'objeções_clientes', 'argumentos_venda']:
                        if key in nc and isinstance(nc[key], list):
                            docs.extend(nc[key])
                if 'areas_tecnicas' in data and isinstance(data['areas_tecnicas'], list):
                    docs.extend(data['areas_tecnicas'])
                if 'items' in data and isinstance(data['items'], list):
                    docs.extend(data['items'])
            total += len(docs)
        except Exception as e:
            pass
    running_total += total
    print(f'{avatar}: ~{total} docs (running: {running_total})')

print()
print(f'Total geral (sem herança): ~{running_total} docs')
rafael_count = 807
before_rafael = running_total - rafael_count
print(f'Rafael: ~{rafael_count} docs')
print(f'Antes do Rafael: ~{before_rafael} docs')
print(f'Se 232 docs observados < {before_rafael}, ingestão parou ANTES do Rafael')
