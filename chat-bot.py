import os
import sys
import time
import uuid
import json
import base64
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# If running directly via `python chat-bot.py`, launch streamlit automatically
try:
    from streamlit.runtime import exists as _streamlit_exists

    _is_streamlit = _streamlit_exists()
except Exception:
    _is_streamlit = False

if __name__ == "__main__" and not _is_streamlit:
    print("\n" + "=" * 60)
    print("  🚀 Launching Audio-Only Voice Assistant in Streamlit...")
    print("  If your browser doesn't open automatically, visit:")
    print("  http://localhost:8501")
    print("=" * 60 + "\n")
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__] + sys.argv[1:])
    sys.exit(0)

# -------------------------------------------------------------
# Streamlit Application Code Below
# -------------------------------------------------------------
import streamlit as st
import streamlit.components.v1 as components
from tamil_voice import (
    GEMINI_AUDIO_MODELS,
    GEMINI_VOICES,
    TAMIL_SAMPLE_PHRASES,
    synthesize_tamil_speech,
    render_audio_controller_html,
)
from product_assistant import (
    load_products_data,
    get_product_system_prompt,
    generate_product_voice_response,
)

# Configure page metadata
st.set_page_config(
    page_title="Sri Diya Audio-Only Voice Assistant",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS — Clean White Audio Studio Theme
st.markdown(
    """
<style>
    /* ── Global white background ── */
    .stApp {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa !important;
        border-right: 1px solid #e0e0e0;
    }
    section[data-testid="stSidebar"] * {
        color: #1a1a2e !important;
    }

    /* Header */
    .voice-header {
        text-align: center;
        padding: 1.5rem 0 1rem 0;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid #eef2f6;
    }
    .voice-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #2563eb, #7c3aed, #db2777);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .voice-subtitle {
        color: #64748b;
        font-size: 1.05rem;
        margin: 8px 0 0 0;
    }

    /* Voice Center Orb */
    .orb-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        margin: 2rem 0;
    }
    .voice-orb {
        width: 130px;
        height: 130px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #60a5fa, #3b82f6, #1d4ed8);
        box-shadow: 0 0 35px rgba(59, 130, 246, 0.45), inset 0 0 15px rgba(255, 255, 255, 0.6);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 3rem;
        color: #ffffff;
        animation: pulse-slow 3s infinite ease-in-out;
        cursor: pointer;
        transition: transform 0.2s ease;
    }
    .voice-orb:hover {
        transform: scale(1.05);
    }
    .voice-orb.speaking {
        animation: pulse-fast 1s infinite alternate;
        box-shadow: 0 0 55px rgba(139, 92, 246, 0.65), inset 0 0 20px rgba(255, 255, 255, 0.8);
        background: radial-gradient(circle at 30% 30%, #a78bfa, #8b5cf6, #6d28d9);
    }
    .voice-orb.listening {
        animation: pulse-listening 1.1s infinite alternate;
        box-shadow: 0 0 60px rgba(239, 68, 68, 0.75), inset 0 0 25px rgba(255, 255, 255, 0.85);
        background: radial-gradient(circle at 30% 30%, #f87171, #ef4444, #b91c1c) !important;
    }

    @keyframes pulse-slow {
        0% { transform: scale(1); box-shadow: 0 0 25px rgba(59, 130, 246, 0.35); }
        50% { transform: scale(1.06); box-shadow: 0 0 45px rgba(59, 130, 246, 0.6); }
        100% { transform: scale(1); box-shadow: 0 0 25px rgba(59, 130, 246, 0.35); }
    }
    @keyframes pulse-fast {
        0% { transform: scale(1); box-shadow: 0 0 35px rgba(139, 92, 246, 0.5); }
        100% { transform: scale(1.1); box-shadow: 0 0 65px rgba(139, 92, 246, 0.85); }
    }
    @keyframes pulse-listening {
        0% { transform: scale(1.02); box-shadow: 0 0 35px rgba(239, 68, 68, 0.55); }
        100% { transform: scale(1.16); box-shadow: 0 0 70px rgba(239, 68, 68, 0.9); }
    }

    .voice-mode-badge {
        display: inline-block;
        background: #f1f5f9;
        color: #334155;
        border: 1px solid #cbd5e1;
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 700;
        margin-top: 12px;
        letter-spacing: 0.3px;
    }

    /* Status pills */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .status-active {
        background: #e6f4ea;
        color: #1e7e34;
        border: 1px solid #a3d9a5;
    }
    .status-demo {
        background: #fff8e1;
        color: #b8860b;
        border: 1px solid #f0d080;
    }

    /* Sidebar section divider */
    .sidebar-section {
        margin-top: 1rem;
        padding-top: 0.8rem;
        border-top: 1px solid #e0e0e0;
    }

    /* Buttons */
    .stButton > button {
        background-color: #f8fafc !important;
        color: #1a1a2e !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    .stButton > button:hover {
        background-color: #e2e8f0 !important;
        border-color: #2563eb !important;
    }

    /* Primary buttons */
    .stButton > button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border-color: #1d4ed8 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
    }

    /* Selectbox / inputs */
    .stSelectbox > div > div,
    .stTextInput > div > div > input,
    .stTextArea textarea {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
        border-color: #cbd5e1 !important;
        border-radius: 10px !important;
    }

    /* Scrollbar (light) */
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
    }
    ::-webkit-scrollbar-thumb {
        background: #c1c1c1;
        border-radius: 4px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# -------------------------------------------------------------
# System Prompt Presets for General Chat Mode
# -------------------------------------------------------------
PERSONAS = {
    "🌟 Helpful Assistant": "You are a friendly, highly capable AI assistant powered by Google Gemini. Provide clear, accurate, and insightful answers with proper markdown formatting.",
    "💻 Senior Software Engineer": "You are a principal software engineer. Provide efficient, modular, idiomatic code with clear explanations, time/space complexity notes, and best practices.",
    "📊 Data Scientist & Analyst": "You are an expert data scientist and statistician. Help with Python data analysis, pandas, machine learning, mathematics, and visualization.",
    "✍️ Creative Writer": "You are an imaginative and eloquent writer. Help compose engaging narratives, emails, poetry, and persuasive copy with vivid vocabulary.",
    "🎯 Concise & Direct": "You are a concise assistant. Provide short, direct, high-signal responses. Prefer bullet points and omit pleasantries.",
    "⚙️ Custom": "",
}

# -------------------------------------------------------------
# Load Products Catalog
# -------------------------------------------------------------
products_catalog = load_products_data()

# -------------------------------------------------------------
# Google Gemini API Key Configuration
# -------------------------------------------------------------
DEFAULT_GEMINI_API_KEY = "AIzaSyAvPbM6X0U0HNMPHaia1SIuNn3inW63AU0"
active_key = (
    os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or DEFAULT_GEMINI_API_KEY
)
st.session_state["gemini_api_key"] = active_key

# -------------------------------------------------------------
# Session Persistence Helpers (Survives Page Refreshes)
# ---------------------------------------------------------
SESSION_DIR = Path(__file__).parent / ".voice_sessions"
SESSION_DIR.mkdir(exist_ok=True)


def get_current_session_id() -> str:
    sess_id = st.query_params.get("session_id")
    if not sess_id:
        sess_id = st.session_state.get("voice_session_id")
    if not sess_id:
        sess_id = uuid.uuid4().hex[:12]
    st.query_params["session_id"] = sess_id
    st.session_state["voice_session_id"] = sess_id
    return sess_id


def load_persisted_session(session_id: str):
    sess_file = SESSION_DIR / f"{session_id}.json"
    audio_file = SESSION_DIR / f"{session_id}.wav"
    if sess_file.exists():
        try:
            with open(sess_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if audio_file.exists():
                try:
                    with open(audio_file, "rb") as af:
                        data["audio_bytes"] = af.read()
                except Exception:
                    pass
            return data
        except Exception:
            return None
    return None


def save_persisted_session(
    session_id: str,
    history: list,
    audio_bytes: Optional[bytes],
    audio_meta: Optional[dict],
):
    sess_file = SESSION_DIR / f"{session_id}.json"
    audio_file = SESSION_DIR / f"{session_id}.wav"
    try:
        data = {
            "history": history,
            "audio_meta": audio_meta,
            "updated_at": time.time(),
        }
        with open(sess_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        if audio_bytes:
            with open(audio_file, "wb") as f:
                f.write(audio_bytes)
    except Exception as e:
        print(f"Error saving session {session_id}: {e}")


def clear_persisted_session(session_id: str):
    sess_file = SESSION_DIR / f"{session_id}.json"
    audio_file = SESSION_DIR / f"{session_id}.wav"
    for f in (sess_file, audio_file):
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass


current_session_id = get_current_session_id()

# -------------------------------------------------------------
# Sidebar Configuration
# -------------------------------------------------------------
with st.sidebar:
    if st.button("🔄 Reset Conversation History", use_container_width=True):
        clear_persisted_session(current_session_id)
        new_sess = uuid.uuid4().hex[:12]
        st.query_params["session_id"] = new_sess
        st.session_state["voice_session_id"] = new_sess
        st.session_state.voice_audio_bytes = None
        st.session_state.voice_audio_meta = None
        st.session_state.voice_conversation_history = []
        st.session_state["last_processed_audio_sig"] = None
        st.rerun()
        st.query_params["session_id"] = new_sess
        st.session_state["voice_session_id"] = new_sess
        st.session_state.voice_audio_bytes = None
        st.session_state.voice_audio_meta = None
        st.session_state.voice_conversation_history = []
        st.session_state["last_processed_audio_sig"] = None
        st.rerun()

    # ---------------------------------------------------------
    # Mode & Voice Defaults (Audio-Only Product Assistant)
    # ---------------------------------------------------------
    app_mode = "🎙️ Audio-Only Product Voice Assistant"
    voice_model = "gemini-2.5-flash-native-audio-latest"
    selected_voice_key = "Aoede"
    selected_voice_info = GEMINI_VOICES[selected_voice_key]
    auto_play = True



# =============================================================
# APP MODE 1: AUDIO-ONLY PRODUCT VOICE ASSISTANT
# Zero on-screen product details or text responses. Voice only.
# =============================================================
if app_mode == "🎙️ Audio-Only Product Voice Assistant":
    # Header — Minimal & Clean Audio Interface
    st.markdown(
        f"""
        <div class="voice-header">
            <h1 class="voice-title">🎙️ Sri Diya Voice Assistant</h1>
            <p class="voice-subtitle">Audio-Only Product Interaction  </p>
            <span class="voice-mode-badge">🔒 AUDIO-ONLY MODE ACTIVE • NO ON-SCREEN TEXT DISPLAYED</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # State initialization for voice audio & multi-turn memory (Restores upon page refresh)
    if "voice_conversation_history" not in st.session_state:
        persisted = load_persisted_session(current_session_id)
        if persisted:
            st.session_state.voice_conversation_history = persisted.get("history", [])
            audio_bytes = persisted.get("audio_bytes")
            if not audio_bytes and persisted.get("audio_b64"):
                try:
                    audio_bytes = base64.b64decode(persisted.get("audio_b64"))
                except Exception:
                    audio_bytes = None
            st.session_state.voice_audio_bytes = audio_bytes
            st.session_state.voice_audio_meta = persisted.get("audio_meta")
        else:
            st.session_state.voice_conversation_history = []
            st.session_state.voice_audio_bytes = None
            st.session_state.voice_audio_meta = None

    if "voice_audio_bytes" not in st.session_state:
        st.session_state.voice_audio_bytes = None

    if "voice_audio_meta" not in st.session_state:
        st.session_state.voice_audio_meta = None

    # Glowing Visualizer Orb with Noise / Silence Auto-Close
    is_speaking = st.session_state.voice_audio_bytes is not None
    orb_class = "voice-orb speaking" if is_speaking else "voice-orb"
    orb_icon = "🔊" if is_speaking else "🎙️"

    st.markdown(
        f"""
        <div class="orb-container">
            <div id="mainVoiceOrb" class="{orb_class}" onclick="window.toggleVoiceListening()" title="Click to speak (Auto-closes when you stop speaking)">{orb_icon}</div>
            <div id="voiceStatusText" style="font-size: 0.95rem; font-weight: 600; color: #475569; margin-top: 14px;">
                🎙️ Tap Orb to Speak (Auto-closes on silence)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Silence & Noise Auto-Close Voice Engine (Web Audio VAD & Continuous Speech Recognition)
    st.html(
        """
        <script>
        (function() {
            const rootWin = window;
            const parentWin = (window.parent && window.parent !== window) ? window.parent : window;

            // Remove any stale message handler from previous render
            if (parentWin.__voiceMsgHandler) {
                try { parentWin.removeEventListener('message', parentWin.__voiceMsgHandler); } catch (e) {}
            }
            if (rootWin.__voiceMsgHandler && rootWin !== parentWin) {
                try { rootWin.removeEventListener('message', rootWin.__voiceMsgHandler); } catch (e) {}
            }

            let silenceTimer = null;
            let noSpeechTimer = null;
            let speechDetected = false;
            let isListening = false;
            let capturedText = "";

            const SILENCE_LIMIT_MS = 1500;   // 1.5s of silence after speech -> Auto submit
            const NO_SPEECH_LIMIT_MS = 6500; // 6.5s of no noise -> Auto close to idle

            function updateUI(state, text) {
                const doc = parentWin.document || document;
                const orb = doc.getElementById("mainVoiceOrb");
                const label = doc.getElementById("voiceStatusText");
                if (label) label.textContent = text;

                if (!orb) return;
                if (state === "listening") {
                    orb.className = "voice-orb listening";
                    orb.innerHTML = "🎙️";
                } else if (state === "speaking") {
                    orb.className = "voice-orb speaking";
                    orb.innerHTML = "🔊";
                } else {
                    orb.className = "voice-orb";
                    orb.innerHTML = "🎙️";
                    orb.style.transform = "scale(1)";
                }
            }

            function stopListening(shouldSubmit) {
                isListening = false;
                if (silenceTimer) clearTimeout(silenceTimer);
                if (noSpeechTimer) clearTimeout(noSpeechTimer);

                const recognition = parentWin.__voiceRecognition;
                if (recognition) {
                    try { recognition.stop(); } catch (e) {}
                    parentWin.__voiceRecognition = null;
                }

                const micStream = parentWin.__voiceMicStream;
                if (micStream) {
                    try { micStream.getTracks().forEach(track => track.stop()); } catch (e) {}
                    parentWin.__voiceMicStream = null;
                }

                const audioContext = parentWin.__voiceAudioCtx;
                if (audioContext) {
                    try { audioContext.close(); } catch (e) {}
                    parentWin.__voiceAudioCtx = null;
                }

                const query = capturedText.trim();
                if (shouldSubmit && query) {
                    updateUI("speaking", "⚡ Processing query: \"" + query + "\"");
                    sendQueryToApp(query);
                } else {
                    updateUI("idle", "🎙️ Tap Orb to Speak (Auto-closes on silence)");
                }
            }

            function resetSilenceTimer() {
                if (noSpeechTimer) clearTimeout(noSpeechTimer);
                if (silenceTimer) clearTimeout(silenceTimer);

                silenceTimer = setTimeout(() => {
                    if (isListening && speechDetected) {
                        console.log("[VoiceAssistant] Silence detected after speech. Auto-submitting query...");
                        updateUI("processing", "⚡ Silence detected — Synthesizing audio response...");
                        stopListening(true);
                    }
                }, SILENCE_LIMIT_MS);
            }

            function startListening() {
                if (isListening) {
                    console.log("[VoiceAssistant] Already listening, skipping duplicate call.");
                    return;
                }

                // Clean up any lingering recognition/mic sessions
                stopListening(false);

                const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition || 
                                  parentWin.SpeechRecognition || parentWin.webkitSpeechRecognition;
                if (!SpeechRec) {
                    console.warn("[VoiceAssistant] Web Speech API not supported in this browser.");
                    return;
                }

                try {
                    const recognition = new SpeechRec();
                    parentWin.__voiceRecognition = recognition;
                    recognition.continuous = true;
                    recognition.interimResults = true;
                    recognition.lang = 'en-IN';

                    capturedText = "";
                    speechDetected = false;
                    isListening = true;

                    updateUI("listening", "🔴 Listening... (Speak now, auto-closes on pause)");

                    recognition.onresult = function(event) {
                        let interim = "";
                        for (let i = event.resultIndex; i < event.results.length; ++i) {
                            if (event.results[i].isFinal) {
                                capturedText += event.results[i][0].transcript + " ";
                            } else {
                                interim += event.results[i][0].transcript;
                            }
                        }
                        const current = (capturedText + interim).trim();
                        if (current.length > 0) {
                            speechDetected = true;
                            resetSilenceTimer();
                        }
                    };

                    recognition.onerror = function(event) {
                        console.log("[VoiceAssistant] Speech error:", event.error);
                        if (event.error === 'no-speech') {
                            stopListening(false);
                        }
                    };

                    recognition.onend = function() {
                        if (isListening) {
                            if (speechDetected && capturedText.trim()) {
                                stopListening(true);
                            } else {
                                stopListening(false);
                            }
                        }
                    };

                    // AudioContext Decibel VAD (Detect voice activity)
                    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                        navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                            parentWin.__voiceMicStream = stream;
                            const AudioCtx = window.AudioContext || window.webkitAudioContext || 
                                             parentWin.AudioContext || parentWin.webkitAudioContext;
                            if (AudioCtx) {
                                const audioContext = new AudioCtx();
                                parentWin.__voiceAudioCtx = audioContext;
                                const analyser = audioContext.createAnalyser();
                                analyser.fftSize = 256;
                                const source = audioContext.createMediaStreamSource(stream);
                                source.connect(analyser);

                                function detectNoiseLevels() {
                                    if (!isListening || !analyser) return;
                                    const buffer = new Uint8Array(analyser.frequencyBinCount);
                                    analyser.getByteFrequencyData(buffer);

                                    let sum = 0;
                                    for (let i = 0; i < buffer.length; i++) {
                                        sum += buffer[i];
                                    }
                                    const avgVolume = sum / buffer.length;

                                    const doc = parentWin.document || document;
                                    const orb = doc.getElementById("mainVoiceOrb");
                                    if (orb && isListening) {
                                        const scale = 1.05 + Math.min(avgVolume / 80, 0.25);
                                        orb.style.transform = `scale(${scale})`;
                                    }

                                    if (avgVolume > 14) {
                                        speechDetected = true;
                                        resetSilenceTimer();
                                    }

                                    requestAnimationFrame(detectNoiseLevels);
                                }
                                detectNoiseLevels();
                            }
                        }).catch(err => {
                            console.log("Mic volume monitor warning:", err);
                        });
                    }

                    recognition.start();

                    // Auto-close if no sound/speech detected
                    noSpeechTimer = setTimeout(() => {
                        if (!speechDetected && isListening) {
                            console.log("[VoiceAssistant] No noise detected - Auto-closing microphone.");
                            updateUI("idle", "💤 No voice detected — Microphone closed (Tap Orb to speak)");
                            stopListening(false);
                        }
                    }, NO_SPEECH_LIMIT_MS);

                } catch (e) {
                    console.error("Mic error:", e);
                    stopListening(false);
                }
            }

            function sendQueryToApp(text) {
                const doc = parentWin.document || document;
                const chatInput = doc.querySelector('textarea[data-testid="stChatInputTextArea"]');
                if (chatInput) {
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                    nativeSetter.call(chatInput, text);
                    chatInput.dispatchEvent(new Event('input', { bubbles: true }));
                    chatInput.dispatchEvent(new Event('change', { bubbles: true }));

                    setTimeout(() => {
                        const sendBtn = doc.querySelector('button[data-testid="stChatInputSubmitButton"]');
                        if (sendBtn && !sendBtn.disabled) {
                            sendBtn.click();
                        } else {
                            chatInput.dispatchEvent(new KeyboardEvent('keydown', {
                                key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                            }));
                        }
                    }, 120);
                }
            }

            // Expose controls globally
            parentWin.voiceStartListening = rootWin.voiceStartListening = startListening;
            parentWin.voiceStopListening = rootWin.voiceStopListening = stopListening;
            parentWin.voiceUpdateUI = rootWin.voiceUpdateUI = updateUI;
            parentWin.toggleVoiceListening = rootWin.toggleVoiceListening = function() {
                if (isListening) {
                    stopListening(true);
                } else {
                    startListening();
                }
            };

            // Bind click to main voice orb
            const doc = parentWin.document || document;
            const orbEl = doc.getElementById("mainVoiceOrb");
            if (orbEl) {
                orbEl.onclick = parentWin.toggleVoiceListening;
            }

            // Continuous Two-Way Conversation Message Handler
            // Reacts to messages from the embedded audio player iframe!
            const messageHandler = function(event) {
                if (!event.data || typeof event.data !== 'object') return;
                const type = event.data.type;

                if (type === 'voice_audio_playing') {
                    // Assistant is currently speaking out loud -> pause mic so it does not hear itself
                    console.log("[VoiceAssistant] Assistant audio playing -> Pausing microphone listener.");
                    stopListening(false);
                    updateUI("speaking", "🔊 Assistant is speaking...");
                } else if (type === 'voice_audio_ended') {
                    // Assistant finished speaking -> automatically ready to listen to next user query!
                    console.log("[VoiceAssistant] Assistant finished speaking! Auto-activating microphone for next query...");
                    updateUI("listening", "🟢 Assistant finished. Listening for your next query...");
                    setTimeout(() => {
                        startListening();
                    }, 400);
                } else if (type === 'voice_audio_stopped') {
                    console.log("[VoiceAssistant] Audio playback stopped manually.");
                    stopListening(false);
                    updateUI("idle", "🎙️ Tap Orb to Speak (Auto-closes on silence)");
                }
            };

            parentWin.__voiceMsgHandler = messageHandler;
            parentWin.addEventListener('message', messageHandler);
            if (rootWin !== parentWin) {
                rootWin.__voiceMsgHandler = messageHandler;
                rootWin.addEventListener('message', messageHandler);
            }
        })();
        </script>
        """
    )

    # Microphone Live Audio Input (Native Streamlit Fallback)
    col_mic_left, col_mic_mid, col_mic_right = st.columns([1, 2, 1])
    with col_mic_mid:
        recorded_audio = st.audio_input(
            "🎙️ Record Voice Question", label_visibility="collapsed"
        )

    # Handle Microphone Voice Input
    if recorded_audio is not None and active_key:
        audio_content = recorded_audio.read()
        audio_sig = hash(audio_content)
        if st.session_state.get("last_processed_audio_sig") != audio_sig:
            st.session_state["last_processed_audio_sig"] = audio_sig
            with st.spinner(
                "🎙️ Listening to your spoken voice & generating speech response with Gemini Live..."
            ):
                try:
                    audio_bytes, spoken_script = generate_product_voice_response(
                        api_key=active_key,
                        user_query=audio_content,
                        history=st.session_state.voice_conversation_history,
                        mime_type=recorded_audio.type or "audio/wav",
                        voice_model=voice_model,
                        voice_name=selected_voice_key,
                    )
                    st.session_state.voice_conversation_history.append(
                        {"role": "user", "text": "Customer spoke via microphone"}
                    )
                    st.session_state.voice_conversation_history.append(
                        {"role": "model", "text": spoken_script}
                    )
                    if len(st.session_state.voice_conversation_history) > 4:
                        st.session_state.voice_conversation_history = (
                            st.session_state.voice_conversation_history[-4:]
                        )

                    st.session_state.voice_audio_bytes = audio_bytes
                    st.session_state.voice_audio_meta = {
                        "model": voice_model,
                        "voice": selected_voice_key,
                        "gender": selected_voice_info["gender"],
                        "timestamp": int(time.time()),
                    }
                    save_persisted_session(
                        session_id=current_session_id,
                        history=st.session_state.voice_conversation_history,
                        audio_bytes=audio_bytes,
                        audio_meta=st.session_state.voice_audio_meta,
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"⚠️ Voice processing error: {e}")

    # Quick Spoken Question Prompts (Voice Starters)
    st.markdown(
        "<p style='text-align:center; font-weight:600; color:#475569; margin-top:10px;'>💡 Or tap to ask a question:</p>",
        unsafe_allow_html=True,
    )
    voice_prompts = [
        (
            "🌸 What is the price and benefits of Lotus Mala?",
            "Tell me the price, discount, bead count, and benefits of Lotus Mala.",
        ),
        (
            "⚖️ Compare Lotus Mala vs Navaratna Mala",
            "Compare the Lotus Mala and the Navaratna Gemstone Mala.",
        ),
        (
            "🛒 What items are in my cart right now?",
            "Check my cart status across all products. What is currently in my cart and the quantity?",
        ),
        (
            "📿 Which malas have exactly 108 beads?",
            "Which malas in the store have exactly 108 beads and what are their prices?",
        ),
        (
            "📦 Which product has the lowest stock?",
            "Which product in the catalog has the lowest stock availability?",
        ),
        (
            "🌿 Tell me about Ruthra Sakthi Vilva Mala",
            "What are the bead details, size, and spiritual benefits of Ruthra Sakthi Vilva Mala?",
        ),
    ]

    p_cols = st.columns(3)
    for idx, (label, query_text) in enumerate(voice_prompts):
        with p_cols[idx % 3]:
            if st.button(
                label, key=f"voice_prompt_btn_{idx}", use_container_width=True
            ):
                st.session_state.pending_voice_query = query_text
                st.rerun()

    # User Question Input (Audio Prompt Input)
    st.markdown("<br>", unsafe_allow_html=True)
    pending_v_query = st.session_state.pop("pending_voice_query", None)
    user_voice_query = (
        st.chat_input("Ask any product question to hear the voice response...")
        or pending_v_query
    )

    # Process Voice Query & Generate Exclusively Audio
    if user_voice_query:
        if not active_key:
            st.error(
                "❌ **API Key Required**: Please enter your Google Gemini API key in the left sidebar to enable voice responses."
            )
        else:
            with st.spinner(
                "🎙️ Analyzing product data and synthesizing audio response with Gemini Live..."
            ):
                try:
                    # Generate speech bytes strictly based on mergeProduct without any text printed to screen
                    audio_bytes, spoken_script = generate_product_voice_response(
                        api_key=active_key,
                        user_query=user_voice_query,
                        history=st.session_state.voice_conversation_history,
                        voice_model=voice_model,
                        voice_name=selected_voice_key,
                    )
                    st.session_state.voice_conversation_history.append(
                        {"role": "user", "text": str(user_voice_query)}
                    )
                    st.session_state.voice_conversation_history.append(
                        {"role": "model", "text": spoken_script}
                    )
                    if len(st.session_state.voice_conversation_history) > 4:
                        st.session_state.voice_conversation_history = (
                            st.session_state.voice_conversation_history[-4:]
                        )

                    st.session_state.voice_audio_bytes = audio_bytes
                    st.session_state.voice_audio_meta = {
                        "model": voice_model,
                        "voice": selected_voice_key,
                        "gender": selected_voice_info["gender"],
                        "timestamp": int(time.time()),
                    }
                    save_persisted_session(
                        session_id=current_session_id,
                        history=st.session_state.voice_conversation_history,
                        audio_bytes=audio_bytes,
                        audio_meta=st.session_state.voice_audio_meta,
                    )
                except Exception as e:
                    st.error(f"⚠️ Audio generation failed: {str(e)}")

    # Audio Playback Controls (Displayed Exclusively as Audio Controller)
    if (
        st.session_state.voice_audio_bytes is not None
        and st.session_state.voice_audio_meta is not None
    ):
        st.markdown(
            "<div style='max-width: 800px; margin: 12px auto 0 auto;'>",
            unsafe_allow_html=True,
        )
        c_spk1, c_spk2, c_spk3 = st.columns([1, 1.4, 1])
        with c_spk2:
            if st.button(
                "🔊 Speak Again",
                key="btn_speak_again_action",
                use_container_width=True,
                help="Replay the assistant's latest voice response without making an API request",
            ):
                st.session_state["replay_nonce"] = time.time()
                st.rerun()

        player_nonce = st.session_state.get("replay_nonce", 0)
        player_html = render_audio_controller_html(
            wav_bytes=st.session_state.voice_audio_bytes,
            model_name=st.session_state.voice_audio_meta["model"],
            voice_name=st.session_state.voice_audio_meta["voice"],
            voice_gender=st.session_state.voice_audio_meta["gender"],
            auto_play=True,
        )
        components.html(player_html + f"<!-- nonce: {player_nonce} -->", height=210)
        st.markdown("</div>", unsafe_allow_html=True)


# =============================================================
# APP MODE 2: CUSTOM TAMIL VOICE STUDIO
# =============================================================
elif app_mode == "🎙️ Custom Tamil Voice Studio":
    col_h1, col_h2 = st.columns([0.78, 0.22])
    with col_h1:
        st.markdown(
            """
        <div class="chat-header">
            <div>
                <h1 class="chat-title">🎙️ தமிழ் குரல் ஸ்டுடியோ (Custom Tamil Voice Studio)</h1>
                <p class="chat-subtitle">Speak any custom Tamil text using Gemini Live Native Audio</p>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_h2:
        if active_key:
            st.caption(f"⚡ Model: `{voice_model}`")
            st.caption(
                f"🎙️ Voice: `{selected_voice_key}` ({selected_voice_info['gender']})"
            )
        else:
            st.warning("🔑 API Key Required", icon="⚠️")

    if "tamil_input_text" not in st.session_state:
        st.session_state.tamil_input_text = (
            "வணக்கம்! நான் உங்கள் தமிழ் குரல் உதவியாளர். உங்களுக்கு இன்று நான் எவ்வாறு உதவ முடியும்?"
        )

    if "current_audio_bytes" not in st.session_state:
        st.session_state.current_audio_bytes = None

    if "audio_meta" not in st.session_state:
        st.session_state.audio_meta = None

    sample_cols = st.columns(len(TAMIL_SAMPLE_PHRASES))
    for i, phrase in enumerate(TAMIL_SAMPLE_PHRASES):
        with sample_cols[i]:
            if st.button(
                phrase["title"], key=f"phrase_btn_{i}", use_container_width=True
            ):
                st.session_state.tamil_input_text = phrase["text"]
                st.rerun()

    tamil_text_input = st.text_area(
        label="Tamil Content",
        label_visibility="collapsed",
        value=st.session_state.tamil_input_text,
        height=140,
        placeholder="இங்கு உங்கள் தமிழ் உரையை உள்ளிடவும்...",
    )
    st.session_state.tamil_input_text = tamil_text_input

    col_act1, col_act2 = st.columns([0.3, 0.7])
    with col_act1:
        speak_btn = st.button(
            "🗣️ தமிழில் பேசு (Speak in Tamil)", type="primary", use_container_width=True
        )

    if speak_btn:
        if not active_key:
            st.error(
                "❌ **API Key Required**: Please enter your Gemini API key in the sidebar."
            )
        elif not tamil_text_input or not tamil_text_input.strip():
            st.warning("⚠️ **Empty Text**: Please enter some Tamil text.")
        else:
            with st.spinner(
                f"🎙️ Synthesizing voice with Gemini Live ({voice_model} — {selected_voice_key})..."
            ):
                try:
                    audio_data = synthesize_tamil_speech(
                        api_key=active_key,
                        text=tamil_text_input,
                        model_name=voice_model,
                        voice_name=selected_voice_key,
                    )
                    st.session_state.current_audio_bytes = audio_data
                    st.session_state.audio_meta = {
                        "model": voice_model,
                        "voice": selected_voice_key,
                        "gender": selected_voice_info["gender"],
                        "timestamp": int(time.time()),
                    }
                    st.success("✅ Voice synthesized successfully!")
                except Exception as e:
                    st.error(f"⚠️ Voice Generation Failed: {e}")

    if (
        st.session_state.current_audio_bytes is not None
        and st.session_state.audio_meta is not None
    ):
        player_html = render_audio_controller_html(
            wav_bytes=st.session_state.current_audio_bytes,
            model_name=st.session_state.audio_meta["model"],
            voice_name=st.session_state.audio_meta["voice"],
            voice_gender=st.session_state.audio_meta["gender"],
            auto_play=auto_play,
        )
        components.html(player_html, height=210)


# =============================================================
# APP MODE 3: GEMINI AI CHAT
# =============================================================
else:

    def send_gemini_message(prompt: str, history_messages: list):
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=active_key)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction if system_instruction else None,
            temperature=temperature,
        )

        history_contents = []
        for m in history_messages:
            role = "user" if m["role"] == "user" else "model"
            history_contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=m["content"])],
                )
            )

        chat = client.chats.create(
            model=selected_chat_model,
            config=config,
            history=history_contents if history_contents else None,
        )

        for chunk in chat.send_message_stream(prompt):
            yield chunk

    if "messages" not in st.session_state:
        st.session_state.messages = []

    col_h1, col_h2 = st.columns([0.8, 0.2])
    with col_h1:
        st.markdown(
            """
        <div class="chat-header">
            <div>
                <h1 class="chat-title">Gemini AI Assistant</h1>
                <p class="chat-subtitle">Powered by Google Gemini • Streaming • Multi-turn Chat</p>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    for msg in st.session_state.messages:
        with st.chat_message(
            msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🤖"
        ):
            st.markdown(msg["content"])

    pending_prompt = st.session_state.pop("pending_prompt", None)
    user_prompt = st.chat_input("Type your message here...") or pending_prompt

    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_prompt)

        with st.chat_message("assistant", avatar="🤖"):
            if active_key:
                try:
                    prior_messages = (
                        st.session_state.messages[-11:-1]
                        if len(st.session_state.messages) > 11
                        else st.session_state.messages[:-1]
                    )
                    response_placeholder = st.empty()
                    accumulated_text = ""

                    response_stream = send_gemini_message(user_prompt, prior_messages)
                    for chunk in response_stream:
                        if chunk.text:
                            accumulated_text += chunk.text
                            response_placeholder.markdown(accumulated_text + "▌")

                    response_placeholder.markdown(accumulated_text)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": accumulated_text}
                    )
                except Exception as e:
                    st.error(f"⚠️ Error: {e}")
                    st.session_state.messages.append(
                        {"role": "assistant", "content": f"⚠️ Error: {e}"}
                    )
            else:
                st.warning("Please enter your Gemini API key in the sidebar.")
