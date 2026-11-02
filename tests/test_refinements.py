import json
import sys
import types
from pathlib import Path

import pytest

if "httpx" not in sys.modules:
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.AsyncClient = type("AsyncClient", (), {})
    sys.modules["httpx"] = httpx_stub
if "jsonschema" not in sys.modules:
    jsonschema_stub = types.ModuleType("jsonschema")
    jsonschema_stub.Draft7Validator = type(
        "Draft7Validator",
        (),
        {"__init__": lambda self, *args, **kwargs: None, "iter_errors": lambda self, *args, **kwargs: []},
    )
    sys.modules["jsonschema"] = jsonschema_stub

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # noqa: E402
from src.llm_engine import detect_language  # noqa: E402


def test_marcos_carol_manifest_is_corinthians():
    manifest = json.loads(Path("assets/personas_manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["avatares"] if item["avatar_id"] == "marcos_carol")
    persona = json.loads(Path("assets/persona_marcos_carol.json").read_text(encoding="utf-8"))
    assert entry["segmento_cliente"] == "generico_com_vies_futebol_corinthians"
    assert persona["segmento_cliente"] == "generico_com_vies_futebol_corinthians"


def test_spanish_detection_and_tts_connective_cleanup():
    assert detect_language("¿Te gusta Maradona?") == "es"
    assert " Y " not in main.sanitize_for_tts("rápida Y adaptable", "es")
    assert " Y " in main.sanitize_for_tts("rápida Y adaptable", "pt-BR")


@pytest.mark.asyncio
async def test_send_endpoint_dispatches_catalog_immediately(monkeypatch):
    calls = []

    async def fake_catalog(phone, tenant_id="default"):
        calls.append((phone, tenant_id))
        return {"success": True, "message_id": "wamid.catalog-immediate"}

    monkeypatch.setattr(main, "send_catalog_for_phone", fake_catalog)
    result = await main.send_whatsapp(
        main.WhatsAppRequest(
            phone_number="5514981123802",
            message="Quero receber o catálogo digital",
        )
    )
    assert result["success"] is True
    assert result["method"] == "catalog_document"
    assert result["message_id"] == "wamid.catalog-immediate"
    assert calls == [("5514981123802", "default")]
