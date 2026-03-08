"""
backend/models/evaluation.py
Pydantic models for session evaluation results.
These are imported by the evaluator service and evaluation API route.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class HPICompletenessScore(BaseModel):
    """Scores how thoroughly the doctor covered all OLD CARTS components."""
    score: float = Field(..., ge=0, le=10, description="Score out of 10")
    covered_components: List[str] = Field(default_factory=list)
    missed_components: List[str] = Field(default_factory=list)
    personal_info_collected: bool = False
    notes: str = ""


class CommunicationScore(BaseModel):
    """Scores the doctor's empathy, warmth, and communication quality."""
    average_empathy_score: float = Field(0.0, ge=0, le=10)
    average_clarity_score: float = Field(0.0, ge=0, le=10)
    average_warmth_score: float = Field(0.0, ge=0, le=10)
    tone_consistency: str = "variable"  # consistent / variable / declining
    best_moment: Optional[str] = None
    worst_moment: Optional[str] = None
    notes: str = ""


class RepetitivenessScore(BaseModel):
    """Scores how non-repetitive the doctor was during the consultation."""
    score: float = Field(..., ge=0, le=10, description="10 = no repetition, 0 = very repetitive")
    repeated_questions_count: int = 0
    repeated_questions: List[str] = Field(default_factory=list)
    notes: str = ""


class DiagnosticScore(BaseModel):
    """Scores the accuracy and ordering of the differential diagnosis."""
    score: float = Field(..., ge=0, le=10)
    primary_diagnosis_correct: bool = False
    correct_differentials_named: int = 0
    total_correct_differentials: int = 5
    ordering_correct: bool = False
    missed_critical_diagnoses: List[str] = Field(default_factory=list)
    notes: str = ""


class ClinicalReasoningScore(BaseModel):
    """Scores the doctor's clinical reasoning — red flag identification, systematic approach."""
    score: float = Field(..., ge=0, le=10)
    red_flags_identified: List[str] = Field(default_factory=list)
    red_flags_missed: List[str] = Field(default_factory=list)
    systematic_approach: bool = False
    notes: str = ""


class SessionEvaluation(BaseModel):
    """Complete end-of-session performance evaluation for the trainee doctor."""
    session_id: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    overall_score: float = Field(..., ge=0, le=100)
    grade: str  # A / B / C / D / F

    hpi_completeness: HPICompletenessScore
    communication_quality: CommunicationScore
    repetitiveness: RepetitivenessScore
    diagnostic_accuracy: DiagnosticScore
    clinical_reasoning: ClinicalReasoningScore

    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    detailed_feedback: str = ""

    @property
    def passed(self) -> bool:
        return self.overall_score >= 60

    def score_breakdown(self) -> dict:
        """Return a flat dict of all sub-scores for easy reporting."""
        return {
            "overall": self.overall_score,
            "grade": self.grade,
            "hpi_completeness": self.hpi_completeness.score,
            "empathy": self.communication_quality.average_empathy_score,
            "warmth": self.communication_quality.average_warmth_score,
            "clarity": self.communication_quality.average_clarity_score,
            "non_repetitiveness": self.repetitiveness.score,
            "diagnostic_accuracy": self.diagnostic_accuracy.score,
            "clinical_reasoning": self.clinical_reasoning.score,
            "personal_info_collected": self.hpi_completeness.personal_info_collected,
            "primary_dx_correct": self.diagnostic_accuracy.primary_diagnosis_correct,
            "correct_differentials": f"{self.diagnostic_accuracy.correct_differentials_named}/{self.diagnostic_accuracy.total_correct_differentials}",
        }
