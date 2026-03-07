"""
backend/api/routes/evaluation.py
End-of-session evaluation endpoint.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from fastapi import APIRouter, HTTPException
from loguru import logger

from backend.core.session_manager import session_manager
from backend.services.evaluator import session_evaluator
from backend.models.dialogue import EvaluationResponse

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.post("/evaluate/{session_id}", response_model=EvaluationResponse)
async def evaluate_session(session_id: str):
    """
    Run full end-of-session evaluation.
    Session must be completed (differential diagnosis submitted) first.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_active:
        raise HTTPException(
            status_code=400,
            detail="Session still active. Submit differential diagnosis first via /dialogue/submit-differential"
        )

    logger.info(f"Running evaluation for session {session_id}")
    evaluation = await session_evaluator.evaluate_session(session)

    # Build transcript list for response
    transcript_list = [
        {
            "turn_id": t.turn_id,
            "speaker": t.speaker.value,
            "text": t.text,
            "timestamp": t.timestamp.isoformat(),
            "tone": {
                "label": t.tone_score.tone_label,
                "composite": round(t.tone_score.composite_score, 2),
            } if t.tone_score else None,
        }
        for t in session.transcript.turns
    ]

    return EvaluationResponse(
        session_id=session_id,
        evaluation=evaluation,
        transcript=transcript_list,
    )


@router.get("/report/{session_id}/html")
async def evaluation_html_report(session_id: str):
    """Return a human-readable HTML evaluation report."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_active:
        raise HTTPException(status_code=400, detail="Session still active")

    evaluation = await session_evaluator.evaluate_session(session)
    e = evaluation

    score_color = (
        "#27ae60" if e.overall_score >= 80
        else "#f39c12" if e.overall_score >= 60
        else "#e74c3c"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Session Evaluation Report — {session_id[:8]}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 24px; }}
  .container {{ max-width: 900px; margin: auto; }}
  .card {{ background: #161b22; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #30363d; }}
  .score-big {{ font-size: 72px; font-weight: bold; color: {score_color}; text-align: center; }}
  .grade {{ font-size: 48px; color: {score_color}; text-align: center; }}
  .metric {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #21262d; }}
  .metric-name {{ color: #8b949e; }}
  .metric-val {{ font-size: 20px; font-weight: bold; color: #e6edf3; }}
  .bar {{ height: 8px; background: #21262d; border-radius: 4px; margin-top: 4px; }}
  .bar-fill {{ height: 8px; border-radius: 4px; background: {score_color}; }}
  h2 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
  .pill {{ display: inline-block; background: #21262d; border-radius: 20px; padding: 4px 12px; margin: 4px; font-size: 13px; }}
  .pill.good {{ background: #1a3a1a; color: #56d364; }}
  .pill.bad {{ background: #3a1a1a; color: #f85149; }}
  pre {{ background: #0d1117; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.6; }}
</style>
</head>
<body>
<div class="container">
  <div class="card" style="text-align:center">
    <h1>Medical Consultation Evaluation</h1>
    <p style="color:#8b949e">Session: {session_id[:16]}...</p>
    <div class="score-big">{e.overall_score:.0f}<span style="font-size:32px">/100</span></div>
    <div class="grade">Grade: {e.grade}</div>
  </div>

  <div class="card">
    <h2>📋 HPI Completeness</h2>
    <div class="metric"><span class="metric-name">Score</span><span class="metric-val">{e.hpi_completeness.score:.1f}/10</span></div>
    <div class="bar"><div class="bar-fill" style="width:{e.hpi_completeness.score*10}%"></div></div>
    <p>Covered: {', '.join(e.hpi_completeness.covered_components) or 'None'}</p>
    <p>Missed: {', '.join(e.hpi_completeness.missed_components) or 'None'}</p>
    <p>{e.hpi_completeness.notes}</p>
  </div>

  <div class="card">
    <h2>💬 Communication & Empathy</h2>
    <div class="metric"><span class="metric-name">Empathy</span><span class="metric-val">{e.communication_quality.average_empathy_score:.1f}/10</span></div>
    <div class="bar"><div class="bar-fill" style="width:{e.communication_quality.average_empathy_score*10}%"></div></div>
    <div class="metric"><span class="metric-name">Warmth</span><span class="metric-val">{e.communication_quality.average_warmth_score:.1f}/10</span></div>
    <div class="bar"><div class="bar-fill" style="width:{e.communication_quality.average_warmth_score*10}%"></div></div>
    <div class="metric"><span class="metric-name">Clarity</span><span class="metric-val">{e.communication_quality.average_clarity_score:.1f}/10</span></div>
    <div class="bar"><div class="bar-fill" style="width:{e.communication_quality.average_clarity_score*10}%"></div></div>
    <p>Tone Consistency: <strong>{e.communication_quality.tone_consistency}</strong></p>
    {f'<p>✨ Best moment: <em>{e.communication_quality.best_moment}</em></p>' if e.communication_quality.best_moment else ''}
    {f'<p>⚠️ Worst moment: <em>{e.communication_quality.worst_moment}</em></p>' if e.communication_quality.worst_moment else ''}
  </div>

  <div class="card">
    <h2>🔁 Repetitiveness</h2>
    <div class="metric"><span class="metric-name">Score</span><span class="metric-val">{e.repetitiveness.score:.1f}/10</span></div>
    <div class="bar"><div class="bar-fill" style="width:{e.repetitiveness.score*10}%"></div></div>
    <p>Repeated questions: <strong>{e.repetitiveness.repeated_questions_count}</strong></p>
    {f'<p>{", ".join(e.repetitiveness.repeated_questions)}</p>' if e.repetitiveness.repeated_questions else ''}
  </div>

  <div class="card">
    <h2>🩺 Diagnostic Accuracy</h2>
    <div class="metric"><span class="metric-name">Score</span><span class="metric-val">{e.diagnostic_accuracy.score:.1f}/10</span></div>
    <div class="bar"><div class="bar-fill" style="width:{e.diagnostic_accuracy.score*10}%"></div></div>
    <p>Primary Dx correct: <strong>{"✅ Yes" if e.diagnostic_accuracy.primary_diagnosis_correct else "❌ No"}</strong></p>
    <p>Correct differentials: <strong>{e.diagnostic_accuracy.correct_differentials_named}/{e.diagnostic_accuracy.total_correct_differentials}</strong></p>
    <p>Ordering correct: <strong>{"✅ Yes" if e.diagnostic_accuracy.ordering_correct else "❌ No"}</strong></p>
    {f'<p>Missed critical: {", ".join(e.diagnostic_accuracy.missed_critical_diagnoses)}</p>' if e.diagnostic_accuracy.missed_critical_diagnoses else ''}
  </div>

  <div class="card">
    <h2>🧠 Strengths & Areas for Improvement</h2>
    <div>{''.join(f'<span class="pill good">✓ {s}</span>' for s in e.strengths)}</div>
    <div style="margin-top:12px">{''.join(f'<span class="pill bad">△ {a}</span>' for a in e.areas_for_improvement)}</div>
  </div>

  <div class="card">
    <h2>📝 Detailed Feedback</h2>
    <pre>{e.detailed_feedback}</pre>
  </div>
</div>
</body>
</html>"""

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
