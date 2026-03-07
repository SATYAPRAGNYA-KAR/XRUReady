"""
backend/api/routes/dialogue.py
"""
import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from fastapi import APIRouter, HTTPException
from loguru import logger

from backend.core.session_manager import session_manager
from backend.services.dialogue_manager import dialogue_manager
from backend.services.tts_service import tts_service
from backend.models.dialogue import DoctorInputRequest, DoctorInputResponse, DifferentialRequest

router = APIRouter(prefix="/dialogue", tags=["Dialogue"])


@router.post("/doctor-input", response_model=DoctorInputResponse)
async def doctor_input(request: DoctorInputRequest):
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session is not active")

    doctor_text = request.doctor_text.strip()
    if not doctor_text:
        raise HTTPException(status_code=400, detail="Doctor text cannot be empty")

    try:
        patient_response, tone_score, updated_fields = await dialogue_manager.process_doctor_turn(
            session, doctor_text
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"dialogue_manager error:\n{tb}")
        raise HTTPException(status_code=500, detail=f"Dialogue error: {str(e)}")

    audio_b64 = await tts_service.patient_speech(patient_response)

    return DoctorInputResponse(
        session_id=request.session_id,
        patient_response=patient_response,
        patient_audio_base64=audio_b64,
        tone_score=tone_score,
        hpi_updated_fields=updated_fields,
        session_phase=session.phase.value,
        turn_number=session.turn_counter,
    )


@router.post("/submit-differential")
async def submit_differential(request: DifferentialRequest):
    from backend.services.evaluator import session_evaluator

    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        differentials = await session_evaluator.extract_differential(
            session, request.doctor_differential_text
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"extract_differential error:\n{tb}")
        raise HTTPException(status_code=500, detail=f"Differential extraction error: {str(e)}")

    session.finalize(doctor_differential=differentials)
    return {
        "session_id": request.session_id,
        "extracted_differentials": differentials,
        "message": "Differential recorded. Call /evaluation/evaluate to get full performance report.",
    }
