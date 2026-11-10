"""
In-Memory Data Store Module (Zero DB Connection Required).
Handles calls, conversation transcripts, lead status tracking, order payloads,
and idempotent webhook deduplication in memory without any external database connection.
"""

import json
import datetime
import threading
from typing import Dict, Any, List, Optional
import config

_LOCK = threading.Lock()

# In-memory storage collections
_CALLS_STORE: Dict[str, Dict[str, Any]] = {}
_TRANSCRIPTS_STORE: Dict[str, List[Dict[str, Any]]] = {}
_WEBHOOK_EVENTS_STORE: Dict[str, Dict[str, Any]] = {}


def init_db():
    """No external database connection required."""
    pass


def create_call(
    call_id: str,
    mobile: str,
    proid: str,
    language: str,
    is_simulated: bool = True,
    product_snapshot: Optional[Dict[str, Any]] = None,
    telephony_call_sid: Optional[str] = None
) -> Dict[str, Any]:
    """Creates a new voice call record in memory."""
    now = datetime.datetime.now().isoformat()
    record = {
        "call_id": call_id,
        "mobile": str(mobile),
        "proid": str(proid),
        "language": language or "ta",
        "status": "INITIATED",
        "lead_status": "UNDECIDED",
        "is_simulated": bool(is_simulated),
        "order_payload": None,
        "product_snapshot": product_snapshot or {},
        "duration_seconds": 0,
        "telephony_call_sid": telephony_call_sid,
        "created_at": now,
        "updated_at": now
    }
    with _LOCK:
        _CALLS_STORE[call_id] = record
        if call_id not in _TRANSCRIPTS_STORE:
            _TRANSCRIPTS_STORE[call_id] = []
    return dict(record)


def update_call_status(
    call_id: str,
    status: Optional[str] = None,
    lead_status: Optional[str] = None,
    order_payload: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[int] = None,
    telephony_call_sid: Optional[str] = None
) -> None:
    """Updates call state, lead outcome, and optional strict order JSON in memory."""
    now = datetime.datetime.now().isoformat()
    with _LOCK:
        call = _CALLS_STORE.get(call_id)
        if not call:
            call = {
                "call_id": call_id,
                "mobile": "",
                "proid": "",
                "language": "ta",
                "status": "INITIATED",
                "lead_status": "UNDECIDED",
                "is_simulated": True,
                "order_payload": None,
                "product_snapshot": {},
                "duration_seconds": 0,
                "telephony_call_sid": None,
                "created_at": now,
                "updated_at": now
            }
            _CALLS_STORE[call_id] = call

        if status:
            call["status"] = status
        if lead_status:
            call["lead_status"] = lead_status
        if order_payload is not None:
            call["order_payload"] = order_payload
        if duration_seconds is not None:
            call["duration_seconds"] = duration_seconds
        if telephony_call_sid:
            call["telephony_call_sid"] = telephony_call_sid
        call["updated_at"] = now


def add_transcript(call_id: str, speaker: str, text: str) -> None:
    """Appends a speech turn to conversation transcript in memory."""
    now = datetime.datetime.now().isoformat()
    item = {
        "speaker": speaker.upper(),
        "text": text,
        "timestamp": now,
        "created_at": now
    }
    with _LOCK:
        if call_id not in _TRANSCRIPTS_STORE:
            _TRANSCRIPTS_STORE[call_id] = []
        _TRANSCRIPTS_STORE[call_id].append(item)


def get_call(call_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves full call record by call_id from memory."""
    with _LOCK:
        call = _CALLS_STORE.get(call_id)
        return dict(call) if call else None


def get_call_transcript(call_id: str) -> List[Dict[str, Any]]:
    """Retrieves all conversation transcript items for a call from memory."""
    with _LOCK:
        items = _TRANSCRIPTS_STORE.get(call_id, [])
        return [dict(i) for i in items]


def list_calls(limit: int = 50, lead_status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists recent calls with optional status filtering from memory."""
    with _LOCK:
        calls = list(_CALLS_STORE.values())
    if lead_status:
        calls = [c for c in calls if c.get("lead_status") == lead_status.upper()]
    calls.reverse()
    return [dict(c) for c in calls[:limit]]


def is_event_processed(event_id: str) -> bool:
    """Idempotency check to prevent duplicate order generation or processing."""
    if not event_id:
        return False
    with _LOCK:
        return event_id in _WEBHOOK_EVENTS_STORE


def record_webhook_event(event_id: str, call_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
    """Records processed webhook event in memory."""
    now = datetime.datetime.now().isoformat()
    with _LOCK:
        _WEBHOOK_EVENTS_STORE[event_id] = {
            "event_id": event_id,
            "call_id": call_id,
            "event_type": event_type,
            "payload": payload,
            "processed_at": now
        }
