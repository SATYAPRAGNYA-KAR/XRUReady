"""
backend/services/tone_analyzer.py
Analyzes doctor utterances for empathy, tone, and communication quality.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from loguru import logger
from backend.core.gemini_client import gemini_client
from backend.core.prompts import TONE_ANALYSIS_PROMPT
from backend.models.dialogue import ToneScore


class ToneAnalyzer:
    """
    Uses Gemini to score doctor utterances on empathy, warmth,
    clarity, respect, and professionalism.
    """

    async def analyze(self, doctor_text: str) -> ToneScore:
        """Analyze a single doctor utterance and return a ToneScore."""
        # Very short utterances (greetings, fillers) get default neutral score
        if len(doctor_text.strip().split()) < 3:
            return ToneScore(tone_label="neutral")

        prompt = TONE_ANALYSIS_PROMPT.format(doctor_statement=doctor_text)

        try:
            result = await gemini_client.generate_json(prompt, temperature=0.1)
            if not result:
                return ToneScore(tone_label="neutral")

            return ToneScore(
                empathy_score=float(result.get("empathy_score", 5)),
                clarity_score=float(result.get("clarity_score", 5)),
                respect_score=float(result.get("respect_score", 5)),
                warmth_score=float(result.get("warmth_score", 5)),
                professional_score=float(result.get("professional_score", 5)),
                tone_label=result.get("tone_label", "neutral"),
                empathy_indicators=result.get("empathy_indicators", []),
                improvement_suggestion=result.get("improvement_suggestion"),
            )
        except Exception as e:
            logger.warning(f"Tone analysis failed for utterance, using defaults: {e}")
            return ToneScore(tone_label="neutral")

    def aggregate_scores(self, scores: list[ToneScore]) -> dict:
        """Compute aggregate statistics across all tone scores."""
        if not scores:
            return {"average_composite": 0.0, "count": 0}

        return {
            "average_composite": sum(s.composite_score for s in scores) / len(scores),
            "average_empathy": sum(s.empathy_score for s in scores) / len(scores),
            "average_warmth": sum(s.warmth_score for s in scores) / len(scores),
            "average_clarity": sum(s.clarity_score for s in scores) / len(scores),
            "average_respect": sum(s.respect_score for s in scores) / len(scores),
            "average_professional": sum(s.professional_score for s in scores) / len(scores),
            "tone_labels": [s.tone_label for s in scores],
            "count": len(scores),
        }
