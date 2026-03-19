"""logging_atti/logger.py

Logging estruturado (JSON) + Request ID para rastreamento.

ATENÇÃO: Módulo renomeado de 'logging/logger.py' para 'logging_atti/logger.py'
para evitar shadowing do módulo padrão logging do Python.

Requisitos MVP:
- JSON em stdout (bom para Docker) e em arquivo (/var/log/atti/atti.jsonl)
- request_id por requisição (header X-Request-ID, gerado se ausente)
- Propagação simples para tasks Celery (passar request_id como argumento)

Como integrar no FastAPI (app/main.py):

    from logging_atti.logger import init_logging, RequestIdMiddleware

    init_logging()
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Contexto por-request para request_id
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_ctx.get()


class JsonFormatter(logging.Formatter):
    """Formatter JSON minimalista (sem dependências externas)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": int(time.time() * 1000),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)

        return json.dumps(payload, ensure_ascii=False)


class RequestIdFilter(logging.Filter):
    """Anexa request_id a cada log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def init_logging() -> None:
    """Inicializa logging para app e worker.

    - stdout: sempre (Docker-friendly)
    - arquivo: opcional (ATTI_LOG_DIR, default /var/log/atti)

    Observação:
    - Uvicorn tem log próprio. Para MVP, os logs da aplicação
      já ficam padronizados em JSON.
    """
    level_name = os.getenv("ATTI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Evita duplicar handlers (import múltiplo)
    if root.handlers:
        return

    formatter = JsonFormatter()
    req_filter = RequestIdFilter()

    # ── stdout ─────────────────────────────────────────────────────────
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    sh.addFilter(req_filter)
    root.addHandler(sh)

    # ── arquivo (para logrotate) ───────────────────────────────────────
    log_dir = os.getenv("ATTI_LOG_DIR", "/var/log/atti")
    try:
        os.makedirs(log_dir, exist_ok=True)
        fh_path = os.path.join(log_dir, "atti.jsonl")
        fh = logging.FileHandler(fh_path)
        fh.setLevel(level)
        fh.setFormatter(formatter)
        fh.addFilter(req_filter)
        root.addHandler(fh)
    except Exception:
        root.warning(
            "Não foi possível inicializar FileHandler em ATTI_LOG_DIR",
            exc_info=True,
        )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware que garante request_id e devolve no response.

    - Usa X-Request-ID enviado pelo cliente, se existir
    - Caso contrário, gera UUID4
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_ctx.set(rid)
        try:
            response: Response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = rid
        return response
