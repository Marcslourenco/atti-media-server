import logging
import os

logger = logging.getLogger("whatsapp-service")

try:
    from twilio.rest import Client
except ImportError:
    Client = None
    logger.warning("⚠️ Dependência Twilio ausente — WhatsApp desativado")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+5514981123802")


class WhatsAppService:
    def __init__(self):
        if Client is None or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.warning("⚠️ Twilio não configurado — WhatsApp desativado")
            self.client = None
        else:
            self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            logger.info("✅ WhatsApp Service inicializado (Twilio)")

    def enviar_mensagem(self, numero_destino: str, mensagem: str) -> dict:
        if not self.client:
            return {"success": False, "error": "Twilio não configurado"}
        try:
            numero = self._normalizar_numero(numero_destino)
            msg = self.client.messages.create(
                from_=TWILIO_WHATSAPP_FROM,
                to=f"whatsapp:{numero}",
                body=mensagem,
            )
            logger.info("✅ WhatsApp enviado para %s: SID=%s", numero, msg.sid)
            return {"success": True, "sid": msg.sid}
        except Exception as exc:
            logger.error("❌ Erro WhatsApp: %s", exc)
            return {"success": False, "error": str(exc)}

    def enviar_midia(self, numero_destino: str, mensagem: str, media_url: str) -> dict:
        if not self.client:
            return {"success": False, "error": "Twilio não configurado"}
        try:
            numero = self._normalizar_numero(numero_destino)
            msg = self.client.messages.create(
                from_=TWILIO_WHATSAPP_FROM,
                to=f"whatsapp:{numero}",
                body=mensagem,
                media_url=[media_url],
            )
            logger.info("✅ WhatsApp com mídia para %s: SID=%s", numero, msg.sid)
            return {"success": True, "sid": msg.sid}
        except Exception as exc:
            logger.error("❌ Erro WhatsApp mídia: %s", exc)
            return {"success": False, "error": str(exc)}

    def _normalizar_numero(self, numero: str) -> str:
        digits = "".join(char for char in str(numero) if char.isdigit())
        if digits.startswith("55"):
            return f"+{digits}"
        if len(digits) in (10, 11):
            return f"+55{digits}"
        return f"+{digits}"


whatsapp_service = WhatsAppService()
