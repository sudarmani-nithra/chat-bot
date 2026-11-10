"""
Tamil Voice Assistant Engine using Google Gemini Live API.
Provides native audio generation, PCM to WAV conversion,
and interactive audio player UI controls (Speak, Pause, Resume, Stop, Replay).
"""

import io
import wave
import time
import base64
import asyncio
import threading
from typing import Optional, Dict

# Supported Gemini Live & Audio Models
GEMINI_AUDIO_MODELS = [
    "gemini-2.5-flash-native-audio-latest",  # Gemini 2.5 Flash Native Audio (Official Live Audio Model)
    "gemini-2.0-flash-exp",  # Gemini 2.0 Flash Experimental Live
]

# Curated Male and Female Prebuilt Voices
GEMINI_VOICES: Dict[str, Dict[str, str]] = {
    # Female Voices
    "Aoede": {
        "gender": "Female",
        "label": "Aoede (Female — Breezy, melodious & expressive)",
        "desc": "Natural, clear, and melodious female voice",
    },
    "Kore": {
        "gender": "Female",
        "label": "Kore (Female — Warm, firm & confident)",
        "desc": "Warm, articulate, and firm female voice",
    },
    "Leda": {
        "gender": "Female",
        "label": "Leda (Female — Youthful, lively & bright)",
        "desc": "Youthful, energetic, and engaging female voice",
    },
    "Callirrhoe": {
        "gender": "Female",
        "label": "Callirrhoe (Female — Calm, easy-going & gentle)",
        "desc": "Gentle, easy-going, and relaxed female voice",
    },
    "Sulafat": {
        "gender": "Female",
        "label": "Sulafat (Female — Soft, soothing & warm)",
        "desc": "Soft, warm, and soothing female voice",
    },
    # Male Voices
    "Puck": {
        "gender": "Male",
        "label": "Puck (Male — Upbeat, lively & engaging)",
        "desc": "Upbeat, lively, and engaging male voice",
    },
    "Charon": {
        "gender": "Male",
        "label": "Charon (Male — Calm, informative & deep)",
        "desc": "Calm, professional, and lower-pitched male voice",
    },
    "Fenrir": {
        "gender": "Male",
        "label": "Fenrir (Male — Energetic, confident & dynamic)",
        "desc": "Energetic, clear, and confident male voice",
    },
    "Orus": {
        "gender": "Male",
        "label": "Orus (Male — Firm, professional & clear)",
        "desc": "Authoritative, firm, and corporate male voice",
    },
    "Iapetus": {
        "gender": "Male",
        "label": "Iapetus (Male — Articulate, smooth & clear)",
        "desc": "Clear, articulated, and balanced male voice",
    },
}

# Sample Tamil phrases for quick testing
TAMIL_SAMPLE_PHRASES = [
    {
        "title": "🙏 வாழ்த்து (Greeting)",
        "text": "வணக்கம்! நான் உங்கள் தமிழ் குரல் உதவியாளர். உங்களுக்கு இன்று நான் எவ்வாறு உதவ முடியும்?",
    },
    {
        "title": "📜 தமிழ் பெருமை (Tamil Heritage)",
        "text": "தமிழ் மொழி உலகின் மிகத் தொன்மையான மற்றும் வளமான செம்மொழிகளில் ஒன்றாகும். அதன் இலக்கிய வளம் ஈடு இணையற்றது.",
    },
    {
        "title": "💡 அறிவுரை (Inspiration)",
        "text": "வாழ்க்கையில் வெற்றி பெற கடின உழைப்பும், விடாமுயற்சியும், நேர்மறையான எண்ணமும் மிக அவசியம். நம்பிக்கை என்றும் வீண் போகாது.",
    },
    {
        "title": "🚀 தொழில்நுட்பம் (AI & Technology)",
        "text": "செயற்கை நுண்ணறிவு தொழில்நுட்பம் உலகை மிக வேகமாக மாற்றி வருகிறது. இது மனிதர்களின் கற்றல் மற்றும் உற்பத்தித் திறனை பல மடங்கு உயர்த்துகிறது.",
    },
]


def pcm_to_wav(
    pcm_bytes: bytes,
    sample_rate: int = 24000,
    num_channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """
    Wraps raw 16-bit linear PCM audio into a standard RIFF/WAV container.
    Defaults: 24,000 Hz, 16-bit (2 bytes) signed little-endian, Mono.
    """
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return wav_io.getvalue()


def run_async_coroutine(coro):
    """
    Safely executes an async coroutine inside an isolated thread with its own event loop.
    Prevents event-loop collision in Streamlit's script-runner thread.
    """
    result = None
    exception = None

    def runner():
        nonlocal result, exception
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
        except Exception as e:
            exception = e
        finally:
            try:
                loop.close()
            except Exception:
                pass

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()

    if exception:
        raise exception
    return result


async def _generate_tamil_speech_live_async(
    api_key: str, text: str, model_name: str, voice_name: str
) -> bytes:
    """
    Internal coroutine for Gemini Live API audio generation.
    Connects to client.aio.live.connect with response_modalities=["AUDIO"].
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an authentic, expressive Tamil female voice assistant (Aoede). "
        "Your task is to speak the provided text aloud in a fluent, natural, melodious and warm Tamil female voice. "
        "Pronounce every word accurately with appropriate pauses, natural cadence, and emotion in authentic native Tamil. "
        "Speak EXCLUSIVELY in an authentic Tamil female voice. Never speak with a Western or English accent. "
        "Do NOT speak any introductory phrases or greetings like 'Sure, here is the audio'. "
        "Directly speak the provided text."
    )


    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=system_instruction)]
        ),
    )

    prompt = f"Speak the following text aloud clearly and expressively:\n\n{text}"

    pcm_chunks = []
    async with client.aio.live.connect(model=model_name, config=config) as session:
        # Send user prompt turn
        await session.send_client_content(
            turns=[
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            ],
            turn_complete=True,
        )

        # Receive real-time audio chunks
        async for response in session.receive():
            if response.data:
                pcm_chunks.append(response.data)

            if response.server_content:
                if (
                    response.server_content.turn_complete
                    or response.server_content.generation_complete
                ):
                    break

    if not pcm_chunks:
        raise ValueError("No audio chunks received from Gemini Live API session.")

    raw_data = b"".join(pcm_chunks)
    if raw_data.startswith(b"RIFF"):
        return raw_data
    return pcm_to_wav(raw_data, sample_rate=24000)


def _generate_tamil_speech_content_sync(
    api_key: str, text: str, model_name: str, voice_name: str
) -> bytes:
    """
    Fallback audio generation using client.models.generate_content with AUDIO modality.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an authentic, expressive Tamil female voice assistant (Aoede). "
        "Speak the provided content aloud clearly, warmly and naturally with proper Tamil female pronunciation and pauses. "
        "Speak EXCLUSIVELY in authentic native Tamil female voice. "
        "Do not provide conversational chit-chat. Output only spoken audio."
    )

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        system_instruction=system_instruction,
    )

    response = client.models.generate_content(
        model=model_name,
        contents=f"Speak this text naturally:\n\n{text}",
        config=config,
    )

    for candidate in response.candidates or []:
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    data = part.inline_data.data
                    if data.startswith(b"RIFF"):
                        return data
                    return pcm_to_wav(data, sample_rate=24000)

    raise ValueError("No audio content returned in model response parts.")


def synthesize_tamil_speech(
    api_key: str,
    text: str,
    model_name: str = "gemini-2.5-flash-native-audio-latest",
    voice_name: str = "Aoede",
) -> bytes:
    """
    Generates natural Tamil audio speech using Gemini Live API,
    with an automatic fallback to generate_content if the live websocket session encounters an issue.
    """
    if not api_key:
        raise ValueError("Gemini API key is required.")
    if not text or not text.strip():
        raise ValueError("Tamil text cannot be empty.")

    cleaned_text = text.strip()

    candidate_models = [model_name]
    for alt_model in ["gemini-2.5-flash-native-audio-latest", "gemini-2.0-flash-exp"]:
        if alt_model not in candidate_models:
            candidate_models.append(alt_model)

    last_error = None
    for m in candidate_models:
        for attempt in range(2):
            # 1. Try Gemini Live API
            try:
                return run_async_coroutine(
                    _generate_tamil_speech_live_async(
                        api_key, cleaned_text, m, voice_name
                    )
                )
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "503" in err_str or "high demand" in err_str or "unavailable" in err_str:
                    time.sleep(1.0)

            # 2. Try generate_content with AUDIO modality
            try:
                return _generate_tamil_speech_content_sync(
                    api_key, cleaned_text, m, voice_name
                )
            except Exception as fallback_error:
                last_error = fallback_error
                err_str = str(fallback_error).lower()
                if "503" in err_str or "high demand" in err_str or "unavailable" in err_str:
                    time.sleep(1.0)

    raise RuntimeError(
        f"Failed to generate voice via Gemini Audio models: {last_error}"
    )


def render_audio_controller_html(
    wav_bytes: bytes,
    model_name: str,
    voice_name: str,
    voice_gender: str,
    auto_play: bool = True,
) -> str:
    """
    Generates a sleek, fully-featured HTML5/JS audio player component
    with Speak, Pause, Resume, Stop, and Replay controls, scrubbable progress bar,
    animated waveform, volume slider, and real-time playback status.
    """
    b64_audio = base64.b64encode(wav_bytes).decode("utf-8")
    auto_play_attr = "autoplay" if auto_play else ""

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        * {{
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        body {{
            margin: 0;
            padding: 10px 0;
            background: transparent;
        }}
        .player-container {{
            background: #ffffff;
            border: 1px solid #e1e4e8;
            border-radius: 14px;
            padding: 18px 22px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05);
            max-width: 100%;
        }}
        .player-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 14px;
            padding-bottom: 12px;
            border-bottom: 1px solid #f0f2f5;
        }}
        .badges-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 600;
        }}
        .badge-model {{
            background: #eef2ff;
            color: #4338ca;
            border: 1px solid #c7d2fe;
        }}
        .badge-voice {{
            background: #fdf2f8;
            color: #be185d;
            border: 1px solid #fbcfe8;
        }}
        .badge-status {{
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
            transition: all 0.2s ease;
        }}
        .badge-status.paused {{
            background: #fffbeb;
            color: #b45309;
            border-color: #fde68a;
        }}
        .badge-status.stopped {{
            background: #f3f4f6;
            color: #4b5563;
            border-color: #e5e7eb;
        }}

        /* Waveform Animation */
        .visualizer {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            height: 36px;
            margin: 12px 0 16px 0;
            background: #f8fafc;
            border-radius: 10px;
            padding: 0 16px;
        }}
        .wave-bar {{
            width: 4px;
            height: 8px;
            background: #cbd5e1;
            border-radius: 3px;
            transition: height 0.15s ease, background-color 0.2s ease;
        }}
        .visualizer.active .wave-bar {{
            background: linear-gradient(180deg, #3b82f6, #8b5cf6);
            animation: bounce 0.9s infinite ease-in-out alternate;
        }}
        .visualizer.active .wave-bar:nth-child(2) {{ animation-delay: 0.1s; }}
        .visualizer.active .wave-bar:nth-child(3) {{ animation-delay: 0.25s; }}
        .visualizer.active .wave-bar:nth-child(4) {{ animation-delay: 0.4s; }}
        .visualizer.active .wave-bar:nth-child(5) {{ animation-delay: 0.15s; }}
        .visualizer.active .wave-bar:nth-child(6) {{ animation-delay: 0.3s; }}
        .visualizer.active .wave-bar:nth-child(7) {{ animation-delay: 0.45s; }}
        .visualizer.active .wave-bar:nth-child(8) {{ animation-delay: 0.2s; }}
        .visualizer.active .wave-bar:nth-child(9) {{ animation-delay: 0.35s; }}
        .visualizer.active .wave-bar:nth-child(10) {{ animation-delay: 0.5s; }}
        .visualizer.active .wave-bar:nth-child(11) {{ animation-delay: 0.15s; }}
        .visualizer.active .wave-bar:nth-child(12) {{ animation-delay: 0.3s; }}
        .visualizer.active .wave-bar:nth-child(13) {{ animation-delay: 0.25s; }}
        .visualizer.active .wave-bar:nth-child(14) {{ animation-delay: 0.4s; }}

        @keyframes bounce {{
            0% {{ height: 6px; }}
            100% {{ height: 28px; }}
        }}

        /* Timeline / Progress Bar */
        .timeline-wrapper {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .time-text {{
            font-size: 0.82rem;
            color: #64748b;
            font-variant-numeric: tabular-nums;
            min-width: 42px;
        }}
        .time-current {{ text-align: right; }}
        .time-duration {{ text-align: left; }}
        .progress-bar {{
            flex: 1;
            height: 6px;
            background: #e2e8f0;
            border-radius: 4px;
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #3b82f6, #6366f1);
            border-radius: 4px;
            transition: width 0.1s linear;
        }}

        /* Control Buttons */
        .controls-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .button-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.86rem;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid #d1d5db;
            background: #ffffff;
            color: #1f2937;
            transition: all 0.15s ease-in-out;
            user-select: none;
        }}
        .btn:hover {{
            background: #f9fafb;
            border-color: #9ca3af;
            transform: translateY(-1px);
        }}
        .btn:active {{
            transform: translateY(0);
        }}
        .btn-primary {{
            background: #2563eb;
            color: #ffffff;
            border-color: #1d4ed8;
        }}
        .btn-primary:hover {{
            background: #1d4ed8;
            color: #ffffff;
        }}
        .btn-stop {{
            background: #fee2e2;
            color: #b91c1c;
            border-color: #fca5a5;
        }}
        .btn-stop:hover {{
            background: #fecaca;
            color: #991b1b;
        }}

        /* Volume & Extra */
        .volume-group {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .volume-icon {{
            font-size: 0.95rem;
            color: #64748b;
        }}
        .volume-slider {{
            width: 85px;
            height: 5px;
            accent-color: #3b82f6;
            cursor: pointer;
        }}
    </style>
    </head>
    <body>
        <div class="player-container">
            <!-- Header Badges -->
            <div class="player-header">
                <div class="badges-group">
                    <span class="badge badge-model">🤖 {model_name}</span>
                    <span class="badge badge-voice">🎙️ {voice_name} ({voice_gender})</span>
                    <span class="badge" style="background:#f1f5f9; color:#475569; border:1px solid #cbd5e1;">🔊 24 kHz WAV</span>
                </div>
                <div>
                    <span id="statusBadge" class="badge badge-status">🟢 Playing</span>
                </div>
            </div>

            <!-- Waveform Animation -->
            <div id="visualizer" class="visualizer active">
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
            </div>

            <!-- Progress Bar / Timeline -->
            <div class="timeline-wrapper">
                <span id="currentTime" class="time-text time-current">0:00</span>
                <div id="progressBar" class="progress-bar">
                    <div id="progressFill" class="progress-fill"></div>
                </div>
                <span id="durationTime" class="time-text time-duration">0:00</span>
            </div>

            <!-- Controls Row -->
            <div class="controls-row">
                <div class="button-group">
                    <button id="btnPlay" class="btn btn-primary" title="Speak / Play">
                        <span>▶️ Speak</span>
                    </button>
                    <button id="btnPause" class="btn" title="Pause playback">
                        <span>⏸️ Pause</span>
                    </button>
                    <button id="btnResume" class="btn" title="Resume playback">
                        <span>⏯️ Resume</span>
                    </button>
                    <button id="btnStop" class="btn btn-stop" title="Stop and rewind">
                        <span>⏹️ Stop</span>
                    </button>
                    <button id="btnReplay" class="btn" title="Speak again (Replay response)">
                        <span>🔊 Speak Again</span>
                    </button>
                </div>

                <div class="volume-group">
                    <span class="volume-icon">🔊</span>
                    <input type="range" id="volumeSlider" class="volume-slider" min="0" max="1" step="0.05" value="1" title="Volume">
                </div>
            </div>

            <!-- Embedded Audio Element -->
            <audio id="audioElement" {auto_play_attr} preload="auto">
                <source src="data:audio/wav;base64,{b64_audio}" type="audio/wav">
            </audio>
        </div>

        <script>
            const audio = document.getElementById('audioElement');
            const btnPlay = document.getElementById('btnPlay');
            const btnPause = document.getElementById('btnPause');
            const btnResume = document.getElementById('btnResume');
            const btnStop = document.getElementById('btnStop');
            const btnReplay = document.getElementById('btnReplay');
            const statusBadge = document.getElementById('statusBadge');
            const visualizer = document.getElementById('visualizer');
            const currentTimeEl = document.getElementById('currentTime');
            const durationTimeEl = document.getElementById('durationTime');
            const progressBar = document.getElementById('progressBar');
            const progressFill = document.getElementById('progressFill');
            const volumeSlider = document.getElementById('volumeSlider');

            function formatTime(seconds) {{
                if (isNaN(seconds) || seconds < 0) return "0:00";
                const mins = Math.floor(seconds / 60);
                const secs = Math.floor(seconds % 60);
                return `${{mins}}:${{secs < 10 ? '0' : ''}}${{secs}}`;
            }}

            function setStatus(status, className) {{
                statusBadge.textContent = status;
                statusBadge.className = 'badge badge-status ' + (className || '');
            }}

            // Event Listeners for Audio
            audio.addEventListener('loadedmetadata', () => {{
                durationTimeEl.textContent = formatTime(audio.duration);
            }});

            audio.addEventListener('timeupdate', () => {{
                currentTimeEl.textContent = formatTime(audio.currentTime);
                if (audio.duration) {{
                    const pct = (audio.currentTime / audio.duration) * 100;
                    progressFill.style.width = pct + '%';
                }}
            }});

            function notifyParent(eventType) {{
                try {{
                    if (window.parent && window.parent !== window) {{
                        window.parent.postMessage({{ type: eventType }}, '*');
                    }}
                }} catch (e) {{
                    console.error('Failed to notify parent window:', e);
                }}
            }}

            audio.addEventListener('play', () => {{
                setStatus('🟢 Playing', '');
                visualizer.classList.add('active');
                notifyParent('voice_audio_playing');
            }});

            audio.addEventListener('pause', () => {{
                if (audio.currentTime === 0) {{
                    setStatus('⏹️ Stopped', 'stopped');
                }} else {{
                    setStatus('⏸️ Paused', 'paused');
                }}
                visualizer.classList.remove('active');
                notifyParent('voice_audio_paused');
            }});

            audio.addEventListener('ended', () => {{
                setStatus('🟢 Ready to Listen', '');
                visualizer.classList.remove('active');
                progressFill.style.width = '100%';
                notifyParent('voice_audio_ended');
            }});

            // Controls Implementation
            btnPlay.addEventListener('click', () => {{
                audio.play().catch(e => console.log('Playback error:', e));
            }});

            btnPause.addEventListener('click', () => {{
                audio.pause();
            }});

            btnResume.addEventListener('click', () => {{
                audio.play().catch(e => console.log('Playback error:', e));
            }});

            btnStop.addEventListener('click', () => {{
                audio.pause();
                audio.currentTime = 0;
                progressFill.style.width = '0%';
                currentTimeEl.textContent = '0:00';
                setStatus('⏹️ Stopped', 'stopped');
                notifyParent('voice_audio_stopped');
            }});

            btnReplay.addEventListener('click', () => {{
                audio.currentTime = 0;
                progressFill.style.width = '0%';
                audio.play().catch(e => console.log('Playback error:', e));
            }});

            // Scrubbing Progress Bar
            progressBar.addEventListener('click', (e) => {{
                if (!audio.duration) return;
                const rect = progressBar.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const pct = Math.max(0, Math.min(1, clickX / rect.width));
                audio.currentTime = pct * audio.duration;
            }});

            // Volume Control
            volumeSlider.addEventListener('input', (e) => {{
                audio.volume = parseFloat(e.target.value);
            }});

            // Initial status setup
            if ({'true' if auto_play else 'false'}) {{
                audio.play().then(() => {{
                    setStatus('🟢 Playing', '');
                    visualizer.classList.add('active');
                    notifyParent('voice_audio_playing');
                }}).catch(() => {{
                    // Autoplay policy prevented immediate playback
                    setStatus('🟢 Ready to Speak', '');
                    visualizer.classList.remove('active');
                }});
            }} else {{
                setStatus('🟢 Ready to Speak', '');
                visualizer.classList.remove('active');
            }}
        </script>
    </body>
    </html>
    """
    return html_code
