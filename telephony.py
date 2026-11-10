"""
Pluggable Telephony Provider Module.
Provides adapter interface for Indian outbound telephony providers (Exotel),
global providers (Twilio), and a local voice conversation simulator for development mode.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import urllib.parse
import config


class BaseTelephonyProvider(ABC):
    """Abstract Base Class for Telephony Adapters."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Checks if required API keys and credentials are present."""
        pass

    @abstractmethod
    def initiate_call(
        self,
        to_mobile: str,
        call_id: str,
        language: str,
        product_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Initiates an outbound call to customer's mobile number.
        Returns dictionary with provider_call_id, status, and message.
        """
        pass

    @abstractmethod
    def handle_webhook(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processes provider webhook events (e.g. CallInitiated, CallAnswered, CallCompleted).
        Returns normalized event dict: { event_id, call_id, status, outcome, duration }.
        """
        pass


class SimulatedTelephonyProvider(BaseTelephonyProvider):
    """
    Local Voice Conversation Simulator.
    Enables full end-to-end voice and text testing in development mode
    without spending telephony credits or needing real phone infrastructure.
    """

    def is_configured(self) -> bool:
        return True

    def initiate_call(
        self,
        to_mobile: str,
        call_id: str,
        language: str,
        product_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "provider": "simulated",
            "provider_call_id": f"SIM_{call_id}",
            "status": "CONNECTED",
            "is_simulated": True,
            "message": "Local development simulator active. Speak through mic or chat."
        }

    def handle_webhook(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        call_id = payload.get("call_id") or payload.get("callId", "")
        event_id = payload.get("event_id", f"sim_evt_{call_id}")
        status = payload.get("status", "COMPLETED")
        outcome = payload.get("outcome", "INTERESTED")

        return {
            "event_id": event_id,
            "call_id": call_id,
            "provider": "simulated",
            "status": status,
            "lead_status": outcome,
            "duration": payload.get("duration", 45),
            "raw": payload
        }


class ExotelProvider(BaseTelephonyProvider):
    """
    Exotel Telephony Provider for Indian Outbound Voice Calls.
    Uses Exotel Connect API with webhook audio streaming or app flow.
    """

    def is_configured(self) -> bool:
        return bool(
            config.EXOTEL_ACCOUNT_SID and
            config.EXOTEL_API_KEY and
            config.EXOTEL_API_TOKEN and
            config.EXOTEL_CALLER_ID
        )

    def initiate_call(
        self,
        to_mobile: str,
        call_id: str,
        language: str,
        product_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "provider": "exotel",
                "error": "Exotel credentials are not configured in .env. Use development simulator mode."
            }

        try:
            import requests
            url = f"https://{config.EXOTEL_SUB_DOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Calls/connect.json"
            status_callback = f"{config.WEBHOOK_BASE_URL}/api/voice-leads/webhooks/telephony"

            data = {
                "From": to_mobile,  # Customer number
                "CallerId": config.EXOTEL_CALLER_ID,  # Virtual number assigned by Exotel
                "Url": f"http://my.exotel.com/{config.EXOTEL_ACCOUNT_SID}/exomls/{config.EXOTEL_APP_ID}",
                "StatusCallback": status_callback,
                "CustomField": call_id,
            }

            resp = requests.post(
                url,
                data=data,
                auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN),
                timeout=10
            )

            if resp.status_code in (200, 201):
                res_json = resp.json()
                call_obj = res_json.get("Call", {})
                return {
                    "success": True,
                    "provider": "exotel",
                    "provider_call_id": call_obj.get("Sid"),
                    "status": "INITIATED",
                    "is_simulated": False,
                    "details": call_obj
                }
            else:
                return {
                    "success": False,
                    "provider": "exotel",
                    "error": f"Exotel API error {resp.status_code}: {resp.text}"
                }
        except Exception as e:
            return {
                "success": False,
                "provider": "exotel",
                "error": str(e)
            }

    def handle_webhook(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        call_sid = payload.get("CallSid") or payload.get("Sid") or ""
        call_id = payload.get("CustomField") or payload.get("call_id") or ""
        event_id = f"exotel_{call_sid}_{payload.get('Status', 'event')}"
        status = payload.get("Status", "").lower()

        status_mapping = {
            "in-progress": ("IN_PROGRESS", "UNDECIDED"),
            "completed": ("COMPLETED", "UNDECIDED"),
            "busy": ("FAILED", "NO_ANSWER"),
            "no-answer": ("FAILED", "NO_ANSWER"),
            "failed": ("FAILED", "CALL_FAILED"),
            "canceled": ("CANCELLED", "CALL_FAILED")
        }

        call_status, lead_status = status_mapping.get(status, ("IN_PROGRESS", "UNDECIDED"))

        return {
            "event_id": event_id,
            "call_id": call_id,
            "provider": "exotel",
            "provider_call_sid": call_sid,
            "status": call_status,
            "lead_status": lead_status,
            "duration": int(payload.get("ConversationDuration") or payload.get("Duration") or 0),
            "raw": payload
        }


class TwilioProvider(BaseTelephonyProvider):
    """Twilio Outbound Calling Provider adapter."""

    def is_configured(self) -> bool:
        return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_PHONE_NUMBER)

    def initiate_call(
        self,
        to_mobile: str,
        call_id: str,
        language: str,
        product_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "provider": "twilio",
                "error": "Twilio credentials are not configured in .env. Use development simulator mode."
            }

        try:
            import requests
            url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Calls.json"
            formatted_mobile = to_mobile if to_mobile.startswith("+") else f"+91{to_mobile}"
            status_callback = f"{config.WEBHOOK_BASE_URL}/api/voice-leads/webhooks/telephony"

            data = {
                "To": formatted_mobile,
                "From": config.TWILIO_PHONE_NUMBER,
                "Url": f"{config.WEBHOOK_BASE_URL}/api/voice-leads/twilio-twml/{call_id}",
                "StatusCallback": status_callback,
                "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"]
            }

            resp = requests.post(
                url,
                data=data,
                auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
                timeout=10
            )

            if resp.status_code in (200, 201):
                res_data = resp.json()
                return {
                    "success": True,
                    "provider": "twilio",
                    "provider_call_id": res_data.get("sid"),
                    "status": "INITIATED",
                    "is_simulated": False
                }
            else:
                return {
                    "success": False,
                    "provider": "twilio",
                    "error": f"Twilio API error {resp.status_code}: {resp.text}"
                }
        except Exception as e:
            return {"success": False, "provider": "twilio", "error": str(e)}

    def handle_webhook(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        call_sid = payload.get("CallSid", "")
        call_status = payload.get("CallStatus", "").lower()
        call_id = payload.get("call_id") or ""
        event_id = f"twilio_{call_sid}_{payload.get('SequenceNumber', call_status)}"

        status_mapping = {
            "in-progress": ("IN_PROGRESS", "UNDECIDED"),
            "completed": ("COMPLETED", "UNDECIDED"),
            "busy": ("FAILED", "NO_ANSWER"),
            "no-answer": ("FAILED", "NO_ANSWER"),
            "failed": ("FAILED", "CALL_FAILED")
        }
        status, lead_status = status_mapping.get(call_status, ("IN_PROGRESS", "UNDECIDED"))

        return {
            "event_id": event_id,
            "call_id": call_id,
            "provider": "twilio",
            "provider_call_sid": call_sid,
            "status": status,
            "lead_status": lead_status,
            "duration": int(payload.get("CallDuration", 0)),
            "raw": payload
        }


def get_telephony_provider(provider_name: Optional[str] = None) -> BaseTelephonyProvider:
    """Factory to get selected telephony provider."""
    name = (provider_name or config.TELEPHONY_PROVIDER).lower().strip()
    if name == "exotel":
        provider = ExotelProvider()
        if provider.is_configured():
            return provider
    elif name == "twilio":
        provider = TwilioProvider()
        if provider.is_configured():
            return provider

    # Default to Simulated Provider for Development Mode
    return SimulatedTelephonyProvider()

