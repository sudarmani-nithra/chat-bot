"""
Multilingual AI Voice Calling Assistant Backend.
FastAPI implementation with REST APIs, WebSocket real-time events,
telephony webhook idempotency, and local voice conversation simulator.
"""

import os
import re
import uuid
import json
import time
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field

import config
import database
import catalog
import speech
import telephony
from languages import get_language_config
from ai_engine import LeadConversationEngine

# Create FastAPI app
app = FastAPI(
    title="Multilingual AI Voice Calling Assistant for Lead Conversion",
    description="Automated AI Voice Assistant calling leads in native Tamil and Telugu with strict JSON order output.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory active session engines: call_id -> LeadConversationEngine
active_sessions: Dict[str, LeadConversationEngine] = {}

# Static & Template directories
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


# -------------------------------------------------------------
# Pydantic Request Models
# -------------------------------------------------------------

class CallInitiateRequest(BaseModel):
    mobile: str = Field(..., description="Customer 10-digit mobile number")
    proid: str = Field(..., description="Product ID from catalog (e.g. PROD101, 10)")
    language: Optional[str] = Field("ta", description="Language code: 'ta' (Tamil) or 'te' (Telugu)")
    simulate: Optional[bool] = Field(None, description="Force local simulation mode")


class ConversationTurnRequest(BaseModel):
    text: str = Field(..., description="Customer speech utterance or transcribed text")


# -------------------------------------------------------------
# Mobile Validation Helper
# -------------------------------------------------------------

def validate_indian_mobile(mobile_raw: str) -> str:
    """
    Validates and normalizes Indian mobile number.
    Accepts 10 digits starting with 6, 7, 8, or 9, with optional +91 or 0 prefix.
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", str(mobile_raw).strip())
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]

    if not re.match(r"^[6-9]\d{9}$", cleaned):
        raise ValueError("Invalid Indian mobile number. Must be a valid 10-digit number starting with 6, 7, 8, or 9.")

    return cleaned


async def warmup_lead_cache(engine: LeadConversationEngine):
    """
    Pre-synthesizes voice audio in background for all precomputed product responses
    (price, specs, delivery, pitch, closing) as soon as a lead is entered,
    so that when the user asks, it responds INSTANTLY with 0ms latency.
    """
    try:
        for topic, text in getattr(engine, "cached_responses", {}).items():
            if text:
                await speech.synthesize_speech_async(text, engine.language)
    except Exception as e:
        print(f"[Cache Warmup] Error pre-caching audio for {engine.call_id}: {e}")


# -------------------------------------------------------------
# REST Endpoints (as required by specification)
# -------------------------------------------------------------

@app.post("/api/voice-leads/call", tags=["Voice Leads"])
async def initiate_voice_lead_call(req: CallInitiateRequest):
    """
    1. Accept mobile number and product ID.
    2. Validate mobile number.
    3. Retrieve product details using product ID from catalog.
    4. Initialize outbound AI voice call or local simulator.
    """
    try:
        valid_mobile = validate_indian_mobile(req.mobile)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    proid_clean = req.proid.strip()
    if not proid_clean:
        raise HTTPException(status_code=400, detail="Product ID cannot be empty.")

    # Retrieve product details
    product_data = catalog.get_product(proid_clean)
    if not product_data:
        raise HTTPException(status_code=404, detail=f"Product with ID '{proid_clean}' not found in catalog.")

    lang = req.language.lower().strip() if req.language else "ta"
    if lang not in ("ta", "te"):
        lang = "ta"

    # Decide simulation mode
    is_simulated = True
    provider = telephony.get_telephony_provider()
    if req.simulate is not None:
        is_simulated = bool(req.simulate)
        if not is_simulated and not provider.is_configured():
            is_simulated = True  # Fallback to simulation if provider not configured

    call_id = f"CALL_{uuid.uuid4().hex[:12].upper()}"

    # Initialize conversation state engine
    engine = LeadConversationEngine(
        call_id=call_id,
        mobile=valid_mobile,
        proid=proid_clean,
        language=lang,
        product_info=product_data
    )
    active_sessions[call_id] = engine

    # Initiate through telephony provider
    telephony_result = provider.initiate_call(
        to_mobile=valid_mobile,
        call_id=call_id,
        language=lang,
        product_info=product_data
    )

    # Initial AI disclosure greeting
    initial_greeting = engine.get_initial_greeting()

    # Save initial call in database
    db_call = database.create_call(
        call_id=call_id,
        mobile=valid_mobile,
        proid=proid_clean,
        language=lang,
        is_simulated=is_simulated,
        product_snapshot=product_data,
        telephony_call_sid=telephony_result.get("provider_call_id")
    )


    # Record first AI turn in transcript
    database.add_transcript(call_id=call_id, speaker="AI", text=initial_greeting)
    engine.history.append({"speaker": "AI", "text": initial_greeting})

    # Pre-synthesize initial greeting audio for instant playback
    audio_url = await speech.synthesize_speech_base64_async(initial_greeting, lang)

    # Pre-cache all product responses (price, specs, delivery, pitch, closing) in background
    # so whenever the user asks, the answer and voice audio respond INSTANTLY with 0ms latency!
    asyncio.create_task(warmup_lead_cache(engine))

    return {
        "success": True,
        "callId": call_id,
        "status": "INITIATED",
        "lead_status": "UNDECIDED",
        "is_simulated": is_simulated,
        "product": product_data,
        "initial_greeting": initial_greeting,
        "audio_url": audio_url,
        "telephony": telephony_result
    }


@app.get("/api/voice-leads/calls/{callId}", tags=["Voice Leads"])
async def get_voice_lead_call(callId: str):
    """
    Return the current call status, lead outcome, product details,
    and strict JSON order output (when customer confirms interest).
    """
    call = database.get_call(callId)
    if not call:
        raise HTTPException(status_code=404, detail="Call ID not found")
    return call


@app.get("/api/voice-leads/calls/{callId}/transcript", tags=["Voice Leads"])
async def get_voice_lead_transcript(callId: str):
    """
    Return the full recorded conversation transcript.
    """
    call = database.get_call(callId)
    if not call:
        raise HTTPException(status_code=404, detail="Call ID not found")
    transcript = database.get_call_transcript(callId)
    return {
        "callId": callId,
        "status": call.get("status"),
        "lead_status": call.get("lead_status"),
        "transcript": transcript
    }


@app.post("/api/voice-leads/webhooks/telephony", tags=["Telephony Webhooks"])
async def handle_telephony_webhook(request: Request):
    """
    Receive authenticated call events and final call completion notifications.
    Implement idempotent backend handling to prevent duplicate orders from repeated events or callbacks.
    """
    headers = dict(request.headers)
    body = {}
    try:
        content_type = headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)
    except Exception:
        pass

    provider = telephony.get_telephony_provider()
    parsed_event = provider.handle_webhook(headers, body)
    event_id = parsed_event.get("event_id")

    # Idempotency check: prevent duplicate event processing
    if event_id and database.is_event_processed(event_id):
        return JSONResponse({"status": "ignored", "message": "Duplicate event already processed"})

    call_id = parsed_event.get("call_id")
    if call_id:
        existing_call = database.get_call(call_id)
        if existing_call:
            new_status = parsed_event.get("status", existing_call.get("status"))
            lead_status = parsed_event.get("lead_status") or existing_call.get("lead_status")
            duration = parsed_event.get("duration", existing_call.get("duration_seconds", 0))

            database.update_call_status(
                call_id=call_id,
                status=new_status,
                lead_status=lead_status,
                duration_seconds=duration,
                telephony_call_sid=parsed_event.get("provider_call_sid")
            )

    # Record event in idempotency table
    if event_id:
        database.record_webhook_event(
            event_id=event_id,
            call_id=call_id,
            event_type=parsed_event.get("status", "webhook"),
            payload=parsed_event
        )

    return {"status": "success", "event_id": event_id}


# -------------------------------------------------------------
# Conversation Simulator & Interaction Endpoints
# -------------------------------------------------------------

@app.post("/api/voice-leads/calls/{callId}/turn", tags=["Voice Simulator"])
async def conversation_turn(callId: str, req: ConversationTurnRequest):
    """
    Processes a dialogue turn in real-time.
    Supports mic transcription or text message input.
    Returns AI response in natural Tamil/Telugu with audio playback.
    Enforces strict JSON output when customer confirms interest.
    """
    call = database.get_call(callId)
    if not call:
        raise HTTPException(status_code=404, detail="Call ID not found")

    engine = active_sessions.get(callId)
    if not engine:
        # Reconstruct engine from database snapshot
        engine = LeadConversationEngine(
            call_id=callId,
            mobile=call["mobile"],
            proid=call["proid"],
            language=call["language"],
            product_info=call.get("product_snapshot") or {}
        )
        active_sessions[callId] = engine

    customer_text = req.text.strip()
    if not customer_text:
        raise HTTPException(status_code=400, detail="Customer text cannot be empty.")

    # Record customer speech
    database.add_transcript(call_id=callId, speaker="CUSTOMER", text=customer_text)
    engine.history.append({"speaker": "CUSTOMER", "text": customer_text})

    # Process conversation reasoning and intent
    turn_result = engine.process_customer_turn(customer_text)
    reply_text = turn_result["reply_text"]
    lead_status = turn_result["lead_status"]
    order_payload = turn_result["order_payload"]
    is_completed = turn_result["is_completed"]

    # Record AI speech
    database.add_transcript(call_id=callId, speaker="AI", text=reply_text)
    engine.history.append({"speaker": "AI", "text": reply_text})

    # Update database
    call_status = "COMPLETED" if is_completed else "IN_PROGRESS"
    database.update_call_status(
        call_id=callId,
        status=call_status,
        lead_status=lead_status,
        order_payload=order_payload
    )

    # Synthesize AI speech audio (Tamil/Telugu)
    audio_url = await speech.synthesize_speech_base64_async(reply_text, engine.language)

    return {
        "callId": callId,
        "speaker": "AI",
        "reply_text": reply_text,
        "language": engine.language,
        "lead_status": lead_status,
        "order_payload": order_payload,
        "is_completed": is_completed,
        "audio_url": audio_url
    }


@app.post("/api/voice-leads/stt", tags=["Speech"])
async def transcribe_speech(audio_file: UploadFile = File(...), language: str = Form("ta")):
    """
    Transcribe audio blob recorded from browser microphone.
    Handles Tamil, Telugu, and mixed Tanglish/Telugish speech.
    """
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        return {"transcript": ""}

    transcript = speech.transcribe_audio_gemini(
        audio_bytes=audio_bytes,
        mime_type=audio_file.content_type or "audio/webm",
        language_hint=language
    )
    return {"transcript": transcript}


@app.post("/api/voice-leads/tts", tags=["Speech"])
async def synthesize_tts(request: Request):
    """
    Synthesize Tamil or Telugu text to speech audio.
    """
    data = await request.json()
    text = data.get("text", "")
    language = data.get("language", "ta")
    audio_url = await speech.synthesize_speech_base64_async(text, language)
    return {"audio_url": audio_url}


@app.get("/api/voice-leads/fillers", tags=["Speech"])
async def get_filler_phrases():
    """
    Returns natural conversational filler audio for instant playback
    when customer asks questions, completely eliminating awkward silence.
    """
    ta_fillers = [
        "ஒரு நிமிஷம், செக் பண்ணி சொல்றேன்.",
        "இருங்க, பார்த்து சொல்றேன்.",
        "நல்ல கேள்வி, சொல்றேன்.",
        "சரிங்க, பார்த்து சொல்றேன்.",
    ]
    te_fillers = [
        "ఒక్క నిమిషం, చెక్ చేసి చెప్తాను.",
        "మంచి ప్రశ్న అండి, చెప్తాను.",
        "తప్పకుండా, చూసి చెప్తాను.",
    ]

    result = {"ta": [], "te": []}
    for phrase in ta_fillers:
        audio_url = await speech.synthesize_speech_base64_async(phrase, "ta")
        result["ta"].append({"text": phrase, "audio_url": audio_url})

    for phrase in te_fillers:
        audio_url = await speech.synthesize_speech_base64_async(phrase, "te")
        result["te"].append({"text": phrase, "audio_url": audio_url})

    return result


@app.get("/api/voice-leads/calls", tags=["Voice Leads"])
async def list_recent_calls(limit: int = 50, lead_status: Optional[str] = None):
    """List recent call records with optional status filter."""
    return database.list_calls(limit=limit, lead_status=lead_status)


@app.get("/api/products", tags=["Product Catalog"])
async def list_catalog_products():
    """Retrieve sample products for dashboard selector."""
    return catalog.list_sample_products(limit=25)


# -------------------------------------------------------------
# Admin Dashboard Frontend Route
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def serve_admin_dashboard():
    """Serves the rich web-based Admin Dashboard and Voice Simulator."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        try:
            content = html_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)
        except Exception as e:
            return HTMLResponse(f"<h1>Error reading dashboard template: {e}</h1>", status_code=500)
    return HTMLResponse("<h1>AI Voice Assistant Dashboard</h1>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
