"""
backend/api/main.py
FastAPI application entry point.
Includes REST endpoints + WebSocket for real-time Unity/Convai integration.

Changes from previous version
───────────────────────────────
Added startup event that calls validate_credentials() so you can see
immediately in the server log whether Google STT/TTS will work or be
in stub mode, and exactly why if not.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.api.routes import session, dialogue, stt_tts, evaluation
from backend.core.session_manager import session_manager
from backend.services.dialogue_manager import dialogue_manager
from backend.services.stt_service import stt_service
from backend.services.tts_service import tts_service
from backend.services.evaluator import session_evaluator
from backend.models.dialogue import Speaker
from config.settings import validate_credentials

# ── App setup ─────────────────────────────────────────────────────────
app = FastAPI(
    title="XR Medical Training API",
    description="Chest Pain Consultation Simulation — powered by Gemini",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register REST routes ───────────────────────────────────────────────
# /api prefix makes all Unity calls resolve correctly.
# Backward-compatible unprefixed routes are also registered so the web
# dashboard (/session/...) and any other existing clients keep working.
#
# Final URL table:
#   POST /api/session/start                  ← Unity StartMedicalSession()
#   GET  /api/session/{id}/status
#   GET  /api/session/{id}/transcript
#   POST /api/dialogue/doctor-input          ← Unity ProcessDoctorTurn()
#   POST /api/dialogue/submit-differential   ← Unity RunEvaluation()
#   POST /api/stt/transcribe                 ← Unity TranscribeDoctorAudio()
#   POST /api/audio/stt/base64
#   POST /api/audio/stt/upload
#   POST /api/audio/tts/synthesize
#   POST /api/evaluation/evaluate/{id}       ← Unity RunEvaluation()
#   GET  /api/evaluation/report/{id}/html
#
# Backward-compatible (no prefix — for web dashboard):
#   GET  /session/{id}/status
#   GET  /session/{id}/transcript
#   POST /dialogue/doctor-input
#   etc.

app.include_router(session.router,    prefix="/api")
app.include_router(dialogue.router,   prefix="/api")
app.include_router(stt_tts.router,    prefix="/api")
app.include_router(evaluation.router, prefix="/api")

# Backward-compatible routes — dashboard and other non-Unity clients
app.include_router(session.router)
app.include_router(dialogue.router)
app.include_router(stt_tts.router)
app.include_router(evaluation.router)


# ── Startup event ─────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """
    Runs once when uvicorn starts. Logs credential status so you can
    immediately see whether STT/TTS will work or be in stub mode.

    Look for these lines in the startup output:
      ✓ Gemini API key loaded
      ✓ Google credentials loaded from: /path/to/key.json
    or:
      ✗ GOOGLE_APPLICATION_CREDENTIALS not set — STT and TTS will run in stub mode
    """
    validate_credentials()


# ── Health check ──────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_sessions": session_manager.active_count(),
    }


# ── WebSocket endpoint for Unity real-time integration ────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Real-time WebSocket for Unity/Meta Quest integration.

    Message protocol (JSON):
    Client → Server:
      { "type": "doctor_text", "text": "..." }
      { "type": "doctor_audio", "audio_base64": "...", "encoding": "LINEAR16", "sample_rate": 16000 }
      { "type": "submit_differential", "text": "..." }
      { "type": "request_evaluation" }
      { "type": "ping" }

    Server → Client:
      { "type": "patient_response", "text": "...", "audio_base64": "...", "tone": {...} }
      { "type": "hpi_update", "hpi_state": {...}, "coverage_percent": 0.0 }
      { "type": "evaluation", "evaluation": {...} }
      { "type": "error", "message": "..." }
      { "type": "pong" }
    """
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "doctor_text":
                doctor_text = msg.get("text", "").strip()
                if not doctor_text:
                    await websocket.send_json({"type": "error", "message": "Empty doctor text"})
                    continue

                patient_response, tone_score, updated_fields = await dialogue_manager.process_doctor_turn(
                    session, doctor_text
                )
                audio_b64 = await tts_service.patient_speech(patient_response)

                await websocket.send_json({
                    "type": "patient_response",
                    "text": patient_response,
                    "audio_base64": audio_b64,
                    "tone": {
                        "label": tone_score.tone_label,
                        "composite": round(tone_score.composite_score, 2),
                        "empathy": tone_score.empathy_score,
                        "warmth": tone_score.warmth_score,
                    },
                    "hpi_updated": updated_fields,
                    "session_phase": session.phase.value,
                    "turn": session.turn_counter,
                })

                await websocket.send_json({
                    "type": "hpi_update",
                    "hpi_state": session.hpi_tracker.get_state_dict(),
                    "coverage_percent": session.hpi_tracker.completion_percentage(),
                    "missing_fields": session.hpi_tracker.get_missing_old_carts(),
                })

            elif msg_type == "doctor_audio":
                audio_b64    = msg.get("audio_base64", "")
                encoding     = msg.get("encoding", "LINEAR16")
                sample_rate  = msg.get("sample_rate", 16000)

                doctor_text = await stt_service.transcribe_base64_audio(
                    audio_b64, sample_rate=sample_rate, encoding=encoding
                )
                if not doctor_text:
                    await websocket.send_json({"type": "error", "message": "STT returned empty transcript"})
                    continue

                await websocket.send_json({"type": "stt_result", "text": doctor_text})

                patient_response, tone_score, updated_fields = await dialogue_manager.process_doctor_turn(
                    session, doctor_text
                )
                audio_b64_out = await tts_service.patient_speech(patient_response)

                await websocket.send_json({
                    "type": "patient_response",
                    "text": patient_response,
                    "audio_base64": audio_b64_out,
                    "tone": {
                        "label": tone_score.tone_label,
                        "composite": round(tone_score.composite_score, 2),
                        "empathy": tone_score.empathy_score,
                        "warmth": tone_score.warmth_score,
                    },
                    "hpi_updated": updated_fields,
                    "session_phase": session.phase.value,
                    "turn": session.turn_counter,
                })

            elif msg_type == "submit_differential":
                diff_text    = msg.get("text", "")
                differentials = await session_evaluator.extract_differential(session, diff_text)
                session.finalize(doctor_differential=differentials)
                await websocket.send_json({
                    "type": "differential_confirmed",
                    "extracted_differentials": differentials,
                })

            elif msg_type == "request_evaluation":
                if session.is_active:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Submit differential diagnosis before requesting evaluation"
                    })
                    continue
                evaluation = await session_evaluator.evaluate_session(session)
                await websocket.send_json({
                    "type": "evaluation",
                    "evaluation": evaluation.model_dump(),
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass