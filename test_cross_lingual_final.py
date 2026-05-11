from src.chroma_engine import AvatarRAGEngine
engine = AvatarRAGEngine()

testes = [
    ("sofia", "What is the difference between digital human and chatbot?"),
    ("lais", "How does medical internship work?"),
    ("rafael", "What is the ICMS tax rate?"),
]

print("=== TESTE CROSS-LINGUAL ===")
for avatar, pergunta in testes:
    resposta = engine.generate_response(pergunta, avatar)
    print(f"\nAvatar: {avatar}")
    print(f"Pergunta (EN): {pergunta}")
    print(f"Resposta: {resposta[:200] if resposta else 'VAZIO'}")
    # Verifica se a resposta está em inglês
    palavras_en = ['the', 'is', 'are', 'what', 'how', 'tax', 'rate', 'medical', 'internship']
    score = sum(1 for p in palavras_en if p.lower() in resposta.lower())
    print(f"Confiabilidade (EN): {'✅ BOA' if score > 2 else '⚠️ VERIFICAR'}")
