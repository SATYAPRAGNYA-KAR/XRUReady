"""
backend/api/routes/stt_tts.py
Speech-to-Text and Text-to-Speech endpoints.
These are used by Unity/Convai to convert audio ↔ text.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

from backend.services.stt_service import stt_service
from backend.services.tts_service import tts_service

router = APIRouter(prefix="/audio", tags=["Audio"])


class TTSRequest(BaseModel):
    text: str
    speaker: str = "patient"  # "patient" or "system"
    speaking_rate: float = 1.0


class STTRequest(BaseModel):
    audio_base64: str
    sample_rate: int = 16000
    encoding: str = "LINEAR16"


@router.post("/stt/base64")
async def speech_to_text_base64(request: STTRequest):
    """Convert base64-encoded audio to text."""
    if not request.audio_base64:
        raise HTTPException(status_code=400, detail="audio_base64 is required")

    transcript = await stt_service.transcribe_base64_audio(
        request.audio_base64,
        sample_rate=request.sample_rate,
        encoding=request.encoding,
    )
    return {"transcript": transcript, "length": len(transcript)}


@router.post("/stt/upload")
async def speech_to_text_upload(
    file: UploadFile = File(...),
    sample_rate: int = Form(16000),
    encoding: str = Form("LINEAR16"),
):
    """Upload audio file for STT transcription."""
    audio_bytes = await file.read()
    transcript = await stt_service.transcribe_audio_bytes(
        audio_bytes, sample_rate=sample_rate, encoding=encoding
    )
    return {"transcript": transcript, "filename": file.filename}


@router.post("/tts/synthesize")
async def text_to_speech(request: TTSRequest):
    """Synthesize text to base64-encoded MP3 audio."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    if request.speaker == "patient":
        audio_b64 = await tts_service.patient_speech(request.text)
    else:
        audio_b64 = await tts_service.system_speech(request.text)

    if audio_b64 is None:
        return {"audio_base64": None, "message": "TTS running in stub mode — no audio generated"}

    return {
        "audio_base64": audio_b64,
        "speaker": request.speaker,
        "text_length": len(request.text),
    }
