"""
backend/models/session.py
Pydantic models for session state management.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SessionPhase(str, Enum):
    INTRO = "introduction"
    HPI = "history_of_present_illness"
    PMH = "past_medical_history"
    DIFFERENTIAL = "differential_diagnosis"
    COMPLETED = "completed"


class HPIState(BaseModel):
    """Tracks all OLD CARTS information collected so far."""
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    # OLD CARTS
    onset: Optional[str] = None
    location: Optional[str] = None
    duration: Optional[str] = None
    characteristics: Optional[str] = None
    aggravating_factors: Optional[str] = None
    alleviating_factors: Optional[str] = None
    radiation: Optional[str] = None
    timing: Optional[str] = None
    associated_symptoms: Optional[List[str]] = Field(default_factory=list)
    # PMH
    past_medical_history: Optional[List[str]] = Field(default_factory=list)
    medications: Optional[List[str]] = Field(default_factory=list)
    allergies: Optional[List[str]] = Field(default_factory=list)
    family_history: Optional[str] = None
    social_history: Optional[str] = None

    def covered_fields(self) -> List[str]:
        """Return list of OLD CARTS fields that have been filled."""
        fields = [
            "onset", "location", "duration", "characteristics",
            "aggravating_factors", "alleviating_factors",
            "radiation", "timing", "associated_symptoms"
        ]
        covered = []
        for f in fields:
            val = getattr(self, f)
            if val is not None and val != [] and val != "":
                covered.append(f)
        return covered

    def missing_fields(self) -> List[str]:
        all_fields = [
            "onset", "location", "duration", "characteristics",
            "aggravating_factors", "alleviating_factors",
            "radiation", "timing", "associated_symptoms"
        ]
        return [f for f in all_fields if f not in self.covered_fields()]

    def to_summary_string(self) -> str:
        lines = []
        if self.patient_name:
            lines.append(f"Name: {self.patient_name}")
        if self.patient_age:
            lines.append(f"Age: {self.patient_age}")
        if self.onset:
            lines.append(f"Onset: {self.onset}")
        if self.location:
            lines.append(f"Location: {self.location}")
        if self.duration:
            lines.append(f"Duration: {self.duration}")
        if self.characteristics:
            lines.append(f"Characteristics: {self.characteristics}")
        if self.aggravating_factors:
            lines.append(f"Aggravating: {self.aggravating_factors}")
        if self.alleviating_factors:
            lines.append(f"Alleviating: {self.alleviating_factors}")
        if self.radiation:
            lines.append(f"Radiation: {self.radiation}")
        if self.timing:
            lines.append(f"Timing: {self.timing}")
        if self.associated_symptoms:
            lines.append(f"Associated symptoms: {', '.join(self.associated_symptoms)}")
        if self.past_medical_history:
            lines.append(f"PMH: {', '.join(self.past_medical_history)}")
        if self.medications:
            lines.append(f"Medications: {', '.join(self.medications)}")
        if self.allergies:
            lines.append(f"Allergies: {', '.join(self.allergies)}")
        if self.family_history:
            lines.append(f"Family Hx: {self.family_history}")
        if self.social_history:
            lines.append(f"Social Hx: {self.social_history}")
        return "\n".join(lines) if lines else "No information collected yet."
