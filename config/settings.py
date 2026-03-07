"""
config/settings.py
Central configuration loaded from environment variables.
"""
import os
import json
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"

    # Google Cloud
    google_application_credentials: str = ""
    tts_language_code: str = "en-US"
    tts_voice_patient: str = "en-US-Neural2-F"
    tts_voice_system: str = "en-US-Neural2-C"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Session
    max_session_duration_minutes: int = 30
    session_storage_path: str = "./sessions"

    class Config:
        env_file = BASE_DIR / ".env"
        case_sensitive = False


settings = Settings()

# ── Load static case data ────────────────────────────────────────────
def load_case() -> dict:
    path = BASE_DIR / "config" / "case_chest_pain.json"
    with open(path) as f:
        return json.load(f)

def load_differentials() -> dict:
    path = BASE_DIR / "config" / "differential_diagnoses.json"
    with open(path) as f:
        return json.load(f)

CHEST_PAIN_CASE = load_case()
DIFFERENTIALS = load_differentials()
