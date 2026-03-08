"""
backend/api/routes/session.py
Session lifecycle endpoints.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from fastapi import APIRouter, HTTPException
from loguru import logger

from backend.core.session_manager import session_manager
from backend.services.dialogue_manager import dialogue_manager
from backend.services.tts_service import tts_service
from backend.models.dialogue import StartSessionRequest, StartSessionResponse

router = APIRouter(prefix="/session", tags=["Session"])


@router.post("/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """
    Start a new consultation simulation session.
    Returns session_id and the patient's opening statement.
    """
    session = session_manager.create_session(
        trainee_id=request.trainee_id or "anonymous",
        trainee_name=request.trainee_name or "Trainee Doctor",
    )

    opening_text = await dialogue_manager.get_opening_statement(session)

    # Generate TTS for patient opening
    audio_b64 = await tts_service.patient_speech(opening_text)

    logger.info(f"Session started: {session.session_id}")
    return StartSessionResponse(
        session_id=session.session_id,
        opening_patient_statement=opening_text,
        opening_audio_base64=audio_b64,
    )


@router.get("/{session_id}/status")
async def session_status(session_id: str):
    """Get current session status and HPI coverage."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "is_active": session.is_active,
        "phase": session.phase.value,
        "turn_count": session.turn_counter,
        "hpi_coverage_percent": session.hpi_tracker.completion_percentage(),
        "hpi_covered_fields": session.hpi_tracker.state.covered_fields(),
        "hpi_missing_fields": session.hpi_tracker.get_missing_old_carts(),
        "average_tone_score": round(session.average_tone_score(), 2),
    }


@router.get("/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Get the full session transcript so far."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    turns = []
    for turn in session.transcript.turns:
        t = {
            "turn_id": turn.turn_id,
            "speaker": turn.speaker.value,
            "text": turn.text,
            "timestamp": turn.timestamp.isoformat(),
        }
        if turn.tone_score:
            t["tone"] = {
                "label": turn.tone_score.tone_label,
                "composite_score": round(turn.tone_score.composite_score, 2),
                "empathy_score": turn.tone_score.empathy_score,
            }
        turns.append(t)

    return {
        "session_id": session_id,
        "total_turns": len(turns),
        "turns": turns,
    }
