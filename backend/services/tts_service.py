"""
backend/services/tts_service.py
Text-to-Speech via Gemini 2.5 Flash TTS REST API (direct HTTP — no google-genai).

Uses httpx (already in your requirements.txt) to call the Gemini REST endpoint
directly. No new packages. No dependency conflicts.

Gemini TTS returns raw PCM-16 audio at 24000 Hz mono wrapped in a base64 blob.
We prepend a 44-byte RIFF/WAV header so Unity's WavUtility.TryParseWavHeader()
decodes it exactly as before.

Voices:
  Patient : Aoede   — warm female, slightly anxious
  Doctor  : Charon  — calm male, authoritative
  System  : Kore    — clear neutral narrator
  Full list: https://ai.google.dev/gemini-api/docs/speech-generation#voices
"""
import base64
import struct
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from typing import Optional

import httpx
from config.settings import settings

# Gemini TTS output is always 24 kHz mono 16-bit PCM — not configurable
SAMPLE_RATE = 24000
CHANNELS    = 1
BITS        = 16

# REST endpoint for Gemini TTS
_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)


def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw PCM-16 bytes in a standard 44-byte RIFF/WAV header."""
    byte_rate   = SAMPLE_RATE * CHANNELS * BITS // 8
    block_align = CHANNELS * BITS // 8
    data_size   = len(pcm_bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size,
        b"WAVE",
        b"fmt ", 16,
        1,              # PCM
        CHANNELS,
        SAMPLE_RATE,
        byte_rate,
        block_align,
        BITS,
        b"data", data_size,
    )
    return header + pcm_bytes


class TTSService:
    """
    Converts text to speech using Gemini 2.5 Flash TTS via direct REST call.
    Returns base64-encoded LINEAR16 WAV for Unity playback.
    """

    TTS_MODEL     = "gemini-2.5-flash-preview-tts"
    VOICE_PATIENT = "Aoede"
    VOICE_DOCTOR  = "Charon"
    VOICE_SYSTEM  = "Kore"

    def __init__(self):
        self._ready = False
        if not settings.gemini_api_key:
            logger.warning("TTS: GEMINI_API_KEY not set — stub mode")
            return
        self._api_key = settings.gemini_api_key
        self._url     = _TTS_URL.format(
            model=self.TTS_MODEL,
            api_key=self._api_key,
        )
        self._ready = True
        logger.info(f"Gemini TTS initialized (model: {self.TTS_MODEL})")

    # ── Core ──────────────────────────────────────────────────────────────────

    async def _synthesize(
        self,
        text: str,
        voice_name: str,
        style: str = "",
    ) -> Optional[str]:
        """
        POST to the Gemini TTS REST endpoint, extract PCM bytes, wrap in WAV,
        return as base64. Uses httpx which is already in your requirements.txt.
        """
        if not self._ready:
            logger.warning("TTS stub mode — no audio returned")
            return None

        if not text or not text.strip():
            return None

        spoken_text = f"{style}{text}" if style else text

        payload = {
            "contents": [
                {"parts": [{"text": spoken_text}]}
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._url, json=payload)
                response.raise_for_status()

            data = response.json()

            # Extract base64-encoded PCM from the response
            # Structure: candidates[0].content.parts[0].inlineData.data
            pcm_b64 = (
                data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            )
            pcm_bytes = base64.b64decode(pcm_b64)

            if not pcm_bytes:
                logger.warning(f"TTS: empty audio in response (voice={voice_name})")
                return None

            wav_bytes = _pcm_to_wav(pcm_bytes)
            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")

            logger.debug(
                f"TTS: {len(text)} chars → {len(pcm_bytes)} PCM bytes "
                f"→ {len(audio_b64)} b64 chars (voice={voice_name})"
            )
            return audio_b64

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Gemini TTS HTTP error {e.response.status_code} "
                f"(voice={voice_name}): {e.response.text[:300]}"
            )
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"Gemini TTS response parse error (voice={voice_name}): {e}")
            return None
        except Exception as e:
            logger.error(f"Gemini TTS error (voice={voice_name}): {e}")
            return None

    # ── Public voice helpers ──────────────────────────────────────────────────

    async def patient_speech(self, text: str) -> Optional[str]:
        """Anxious female patient voice (Aoede). Returns LINEAR16 WAV base64."""
        return await self._synthesize(
            text,
            voice_name=self.VOICE_PATIENT,
            style="Speak as a worried patient in a hospital, slightly anxious and in pain. ",
        )

    async def doctor_speech(self, text: str) -> Optional[str]:
        """Calm male doctor voice (Charon). Returns LINEAR16 WAV base64."""
        return await self._synthesize(
            text,
            voice_name=self.VOICE_DOCTOR,
            style="Speak as a calm professional doctor, clear and reassuring. ",
        )

    async def system_speech(self, text: str) -> Optional[str]:
        """Neutral narrator voice (Kore). Returns LINEAR16 WAV base64."""
        return await self._synthesize(
            text,
            voice_name=self.VOICE_SYSTEM,
            style="Speak clearly as a neutral narrator. ",
        )

    # ── Backward-compatible wrappers ──────────────────────────────────────────

    async def synthesize_wav(
        self,
        text: str,
        voice_name: Optional[str] = None,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        sample_rate_hertz: int = 24000,
    ) -> Optional[str]:
        return await self.patient_speech(text)

    async def synthesize(
        self,
        text: str,
        voice_name: Optional[str] = None,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> Optional[str]:
        return await self.patient_speech(text)


tts_service = TTSService()