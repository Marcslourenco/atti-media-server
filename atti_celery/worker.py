"""atti_celery/worker.py

Configuração do Celery (MVP) usando Redis como broker e backend.

Este arquivo é importado por:
- Worker: celery -A atti_celery.worker celery_app worker ...
- API FastAPI: para enfileirar tasks e consultar status

Integração no seu app FastAPI (app/main.py):

    from atti_celery.worker import celery_app, create_task_status_router
    from atti_celery.tasks import generate_full_video, synthesize_long_tts

    # enfileirar
    task = generate_full_video.delay(payload_dict)

    # status
    result = celery_app.AsyncResult(task.id)
"""

from __future__ import annotations

import os
from typing import Any, Dict

from celery import Celery
from fastapi import APIRouter


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


CELERY_BROKER_URL = _env("CELERY_BROKER_URL", _env("REDIS_URL", "redis://localhost:6379/0"))
CELERY_RESULT_BACKEND = _env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")


celery_app = Celery(
    "atti_media",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["atti_celery.tasks"],
)


# Configurações base MVP
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,   # evita pegar muitos jobs e "prender" em 1 worker
    task_acks_late=True,            # ack só depois de finalizar (melhor p/ tarefas longas)
    broker_connection_retry_on_startup=True,
    # Rotas por fila
    task_routes={
        "atti_celery.tasks.generate_full_video": {"queue": "media"},
        "atti_celery.tasks.synthesize_long_tts": {"queue": "tts"},
    },
)


def task_status(task_id: str) -> Dict[str, Any]:
    """Retorna status padronizado de uma task."""

    res = celery_app.AsyncResult(task_id)

    payload: Dict[str, Any] = {
        "task_id": task_id,
        "state": res.state,
    }

    if res.successful():
        payload["result"] = res.result
    elif res.failed():
        payload["error"] = str(res.result)

    return payload


def create_task_status_router(prefix: str = "/api") -> APIRouter:
    """Cria um router FastAPI com o endpoint:

    GET {prefix}/task/{task_id}

    Uso no app/main.py:
        app.include_router(create_task_status_router())
    """

    router = APIRouter(prefix=prefix, tags=["tasks"])

    @router.get("/task/{task_id}")
    async def get_task(task_id: str) -> Dict[str, Any]:
        return task_status(task_id)

    return router
