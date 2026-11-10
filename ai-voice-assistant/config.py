"""
Configuration settings for AI Voice Assistant.
Loads environment variables for Gemini API, Telephony providers, MySQL database, and application options.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


# Search for .env in current folder and parent directory
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent

if (current_dir / ".env").exists():
    load_dotenv(current_dir / ".env")
elif (parent_dir / ".env").exists():
    load_dotenv(parent_dir / ".env")
else:
    load_dotenv()

# Gemini AI Key & Models
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_AUDIO_MODEL = os.getenv("GEMINI_AUDIO_MODEL", "gemini-2.5-flash-native-audio-latest")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")

# Server configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

# Database configuration (MySQL with SQLite automatic fallback)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "voice_leads_db")
USE_SQLITE_FALLBACK = os.getenv("USE_SQLITE_FALLBACK", "true").lower() in ("true", "1", "yes")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(current_dir / "voice_leads.db"))

# Telephony Configuration
# Supported providers: 'simulated', 'exotel', 'twilio'
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "simulated").lower()

# Exotel Configuration (for Indian outbound calling)
EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID", "")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY", "")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN", "")
EXOTEL_SUB_DOMAIN = os.getenv("EXOTEL_SUB_DOMAIN", "api.exotel.com")
EXOTEL_CALLER_ID = os.getenv("EXOTEL_CALLER_ID", "")
EXOTEL_APP_ID = os.getenv("EXOTEL_APP_ID", "")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# Webhook Base URL (e.g. ngrok or deployed domain for telephony callbacks)
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")

# Default language
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ta")  # 'ta' or 'te'

