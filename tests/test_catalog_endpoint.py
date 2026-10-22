import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

# O sandbox pode não ter dependências opcionais do runtime; os stubs mantêm
# estes testes focados no endpoint e no serviço Meta, sem instalar pacotes.
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
from src.whatsapp_service import MetaWhatsAppService  # noqa: E402


@pytest.mark.asyncio
async def test_send_catalog_payload_and_response(monkeypatch):
    monkeypatch.setenv("CATALOG_PDF_URL", "https://raw.example/catalog-v1.pdf")
    captured = {}

    def fake_send_document(phone, url, caption, filename):
        captured.update(phone=phone, url=url, caption=caption, filename=filename)
        return {"success": True, "message_id": "wamid.catalog-test"}

    monkeypatch.setattr(main.meta_whatsapp_service, "send_document", fake_send_document)
    result = await main.send_catalog(main.CatalogRequest(phone_number="5514981123802", tenant_id="default"))

    assert result == {"success": True, "message_id": "wamid.catalog-test"}
    assert captured == {
        "phone": "5514981123802",
        "url": "https://raw.example/catalog-v1.pdf",
        "caption": "Olá! Aqui está o Catálogo Comercial da Humanos Digitais.",
        "filename": "Catalogo_Humanos_Digitais_2026.pdf",
    }


@pytest.mark.asyncio
async def test_send_catalog_without_url_returns_500(monkeypatch):
    monkeypatch.delenv("CATALOG_PDF_URL", raising=False)
    with pytest.raises(main.HTTPException) as error:
        await main.send_catalog(main.CatalogRequest(phone_number="5514981123802"))
    assert error.value.status_code == 500
    assert error.value.detail == "CATALOG_PDF_URL not configured"


@pytest.mark.asyncio
async def test_send_catalog_meta_failure_returns_502(monkeypatch):
    monkeypatch.setenv("CATALOG_PDF_URL", "https://raw.example/catalog-v1.pdf")
    monkeypatch.setattr(main.meta_whatsapp_service, "send_document", lambda *args: {"success": False, "error": "recipient_not_allowed"})
    with pytest.raises(main.HTTPException) as error:
        await main.send_catalog(main.CatalogRequest(phone_number="5514981123802"))
    assert error.value.status_code == 502
    assert error.value.detail == "recipient_not_allowed"


def test_meta_document_payload(monkeypatch):
    service = MetaWhatsAppService()
    service.token = "test-token"
    service.phone_number_id = "phone-id"
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"messages": [{"id": "wamid.document-test"}]}).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("src.whatsapp_service.urllib.request.urlopen", fake_urlopen)
    result = service.send_document(
        "5514981123802",
        "https://raw.example/catalog-v1.pdf",
        "Olá! Aqui está o Catálogo Comercial da Humanos Digitais.",
        "Catalogo_Humanos_Digitais_2026.pdf",
    )

    payload = json.loads(captured["request"].data.decode())
    assert result["success"] is True
    assert payload == {
        "messaging_product": "whatsapp",
        "to": "5514981123802",
        "type": "document",
        "document": {
            "link": "https://raw.example/catalog-v1.pdf",
            "caption": "Olá! Aqui está o Catálogo Comercial da Humanos Digitais.",
            "filename": "Catalogo_Humanos_Digitais_2026.pdf",
        },
    }


@pytest.mark.asyncio
async def test_webhook_catalog_keyword_sends_confirmation(monkeypatch):
    calls = []

    async def fake_catalog(phone, tenant_id="default"):
        calls.append(("catalog", phone, tenant_id))
        return {"success": True, "message_id": "wamid.catalog-test"}

    def fake_message(phone, text, pdf_url=None):
        calls.append(("message", phone, text, pdf_url))
        return {"success": True}

    monkeypatch.setattr(main, "send_catalog_for_phone", fake_catalog)
    monkeypatch.setattr(main.meta_whatsapp_service, "send_message", fake_message)
    await main.process_whatsapp_message("5514981123802", "catalogo")

    assert calls[0] == ("catalog", "5514981123802", "default")
    assert calls[1][0:3] == ("message", "5514981123802", "Enviamos o catálogo para você! Confira seu WhatsApp.")
