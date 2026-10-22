import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger("whatsapp-service")

try:
    from twilio.rest import Client
except ImportError:
    Client = None
    logger.warning("⚠️ Dependência Twilio ausente — WhatsApp legado desativado")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+5514981123802")
META_WHATSAPP_TOKEN = os.environ.get("META_WHATSAPP_TOKEN", "")
META_PHONE_NUMBER_ID = os.environ.get("META_PHONE_NUMBER_ID", "")
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v20.0")


class WhatsAppService:
    def __init__(self):
        if Client is None or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.warning("⚠️ Twilio não configurado — WhatsApp legado desativado")
            self.client = None
        else:
            self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            logger.info("✅ WhatsApp Service legado inicializado (Twilio)")

    def enviar_mensagem(self, numero_destino: str, mensagem: str) -> dict:
        if not self.client:
            return {"success": False, "error": "Twilio não configurado"}
        try:
            numero = self._normalizar_numero(numero_destino)
            msg = self.client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=f"whatsapp:{numero}", body=mensagem)
            logger.info("✅ WhatsApp Twilio enviado para %s: SID=%s", numero, msg.sid)
            return {"success": True, "sid": msg.sid}
        except Exception as exc:
            logger.error("❌ Erro WhatsApp Twilio: %s", exc)
            return {"success": False, "error": str(exc)}

    def enviar_midia(self, numero_destino: str, mensagem: str, media_url: str) -> dict:
        if not self.client:
            return {"success": False, "error": "Twilio não configurado"}
        try:
            numero = self._normalizar_numero(numero_destino)
            msg = self.client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=f"whatsapp:{numero}", body=mensagem, media_url=[media_url])
            logger.info("✅ WhatsApp Twilio com mídia para %s: SID=%s", numero, msg.sid)
            return {"success": True, "sid": msg.sid}
        except Exception as exc:
            logger.error("❌ Erro WhatsApp Twilio mídia: %s", exc)
            return {"success": False, "error": str(exc)}

    def _normalizar_numero(self, numero: str) -> str:
        digits = "".join(char for char in str(numero) if char.isdigit())
        if digits.startswith("55"):
            return f"+{digits}"
        if len(digits) in (10, 11):
            return f"+55{digits}"
        return f"+{digits}"


class MetaWhatsAppService:
    def __init__(self):
        self.token = META_WHATSAPP_TOKEN
        self.phone_number_id = META_PHONE_NUMBER_ID
        self.graph_version = META_GRAPH_VERSION

    def send_document(self, phone_number: str, document_url: str, caption: str, filename: str) -> dict:
        """Send a public PDF document through Meta Cloud API without dispatching in tests."""
        numero = self.normalizar_numero(phone_number)
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info("Meta WhatsApp catálogo: numero=%s timestamp=%s", numero, timestamp)
        if not self.token or not self.phone_number_id:
            logger.error("Meta WhatsApp não configurado: token ou phone number id ausente")
            return {"success": False, "error": "meta_not_configured"}
        if not numero:
            return {"success": False, "error": "invalid_phone_number"}
        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "document",
            "document": {"link": document_url, "caption": caption, "filename": filename},
        }
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
            message_id = body.get("messages", [{}])[0].get("id")
            logger.info("Meta WhatsApp catálogo enviado: numero=%s message_id=%s", numero, message_id)
            return {"success": True, "message_id": message_id, "id": message_id, "response": body}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            lower = raw.lower()
            if "recipient not in allowed list" in lower or "131030" in lower:
                error = "recipient_not_allowed"
            elif "rate limit" in lower or "too many requests" in lower or exc.code == 429:
                error = "rate_limited"
            else:
                error = "unknown"
            logger.error("Meta WhatsApp catálogo falha: numero=%s status=%s error=%s", numero, exc.code, error)
            return {"success": False, "error": error, "detail": raw, "status_code": exc.code}
        except Exception as exc:
            logger.error("Meta WhatsApp catálogo exceção: numero=%s error=%s", numero, exc)
            return {"success": False, "error": "unknown", "detail": str(exc)}


    def normalizar_numero(self, numero: str) -> str:
        digits = re.sub(r"\D", "", str(numero or ""))
        if digits.startswith("55"):
            return digits
        if len(digits) in (10, 11):
            return "55" + digits
        return digits

    def _endpoint(self) -> str:
        return f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"

    def send_message(self, phone_number: str, message_text: str, pdf_url: str | None = None) -> dict:
        numero = self.normalizar_numero(phone_number)
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info("Meta WhatsApp envio: numero=%s timestamp=%s pdf=%s", numero, timestamp, bool(pdf_url))
        if not self.token or not self.phone_number_id:
            logger.error("Meta WhatsApp não configurado: token ou phone number id ausente")
            return {"success": False, "error": "meta_not_configured"}
        if not numero:
            return {"success": False, "error": "invalid_phone_number"}
        if pdf_url:
            payload = {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "document",
                "document": {"link": pdf_url, "caption": message_text or "Catálogo Humanos Digitais"},
            }
        else:
            payload = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": message_text}}
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
            logger.info("Meta WhatsApp envio sucesso: numero=%s timestamp=%s", numero, timestamp)
            return {"success": True, "id": body.get("messages", [{}])[0].get("id"), "response": body}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            lower = raw.lower()
            if "recipient not in allowed list" in lower or "131030" in lower:
                error = "recipient_not_allowed"
            elif "rate limit" in lower or "too many requests" in lower or exc.code == 429:
                error = "rate_limited"
            else:
                error = "unknown"
            logger.error("Meta WhatsApp falha: numero=%s timestamp=%s status=%s error=%s", numero, timestamp, exc.code, error)
            return {"success": False, "error": error, "detail": raw, "status_code": exc.code}
        except Exception as exc:
            logger.error("Meta WhatsApp exceção: numero=%s timestamp=%s error=%s", numero, timestamp, exc)
            return {"success": False, "error": "unknown", "detail": str(exc)}


whatsapp_service = WhatsAppService()
meta_whatsapp_service = MetaWhatsAppService()
