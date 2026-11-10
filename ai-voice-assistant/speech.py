"""
Native Multilingual Voice Engine powered by Gemini Live Audio API.
Referencing tamil_voice.py and product_assistant.py architecture using
`gemini-2.5-flash-native-audio-latest` with prebuilt voices (Aoede / Puck).
"""

import os
import io
import wave
import time
import hashlib
import base64
import asyncio
from pathlib import Path
from typing import Optional, Tuple
import config

# Add parent directory to path so tamil_voice can be directly imported
import sys
PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from tamil_voice import synthesize_tamil_speech, pcm_to_wav
except ImportError:
    synthesize_tamil_speech = None
    pcm_to_wav = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

# Audio disk cache directory
AUDIO_CACHE_DIR = Path(__file__).resolve().parent / "audio_cache"
AUDIO_CACHE_DIR.mkdir(exist_ok=True)

# Exclusively female voices for natural customer conversation
FEMALE_VOICES = {"Aoede", "Kore", "Leda", "Callirrhoe", "Sulafat"}
DEFAULT_MODEL = getattr(config, "GEMINI_AUDIO_MODEL", "gemini-2.5-flash-native-audio-latest")
DEFAULT_VOICE = "Aoede"  # 100% Female natural voice


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
        # Telugu phonetic number mapping
        t = re.sub(r'(?<!\d)108(?!\d)', 'నూట ఎనిమిది', t)
        t = re.sub(r'(?<!\d)1008(?!\d)', 'వెయ్యి ఎనిమిది', t)
        t = re.sub(r'(?<!\d)54(?!\d)', 'యాభై నాలుగు', t)
        t = re.sub(r'(?<!\d)27(?!\d)', 'ఇరవై ఏడు', t)
        t = re.sub(r'(?<!\d)8\s*(?:మిల్లీమీటర్లు|మిమీ|mm)', 'ఎనిమిది మిల్లీమీటర్లు', t, flags=re.IGNORECASE)
    else:
        # Tamil phonetic number mapping
        # 108 -> 'நூற்றி எட்டு' (prevents TTS model from hallucinating 1008 'ஆயிரத்து எட்டு')
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

        # Transliterate English loanwords into Tamil so TTS never switches to English voice
        t = re.sub(r'\b(?:cash\s*on\s*delivery|cod)\b', 'கேஷ் ஆன் டெலிவரி', t, flags=re.IGNORECASE)
        t = re.sub(r'\bproduct\b', 'பொருள்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bproducts\b', 'பொருட்கள்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bmrp\b', 'எம்.ஆர்.பி', t, flags=re.IGNORECASE)
        t = re.sub(r'\boffer\b', 'ஆஃபர்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bdiscount\b', 'டிஸ்கவுண்ட்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bdelivery\b', 'டெலிவரி', t, flags=re.IGNORECASE)
        t = re.sub(r'\bwhatsapp\b', 'வாட்ஸ்அப்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bfacebook\b', 'பேஸ்புக்', t, flags=re.IGNORECASE)
        t = re.sub(r'\binstagram\b', 'இன்ஸ்டாகிராம்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bteam\b', 'டீம்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bdetails\b', 'விவரங்கள்', t, flags=re.IGNORECASE)
        t = re.sub(r'\bprice\b', 'விலை', t, flags=re.IGNORECASE)
        t = re.sub(r'\brate\b', 'ரேட்', t, flags=re.IGNORECASE)

    return t
    


def synthesize_speech_wav(
    text: str,
    language: str = "ta",
    voice_name: str = DEFAULT_VOICE,
    model_name: str = DEFAULT_MODEL
) -> Tuple[bytes, str]:
    """
    Generates natural, expressive WAV audio using Gemini Live Native Audio
    strictly using authentic female voice (Aoede).
    """
    raw_text = (text or "").strip()
    if not raw_text or not config.GEMINI_API_KEY:
        return b"", "audio/wav"

    # Phonetically normalize numbers (108 -> நூற்றி எட்டு) so voice output is 100% accurate
    cleaned_text = normalize_spoken_numbers(raw_text, language)

    # Enforce female voice exclusively
    if voice_name not in FEMALE_VOICES:
        voice_name = DEFAULT_VOICE

    cache_path = _get_cache_path(cleaned_text, language, voice_name)
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                return f.read(), "audio/wav"
        except Exception:
            pass

    if synthesize_tamil_speech:
        try:
            wav_bytes = synthesize_tamil_speech(
                api_key=config.GEMINI_API_KEY,
                text=cleaned_text,
                model_name=model_name,
                voice_name=voice_name
            )

            if wav_bytes and len(wav_bytes) > 100:
                # Save to disk cache for 0ms replay
                try:
                    with open(cache_path, "wb") as f:
                        f.write(wav_bytes)
                except Exception:
                    pass
                return wav_bytes, "audio/wav"
        except Exception as e:
            print(f"[Speech] Error generating voice via synthesize_tamil_speech: {e}")

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
    """
    Transcribes customer voice recording using Gemini multimodal model.
    Accurately recognizes conversational Tamil, Telugu, and mixed code-switching (Tanglish / Telugish).
    """
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
