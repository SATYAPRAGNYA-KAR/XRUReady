"""
backend/services/tts_service.py
Text-to-Speech using Google Cloud TTS API.
"""
import base64
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from typing import Optional

try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False
    logger.warning("google-cloud-texttospeech not installed; TTS will use stub mode")

from config.settings import settings


class TTSService:
    """
    Converts text to speech audio bytes using Google Cloud TTS.
    Returns base64-encoded audio for transport over HTTP/WebSocket.
    """

    def __init__(self):
        self.client = None
        if GOOGLE_TTS_AVAILABLE and settings.google_application_credentials:
            try:
                self.client = texttospeech.TextToSpeechClient()
                logger.info("Google Cloud TTS client initialized")
            except Exception as e:
                logger.warning(f"TTS client init failed: {e} — using stub mode")

    async def synthesize(
        self,
        text: str,
        voice_name: Optional[str] = None,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> Optional[str]:
        """
        Synthesize text to speech.
        Returns base64-encoded MP3 audio or None in stub mode.
        """
        if self.client is None:
            logger.warning("TTS in stub mode — no audio returned")
            return None

        if not text.strip():
            return None

        try:
            voice_name = voice_name or settings.tts_voice_patient
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=settings.tts_language_code,
                name=voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=speaking_rate,
                pitch=pitch,
                effects_profile_id=["headphone-class-device"],  # good for XR headsets
            )
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )
            audio_b64 = base64.b64encode(response.audio_content).decode("utf-8")
            logger.debug(f"TTS synthesized {len(text)} chars → {len(audio_b64)} b64 chars")
            return audio_b64
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return None

    async def patient_speech(self, text: str) -> Optional[str]:
        """Generate patient voice — slightly slower, slightly higher pitch (anxious)."""
        return await self.synthesize(
            text,
            voice_name=settings.tts_voice_patient,
            speaking_rate=0.95,
            pitch=1.5,
        )

    async def system_speech(self, text: str) -> Optional[str]:
        """Generate system/narrator voice."""
        return await self.synthesize(
            text,
            voice_name=settings.tts_voice_system,
            speaking_rate=1.0,
            pitch=0.0,
        )


tts_service = TTSService()
