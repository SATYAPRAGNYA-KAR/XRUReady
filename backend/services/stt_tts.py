"""
backend/api/routes/stt_tts.py

FastAPI router for Speech-to-Text and Text-to-Speech endpoints.

Where this file lives in your project
──────────────────────────────────────
    backend/api/routes/stt_tts.py          ← this file

How to register it in main.py
──────────────────────────────
    from api.routes.stt_tts import router as stt_tts_router
    app.include_router(stt_tts_router, prefix="/api")

    # This makes the endpoint available at:  POST /api/stt/transcribe
    # Unity's TranscribeDoctorAudio() calls:  backendUrl + "/api/stt/transcribe"

Dependencies
─────────────
    The route uses stt_service from services/stt_service.py (Google STT or Gemini).
    Add that file if it does not exist yet — a minimal version is shown at the bottom
    of this file as a reference.
"""

import base64
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger
from typing import Optional

from services.stt_service import stt_service
from services.tts_service import tts_service

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    """
    Sent by Unity's TranscribeDoctorAudio() coroutine.
    audio_base64: base64-encoded PCM-16 WAV at 16 kHz mono (produced by AudioClipToWav in Unity).
    session_id:   optional — passed through for logging / future per-session STT config.
    """
    session_id:   Optional[str] = ""
    audio_base64: str


class TranscribeResponse(BaseModel):
    """
    Returned to Unity. transcript is the plain-text transcription.
    Empty string means silence or unintelligible audio — Unity falls back to template question.
    """
    transcript: str


class SynthesizeRequest(BaseModel):
    """Optional test/debug endpoint — not called by Unity directly."""
    text:       str
    voice_type: str = "patient"   # "patient" | "doctor" | "system"


class SynthesizeResponse(BaseModel):
    audio_base64: Optional[str] = None


# ── STT endpoint ──────────────────────────────────────────────────────────────

@router.post("/stt/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(request: TranscribeRequest):
    """
    Transcribes the doctor's spoken audio to text.

    Called by Unity on talk-key release (StopDoctorMicAndTranscribe → TranscribeDoctorAudio).
    Audio arrives as a base64-encoded 16 kHz mono PCM-16 WAV.

    Returns { "transcript": "..." } — empty string on silence or error.
    Unity treats an empty transcript as a signal to use the next template question.
    """
    if not request.audio_base64:
        logger.warning("[STT] Empty audio_base64 received")
        return TranscribeResponse(transcript="")

    try:
        audio_bytes = base64.b64decode(request.audio_base64)
    except Exception as e:
        logger.error(f"[STT] base64 decode failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid base64 audio data")

    logger.info(
        f"[STT] Transcribing {len(audio_bytes)} bytes "
        f"(session: {request.session_id or 'unknown'})"
    )

    transcript = await stt_service.transcribe(audio_bytes)

    logger.info(f"[STT] Result: \"{transcript}\"")
    return TranscribeResponse(transcript=transcript or "")


# ── TTS test endpoint (optional — useful for manual testing) ──────────────────

@router.post("/tts/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(request: SynthesizeRequest):
    """
    Test/debug endpoint to synthesize speech outside of a dialogue turn.
    Not called by Unity during normal operation — use /api/dialogue/doctor-input
    for the main flow (which calls tts_service internally).
    """
    if request.voice_type == "doctor":
        audio_b64 = await tts_service.doctor_speech(request.text)
    elif request.voice_type == "system":
        audio_b64 = await tts_service.system_speech(request.text)
    else:
        audio_b64 = await tts_service.patient_speech(request.text)

    return SynthesizeResponse(audio_base64=audio_b64)


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE — backend/services/stt_service.py
# ─────────────────────────────────────────────────────────────────────────────
#
# If you don't have stt_service.py yet, create it at backend/services/stt_service.py
# with the content below. Choose OPTION A (Google Cloud STT) or OPTION B (Gemini).
#
# ─── OPTION A: Google Cloud Speech-to-Text ───────────────────────────────────
#
# """
# backend/services/stt_service.py
# """
# import os
# from loguru import logger
# from typing import Optional
#
# try:
#     from google.cloud import speech
#     GOOGLE_STT_AVAILABLE = True
# except ImportError:
#     GOOGLE_STT_AVAILABLE = False
#     logger.warning("google-cloud-speech not installed — STT will return empty strings")
#
#
# class STTService:
#     def __init__(self):
#         self.client = None
#         if GOOGLE_STT_AVAILABLE:
#             try:
#                 self.client = speech.SpeechClient()
#                 logger.info("Google Cloud STT client initialized")
#             except Exception as e:
#                 logger.warning(f"STT client init failed: {e}")
#
#     async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
#         if self.client is None:
#             return ""
#         try:
#             audio  = speech.RecognitionAudio(content=audio_bytes)
#             config = speech.RecognitionConfig(
#                 encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
#                 sample_rate_hertz=16000,
#                 language_code="en-US",
#                 speech_contexts=[speech.SpeechContext(
#                     phrases=["STEMI", "NSTEMI", "angina", "aortic dissection",
#                              "pulmonary embolism", "myocardial infarction",
#                              "troponin", "ECG", "nitroglycerin", "dyspnea"]
#                 )],
#             )
#             response   = self.client.recognize(config=config, audio=audio)
#             transcript = response.results[0].alternatives[0].transcript \
#                          if response.results else ""
#             return transcript
#         except Exception as e:
#             logger.error(f"STT transcription error: {e}")
#             return ""
#
#
# stt_service = STTService()
#
#
# ─── OPTION B: Gemini multimodal (same API key as the rest of your backend) ───
#
# """
# backend/services/stt_service.py
# """
# import os
# from loguru import logger
# from typing import Optional
# import google.generativeai as genai
#
# genai.configure(api_key=os.environ["GEMINI_API_KEY"])
#
#
# class STTService:
#     async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
#         try:
#             model    = genai.GenerativeModel("gemini-1.5-flash")
#             response = model.generate_content([
#                 {"mime_type": "audio/wav", "data": audio_bytes},
#                 (
#                     "You are a medical transcription system. "
#                     "Transcribe EXACTLY what the doctor says. "
#                     "Return ONLY the transcript — no explanation, no prefix. "
#                     "If there is no intelligible speech, return an empty string."
#                 )
#             ])
#             transcript = response.text.strip()
#             # Guard against Gemini returning an explanation instead of a transcript
#             if len(transcript) > 400 or transcript.lower().startswith(("i ", "the ", "this ")):
#                 return ""
#             return transcript
#         except Exception as e:
#             logger.error(f"Gemini STT error: {e}")
#             return ""
#
#
# stt_service = STTService()