"""
Vercel Serverless Function entry point for the FastAPI backend (ai-voice-assistant).
Exports top-level `app` ASGI instance for Vercel Python runtime.
"""
import sys
import importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VOICE_DIR = BASE_DIR / "ai-voice-assistant"

# Ensure both directories are in Python path
if str(VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Dynamically load the FastAPI application from ai-voice-assistant/app.py
voice_app_path = VOICE_DIR / "app.py"
spec = importlib.util.spec_from_file_location("voice_assistant_app", str(voice_app_path))
voice_module = importlib.util.module_from_spec(spec)
sys.modules["voice_assistant_app"] = voice_module
spec.loader.exec_module(voice_module)

# Top-level 'app' instance exported for Vercel
app = voice_module.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
