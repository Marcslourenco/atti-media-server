import logging
from main import sanitize_for_tts

logging.basicConfig(level=logging.INFO)

entrada = "O CPF é 123.456.789-00 e o suporte é 24/7. Acesse https://humanosdigitais.com.br ou mande email para contato@humanosdigitais.com.br."
saida = sanitize_for_tts(entrada)

print(f"--- TESTE FONÉTICO ---")
print(f"ENTRADA: {entrada}")
print(f"SAÍDA  : {saida}")
