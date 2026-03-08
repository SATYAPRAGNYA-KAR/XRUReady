"""
backend/models/dialogue.py
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from backend.models.evaluation import (
    SessionEvaluation, HPICompletenessScore, CommunicationScore,
    RepetitivenessScore, DiagnosticScore, ClinicalReasoningScore,
)

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
            self.empathy_score * 0.35 + self.warmth_score * 0.25 +
            self.respect_score * 0.20 + self.clarity_score * 0.10 +
            self.professional_score * 0.10
        )

class DialogueTurn(BaseModel):
    turn_id: int
    speaker: Speaker
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tone_score: Optional[ToneScore] = None
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

class StartSessionRequest(BaseModel):
    trainee_id: Optional[str] = "anonymous"
    trainee_name: Optional[str] = "Trainee Doctor"

class StartSessionResponse(BaseModel):
    session_id: str
    opening_patient_statement: str
    opening_audio_base64: Optional[str] = None

class DoctorInputRequest(BaseModel):
    session_id: str
    doctor_text: str

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
    doctor_differential_text: str

class EvaluationResponse(BaseModel):
    session_id: str
    evaluation: SessionEvaluation
    transcript: List[Dict[str, Any]]
