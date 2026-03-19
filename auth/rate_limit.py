"""auth/rate_limit.py

Rate limiting por IP usando SlowAPI (FastAPI).

Requisito MVP:
- Ex.: 100 requisições/hora para endpoints públicos

Este módulo fornece um helper para inicializar o limiter na aplicação.

Uso sugerido:

    import os
    from fastapi import FastAPI
    from auth.rate_limit import init_rate_limiter

    app = FastAPI()
    limiter = init_rate_limiter(app)

    @app.get("/public")
    @limiter.limit(os.getenv("ATTI_RATE_LIMIT_PUBLIC", "100/hour"))
    async def public():
        return {"ok": True}

"""

from __future__ import annotations

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def init_rate_limiter(app: FastAPI) -> Limiter:
    """Configura o Limiter no app e registra handler de erro.

    Retorna o objeto limiter para uso nos decorators.
    """

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return limiter
