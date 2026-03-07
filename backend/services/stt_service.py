"""
backend/services/stt_service.py
Speech-to-Text using Google Cloud Speech API.
"""
import base64
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from typing import Optional

try:
    from google.cloud import speech
    GOOGLE_STT_AVAILABLE = True
except ImportError:
    GOOGLE_STT_AVAILABLE = False
    logger.warning("google-cloud-speech not installed; STT will use stub mode")

from config.settings import settings


class STTService:
    """
    Converts audio bytes (WAV/FLAC/OGG) to text using Google Cloud STT.
    Falls back to stub/mock if credentials are unavailable.
    """

    def __init__(self):
        self.client = None
        if GOOGLE_STT_AVAILABLE and settings.google_application_credentials:
            try:
                self.client = speech.SpeechClient()
                logger.info("Google Cloud STT client initialized")
            except Exception as e:
                logger.warning(f"STT client init failed: {e} — using stub mode")

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        encoding: str = "LINEAR16",
        language_code: str = "en-US",
    ) -> str:
        """Transcribe raw audio bytes to text."""
        if self.client is None:
            logger.warning("STT in stub mode — returning placeholder text")
            return "[STT STUB] Doctor's spoken input here"

        try:
            audio = speech.RecognitionAudio(content=audio_bytes)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding[encoding],
                sample_rate_hertz=sample_rate,
                language_code=language_code,
                enable_automatic_punctuation=True,
                model="medical_conversation",  # specialized medical model
            )
            response = self.client.recognize(config=config, audio=audio)
            if response.results:
                transcript = " ".join(
                    result.alternatives[0].transcript
                    for result in response.results
                )
                logger.info(f"STT transcript: {transcript[:100]}")
                return transcript.strip()
            return ""
        except Exception as e:
            logger.error(f"STT transcription error: {e}")
            return ""

    async def transcribe_base64_audio(
        self,
        audio_base64: str,
        sample_rate: int = 16000,
        encoding: str = "LINEAR16",
    ) -> str:
        """Transcribe base64-encoded audio."""
        audio_bytes = base64.b64decode(audio_base64)
        return await self.transcribe_audio_bytes(audio_bytes, sample_rate, encoding)


stt_service = STTService()
