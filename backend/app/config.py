import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Deepgram (for streaming transcription when TRANSCRIPTION_MODE="stream")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# App URLs
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Session
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# GCS (optional - for audio > 1 min, required by Speech-to-Text)
GCS_BUCKET = os.getenv("GCS_BUCKET", "")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "chipmunk.db"
CHROMA_PATH = BASE_DIR / "chroma_data"

# ChromaDB: use HTTP server when set (recommended for multi-process - avoids SQLite corruption).
# Format: http://localhost:8100 (use 8100 to avoid conflict with backend on 8000).
CHROMA_HTTP_URL = os.getenv("CHROMA_HTTP_URL", "").strip() or None

# Service account credentials.
# On Railway/production: set GOOGLE_APPLICATION_CREDENTIALS_JSON to the full JSON file contents.
# Locally: set GOOGLE_APPLICATION_CREDENTIALS to the file path (falls back to ./credentials/service-account.json).
_creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
if _creds_json:
    _tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    _tmp.write(_creds_json)
    _tmp.close()
    GOOGLE_APPLICATION_CREDENTIALS = _tmp.name
else:
    _creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./credentials/service-account.json")
    if not Path(_creds_path).is_absolute():
        _creds_path = str(BASE_DIR / _creds_path.lstrip("./"))
    GOOGLE_APPLICATION_CREDENTIALS = _creds_path
