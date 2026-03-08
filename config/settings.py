"""
config/settings.py
Central configuration loaded from environment variables.

Only GEMINI_API_KEY is required — Google Cloud credentials removed entirely.
STT and TTS now both use the Gemini API.
"""
import os
import json
from pathlib import Path
from pydantic_settings import BaseSettings
from loguru import logger

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # ── Gemini (required for dialogue, STT, and TTS) ──────────────────
    gemini_api_key: str = ""
    gemini_model:   str = "gemini-2.5-flash"   # used by dialogue_manager

    # ── Server ────────────────────────────────────────────────────────
    host:      str = "0.0.0.0"
    port:      int = 8000
    log_level: str = "INFO"

    # ── Session ───────────────────────────────────────────────────────
    max_session_duration_minutes: int = 30
    session_storage_path:         str = "./sessions"

    class Config:
        env_file    = BASE_DIR / ".env"
        case_sensitive = False


settings = Settings()


def validate_credentials() -> None:
    """
    Log credential status clearly at startup.
    Called from main.py startup event so you see it immediately in the terminal.
    """
    if settings.gemini_api_key:
        logger.info(
            f"✓ Gemini API key loaded — "
            f"dialogue: {settings.gemini_model} | "
            f"STT: gemini-1.5-flash | "
            f"TTS: gemini-2.5-flash-preview-tts"
        )
    else:
        logger.error(
            "✗ GEMINI_API_KEY not set — dialogue, STT, and TTS will all fail.\n"
            "  To fix: add this line to xr-medical-training/.env\n"
            "    GEMINI_API_KEY=your-api-key-here\n"
            "  Get a key at: https://aistudio.google.com/app/apikey"
        )


# ── Load static case data ─────────────────────────────────────────────
def load_case() -> dict:
    path = BASE_DIR / "config" / "case_chest_pain.json"
    with open(path) as f:
        return json.load(f)

def load_differentials() -> dict:
    path = BASE_DIR / "config" / "differential_diagnoses.json"
    with open(path) as f:
        return json.load(f)

CHEST_PAIN_CASE  = load_case()
DIFFERENTIALS    = load_differentials()