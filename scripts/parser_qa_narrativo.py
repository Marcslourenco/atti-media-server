"""
Parser Q/A + Narrativo para melhorar scores de retrieval
Detecta automaticamente o tipo de documento e aplica o parser correto
"""

import re
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_qa_document(text: str, avatar_id: str) -> list:
    """
    Parser para documentos Q/A.
    Conteúdo vetorizado = resposta (A:).
    Pergunta (Q:) vira metadado para boost de retrieval.
    """
    chunks = []
    pattern = r'Q:\s*(.+?)\s*A:\s*(.+?)(?=Q:|$)'
    matches = re.findall(pattern, text, re.DOTALL)
    
    for question, answer in matches:
        answer_clean = answer.strip()
        if len(answer_clean) > 10:  # ignora respostas vazias/curtas
            chunks.append({
                "content": answer_clean,
                "metadata": {
                    "avatar_id": avatar_id,
                    "question_trigger": question.strip(),
                    "doc_type": "qa"
                }
            })
    
    logger.info(f"[Parser Q/A] avatar={avatar_id}: {len(chunks)} chunks extraídos")
    return chunks


def parse_narrative_document(text: str, avatar_id: str, chunk_size: int = 350, overlap: int = 70) -> list:
    """
    Parser para documentos narrativos (não Q/A).
    Usa chunking com overlap para preservar contexto.
    """
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        
        if len(chunk) > 30:
            chunks.append({
                "content": chunk,
                "metadata": {
                    "avatar_id": avatar_id,
                    "doc_type": "narrative"
                }
            })
        
        start += chunk_size - overlap
    
    logger.info(f"[Parser Narrativo] avatar={avatar_id}: {len(chunks)} chunks (chunk_size={chunk_size}, overlap={overlap})")
    return chunks


def detect_and_parse(text: str, avatar_id: str) -> list:
    """
    Detecta automaticamente o tipo de documento e aplica o parser correto.
    """
    is_qa = bool(re.search(r'Q:\s*.+?\s*A:\s*', text, re.DOTALL))
    
    if is_qa:
        return parse_qa_document(text, avatar_id)
    
    return parse_narrative_document(text, avatar_id)


# Teste
if __name__ == "__main__":
    # Teste Q/A
    qa_text = """Q: Qual é o seu horário de atendimento?
A: Atendemos segunda a sexta, das 9h às 18h.

Q: Como posso entrar em contato?
A: Você pode nos contatar por email, telefone ou através do formulário no site."""
    
    print("=== TESTE Q/A ===")
    result = detect_and_parse(qa_text, "sofia")
    print(f"Chunks: {len(result)}")
    for chunk in result:
        print(f"  - {chunk['content'][:60]}...")
    
    # Teste Narrativo
    narrative_text = """Sofia é uma assistente digital especializada em humanização de tecnologia. 
    Ela ajuda empresas a implementar soluções de atendimento ao cliente mais humanas e eficientes.
    Com mais de 5 anos de experiência em transformação digital, Sofia entende os desafios
    das organizações modernas e oferece soluções práticas e inovadoras."""
    
    print("\n=== TESTE NARRATIVO ===")
    result = detect_and_parse(narrative_text, "sofia")
    print(f"Chunks: {len(result)}")
    for chunk in result:
        print(f"  - {chunk['content'][:60]}...")
