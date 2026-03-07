"""
backend/services/evaluator.py
End-of-session performance evaluation for the trainee doctor.
"""
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from typing import List

from backend.core.gemini_client import gemini_client
from backend.core.session_manager import ConsultationSession
from backend.core.prompts import EVALUATION_PROMPT, DIFFERENTIAL_EXTRACTION_PROMPT
from backend.models.dialogue import (
    SessionEvaluation, Speaker, ToneScore,
    HPICompletenessScore, CommunicationScore, RepetitivenessScore,
    DiagnosticScore, ClinicalReasoningScore,
)
from backend.services.tone_analyzer import ToneAnalyzer
from config.settings import CHEST_PAIN_CASE, DIFFERENTIALS

tone_analyzer = ToneAnalyzer()


class SessionEvaluator:

    async def extract_differential(
        self,
        session: ConsultationSession,
        doctor_differential_text: str,
    ) -> List[str]:
        """Parse doctor's differential diagnosis statement."""
        valid_list = json.dumps(
            [d["name"] for d in DIFFERENTIALS["chest_pain_differentials"]],
            indent=2
        )
        prompt = DIFFERENTIAL_EXTRACTION_PROMPT.format(
            doctor_statement=doctor_differential_text,
            valid_differentials=valid_list,
        )
        result = await gemini_client.generate_json(prompt, temperature=0.1)
        return result.get("given_differentials", [])

    async def evaluate_session(self, session: ConsultationSession) -> SessionEvaluation:
        """Run the full end-of-session evaluation."""
        logger.info(f"Evaluating session {session.session_id}")

        transcript = session.transcript.to_formatted_transcript()
        hpi_coverage = session.hpi_tracker.get_covered_summary()
        tone_scores_data = json.dumps(
            tone_analyzer.aggregate_scores(session.tone_scores), indent=2
        )

        # Individual turn tone details
        tone_details = []
        for turn in session.transcript.turns:
            if turn.speaker == Speaker.DOCTOR and turn.tone_score:
                tone_details.append({
                    "turn": turn.turn_id,
                    "text": turn.text[:100],
                    "tone_label": turn.tone_score.tone_label,
                    "composite": round(turn.tone_score.composite_score, 2),
                })
        tone_scores_full = json.dumps({
            "aggregate": json.loads(tone_scores_data),
            "per_turn": tone_details,
        }, indent=2)

        doctor_differential = json.dumps(session.doctor_differential, indent=2)
        correct_differential = json.dumps(
            CHEST_PAIN_CASE["correct_differential_diagnoses_ordered"], indent=2
        )

        prompt = EVALUATION_PROMPT.format(
            transcript=transcript,
            hpi_coverage=hpi_coverage,
            tone_scores=tone_scores_full,
            doctor_differential=doctor_differential,
            correct_differential=correct_differential,
        )

        try:
            raw = await gemini_client.generate_json(prompt, temperature=0.2)
        except Exception as e:
            logger.error(f"Evaluation generation failed: {e}")
            raw = self._fallback_evaluation()

        evaluation = self._parse_evaluation(session.session_id, raw)
        return evaluation

    def _parse_evaluation(self, session_id: str, raw: dict) -> SessionEvaluation:
        """Parse raw Gemini JSON into structured SessionEvaluation."""
        from datetime import datetime

        def safe(d, key, default):
            return d.get(key, default) if isinstance(d, dict) else default

        hpi_raw = safe(raw, "hpi_completeness", {})
        comm_raw = safe(raw, "communication_quality", {})
        rep_raw = safe(raw, "repetitiveness", {})
        diag_raw = safe(raw, "diagnostic_accuracy", {})
        clin_raw = safe(raw, "clinical_reasoning", {})

        return SessionEvaluation(
            session_id=session_id,
            overall_score=float(safe(raw, "overall_score", 50)),
            grade=safe(raw, "grade", "C"),
            hpi_completeness=HPICompletenessScore(
                score=float(safe(hpi_raw, "score", 5)),
                covered_components=safe(hpi_raw, "covered_components", []),
                missed_components=safe(hpi_raw, "missed_components", []),
                personal_info_collected=bool(safe(hpi_raw, "personal_info_collected", False)),
                notes=safe(hpi_raw, "notes", ""),
            ),
            communication_quality=CommunicationScore(
                average_empathy_score=float(safe(comm_raw, "average_empathy_score", 5)),
                average_clarity_score=float(safe(comm_raw, "average_clarity_score", 5)),
                average_warmth_score=float(safe(comm_raw, "average_warmth_score", 5)),
                tone_consistency=safe(comm_raw, "tone_consistency", "variable"),
                best_moment=safe(comm_raw, "best_moment", None),
                worst_moment=safe(comm_raw, "worst_moment", None),
                notes=safe(comm_raw, "notes", ""),
            ),
            repetitiveness=RepetitivenessScore(
                score=float(safe(rep_raw, "score", 5)),
                repeated_questions_count=int(safe(rep_raw, "repeated_questions_count", 0)),
                repeated_questions=safe(rep_raw, "repeated_questions", []),
                notes=safe(rep_raw, "notes", ""),
            ),
            diagnostic_accuracy=DiagnosticScore(
                score=float(safe(diag_raw, "score", 5)),
                primary_diagnosis_correct=bool(safe(diag_raw, "primary_diagnosis_correct", False)),
                correct_differentials_named=int(safe(diag_raw, "correct_differentials_named", 0)),
                total_correct_differentials=int(safe(diag_raw, "total_correct_differentials", 5)),
                ordering_correct=bool(safe(diag_raw, "ordering_correct", False)),
                missed_critical_diagnoses=safe(diag_raw, "missed_critical_diagnoses", []),
                notes=safe(diag_raw, "notes", ""),
            ),
            clinical_reasoning=ClinicalReasoningScore(
                score=float(safe(clin_raw, "score", 5)),
                red_flags_identified=safe(clin_raw, "red_flags_identified", []),
                red_flags_missed=safe(clin_raw, "red_flags_missed", []),
                systematic_approach=bool(safe(clin_raw, "systematic_approach", False)),
                notes=safe(clin_raw, "notes", ""),
            ),
            strengths=safe(raw, "strengths", ["Completed the consultation"]),
            areas_for_improvement=safe(raw, "areas_for_improvement", ["More empathy needed"]),
            detailed_feedback=safe(raw, "detailed_feedback", "Session completed. Full evaluation unavailable."),
        )

    def _fallback_evaluation(self) -> dict:
        return {
            "overall_score": 50,
            "grade": "C",
            "hpi_completeness": {"score": 5, "covered_components": [], "missed_components": [], "personal_info_collected": False, "notes": "Could not evaluate"},
            "communication_quality": {"average_empathy_score": 5, "average_clarity_score": 5, "average_warmth_score": 5, "tone_consistency": "unknown", "best_moment": None, "worst_moment": None, "notes": "Could not evaluate"},
            "repetitiveness": {"score": 5, "repeated_questions_count": 0, "repeated_questions": [], "notes": ""},
            "diagnostic_accuracy": {"score": 5, "primary_diagnosis_correct": False, "correct_differentials_named": 0, "total_correct_differentials": 5, "ordering_correct": False, "missed_critical_diagnoses": [], "notes": ""},
            "clinical_reasoning": {"score": 5, "red_flags_identified": [], "red_flags_missed": [], "systematic_approach": False, "notes": ""},
            "strengths": [],
            "areas_for_improvement": [],
            "detailed_feedback": "Evaluation service temporarily unavailable.",
        }


session_evaluator = SessionEvaluator()
