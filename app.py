"""
Vercel Serverless Function entry point for the FastAPI backend (ai-voice-assistant).
Exports top-level `app` ASGI instance for Vercel Python runtime.
"""
import sys
import traceback
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
VOICE_DIR = BASE_DIR / "ai-voice-assistant"

# Ensure both directories are in Python path
if str(VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import importlib.util
    voice_app_path = VOICE_DIR / "app.py"
    if not voice_app_path.exists():
        raise FileNotFoundError(f"Cannot find voice assistant app at {voice_app_path}")

    spec = importlib.util.spec_from_file_location("voice_assistant_app", str(voice_app_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load spec from {voice_app_path}")

    voice_module = importlib.util.module_from_spec(spec)
    sys.modules["voice_assistant_app"] = voice_module
    spec.loader.exec_module(voice_module)

    app = voice_module.app

except Exception as err:
    error_trace = traceback.format_exc()
    print(f"[VERCEL STARTUP CRASH]\n{error_trace}", file=sys.stderr)

    # Fallback FastAPI app to display the exact startup crash in the browser instead of FUNCTION_INVOCATION_FAILED
    app = FastAPI(title="Startup Error Fallback")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def handle_crash(path: str = ""):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Backend Initialization Error</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #09090b; color: #f43f5e; padding: 40px; margin: 0; }}
                .box {{ max-width: 900px; margin: 0 auto; background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 24px; }}
                h2 {{ color: #fb7185; margin-top: 0; }}
                p {{ color: #a1a1aa; }}
                pre {{ background: #000; color: #fda4af; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.5; border: 1px solid #3f3f46; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h2>⚠️ Application Startup Error</h2>
                <p>The FastAPI application failed during cold-start initialization:</p>
                <pre>{error_trace}</pre>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
