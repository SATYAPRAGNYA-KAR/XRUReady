"""
backend/services/stt_service.py
Speech-to-Text using Gemini multimodal API.

Replaces Google Cloud Speech-to-Text entirely.
Only requires GEMINI_API_KEY in your .env — no Google Cloud credentials needed.

How it works:
  Gemini 1.5 Flash accepts raw audio bytes inline as a multimodal input.
  We send the WAV bytes + a strict transcription prompt and parse the text response.
  The model is instructed to return ONLY the transcript — no explanation, no preamble.
"""
import base64
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger

import google.generativeai as genai
from config.settings import settings


class STTService:
    """
    Converts audio bytes to text using Gemini 1.5 Flash multimodal inference.
    Falls back to stub mode if GEMINI_API_KEY is not set.
    """

    # Gemini model used for transcription.
    # 1.5 Flash is faster and cheaper than Pro for this task; swap to
    # "gemini-1.5-pro" if you need higher accuracy on noisy audio.
    STT_MODEL = "gemini-1.5-flash"

    # Prompt that tells Gemini to act as a pure transcription engine.
    # The medical context list improves accuracy on clinical terminology.
    STT_PROMPT = (
        "You are a medical transcription system. "
        "The audio is a doctor speaking during a patient consultation. "
        "Transcribe EXACTLY what is said — nothing more, nothing less. "
        "Do NOT add any explanation, greeting, prefix, or commentary. "
        "Do NOT correct grammar or rephrase. "
        "If the audio contains no intelligible speech, return only the text: EMPTY\n\n"
        "Medical terms that may appear: STEMI, NSTEMI, angina, troponin, ECG, "
        "aortic dissection, pulmonary embolism, myocardial infarction, "
        "nitroglycerin, dyspnea, diaphoresis, radiation, OLD CARTS."
    )

    def __init__(self):
        self._ready = False
        if not settings.gemini_api_key:
            logger.warning("STT: GEMINI_API_KEY not set — STT will run in stub mode")
            return
        try:
            genai.configure(api_key=settings.gemini_api_key)
            self._model = genai.GenerativeModel(self.STT_MODEL)
            self._ready = True
            logger.info(f"Gemini STT initialized (model: {self.STT_MODEL})")
        except Exception as e:
            logger.warning(f"Gemini STT init failed: {e} — stub mode")

    # ── Primary entry point (called by stt_tts.py route handler) ─────────────

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,   # accepted for API compatibility, not used by Gemini
        encoding: str = "LINEAR16", # accepted for API compatibility, not used by Gemini
    ) -> str:
        """
        Transcribe raw PCM-16 WAV bytes to text.
        Called by the Unity STT endpoint after base64-decoding the audio.
        Returns empty string on silence or failure — Unity falls back to template question.
        """
        return await self.transcribe_audio_bytes(audio_bytes)

    # ── Core transcription ────────────────────────────────────────────────────

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        encoding: str = "LINEAR16",
        language_code: str = "en-US",
    ) -> str:
        """Transcribe raw audio bytes using Gemini multimodal inference."""
        if not self._ready:
            logger.warning("STT stub mode — returning placeholder")
            return "[STT STUB] Doctor's spoken input here"

        try:
            # Gemini accepts WAV inline as base64-encoded blob
            audio_part = {
                "mime_type": "audio/wav",
                "data": base64.b64encode(audio_bytes).decode("utf-8"),
            }

            response = self._model.generate_content([audio_part, self.STT_PROMPT])
            raw = response.text.strip() if response.text else ""

            # Guard: if Gemini returns an explanation instead of a transcript,
            # treat as empty so Unity falls back to the template question.
            if (
                not raw
                or raw.upper() == "EMPTY"
                or len(raw) > 500          # suspiciously long = explanation not transcript
                or raw.lower().startswith(("i ", "i'm ", "the audio", "this audio",
                                           "the speaker", "there is", "there are"))
            ):
                logger.info(f"STT: no intelligible speech detected (raw='{raw[:80]}')")
                return ""

            logger.info(f"STT transcript: \"{raw[:100]}\"")
            return raw

        except Exception as e:
            logger.error(f"Gemini STT error: {e}")
            return ""

    # ── Convenience wrapper for WebSocket / non-Unity callers ────────────────

    async def transcribe_base64_audio(
        self,
        audio_base64: str,
        sample_rate: int = 16000,
        encoding: str = "LINEAR16",
    ) -> str:
        """Transcribe base64-encoded audio (used by WebSocket doctor_audio handler)."""
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            logger.error(f"STT base64 decode failed: {e}")
            return ""
        return await self.transcribe_audio_bytes(audio_bytes, sample_rate, encoding)


stt_service = STTService()