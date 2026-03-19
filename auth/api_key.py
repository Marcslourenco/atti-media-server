"""auth/api_key.py

Autenticação simples por API Key para endpoints de geração (MVP).

- Recebe a chave via header: X-API-Key
- Chaves válidas são configuradas em ATTI_API_KEYS (separadas por vírgula)

Exemplo de uso no FastAPI:

    from fastapi import Depends
    from auth.api_key import require_api_key

    @app.post("/api/generate", dependencies=[Depends(require_api_key)])
    async def generate(...):
        ...

Observação de segurança:
- Para MVP, isso é suficiente.
- Futuro: trocar por JWT/OAuth2 + RBAC + auditoria.
"""

from __future__ import annotations

import os
from typing import Set

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_keys() -> Set[str]:
    raw = os.getenv("ATTI_API_KEYS", "").strip()
    if not raw:
        return set()
    # Normaliza e remove vazios
    return {k.strip() for k in raw.split(",") if k.strip()}


def require_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Dependency FastAPI: valida API Key.

    - Se ATTI_API_KEYS estiver vazio, bloqueamos por padrão para evitar exposição.
      (Você pode alterar a política se preferir "liberar" em local.)
    """

    valid = _load_keys()
    if not valid:
        raise HTTPException(status_code=503, detail="API keys não configuradas (ATTI_API_KEYS vazio).")

    if not api_key or api_key not in valid:
        raise HTTPException(status_code=401, detail="API key inválida.")

    return api_key
