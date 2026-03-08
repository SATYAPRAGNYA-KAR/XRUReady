"""
backend/api/routes/stt_tts.py
Speech-to-Text and Text-to-Speech endpoints.

Registered in main.py as:  app.include_router(stt_tts.router, prefix="/api")

Full URL map after registration:
  POST /api/stt/transcribe          ← called by Unity (TranscribeDoctorAudio in ConvaiNPC.cs)
  POST /api/audio/stt/base64        ← existing endpoint kept for other consumers
  POST /api/audio/stt/upload        ← existing endpoint kept for other consumers
  POST /api/audio/tts/synthesize    ← existing endpoint kept for other consumers

The router uses TWO prefixes via two sub-routers so both URL shapes work from
a single file without duplicating service logic.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import base64
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from backend.services.stt_service import stt_service
from backend.services.tts_service import tts_service

# ── Main router (registered at /api by main.py) ───────────────────────────────
router = APIRouter(tags=["Audio"])

# ── Sub-router for the /audio/* paths (preserves existing API surface) ────────
_audio_router = APIRouter(prefix="/audio")


# ── Request / Response models ─────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    """
    Sent by Unity's TranscribeDoctorAudio() coroutine.
    audio_base64 : base64-encoded PCM-16 WAV at 16 kHz mono (produced by AudioClipToWav).
    session_id   : passed through for logging / future per-session STT config.
    """
    session_id:   Optional[str] = ""
    audio_base64: str


class TranscribeResponse(BaseModel):
    transcript: str


class STTRequest(BaseModel):
    audio_base64: str
    sample_rate:  int = 16000
    encoding:     str = "LINEAR16"


class TTSRequest(BaseModel):
    text:          str
    speaker:       str   = "patient"   # "patient" | "doctor" | "system"
    speaking_rate: float = 1.0


# ═════════════════════════════════════════════════════════════════════════════
# /stt/transcribe  — the endpoint Unity calls
# Full path after main.py prefix:  POST /api/stt/transcribe
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/stt/transcribe", response_model=TranscribeResponse)
async def transcribe_unity_audio(request: TranscribeRequest):
    """
    Transcribes the doctor's spoken audio to text.

    Called by Unity on talk-key release (StopDoctorMicAndTranscribe ->
    TranscribeDoctorAudio in ConvaiNPC.cs). Audio arrives as a base64-encoded
    16 kHz mono PCM-16 WAV produced by AudioClipToWav().

    Returns { "transcript": "..." }.
    An empty string tells Unity to fall back to the next template question.
    """
    if not request.audio_base64:
        logger.warning("[STT] Empty audio_base64 received from Unity")
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


# ═════════════════════════════════════════════════════════════════════════════
# /audio/*  — existing endpoints preserved unchanged
# Full paths after main.py prefix:  POST /api/audio/stt/base64, etc.
# ═════════════════════════════════════════════════════════════════════════════

@_audio_router.post("/stt/base64")
async def speech_to_text_base64(request: STTRequest):
    """Convert base64-encoded audio to text (non-Unity consumers)."""
    if not request.audio_base64:
        raise HTTPException(status_code=400, detail="audio_base64 is required")

    transcript = await stt_service.transcribe_base64_audio(
        request.audio_base64,
        sample_rate=request.sample_rate,
        encoding=request.encoding,
    )
    return {"transcript": transcript, "length": len(transcript)}


@_audio_router.post("/stt/upload")
async def speech_to_text_upload(
    file:        UploadFile = File(...),
    sample_rate: int        = Form(16000),
    encoding:    str        = Form("LINEAR16"),
):
    """Upload audio file for STT transcription."""
    audio_bytes = await file.read()
    transcript  = await stt_service.transcribe_audio_bytes(
        audio_bytes, sample_rate=sample_rate, encoding=encoding
    )
    return {"transcript": transcript, "filename": file.filename}


@_audio_router.post("/tts/synthesize")
async def text_to_speech(request: TTSRequest):
    """Synthesize text to base64-encoded LINEAR16 WAV audio."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    if request.speaker == "doctor":
        audio_b64 = await tts_service.doctor_speech(request.text)
    elif request.speaker == "system":
        audio_b64 = await tts_service.system_speech(request.text)
    else:
        audio_b64 = await tts_service.patient_speech(request.text)

    if audio_b64 is None:
        return {
            "audio_base64": None,
            "message": "TTS running in stub mode — no audio generated",
        }

    return {
        "audio_base64": audio_b64,
        "speaker": request.speaker,
        "text_length": len(request.text),
    }


# Attach the /audio sub-router to the main router
router.include_router(_audio_router)