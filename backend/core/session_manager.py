"""
backend/core/session_manager.py
Manages all active consultation sessions, their state, and transcript.
"""
import uuid
from datetime import datetime
from typing import Dict, Optional, List
from loguru import logger

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.core.hpi_tracker import HPITracker
from backend.models.session import SessionPhase
from backend.models.dialogue import (
    DialogueTurn, SessionTranscript, Speaker, ToneScore
)


class ConsultationSession:
    """Represents a single doctor-patient consultation session."""

    def __init__(self, session_id: str, trainee_id: str, trainee_name: str):
        self.session_id = session_id
        self.trainee_id = trainee_id
        self.trainee_name = trainee_name
        self.phase = SessionPhase.INTRO
        self.hpi_tracker = HPITracker()
        self.transcript = SessionTranscript(
            session_id=session_id,
            started_at=datetime.utcnow()
        )
        self.turn_counter = 0
        self.tone_scores: List[ToneScore] = []
        self.doctor_differential: List[str] = []
        self.is_active = True
        logger.info(f"Session {session_id} created for trainee {trainee_name}")

    def add_turn(
        self,
        speaker: Speaker,
        text: str,
        tone_score: Optional[ToneScore] = None,
        audio_path: Optional[str] = None,
    ) -> DialogueTurn:
        self.turn_counter += 1
        turn = DialogueTurn(
            turn_id=self.turn_counter,
            speaker=speaker,
            text=text,
            tone_score=tone_score,
            audio_path=audio_path,
        )
        self.transcript.turns.append(turn)
        if tone_score and speaker == Speaker.DOCTOR:
            self.tone_scores.append(tone_score)
        return turn

    def get_conversation_history_string(self, last_n: int = 10) -> str:
        """Return last N turns as a readable string for prompting."""
        relevant = self.transcript.turns[-last_n:]
        lines = []
        for turn in relevant:
            if turn.speaker == Speaker.DOCTOR:
                lines.append(f"DOCTOR: {turn.text}")
            elif turn.speaker == Speaker.PATIENT:
                lines.append(f"PATIENT: {turn.text}")
        return "\n".join(lines)

    def advance_phase(self):
        phases = list(SessionPhase)
        current_idx = phases.index(self.phase)
        if current_idx < len(phases) - 1:
            self.phase = phases[current_idx + 1]
            logger.info(f"Session {self.session_id} advanced to phase: {self.phase}")

    def finalize(self, doctor_differential: List[str]):
        self.doctor_differential = doctor_differential
        self.transcript.doctor_differential = doctor_differential
        self.transcript.ended_at = datetime.utcnow()
        self.phase = SessionPhase.COMPLETED
        self.is_active = False
        logger.info(f"Session {self.session_id} finalized.")

    def average_tone_score(self) -> float:
        if not self.tone_scores:
            return 0.0
        return sum(s.composite_score for s in self.tone_scores) / len(self.tone_scores)


class SessionManager:
    """Singleton that holds all active sessions in memory."""

    def __init__(self):
        self._sessions: Dict[str, ConsultationSession] = {}

    def create_session(self, trainee_id: str, trainee_name: str) -> ConsultationSession:
        session_id = str(uuid.uuid4())
        session = ConsultationSession(session_id, trainee_id, trainee_name)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConsultationSession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str):
        if session_id in self._sessions:
            self._sessions[session_id].is_active = False

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_active)


# Singleton
session_manager = SessionManager()
