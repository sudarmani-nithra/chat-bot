"""
Native Multilingual Voice Engine powered by Google Gemini Live Audio API.
Provides high-fidelity Tamil and Telugu voice synthesis (TTS) using Aoede female voice
and Gemini multimodal audio transcription (STT).
"""

import os
import io
import wave
import time
import hashlib
import base64
import asyncio
import threading
from pathlib import Path
from typing import Optional, Tuple
import config

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

# Audio disk cache directory (use /tmp on Vercel serverless environment)
if os.getenv("VERCEL"):
    AUDIO_CACHE_DIR = Path("/tmp/audio_cache")
else:
    AUDIO_CACHE_DIR = Path(__file__).resolve().parent / "audio_cache"

try:
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Exclusively female voices for natural customer conversation
FEMALE_VOICES = {"Aoede", "Kore", "Leda", "Callirrhoe", "Sulafat"}
DEFAULT_MODEL = getattr(config, "GEMINI_AUDIO_MODEL", "gemini-2.0-flash-exp")
DEFAULT_VOICE = "Aoede"  # 100% Female natural voice


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
    """Safely executes an async coroutine inside an isolated thread with its own event loop."""
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


async def _generate_speech_live_async(
    api_key: str, text: str, model_name: str, voice_name: str
) -> bytes:
    """Internal coroutine for Gemini Live API audio generation."""
    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an authentic, expressive female voice assistant (Aoede). "
        "Your task is to speak the provided text aloud in a fluent, natural, melodious and warm female voice. "
        "Pronounce every word accurately with appropriate pauses, natural cadence, and emotion in authentic native Tamil or Telugu. "
        "Never speak with a Western or English accent. Output only the spoken audio."
    )

    live_config = types.LiveConnectConfig(
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
    async with client.aio.live.connect(model=model_name, config=live_config) as session:
        await session.send_client_content(
            turns=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            turn_complete=True,
        )

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


def _generate_speech_content_sync(
    api_key: str, text: str, model_name: str, voice_name: str
) -> bytes:
    """Fallback audio generation using client.models.generate_content with AUDIO modality."""
    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an authentic, expressive female voice assistant (Aoede). "
        "Speak the provided content aloud clearly, warmly and naturally with proper native pronunciation and pauses. "
        "Do not provide conversational chit-chat. Output only spoken audio."
    )

    gen_config = types.GenerateContentConfig(
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
        config=gen_config,
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
    model_name: str = DEFAULT_MODEL,
    voice_name: str = DEFAULT_VOICE,
) -> bytes:
    """Generates natural audio speech using Gemini Live API."""
    if not api_key:
        raise ValueError("Gemini API key is required.")
    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")

    cleaned_text = text.strip()
    candidate_models = [model_name, "gemini-2.0-flash-exp"]
    unique_models = []
    for m in candidate_models:
        if m and m not in unique_models:
            unique_models.append(m)

    last_error = None
    for m in unique_models:
        for attempt in range(2):
            try:
                return run_async_coroutine(
                    _generate_speech_live_async(api_key, cleaned_text, m, voice_name)
                )
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "503" in err_str or "high demand" in err_str or "unavailable" in err_str:
                    time.sleep(0.5)

    raise RuntimeError(f"Gemini Live voice synthesis failed: {last_error}")


def _get_cache_path(text: str, language: str, voice_name: str) -> Path:
    """Generates unique file path for caching generated WAV audio on disk."""
    key = f"{language}_{voice_name}_{text}".encode("utf-8")
    md5 = hashlib.md5(key).hexdigest()
    return AUDIO_CACHE_DIR / f"{md5}.wav"


def normalize_spoken_numbers(text: str, language: str = "ta") -> str:
    """
    Converts numbers into exact phonetic words in Tamil and Telugu so TTS models
    never mispronounce numbers (e.g. 108 is pronounced 'நூற்றி எட்டு', NOT 'ஆயிரத்து எட்டு' 1008).
    """
    if not text:
        return ""
    import re
    t = text
    lang = (language or "ta").lower().strip()

    if lang == "te":
        t = re.sub(r'(?<!\d)108(?!\d)', 'నూట ఎనిమిది', t)
        t = re.sub(r'(?<!\d)1008(?!\d)', 'వెయ్యి ఎనిమిది', t)
        t = re.sub(r'(?<!\d)54(?!\d)', 'యాభై నాలుగు', t)
        t = re.sub(r'(?<!\d)27(?!\d)', 'ఇరవై ఏడు', t)
        t = re.sub(r'(?<!\d)8\s*(?:మిல்లీమీటర్లు|మిమీ|mm)', 'ఎనిమిది మిల్లీమీటర్లు', t, flags=re.IGNORECASE)
    else:
        t = re.sub(r'(?<!\d)108(?!\d)', 'நூற்றி எட்டு', t)
        t = re.sub(r'(?<!\d)1008(?!\d)', 'ஆயிரத்து எட்டு', t)
        t = re.sub(r'(?<!\d)54(?!\d)', 'ஐம்பத்து நான்கு', t)
        t = re.sub(r'(?<!\d)27(?!\d)', 'இருபத்தேழு', t)
        t = re.sub(r'(?<!\d)8\s*(?:மில்லிமீட்டர்|மிமீ|mm)', 'எட்டு மில்லிமீட்டர்', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!\d)12\s*(?:இன்ச்|inch)', 'பன்னிரண்டு இன்ச்', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!\d)14\s*(?:இன்ச்|inch)', 'பதினான்கு இன்ச்', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!\d)9\s*(?:இன்ச்|inch)', 'ஒன்பது இன்ச்', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!\d)5\s*(?:இன்ச்|inch)', 'ஐந்து இன்ச்', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!\d)3\s*(?:இன்ச்|inch)', 'மூன்று இன்ச்', t, flags=re.IGNORECASE)

        t = re.sub(r'\b(?:cash\s*on\s*delivery|cod)\b', 'கேஷ் ஆன் டெலிவரி', t, flags=re.IGNORECASE)
        t = re.sub(r'\bproduct\b', 'பொருள்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bproducts\b', 'பொருட்கள்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bmrp\b', 'எம்.ஆர்.பி', t, flags=re.IGNORECASE)
        t = re.sub(r'\boffer\b', 'ஆஃபர்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bdiscount\b', 'டிஸ்கவுண்ட்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bdelivery\b', 'டெலிவரி', t, flags=re.IGNORECASE)
        t = re.sub(r'\bwhatsapp\b', 'வாட்ஸ்அப்', t, flags=re.IGNORECASE)

    return t


def synthesize_speech_wav(
    text: str,
    language: str = "ta",
    voice_name: str = DEFAULT_VOICE,
    model_name: str = DEFAULT_MODEL
) -> Tuple[bytes, str]:
    """Generates natural WAV audio using Gemini Live Native Audio with authentic female voice."""
    raw_text = (text or "").strip()
    if not raw_text or not config.GEMINI_API_KEY:
        return b"", "audio/wav"

    cleaned_text = normalize_spoken_numbers(raw_text, language)

    if voice_name not in FEMALE_VOICES:
        voice_name = DEFAULT_VOICE

    cache_path = _get_cache_path(cleaned_text, language, voice_name)
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                return f.read(), "audio/wav"
        except Exception:
            pass

    try:
        wav_bytes = synthesize_tamil_speech(
            api_key=config.GEMINI_API_KEY,
            text=cleaned_text,
            model_name=model_name,
            voice_name=voice_name
        )

        if wav_bytes and len(wav_bytes) > 100:
            try:
                with open(cache_path, "wb") as f:
                    f.write(wav_bytes)
            except Exception:
                pass
            return wav_bytes, "audio/wav"
    except Exception as e:
        print(f"[Speech] Error generating voice: {e}")

    return b"", "audio/wav"


async def synthesize_speech_async(text: str, language: str = "ta") -> Tuple[bytes, str]:
    """Asynchronous wrapper running Gemini Native Audio synthesis in thread executor with timeout protection."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,
                synthesize_speech_wav,
                text,
                language,
                DEFAULT_VOICE,
                DEFAULT_MODEL
            ),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        print(f"[Speech] Voice synthesis timed out after 10s for: {text[:30]}...")
        return b"", "audio/wav"
    except Exception as e:
        print(f"[Speech] Error during async voice synthesis: {e}")
        return b"", "audio/wav"


async def synthesize_speech_base64_async(text: str, language: str = "ta") -> Optional[str]:
    """Returns base64 encoded WAV audio URI for direct in-browser playback."""
    wav_bytes, mime = await synthesize_speech_async(text, language)
    if not wav_bytes or len(wav_bytes) < 100:
        return None
    b64 = base64.b64encode(wav_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def synthesize_speech(text: str, language: str = "ta") -> Tuple[bytes, str]:
    """Synchronous runner for Gemini Live Audio."""
    return synthesize_speech_wav(text, language, DEFAULT_VOICE, DEFAULT_MODEL)


def synthesize_speech_base64(text: str, language: str = "ta") -> Optional[str]:
    """Synchronous base64 helper."""
    wav_bytes, mime = synthesize_speech(text, language)
    if not wav_bytes or len(wav_bytes) < 100:
        return None
    b64 = base64.b64encode(wav_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def transcribe_audio_gemini(audio_bytes: bytes, mime_type: str = "audio/webm", language_hint: str = "ta") -> str:
    """Transcribes customer voice recording using Gemini multimodal model."""
    if not config.GEMINI_API_KEY or not genai:
        return ""

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        lang_name = "Telugu" if (language_hint or "").lower().startswith("te") else "Tamil"

        prompt = (
            f"You are a native speech-to-text transcriber for {lang_name} phone calls. "
            f"Transcribe the customer speech from this audio recording verbatim. "
            f"Preserve native phrasing, casual speech, and mixed English words (Tanglish / Telugish). "
            f"Output ONLY the transcribed text in the native script or Latin script as spoken. "
            f"Do not add any conversational commentary, explanations, or quotes."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                prompt
            ]
        )
        return response.text.strip() if response.text else ""
    except Exception as e:
        print(f"[STT] Gemini audio transcription error: {e}")
        return ""
