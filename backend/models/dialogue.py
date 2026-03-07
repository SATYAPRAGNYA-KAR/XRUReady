"""
backend/models/dialogue.py + evaluation.py combined
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class Speaker(str, Enum):
    DOCTOR = "doctor"
    PATIENT = "patient"
    SYSTEM = "system"


class ToneScore(BaseModel):
    empathy_score: float = 0.0
    clarity_score: float = 0.0
    respect_score: float = 0.0
    warmth_score: float = 0.0
    professional_score: float = 0.0
    tone_label: str = "neutral"
    empathy_indicators: List[str] = Field(default_factory=list)
    improvement_suggestion: Optional[str] = None

    @property
    def composite_score(self) -> float:
        return (
            self.empathy_score * 0.35 +
            self.warmth_score * 0.25 +
            self.respect_score * 0.20 +
            self.clarity_score * 0.10 +
            self.professional_score * 0.10
        )


class DialogueTurn(BaseModel):
    turn_id: int
    speaker: Speaker
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tone_score: Optional[ToneScore] = None  # only for doctor turns
    audio_path: Optional[str] = None


class SessionTranscript(BaseModel):
    session_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    turns: List[DialogueTurn] = Field(default_factory=list)
    doctor_differential: List[str] = Field(default_factory=list)

    def to_formatted_transcript(self) -> str:
        lines = [f"SESSION: {self.session_id}", f"Started: {self.started_at}", ""]
        for turn in self.turns:
            prefix = "DOCTOR" if turn.speaker == Speaker.DOCTOR else "PATIENT"
            lines.append(f"[{prefix}]: {turn.text}")
        return "\n".join(lines)


# ── Evaluation Models ────────────────────────────────────────────────

class HPICompletenessScore(BaseModel):
    score: float
    covered_components: List[str]
    missed_components: List[str]
    personal_info_collected: bool
    notes: str


class CommunicationScore(BaseModel):
    average_empathy_score: float
    average_clarity_score: float
    average_warmth_score: float
    tone_consistency: str
    best_moment: Optional[str]
    worst_moment: Optional[str]
    notes: str


class RepetitivenessScore(BaseModel):
    score: float
    repeated_questions_count: int
    repeated_questions: List[str]
    notes: str


class DiagnosticScore(BaseModel):
    score: float
    primary_diagnosis_correct: bool
    correct_differentials_named: int
    total_correct_differentials: int
    ordering_correct: bool
    missed_critical_diagnoses: List[str]
    notes: str


class ClinicalReasoningScore(BaseModel):
    score: float
    red_flags_identified: List[str]
    red_flags_missed: List[str]
    systematic_approach: bool
    notes: str


class SessionEvaluation(BaseModel):
    session_id: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    overall_score: float
    grade: str
    hpi_completeness: HPICompletenessScore
    communication_quality: CommunicationScore
    repetitiveness: RepetitivenessScore
    diagnostic_accuracy: DiagnosticScore
    clinical_reasoning: ClinicalReasoningScore
    strengths: List[str]
    areas_for_improvement: List[str]
    detailed_feedback: str


# ── Request/Response schemas ─────────────────────────────────────────

class StartSessionRequest(BaseModel):
    trainee_id: Optional[str] = "anonymous"
    trainee_name: Optional[str] = "Trainee Doctor"

class StartSessionResponse(BaseModel):
    session_id: str
    opening_patient_statement: str
    opening_audio_base64: Optional[str] = None

class DoctorInputRequest(BaseModel):
    session_id: str
    doctor_text: str  # transcribed doctor speech

class DoctorInputResponse(BaseModel):
    session_id: str
    patient_response: str
    patient_audio_base64: Optional[str] = None
    tone_score: Optional[ToneScore] = None
    hpi_updated_fields: List[str] = Field(default_factory=list)
    session_phase: str
    turn_number: int

class DifferentialRequest(BaseModel):
    session_id: str
    doctor_differential_text: str  # doctor's verbal differential diagnosis

class EvaluationResponse(BaseModel):
    session_id: str
    evaluation: SessionEvaluation
    transcript: List[Dict[str, Any]]
