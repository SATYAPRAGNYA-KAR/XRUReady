"""
backend/services/evaluator.py
End-of-session performance evaluation for the trainee doctor.
"""
import json
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from typing import List

from backend.core.gemini_client import gemini_client
from backend.core.session_manager import ConsultationSession
from backend.core.prompts import DIFFERENTIAL_EXTRACTION_PROMPT
from backend.models.dialogue import Speaker, ToneScore
from backend.models.evaluation import (
    SessionEvaluation,
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

    # ── Main entry point ─────────────────────────────────────────────────────

    async def evaluate_session(self, session: ConsultationSession) -> SessionEvaluation:
        """Run the full end-of-session evaluation using parallel sub-calls."""
        logger.info(f"Evaluating session {session.session_id}")

        transcript = session.transcript.to_formatted_transcript()
        hpi_coverage = session.hpi_tracker.get_covered_summary()
        doctor_differential = json.dumps(session.doctor_differential, indent=2)
        correct_differential = json.dumps(
            CHEST_PAIN_CASE["correct_differential_diagnoses_ordered"], indent=2
        )

        # Build per-turn tone details
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
            "aggregate": tone_analyzer.aggregate_scores(session.tone_scores),
            "per_turn": tone_details,
        }, indent=2)

        # Run all 5 evaluations in parallel
        try:
            hpi_raw, comm_raw, rep_raw, diag_raw, clin_raw = await asyncio.gather(
                self._eval_hpi(transcript, hpi_coverage),
                self._eval_communication(transcript, tone_scores_full),
                self._eval_repetitiveness(transcript),
                self._eval_diagnostic(doctor_differential, correct_differential),
                self._eval_clinical_reasoning(transcript),
            )
        except Exception as e:
            logger.error(f"Evaluation generation failed: {type(e).__name__}: {e}")
            return self._parse_evaluation(session.session_id, self._fallback_evaluation())

        # Calculate overall score from sub-scores (weighted)
        overall = round(
            hpi_raw.get("score", 5) * 2.0 +
            comm_raw.get("average_empathy_score", 5) * 1.5 +
            rep_raw.get("score", 5) * 1.0 +
            diag_raw.get("score", 5) * 3.0 +
            clin_raw.get("score", 5) * 2.5,
            1
        )
        overall = min(100, max(0, overall))
        grade = (
            "A" if overall >= 90 else
            "B" if overall >= 80 else
            "C" if overall >= 70 else
            "D" if overall >= 60 else "F"
        )

        raw = {
            "overall_score": overall,
            "grade": grade,
            "hpi_completeness": hpi_raw,
            "communication_quality": comm_raw,
            "repetitiveness": rep_raw,
            "diagnostic_accuracy": diag_raw,
            "clinical_reasoning": clin_raw,
            "strengths": (
                hpi_raw.get("strengths", []) +
                comm_raw.get("strengths", [])
            ),
            "areas_for_improvement": (
                hpi_raw.get("areas_for_improvement", []) +
                diag_raw.get("areas_for_improvement", [])
            ),
            "detailed_feedback": clin_raw.get("detailed_feedback", ""),
        }

        return self._parse_evaluation(session.session_id, raw)

    # ── Sub-evaluation calls ──────────────────────────────────────────────────

    async def _eval_hpi(self, transcript: str, hpi_coverage: str) -> dict:
        prompt = f"""Evaluate HPI completeness from this medical consultation transcript.
Return ONLY valid JSON with no markdown, no explanation.

Transcript:
{transcript}

HPI Coverage summary:
{hpi_coverage}

Return exactly this JSON structure:
{{
  "score": <number 0-10>,
  "covered_components": ["list", "of", "covered", "HPI", "components"],
  "missed_components": ["list", "of", "missed", "HPI", "components"],
  "personal_info_collected": <true or false>,
  "notes": "brief notes on HPI completeness",
  "strengths": ["strength 1", "strength 2"],
  "areas_for_improvement": ["improvement 1", "improvement 2"]
}}"""
        try:
            return await gemini_client.generate_json(prompt, temperature=0.1)
        except Exception as e:
            logger.error(f"HPI eval failed: {e}")
            return {"score": 5, "covered_components": [], "missed_components": [],
                    "personal_info_collected": False, "notes": "Eval failed",
                    "strengths": [], "areas_for_improvement": []}

    async def _eval_communication(self, transcript: str, tone_scores: str) -> dict:
        prompt = f"""Evaluate the doctor's communication quality and empathy from this transcript.
Return ONLY valid JSON with no markdown, no explanation.

Transcript:
{transcript}

Tone scores per turn:
{tone_scores}

Return exactly this JSON structure:
{{
  "average_empathy_score": <number 0-10>,
  "average_clarity_score": <number 0-10>,
  "average_warmth_score": <number 0-10>,
  "tone_consistency": "<consistent or variable or declining>",
  "best_moment": "quote or description of best communication moment",
  "worst_moment": "quote or description of worst communication moment",
  "notes": "brief notes",
  "strengths": ["strength 1", "strength 2"]
}}"""
        try:
            return await gemini_client.generate_json(prompt, temperature=0.1)
        except Exception as e:
            logger.error(f"Communication eval failed: {e}")
            return {"average_empathy_score": 5, "average_clarity_score": 5,
                    "average_warmth_score": 5, "tone_consistency": "variable",
                    "best_moment": None, "worst_moment": None, "notes": "Eval failed",
                    "strengths": []}

    async def _eval_repetitiveness(self, transcript: str) -> dict:
        prompt = f"""Evaluate how repetitive the doctor was during this consultation.
Return ONLY valid JSON with no markdown, no explanation.

Transcript:
{transcript}

Return exactly this JSON structure:
{{
  "score": <number 0-10, where 10 means no repetition at all>,
  "repeated_questions_count": <integer>,
  "repeated_questions": ["repeated question 1", "repeated question 2"],
  "notes": "brief notes on repetitiveness"
}}"""
        try:
            return await gemini_client.generate_json(prompt, temperature=0.1)
        except Exception as e:
            logger.error(f"Repetitiveness eval failed: {e}")
            return {"score": 5, "repeated_questions_count": 0,
                    "repeated_questions": [], "notes": "Eval failed"}

    async def _eval_diagnostic(self, doctor_differential: str, correct_differential: str) -> dict:
        prompt = f"""Evaluate the accuracy of the doctor's differential diagnosis.
Return ONLY valid JSON with no markdown, no explanation.

Doctor's submitted differential:
{doctor_differential}

Correct differential (in order of likelihood):
{correct_differential}

Return exactly this JSON structure:
{{
  "score": <number 0-10>,
  "primary_diagnosis_correct": <true or false>,
  "correct_differentials_named": <integer count>,
  "total_correct_differentials": 5,
  "ordering_correct": <true or false>,
  "missed_critical_diagnoses": ["missed dx 1", "missed dx 2"],
  "notes": "brief notes on diagnostic accuracy",
  "areas_for_improvement": ["improvement 1", "improvement 2"]
}}"""
        try:
            return await gemini_client.generate_json(prompt, temperature=0.1)
        except Exception as e:
            logger.error(f"Diagnostic eval failed: {e}")
            return {"score": 5, "primary_diagnosis_correct": False,
                    "correct_differentials_named": 0, "total_correct_differentials": 5,
                    "ordering_correct": False, "missed_critical_diagnoses": [],
                    "notes": "Eval failed", "areas_for_improvement": []}

    async def _eval_clinical_reasoning(self, transcript: str) -> dict:
        prompt = f"""Evaluate the doctor's clinical reasoning from this consultation transcript.
Return ONLY valid JSON with no markdown, no explanation.

Transcript:
{transcript}

Return exactly this JSON structure:
{{
  "score": <number 0-10>,
  "red_flags_identified": ["red flag 1", "red flag 2"],
  "red_flags_missed": ["missed flag 1", "missed flag 2"],
  "systematic_approach": <true or false>,
  "notes": "brief notes",
  "detailed_feedback": "Write 3-5 sentences of overall feedback on the doctor's performance in this consultation."
}}"""
        try:
            return await gemini_client.generate_json(prompt, temperature=0.1)
        except Exception as e:
            logger.error(f"Clinical reasoning eval failed: {e}")
            return {"score": 5, "red_flags_identified": [], "red_flags_missed": [],
                    "systematic_approach": False, "notes": "Eval failed",
                    "detailed_feedback": "Evaluation unavailable."}

    # ── Parsing & fallback ────────────────────────────────────────────────────

    def _parse_evaluation(self, session_id: str, raw: dict) -> SessionEvaluation:
        """Parse raw dict into structured SessionEvaluation."""

        def safe(d, key, default):
            return d.get(key, default) if isinstance(d, dict) else default

        hpi_raw  = safe(raw, "hpi_completeness", {})
        comm_raw = safe(raw, "communication_quality", {})
        rep_raw  = safe(raw, "repetitiveness", {})
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
            detailed_feedback=safe(raw, "detailed_feedback", "Session completed."),
        )

    def _fallback_evaluation(self) -> dict:
        return {
            "overall_score": 50,
            "grade": "C",
            "hpi_completeness": {
                "score": 5, "covered_components": [], "missed_components": [],
                "personal_info_collected": False, "notes": "Could not evaluate",
                "strengths": [], "areas_for_improvement": [],
            },
            "communication_quality": {
                "average_empathy_score": 5, "average_clarity_score": 5,
                "average_warmth_score": 5, "tone_consistency": "unknown",
                "best_moment": None, "worst_moment": None, "notes": "Could not evaluate",
                "strengths": [],
            },
            "repetitiveness": {
                "score": 5, "repeated_questions_count": 0,
                "repeated_questions": [], "notes": "",
            },
            "diagnostic_accuracy": {
                "score": 5, "primary_diagnosis_correct": False,
                "correct_differentials_named": 0, "total_correct_differentials": 5,
                "ordering_correct": False, "missed_critical_diagnoses": [],
                "notes": "", "areas_for_improvement": [],
            },
            "clinical_reasoning": {
                "score": 5, "red_flags_identified": [], "red_flags_missed": [],
                "systematic_approach": False, "notes": "",
                "detailed_feedback": "Evaluation service temporarily unavailable.",
            },
            "strengths": [],
            "areas_for_improvement": [],
            "detailed_feedback": "Evaluation service temporarily unavailable.",
        }


session_evaluator = SessionEvaluator()