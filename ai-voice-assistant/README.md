# Multilingual AI Voice Calling Assistant for Lead Conversion (Tamil & Telugu)

An end-to-end AI-powered outbound voice calling assistant that automatically contacts leads generated through Instagram and Facebook advertisements, communicates naturally in native Tamil or Telugu, understands customer purchase intent, and returns structured strict JSON for interested customers.

---

## Key Features

1. **Phase 1 Manual Lead Input & Admin Dashboard**:
   - Web-based admin dashboard at `http://localhost:8000/`.
   - Validates 10-digit Indian mobile numbers (`^[6-9]\d{9}$`).
   - Retrieves product specifications, verified pricing, and discounts from `products.json`.
   - Supports language switching: **Tamil (`ta-IN`)** and **Telugu (`te-IN`)**.

2. **Conversational AI Calling Engine**:
   - **Tamil Calling Flow**:
     - Greeting: *"வணக்கம்! நான் நித்ரா நிறுவனத்திலிருந்து பேசுற AI உதவியாளர். நீங்க Facebook அல்லது Instagram-ல எங்களோட product பற்றிய விவரங்களை கேட்டிருந்தீங்க. அதைப் பற்றி ஒரு நிமிஷம் பேசலாமா?"*
     - Pitch: *"நீங்க பார்த்த [Product Name] பற்றித்தான் பேசுறேன். இந்த product வாங்க உங்களுக்கு விருப்பம் இருக்கா?"*
     - Interest confirmation: *"சரிங்க, உங்களுக்கு இந்த product வாங்க விருப்பம் இருக்குன்னு confirm பண்ணிக்கிறேன். எங்க team அடுத்த விவரங்களுக்கு உங்களைத் தொடர்பு கொள்வாங்க. நன்றி!"*
     - Rejection closing: *"சரிங்க, பரவாயில்லை. உங்க நேரத்துக்கு ரொம்ப நன்றி!"*
   - **Telugu Calling Flow**:
     - Greeting: *"నమస్కారం! నేను నిత్రా సంస్థ నుంచి మాట్లాడుతున్న AI అసిస్టెంట్ని. మీరు Facebook లేదా Instagramలో మా ప్రొడక్ట్ గురించి వివరాలు అడిగారు. ఒక నిమిషం మాట్లాడవచ్చా?"*
     - Pitch: *"మీరు చూసిన [Product Name] గురించి మాట్లాడుతున్నాను. ఈ ప్రొడక్ట్ కొనడానికి మీకు ఆసక్తి ఉందా?"*
     - Interest confirmation: *"సరే, మీకు ఈ ప్రొడక్ట్ కొనడానికి ఆసక్తి ఉందని నిర్ధారించుకుంటున్నాను. తదుపరి వివరాల కోసం మా టీమ్ మిమ్మల్ని సంప్రదిస్తుంది. ధన్యవాదాలు!"*
     - Rejection closing: *"సరే, పర్వాలేదు. మీ సమయానికి ధన్యవాదాలు!"*
   - **Conversational Intelligence & Guardrails**:
     - Never invents prices or discounts.
     - Never claims order is already placed.
     - Discloses caller is an AI assistant.
     - Avoids processing sensitive payment info (states Cash On Delivery / team follow-up).
     - Understands mixed speech (Tanglish / Telugish).
     - Dynamically switches languages upon request.

3. **Strict JSON Output for Confirmed Orders**:
   When customer confirms purchase interest, returns strictly:
   ```json
   {
     "mobile": "9876543210",
     "proid": "PROD101"
   }
   ```
   *(No additional fields. Values come exclusively from original validated lead input).*

4. **Internal Lead Status Tracking**:
   - `INTERESTED` (Triggers order payload)
   - `NOT_INTERESTED`
   - `CALLBACK_REQUESTED`
   - `UNDECIDED`
   - `NO_ANSWER`
   - `CALL_FAILED`
   - `DO_NOT_CALL`

5. **Development Mode & Voice Simulator**:
   - Test full voice conversation locally using your microphone and natural audio playback.
   - Live speech recognition (STT) + Text-to-Speech (TTS) + Voice Activity & Interruption Handling.
   - Test without spending telephony credits.
   - Clearly labels `SIMULATED` vs `REAL TELEPHONY`.

6. **Pluggable Telephony Architecture**:
   - `SimulatedTelephonyProvider` (for local development simulator)
   - `ExotelProvider` (Indian outbound calling provider)
   - `TwilioProvider`

7. **Database & Idempotency**:
   - MySQL persistence with automated SQLite fallback (`voice_leads.db`).
   - Idempotent webhook event handling preventing duplicate orders from retried callbacks.

---

## Required REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/voice-leads/call` | Validate lead, retrieve product, initiate outbound AI call or simulator |
| `GET` | `/api/voice-leads/calls/:callId` | Get current call status, lead outcome, and final strict JSON order payload |
| `GET` | `/api/voice-leads/calls/:callId/transcript` | Retrieve full recorded conversation transcript with speaker turns |
| `POST` | `/api/voice-leads/webhooks/telephony` | Telephony event callbacks with idempotent deduplication |
| `POST` | `/api/voice-leads/calls/:callId/turn` | Process dialogue turn with AI response and audio synthesis |
| `POST` | `/api/voice-leads/stt` | Transcribe speech audio (Tamil / Telugu) via Gemini |
| `GET` | `/api/voice-leads/calls` | Call history with status filtering |
| `GET` | `/api/products` | Retrieve sample products from verified catalog |

---

## Project Structure

```
ai-voice-assistant/
├── app.py               # Main FastAPI application and REST endpoints
├── config.py            # Environment configuration
├── catalog.py           # Product catalog lookup & verified ground-truth data
├── languages.py         # Tamil & Telugu scripts, prompts, and switching rules
├── ai_engine.py         # Conversational agent, intent detector, strict JSON generator
├── telephony.py         # Pluggable telephony adapter (Simulated, Exotel, Twilio)
├── speech.py            # STT (Gemini Multimodal) and TTS (Edge-TTS / Browser)
├── database.py          # MySQL / SQLite layer and webhook idempotency
├── test_system.py       # Automated test suite
├── static/
│   └── index.html       # Admin Dashboard with mic voice simulator and history
└── README.md
```

---

## Running the Application

### 1. Start the Server
```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000/](http://localhost:8000/) in your web browser.

### 2. Run the Verification Tests
```bash
python test_system.py
```
All 8 verification test suites will execute and validate the entire flow.

