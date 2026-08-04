import re, sys
sys.path.insert(0, '.')

# Importar do main.py
import importlib.util
spec = importlib.util.spec_from_file_location("main", "main.py")

# Reimplementar sanitize_for_tts localmente
def sanitize_for_tts(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'#{1,6}', '', text)
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'___([^_]+)___', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'\`\`\`[^\`]*\`\`\`', '', text)
    text = re.sub(r'\`([^\`]+)\`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\([^)]{0,40}\)', '', text)
    text = re.sub(r'\(([^)]{41,})\)', r'\1', text)
    text = re.sub(r'[#*_~\`|>]', '', text)
    text = re.sub(r',{2,}', ', ', text)
    text = re.sub(r'\.{2,}', '. ', text)
    text = re.sub(r'!{2,}', '!', text)
    text = re.sub(r'\?{2,}', '?', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# Casos de teste
tests = [
    ('### Bem-vindo! **Olá** mundo.', 'Bem-vindo! Olá mundo.'),
    ('Veja [neste link](https://exemplo.com) o codigo', 'Veja neste link o codigo'),
    ('Olá (sistema) tudo bem (status: ok) e agora?', 'Olá tudo bem e agora?'),
    ('- Item 1\n- Item 2\n- Item 3', 'Item 1 Item 2 Item 3'),
    ('1. Numerado 1\n2. Numerado 2', 'Numerado 1 Numerado 2'),
    ('# Título **bold** *italic* `code`', 'Título bold italic code'),
    ('Texto com emoji e **negrito**', 'Texto com emoji e negrito'),
]

passed = 0
for i, (input_text, expected) in enumerate(tests, 1):
    result = sanitize_for_tts(input_text)
    ok = result == expected
    if ok:
        passed += 1
    status = 'PASS' if ok else 'FAIL'
    print(f'{status} Teste {i}: {result}')
    if not ok:
        print(f'  esperado: {expected}')

print(f'\n{passed}/{len(tests)} testes passaram')
