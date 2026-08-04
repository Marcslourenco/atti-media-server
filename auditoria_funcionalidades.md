# Auditoria Real de Funcionalidades Anunciadas

## Tabela de Evidências

| Funcionalidade | Existe código? | Existe rota? | Está ativa? | Evidência | Status real |
|---|---|---|---|---|---|
| Scraper de site | NÃO | NÃO | NÃO | Apenas referenciado em feature_catalog.py como "INVESTIGATING". Nenhum arquivo .py com implementação de scraper. | INVESTIGATING |
| PDF parsing | NÃO | NÃO | NÃO | Apenas referenciado em feature_catalog.py como "INVESTIGATING". Nenhum arquivo .py com implementação de PDF parser. | INVESTIGATING |
| RAG temporário por sessão | NÃO | NÃO | NÃO | Apenas referenciado em feature_catalog.py. Não há implementação de RAG por sessão. | INVESTIGATING |
| Onboarding WhatsApp | NÃO | NÃO | NÃO | Apenas referenciado em feature_catalog.py como "PLANNED". Nenhum arquivo .py com integração WhatsApp. | PLANNED |
| Captura de lead | NÃO | NÃO | NÃO | Apenas test_extracao.py (não é rota ativa). Sem endpoint de captura de lead. | PLANNED |
| Analytics dashboard | NÃO | NÃO | NÃO | Apenas referenciado em feature_catalog.py como "PLANNED". Sem dashboard implementado. | PLANNED |

## Funcionalidades VERIFICADAS como ATIVAS

| Funcionalidade | Existe código? | Existe rota? | Está ativa? | Evidência | Status real |
|---|---|---|---|---|---|
| Avatar conversacional | SIM | SIM | SIM | /api/avatar/speak retorna HTTP 200 | AVAILABLE |
| TTS + Visemes | SIM | SIM | SIM | /api/tts retorna audio_base64 + visemes | AVAILABLE |
| RAG por avatar | SIM | SIM | SIM | ChromaDB carregado, ingestão via worker | AVAILABLE |
| FAQ verbal | SIM | SIM | SIM | /api/avatar/speak com event_type=intro | AVAILABLE |
| Multi idioma | SIM | SIM | SIM | i18n_engine.py + /api/translate | AVAILABLE |
| TTS direto (sem RAG/LLM) | SIM | SIM | SIM | /api/tts-direct | AVAILABLE |
| Plataforma Humanos Digitais | SIM | SIM | SIM | humanosdigitais.com.br, feature_catalog | AVAILABLE |
| Onboarding gratuito | SIM | SIM | SIM | Mencionado no site e feature_catalog | AVAILABLE |
| Demonstração avatares | SIM | SIM | SIM | 15 avatares no /api/avatars | AVAILABLE |
